"""The pre-flight gate must never be the thing that kills the pipeline.

A definitively bad credential SHOULD stop the run — nothing can post without a
valid token, and the owner needs to know. But a provider 5xx, a rate limit or a
DNS blip says nothing about the credential, and aborting on one costs a whole
posting slot. That exact bug killed the 2026-08-05 05:37 run (Google 500).
"""
import io
import socket
import sys
import urllib.error
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_secrets as cs  # noqa: E402


def _http_error(code: int, body: bytes = b"{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.test", code, "err", {}, io.BytesIO(body)
    )


# ------------------------------------------------------------- classification

@pytest.mark.parametrize("code", [500, 502, 503, 504, 429])
def test_server_errors_are_transient(code):
    assert cs._is_transient(_http_error(code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_are_not_transient(code):
    assert cs._is_transient(_http_error(code)) is False


def test_network_failures_are_transient():
    assert cs._is_transient(urllib.error.URLError("dns go boom"))
    assert cs._is_transient(socket.timeout("slow"))
    assert cs._is_transient(TimeoutError())
    assert cs._is_transient(ConnectionError())
    assert cs._is_transient(requests.exceptions.ConnectionError())


def test_requests_http_error_classified_by_status():
    resp = requests.Response()
    resp.status_code = 503
    assert cs._is_transient(requests.exceptions.HTTPError(response=resp))
    resp.status_code = 401
    assert cs._is_transient(requests.exceptions.HTTPError(response=resp)) is False


def test_unrelated_exception_is_not_transient():
    assert cs._is_transient(ValueError("bad json")) is False


# ------------------------------------------------------------------- retrying

def test_retrying_returns_value_on_success(monkeypatch):
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)
    val, err = cs._retrying(lambda: "ok", "X")
    assert (val, err) == ("ok", None)


def test_retrying_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def _flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(500)
        return "recovered"

    val, err = cs._retrying(_flaky, "X")
    assert val == "recovered" and err is None
    assert calls["n"] == 3, "should have retried through the blips"


def test_retrying_does_not_retry_fatal(monkeypatch):
    """A revoked token will still be revoked in two seconds. Fail fast."""
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def _dead():
        calls["n"] += 1
        raise _http_error(401)

    val, err = cs._retrying(_dead, "X")
    assert val is None and isinstance(err, urllib.error.HTTPError)
    assert calls["n"] == 1


def test_retrying_gives_up_after_limit(monkeypatch):
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def _always_500():
        calls["n"] += 1
        raise _http_error(503)

    val, err = cs._retrying(_always_500, "X")
    assert val is None and cs._is_transient(err)
    assert calls["n"] == cs.RETRIES


# ------------------------------------------------------- youtube check policy

@pytest.fixture
def yt_env(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)


def test_youtube_500_does_not_fail_the_run(yt_env, monkeypatch, capsys):
    """THE REGRESSION. Google 500 must not abort the pipeline."""
    def _boom(*a, **k):
        raise _http_error(500)

    monkeypatch.setattr(cs.urllib.request, "urlopen", _boom)
    assert cs.check_youtube() is True
    assert "500" in capsys.readouterr().out


def test_youtube_connection_error_does_not_fail_the_run(yt_env, monkeypatch):
    def _boom(*a, **k):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(cs.urllib.request, "urlopen", _boom)
    assert cs.check_youtube() is True


def test_youtube_quota_still_skips(yt_env, monkeypatch):
    def _boom(*a, **k):
        raise _http_error(403, b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')

    monkeypatch.setattr(cs.urllib.request, "urlopen", _boom)
    assert cs.check_youtube() is True


def test_youtube_invalid_grant_still_fails(yt_env, monkeypatch, capsys):
    """A genuinely dead refresh token must still stop the run loudly."""
    def _boom(*a, **k):
        raise _http_error(400, b'{"error":"invalid_grant"}')

    monkeypatch.setattr(cs.urllib.request, "urlopen", _boom)
    assert cs.check_youtube() is False


def test_youtube_missing_secret_still_fails(monkeypatch):
    for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert cs.check_youtube() is False


# ----------------------------------------------------- anthropic check policy

def test_anthropic_500_does_not_fail_the_run(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)

    def _boom(*a, **k):
        raise _http_error(500)

    monkeypatch.setattr(cs.urllib.request, "urlopen", _boom)
    assert cs.check_anthropic() is True


def test_anthropic_401_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-bad")
    monkeypatch.setattr(cs.time, "sleep", lambda _s: None)

    def _boom(*a, **k):
        raise _http_error(401)

    monkeypatch.setattr(cs.urllib.request, "urlopen", _boom)
    assert cs.check_anthropic() is False


def test_anthropic_missing_key_fails(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cs.check_anthropic() is False
