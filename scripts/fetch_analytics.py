"""
Fetch recent YouTube video stats and print them as JSON to stdout.
Used by auto-improve.yml: python scripts/fetch_analytics.py > analytics.json

Reuses the OAuth logic from src/analytics.py — no extra secrets needed beyond
YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from analytics import fetch_recent  # noqa: E402


def main():
    rows = fetch_recent()
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
