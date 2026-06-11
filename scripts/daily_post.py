"""
Self-healing daily post orchestrator.

Loop (up to 3 attempts): render → QA → apply corrections → retry.

After the loop:
  - pass=true OR severity=low on last attempt  → upload + log issues to QA_LOG.md
  - all 3 attempts high-severity              → upload from backup bank + open GitHub issue

After a successful normal upload: if backup bank < 3 videos, render+QA one
evergreen short and add it to the bank.
"""
import importlib
import json
import os
import sys
import datetime
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from content import generate_content      # noqa: E402 (after sys.path)
from tts import synthesize_voice          # noqa: E402
from publish import publish_short         # noqa: E402
from logbook import log_post              # noqa: E402
import render as render_mod               # noqa: E402

from qa_check import run_qa               # noqa: E402  (scripts/ is on sys.path)

BACKUPS_DIR = ROOT / "backups"
QA_LOG = ROOT / "QA_LOG.md"
MAX_ATTEMPTS = 3
BACKUP_MIN = 3


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

def _apply_corrections(env: dict, issues: list, attempt: int) -> dict:
    """Return updated env-var dict based on QA issues for the next render."""
    env = dict(env)
    joined = " ".join(issues).lower()

    if "clip" in joined or "safe zone" in joined:
        # Push captions inward and shrink hook font
        marginv = int(env.get("REEL_CAPTION_MARGINV", "470"))
        env["REEL_CAPTION_MARGINV"] = str(min(marginv + 80 * attempt, 700))
        hook_fs = int(env.get("REEL_HOOK_FONTSIZE", "94"))
        env["REEL_HOOK_FONTSIZE"] = str(max(hook_fs - 15, 60))

    if "contrast" in joined or "unreadable" in joined:
        # Force a darker colour grade by bumping brightness down
        env["_FORCE_DARKER"] = "1"

    if "frozen" in joined or "black frame" in joined:
        env["_RETRY_BG"] = "1"

    if "desync" in joined or "sync" in joined or "mispronounce" in joined:
        # Shift caption vertical margin slightly
        marginv = int(env.get("REEL_CAPTION_MARGINV", "470"))
        env["REEL_CAPTION_MARGINV"] = str(min(marginv + 40, 700))

    return env


