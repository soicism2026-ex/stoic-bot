#!/usr/bin/env python3
"""
Delete orphaned MP4s from the GitHub Release used as an Instagram media bucket.

src/publish_instagram.py hosts each rendered Short as a public release asset
so Meta can fetch it. Nothing ever deleted them. By 2026-08-23 the bucket held
59 files and 12.2 GB, one per day since June — every single one uploaded for a
cross-post that failed, because the IG token has been invalid the whole time.

publish_instagram now deletes its own asset after each attempt, so the bucket
stops growing. This clears what accumulated before that.

Nothing here is irreplaceable: the videos are published on YouTube and the
pipeline can re-render any of them. The assets are transient hosting only.

    python scripts/prune_media_bucket.py                 # dry run (default)
    python scripts/prune_media_bucket.py --keep-days 3   # keep the recent ones
    python scripts/prune_media_bucket.py --delete        # actually delete

Requires GITHUB_TOKEN and GITHUB_REPOSITORY (or --repo).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

API = "https://api.github.com"
MEDIA_TAG = os.environ.get("IG_MEDIA_RELEASE_TAG", "media-bucket")


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("GITHUB_TOKEN not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def list_assets(repo: str, tag: str = MEDIA_TAG) -> list[dict]:
    """Every asset on the media release, or [] if the release does not exist."""
    r = requests.get(f"{API}/repos/{repo}/releases/tags/{tag}",
                     headers=_headers(), timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("assets", [])


def _age_days(asset: dict, now: datetime) -> float:
    created = asset.get("created_at") or ""
    try:
        ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")   # undatable -> treat as old
    return (now - ts).total_seconds() / 86400


def select(assets: list[dict], keep_days: int, now: datetime) -> list[dict]:
    """Assets older than keep_days.

    keep_days exists because a very recent asset may still be mid-ingest by
    Meta: deleting it underneath an in-flight container would break the one
    thing this bucket is for.
    """
    return [a for a in assets if _age_days(a, now) > keep_days]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--tag", default=MEDIA_TAG)
    ap.add_argument("--keep-days", type=int, default=1,
                    help="do not touch assets younger than this (default 1)")
    ap.add_argument("--delete", action="store_true",
                    help="actually delete; without it this only reports")
    args = ap.parse_args()

    if not args.repo:
        sys.exit("no repo: pass --repo owner/name or set GITHUB_REPOSITORY")

    assets = list_assets(args.repo, args.tag)
    if not assets:
        print(f"no assets on release '{args.tag}' — nothing to prune")
        return 0

    now = datetime.now(timezone.utc)
    doomed = select(assets, args.keep_days, now)
    total = sum(a.get("size", 0) for a in assets)
    freed = sum(a.get("size", 0) for a in doomed)

    print(f"=== {args.tag}: {len(assets)} assets, {total / 1e9:.2f} GB ===")
    for a in sorted(doomed, key=lambda x: x.get("created_at", "")):
        print(f"  {'DELETE' if args.delete else '  would'} "
              f"{a['name']:<28} {a.get('size', 0) / 1e6:7.1f} MB  "
              f"{a.get('created_at', '?')}")
    kept = len(assets) - len(doomed)
    print(f"\n{len(doomed)} to remove ({freed / 1e9:.2f} GB), {kept} kept "
          f"(younger than {args.keep_days}d)")

    if not args.delete:
        print("\nDRY RUN — nothing deleted. Re-run with --delete to apply.")
        return 0

    failed = 0
    for a in doomed:
        r = requests.delete(f"{API}/repos/{args.repo}/releases/assets/{a['id']}",
                            headers=_headers(), timeout=30)
        if r.status_code not in (204, 404):
            print(f"  FAILED {a['name']}: {r.status_code} {r.text[:100]}",
                  file=sys.stderr)
            failed += 1
    print(f"deleted {len(doomed) - failed}/{len(doomed)} assets, "
          f"freed ~{freed / 1e9:.2f} GB")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
