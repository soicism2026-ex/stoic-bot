"""Rename the channel for search and rewrite its About (owner 2026-11-16, Go on
the Ideas card idea-channel-seo).

The target lives in data/channel_branding.json: the channel name, an About
built from the ten searches in data/search_phrases.json that ends with the
journal line from src/promo.py, and the searches as the channel's keywords.

    python3 scripts/channel_seo.py plan    # print what it would set, no network
    python3 scripts/channel_seo.py apply   # compare with the live channel, update if different

`apply` reads the channel's brandingSettings with the YouTube Data API (the same
credentials and client builder as src/publish.py, youtube.force-ssl scope), and
sends channels.update(part="brandingSettings") only when something differs. If
YouTube refuses the new name through the API, the About and keywords are still
applied, the refusal is written in plain words to
data/channel_branding_applied.json and the name is not retried every run. Once
everything matches the live channel it does nothing, so the daily workflow can
run it after every post (continue-on-error).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
TARGET = ROOT / "data" / "channel_branding.json"
APPLIED = ROOT / "data" / "channel_branding_applied.json"
FORCE_SSL = "https://www.googleapis.com/auth/youtube.force-ssl"
ABOUT_MAX = 1000
KEYWORDS_MAX = 500


def load_target(path: Path = TARGET) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_target(t: dict) -> None:
    """The rules the About must meet; raises ValueError."""
    d = t["description"]
    if len(d) >= ABOUT_MAX:
        raise ValueError(f"the About is {len(d)} characters; YouTube allows under {ABOUT_MAX}")
    if len(t.get("keywords", "")) > KEYWORDS_MAX:
        raise ValueError(f"the keywords are over {KEYWORDS_MAX} characters")
    for who in ("Marcus Aurelius", "Seneca", "Epictetus"):
        if who not in d:
            raise ValueError(f"the About does not name {who}")


def plan_text(t: dict) -> str:
    return (
        "Channel name: " + t["title"] + "\n"
        f"About ({len(t['description'])} characters):\n" + t["description"] + "\n"
        "Keywords: " + t["keywords"]
    )


def _channel(item: dict) -> dict:
    return ((item.get("brandingSettings") or {}).get("channel")) or {}


def differences(live: dict, t: dict, skip_title: bool = False) -> list[str]:
    """Which of title / description / keywords differ from the live channel."""
    out = []
    for key in ("title", "description", "keywords"):
        if key == "title" and skip_title:
            continue
        if (live.get(key) or "").strip() != t[key].strip():
            out.append(key)
    return out


def _title_refused_before(applied: dict, t: dict) -> bool:
    return bool(applied.get("titleRefused")) and applied.get("targetTitle") == t["title"]


def _read_applied(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def apply(yt, t: dict, applied_path: Path = APPLIED, now=None) -> dict:
    """Compare with the live channel and update it. `yt` is a YouTube Data API
    client. Returns {"status": "nothing to do" | "applied", "titleRefused": str|None, ...}."""
    check_target(t)
    applied = _read_applied(applied_path)
    resp = yt.channels().list(part="id,brandingSettings", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        raise RuntimeError("YouTube returned no channel for these credentials")
    item = items[0]
    live = _channel(item)
    skip_title = _title_refused_before(applied, t)
    diff = differences(live, t, skip_title)
    if not diff:
        return {"status": "nothing to do", "titleRefused": applied.get("titleRefused") if skip_title else None}

    def _send(with_title: bool) -> dict:
        branding = json.loads(json.dumps(item.get("brandingSettings") or {}))
        ch = branding.setdefault("channel", {})
        ch["description"] = t["description"]
        ch["keywords"] = t["keywords"]
        if with_title:
            ch["title"] = t["title"]
        body = {"id": item["id"], "brandingSettings": branding}
        return yt.channels().update(part="brandingSettings", body=body).execute()

    refused = None
    result = None
    if "title" in diff:
        try:
            result = _send(True)
            if (_channel(result).get("title") or "").strip() != t["title"]:
                refused = "YouTube accepted the request but kept the old channel name"
        except Exception as e:  # noqa: BLE001  HttpError: the API refuses name changes
            refused = f"YouTube refused the new channel name through the API ({_reason(e)})"
            result = None
    if result is None:
        result = _send(False)          # the About and keywords still go through
    rec = {
        "appliedAt": (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "targetTitle": t["title"],
        "description": t["description"],
        "keywords": t["keywords"],
        "titleRefused": refused,
        "titleNote": (refused + ": change the name by hand in YouTube Studio (Customization, Basic info)")
        if refused else "The new name is live.",
    }
    applied_path.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "applied", "titleRefused": refused, "changed": diff}


def _reason(e: Exception) -> str:
    text = str(e).strip().replace("\n", " ")
    return text[:160] or e.__class__.__name__


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "plan"
    t = load_target()
    if cmd == "plan":
        check_target(t)
        print(plan_text(t))
        return 0
    if cmd == "apply":
        from publish import _service
        res = apply(_service(extra_scopes=[FORCE_SSL]), t)
        print(f"[channel_seo] {res['status']}" + (f": {res['changed']}" if res.get("changed") else ""))
        if res.get("titleRefused"):
            print(f"[channel_seo] name not changed: {res['titleRefused']}")
        return 0
    print("usage: channel_seo.py plan|apply")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