def _render_with_env(
    env_overrides: dict, *,
    quote: str, author: str, audio_path: Path, out_path: Path,
    theme: str, word_timings: list, hook: str,
) -> Path:
    """Set env overrides, reload render module constants, call render_reel."""
    saved = {}
    for k, v in env_overrides.items():
        if k.startswith("_"):   # internal hint flags — skip
            continue
        saved[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        importlib.reload(render_mod)
        return render_mod.render_reel(
            quote=quote, author=author, audio_path=audio_path,
            out_path=out_path, theme=theme, word_timings=word_timings,
            hook=hook,
        )
    finally:
        for k, orig in saved.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig


# ---------------------------------------------------------------------------
# QA log
# ---------------------------------------------------------------------------

def _append_qa_log(date: str, attempt: int, issues: list, severity: str, uploaded: bool):
    entry = (
        f"\n## {date} — attempt {attempt}\n"
        f"- uploaded: {uploaded}\n"
        f"- severity: {severity}\n"
        f"- issues:\n"
        + "".join(f"  - {i}\n" for i in issues)
    )
    with open(QA_LOG, "a", encoding="utf-8") as fh:
        fh.write(entry)


# ---------------------------------------------------------------------------
# GitHub issue
# ---------------------------------------------------------------------------

def _open_github_issue(title: str, body: str):
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not repo or not token:
        print(f"  [issue] GITHUB_TOKEN/REPOSITORY missing; would open: {title}", file=sys.stderr)
        return
    data = json.dumps({"title": title, "body": body}).encode()
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=data,
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            issue = json.loads(resp.read())
            print(f"  [issue] opened #{issue['number']}: {issue['html_url']}")
    except Exception as e:
        print(f"  [issue] open failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Backup bank helpers
# ---------------------------------------------------------------------------

def _count_backups() -> int:
    BACKUPS_DIR.mkdir(exist_ok=True)
    return sum(1 for _ in BACKUPS_DIR.glob("*.json"))


def _load_backup():
    """Return (video_path, metadata_dict, meta_file) or None."""
    BACKUPS_DIR.mkdir(exist_ok=True)
    for meta_file in sorted(BACKUPS_DIR.glob("*.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            vp = BACKUPS_DIR / meta["filename"]
            if vp.exists():
                return vp, meta, meta_file
        except Exception:
            continue
    return None


def _remove_backup(meta_file: Path):
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        (BACKUPS_DIR / meta["filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    meta_file.unlink(missing_ok=True)


def _add_to_backup_bank(today: str):
    """Render, QA, and store one evergreen short in the backup bank."""
    print("  [backup] rendering evergreen short...")
    try:
        content = generate_content()
        hook = content["hook"].strip()
        spoken = f"{hook.rstrip('.!? ')}. {content['voiceover_text']}"
        audio_path = ROOT / "data" / f"{today}_bk_voice.mp3"
        audio_path, word_timings = synthesize_voice(spoken, audio_path)

        video_name = f"{today}_bk_reel.mp4"
        video_path = BACKUPS_DIR / video_name
        importlib.reload(render_mod)
        render_mod.render_reel(
            quote=content["quote"], author=content["author"],
            audio_path=audio_path, out_path=video_path,
            theme=content["theme"], word_timings=word_timings, hook=hook,
        )

        qa = run_qa(video_path, content["quote"])
        if not qa["pass"] and qa["severity"] == "high":
            print("  [backup] QA high-severity — discarding")
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            return

        meta = {
            "filename": video_name,
            "title": f'{content["quote"][:70]} | {content["author"]}',
            "description": content["caption"] + "\n\n" + " ".join(content["hashtags"]),
            "tags": content["hashtags"],
            "created": today,
            "qa_issues": qa.get("issues", []),
        }
        (BACKUPS_DIR / f"{today}_bk_reel.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        audio_path.unlink(missing_ok=True)
        print(f"  [backup] added {video_name} (bank now {_count_backups()})")
    except Exception as e:
        print(f"  [backup] failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = datetime.date.today().isoformat()
    print(f"[{today}] daily_post starting")

    BACKUPS_DIR.mkdir(exist_ok=True)

    # Generate content once (quote generation logic untouched)
    content = generate_content()
    print(f"  theme: {content['theme']}")
    print(f"  quote: {content['quote'][:60]}...")

    hook = content["hook"].strip()
    cta = content.get("cta", "").strip()
    spoken_text = f"{hook.rstrip('.!? ')}. {content['voiceover_text']}"
    if cta:
        spoken_text = f"{spoken_text} {cta}"

    # Voiceover once; reused across render attempts
    audio_path = ROOT / "data" / f"{today}_voice.mp3"
    audio_path, word_timings = synthesize_voice(spoken_text, audio_path)
    print(f"  voiceover -> {audio_path.name} ({len(word_timings)} word timings)")

    video_path = ROOT / "data" / f"{today}_reel.mp4"

    # Series framing for title and description
    day = content.get("day_number", "")
    day_prefix = f"Day {day} | " if day else ""
    title = f'{day_prefix}{content["quote"][:55]} — {content["author"]}'[:90].rstrip()
    description = (
        (f"Day {day} of daily Stoic wisdom.\n\n" if day else "")
        + content["caption"]
        + "\n\n"
        + " ".join(content["hashtags"])
    )

    all_qa: list = []
    current_env: dict = {}
    upload_result = None
    used_backup = False

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  [attempt {attempt}/{MAX_ATTEMPTS}] rendering...")
        _render_with_env(
            current_env,
            quote=content["quote"], author=content["author"],
            audio_path=audio_path, out_path=video_path,
            theme=content["theme"], word_timings=word_timings, hook=hook,
        )

        print(f"  [attempt {attempt}] QA check...")
        qa = run_qa(video_path, content["quote"])
        all_qa.append(qa)
        print(
            f"  [attempt {attempt}] pass={qa['pass']} "
            f"severity={qa['severity']} issues={qa['issues']}"
        )

        last_attempt = (attempt == MAX_ATTEMPTS)
        upload_this = qa["pass"] or (last_attempt and qa["severity"] == "low")

        if upload_this:
            upload_result = publish_short(
                video_path=video_path, title=title,
                description=description, tags=content["hashtags"],
            )
            print(f"  published: {upload_result.get('url', 'unknown')}")

            # Post engagement question as a (manually-pinnable) comment
            pinned_q = content.get("pinned_comment", "").strip()
            if pinned_q and upload_result.get("video_id"):
                try:
                    from publish import post_comment
                    post_comment(upload_result["video_id"], pinned_q)
                except Exception as e:
                    print(
                        f"  [comment] failed — re-run auth_setup.py to add "
                        f"force-ssl scope, then update YOUTUBE_REFRESH_TOKEN: {e}",
                        file=sys.stderr,
                    )

            if qa["issues"]:
                _append_qa_log(today, attempt, qa["issues"], qa["severity"], uploaded=True)

            log_post(
                date=today, theme=content["theme"], quote=content["quote"],
                author=content["author"], caption=description,
                publish_result=upload_result,
            )
            print("  logged. done.")
            break

        if last_attempt:
            # All 3 failed with high severity — use backup
            print("  [all high-severity] uploading from backup bank...")
            for i, qa_r in enumerate(all_qa, 1):
                _append_qa_log(today, i, qa_r["issues"], qa_r["severity"], uploaded=False)

            backup = _load_backup()
            if backup:
                bk_video, bk_meta, bk_meta_file = backup
                upload_result = publish_short(
                    video_path=bk_video, title=bk_meta["title"],
                    description=bk_meta["description"], tags=bk_meta["tags"],
                )
                used_backup = True
                print(f"  [backup] published: {upload_result.get('url', 'unknown')}")
                _remove_backup(bk_meta_file)
            else:
                print("  [backup] bank empty — no upload today", file=sys.stderr)

            issue_body = (
                f"Daily render failed on {today}. "
                f"All {MAX_ATTEMPTS} attempts had high-severity QA issues.\n\n"
            )
            for i, qa_r in enumerate(all_qa, 1):
                issue_body += f"### Attempt {i}\n- severity: {qa_r['severity']}\n- issues:\n"
                issue_body += "".join(f"  - {iss}\n" for iss in qa_r["issues"])
                issue_body += "\n"

            _open_github_issue("Daily render failed - investigate", issue_body)
        else:
            current_env = _apply_corrections(current_env, qa["issues"], attempt)
            print(f"  [attempt {attempt}] retrying with corrections: {current_env}")

    # Top up backup bank after a successful normal upload
    if not used_backup and upload_result:
        count = _count_backups()
        if count < BACKUP_MIN:
            print(f"  [backup bank] {count}/{BACKUP_MIN} — adding one...")
            _add_to_backup_bank(today)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        print(f"RUN FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
