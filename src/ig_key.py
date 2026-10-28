"""
Echo's Instagram key, kept alive (owner 2026-10-28: "get people to run that").

An Instagram Login key lasts 60 days. Meta refreshes it once it is a day old,
and a refreshed key is good for another 60 days. The old cross-post's key was
never refreshed, so even a correct one would have died within two months.

The key the owner pastes into GitHub (IG_ACCESS_TOKEN) is the SEED. Echo
refreshes the key in use about once a week (`due`). If Meta hands back a
different string, Echo keeps the new key in the `echo-key` release as one
file encrypted with the seed itself (AES-256, src/vault.py). The seed is a
random string of ~180 characters that only GitHub's secret store holds, so
the file is useless without it, and no key, encrypted or not, enters git.
When the owner pastes a new key, the kept file no longer opens with it, and
Echo starts again from the new seed.

Keys never reach a log: any key Echo did not get from the secret store is
registered with GitHub's ::add-mask:: before use, and status files record a
12-character SHA-256 fingerprint of the seed (to notice it changed), never
the key.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import requests

import publish_instagram as ig
import vault

REPO = os.environ.get("GITHUB_REPOSITORY", "soicism2026-ex/stoic-bot")
TAG = "echo-key"
ASSET = "ig-key.gpg"
REFRESH_EVERY_DAYS = 7
LIFETIME_DAYS = 60
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def mask(token: str) -> None:
    """Tell GitHub to blank this value out of every later log line."""
    if token and os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}", flush=True)


def problem_with(seed: str) -> str | None:
    """What is wrong with the pasted key before Instagram even sees it."""
    if not seed.strip():
        return "There's no Instagram key in GitHub yet."
    if any(c.isspace() for c in seed.strip()):
        return ("The Instagram key in GitHub has line breaks or spaces in it. "
                "Paste it again as one line.")
    return None


# ---------------------------------------------------------------- the kept key

def _public_url() -> str:
    return f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"


def load(seed: str) -> tuple[str, str]:
    """(key, source): the kept key if one is stored and opens with the seed,
    else the seed itself ("github")."""
    seed = seed.strip()
    try:
        with tempfile.TemporaryDirectory() as td:
            enc, out = Path(td) / ASSET, Path(td) / "key"
            req = urllib.request.Request(_public_url(), headers={"User-Agent": "stoic-bot-echo"})
            with urllib.request.urlopen(req, timeout=30) as r:
                enc.write_bytes(r.read())
            vault.decrypt(enc, out, key=seed)
            kept = out.read_text(encoding="utf-8").strip()
        if kept and not any(c.isspace() for c in kept):
            mask(kept)
            return kept, "kept"
    except Exception:  # noqa: BLE001  no kept key, or it was made from another seed
        pass
    return seed, "github"


def _gh_headers() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def keep(token: str, seed: str) -> bool:
    """Store a refreshed key, encrypted with the seed, in the echo-key release."""
    if not os.environ.get("GITHUB_TOKEN"):
        return False
    try:
        with tempfile.TemporaryDirectory() as td:
            plain, enc = Path(td) / "key", Path(td) / ASSET
            plain.write_text(token, encoding="utf-8")
            vault.encrypt(plain, enc, key=seed.strip())
            plain.unlink()
            r = requests.get(f"{API}/repos/{REPO}/releases/tags/{TAG}", headers=_gh_headers(), timeout=30)
            if r.status_code == 200:
                rel = r.json()
            else:
                r = requests.post(f"{API}/repos/{REPO}/releases", headers=_gh_headers(), timeout=30, json={
                    "tag_name": TAG, "name": "Echo's key (encrypted)", "prerelease": True,
                    "body": "Echo's refreshed Instagram key, encrypted with the owner's key from "
                            "GitHub's secret store: useless without it. Auto-managed: do not delete."})
                r.raise_for_status()
                rel = r.json()
            for a in rel.get("assets") or []:
                if a.get("name") == ASSET:
                    requests.delete(f"{API}/repos/{REPO}/releases/assets/{a['id']}",
                                    headers=_gh_headers(), timeout=30)
            up = requests.post(f"{UPLOADS}/repos/{REPO}/releases/{rel['id']}/assets?name={ASSET}",
                               headers={**_gh_headers(), "Content-Type": "application/octet-stream"},
                               data=enc.read_bytes(), timeout=60)
            up.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [echo] could not keep the refreshed key: {type(e).__name__}", file=sys.stderr)
        return False


# ---------------------------------------------------------------- refreshing

def due(state: dict, today: dt.date) -> bool:
    """Refresh about weekly, never twice a day, and never a key less than a
    day old (Meta refuses those)."""
    if state.get("kind") != "instagram" or state.get("lastTry") == today.isoformat():
        return False
    last = state.get("refreshed") or None
    if last:
        return dt.date.fromisoformat(last) <= today - dt.timedelta(days=REFRESH_EVERY_DAYS)
    first = state.get("firstSeen")
    return bool(first) and dt.date.fromisoformat(first) <= today - dt.timedelta(days=1)


def refresh(token: str) -> tuple[str, int]:
    """(new key, seconds it lasts). Raises IGError."""
    got = ig._call("GET", f"{ig.IG_GRAPH}/refresh_access_token", token, grant_type="ig_refresh_token")
    new = str(got.get("access_token") or "").strip()
    if not new:
        raise ig.IGError(0, "Instagram returned no refreshed key")
    mask(new)
    return new, int(got.get("expires_in") or LIFETIME_DAYS * 86400)


def expires(state: dict) -> str | None:
    """When the key in use runs out, as best Echo knows."""
    if state.get("expires"):
        return state["expires"]
    if state.get("firstSeen"):
        return (dt.date.fromisoformat(state["firstSeen"]) + dt.timedelta(days=LIFETIME_DAYS)).isoformat()
    return None
