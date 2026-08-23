"""The Instagram cross-post has never once succeeded, and it was expensive.

Every run: upload the full MP4 to a public GitHub Release, then call the Graph
API with a token that has been invalid for months, then fail. Nothing deleted
the upload. By 2026-08-23 that release held 59 files and 12.2 GB.

Two defects, both about ORDER and CLEANUP rather than about Instagram:
  1. credentials were verified after the upload instead of before it
  2. the hosted asset was never removed, win or lose

These tests pin both, plus the pruner that clears the backlog.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import publish_instagram as ig  # noqa: E402
import prune_media_bucket as pmb  # noqa: E402


class _Resp:
    def __init__(self, ok=True, status=200, payload=None, text=""):
        self.ok, self.status_code = ok, status
        self._payload, self.text = payload or {}, text

    def json(self):
        return self._payload


# ------------------------------------------------- credentials gate

def test_bad_credentials_skip_before_any_upload(tmp_path):
    """The whole 12.2 GB was uploaded after the token was already dead."""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    rejected = _Resp(ok=False, status=400,
                     payload={"error": {"message": "Invalid OAuth access token"}})
    with patch.object(ig.requests, "get", return_value=rejected), \
         patch.object(ig, "_host_via_github_release") as host:
        out = ig.publish_reel(video, "caption", ["#a"])
    host.assert_not_called()
    assert out["status"] == "skipped"


def test_credential_check_failure_fails_closed(tmp_path):
    """A network blip must skip, not upload on the assumption it is fine."""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with patch.object(ig.requests, "get", side_effect=OSError("dns")), \
         patch.object(ig, "_host_via_github_release") as host:
        out = ig.publish_reel(video, "caption", [])
    host.assert_not_called()
    assert out["status"] == "skipped"


def test_missing_credentials_still_skip(tmp_path, monkeypatch):
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("IG_USER_ID", raising=False)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with patch.object(ig, "_host_via_github_release") as host:
        out = ig.publish_reel(video, "c", [])
    host.assert_not_called()
    assert out["status"] == "skipped"


def test_good_credentials_proceed_to_upload(tmp_path, monkeypatch):
    """The gate must not block the working case."""
    monkeypatch.setenv("IG_ACCESS_TOKEN", "t")
    monkeypatch.setenv("IG_USER_ID", "42")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with patch.object(ig.requests, "get", return_value=_Resp(payload={"id": "42"})), \
         patch.object(ig, "_host_via_github_release",
                      return_value=("http://u", "o/r", 7)) as host, \
         patch.object(ig, "_create_container", return_value="c1"), \
         patch.object(ig, "_wait_until_ready", return_value=True), \
         patch.object(ig, "_publish", return_value="m1"), \
         patch.object(ig, "_delete_asset"):
        out = ig.publish_reel(video, "c", [])
    host.assert_called_once()
    assert out == {"status": "published", "media_id": "m1"}


# ------------------------------------------------- asset cleanup

def _run_with_outcome(video, monkeypatch, **overrides):
    monkeypatch.setenv("IG_ACCESS_TOKEN", "t")
    monkeypatch.setenv("IG_USER_ID", "42")
    stack = {
        "_create_container": "c1",
        "_wait_until_ready": True,
        "_publish": "m1",
    }
    stack.update(overrides)
    with patch.object(ig.requests, "get", return_value=_Resp(payload={"id": "42"})), \
         patch.object(ig, "_host_via_github_release",
                      return_value=("http://u", "o/r", 7)), \
         patch.object(ig, "_delete_asset") as dele:
        ctxs = [patch.object(ig, k, **({"side_effect": v}
                if isinstance(v, Exception) else {"return_value": v}))
                for k, v in stack.items()]
        for c in ctxs:
            c.start()
        try:
            out = ig.publish_reel(video, "c", [])
        finally:
            for c in ctxs:
                c.stop()
    return out, dele


def test_asset_is_deleted_after_a_successful_publish(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    out, dele = _run_with_outcome(video, monkeypatch)
    assert out["status"] == "published"
    dele.assert_called_once_with("o/r", 7)


def test_asset_is_deleted_when_the_container_never_becomes_ready(tmp_path, monkeypatch):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    out, dele = _run_with_outcome(video, monkeypatch, _wait_until_ready=False)
    assert out["status"] == "failed"
    dele.assert_called_once_with("o/r", 7)


def test_asset_is_deleted_when_publishing_raises(tmp_path, monkeypatch):
    """The failure path is the one that actually ran for months."""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    out, dele = _run_with_outcome(video, monkeypatch, _publish=RuntimeError("boom"))
    assert out["status"] == "failed"
    dele.assert_called_once_with("o/r", 7)


def test_cleanup_failure_never_breaks_the_post():
    """A post must never be lost to housekeeping."""
    with patch.object(ig.requests, "delete", side_effect=OSError("nope")):
        ig._delete_asset("o/r", 7)   # must not raise


# ------------------------------------------------- the pruner

def _asset(name, days_old, size=300_000_000, now=None):
    now = now or datetime.now(timezone.utc)
    ts = (now - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
    return {"id": abs(hash(name)) % 10000, "name": name, "size": size,
            "created_at": ts}


def test_pruner_selects_only_assets_older_than_keep_days():
    now = datetime.now(timezone.utc)
    assets = [_asset("old.mp4", 30, now=now), _asset("new.mp4", 0.2, now=now)]
    picked = [a["name"] for a in pmb.select(assets, keep_days=1, now=now)]
    assert picked == ["old.mp4"]


def test_pruner_keeps_a_fresh_asset_that_meta_may_still_be_fetching():
    """Deleting an in-flight upload would break the one thing the bucket does."""
    now = datetime.now(timezone.utc)
    assert pmb.select([_asset("today.mp4", 0.1, now=now)], 1, now) == []


def test_pruner_treats_an_undatable_asset_as_old():
    a = {"id": 1, "name": "x.mp4", "size": 1, "created_at": "not-a-date"}
    assert pmb.select([a], keep_days=1, now=datetime.now(timezone.utc)) == [a]


def test_pruner_dry_run_deletes_nothing(monkeypatch, capsys):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(pmb, "list_assets",
                        lambda *a, **k: [_asset("old.mp4", 30, now=now)])
    monkeypatch.setattr(sys, "argv",
                        ["prune_media_bucket.py", "--repo", "o/r"])
    with patch.object(pmb.requests, "delete") as dele:
        assert pmb.main() == 0
    dele.assert_not_called()
    assert "DRY RUN" in capsys.readouterr().out


def test_pruner_deletes_when_asked(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(pmb, "list_assets",
                        lambda *a, **k: [_asset("old.mp4", 30, now=now)])
    monkeypatch.setattr(sys, "argv",
                        ["prune_media_bucket.py", "--repo", "o/r", "--delete"])
    monkeypatch.setattr(pmb, "_headers", lambda: {})
    with patch.object(pmb.requests, "delete",
                      return_value=_Resp(status=204)) as dele:
        assert pmb.main() == 0
    dele.assert_called_once()


def test_pruner_on_a_missing_release_is_not_an_error(monkeypatch):
    monkeypatch.setattr(pmb, "list_assets", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["prune_media_bucket.py", "--repo", "o/r"])
    assert pmb.main() == 0
