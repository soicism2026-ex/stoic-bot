"""
main.py — the Higgsfield SDK / Seedance 2.5 example.

The real generation is billable and cannot run in CI, so these tests fake the
SDK and prove the part that is easy to get wrong: `subscribe()` returns failed,
canceled and moderated requests as ordinary JSON instead of raising, and the
example must never report one of those as a success.

Loaded by path: tests put src/ on sys.path, and src/main.py (the old
orchestrator) would otherwise shadow the root main.py.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("hf_example", ROOT / "main.py")
ex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ex)

FAKE_KEY = "keyid123456:secretABCDEF"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for name in ("HF_KEY", "HF_API_KEY", "HF_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    # never let a developer's real .env.local leak into a test
    monkeypatch.setattr(ex, "ENV_FILE", tmp_path / ".env.local")


def _fake_subscribe(monkeypatch, result, statuses=("Queued", "InProgress", "Completed")):
    calls = {}

    def fake(model, arguments, on_enqueue=None, on_queue_update=None):
        calls["model"], calls["arguments"] = model, arguments
        if on_enqueue:
            on_enqueue("req-1")
        if on_queue_update:
            for name in statuses:
                on_queue_update(type(name, (), {})())
        return result
    monkeypatch.setattr(ex.higgsfield_client, "subscribe", fake)
    return calls


# ------------------------------------------------------------ the request

def test_requests_exactly_what_was_asked_for(monkeypatch):
    monkeypatch.setenv("HF_KEY", FAKE_KEY)
    calls = _fake_subscribe(monkeypatch, {"status": "completed",
                                          "video": {"url": "https://v/x.mp4"}})
    assert ex.main() == 0
    assert calls["model"] == "bytedance/seedance-2.5/text-to-video"
    assert calls["arguments"] == {"prompt": "A cinematic scene at sunset",
                                  "duration": 5, "resolution": "720p",
                                  "aspect_ratio": "16:9"}


def test_completed_prints_the_url(monkeypatch, capsys):
    monkeypatch.setenv("HF_KEY", FAKE_KEY)
    _fake_subscribe(monkeypatch, {"status": "completed",
                                  "video": {"url": "https://v/x.mp4"}})
    assert ex.main() == 0
    assert "video_url  https://v/x.mp4" in capsys.readouterr().out


# ------------------------------------------ never claim success on these

@pytest.mark.parametrize("result,words", [
    ({"status": "failed", "error": "bad prompt"}, "failed: bad prompt"),
    ({"status": "nsfw"}, "moderation"),
    ({"status": "canceled"}, "canceled"),
    ({"status": "completed"}, "no video URL"),
    ({"status": "completed", "video": {"url": ""}}, "no video URL"),
    ({"status": "mystery"}, "unexpected status"),
    ({}, "unexpected status"),
])
def test_non_success_is_never_reported_as_success(monkeypatch, capsys, result, words):
    monkeypatch.setenv("HF_KEY", FAKE_KEY)
    _fake_subscribe(monkeypatch, result)
    assert ex.main() == 1
    out = capsys.readouterr()
    assert "video_url" not in out.out
    assert words in out.err


def test_api_errors_fail_cleanly(monkeypatch, capsys):
    monkeypatch.setenv("HF_KEY", FAKE_KEY)

    def boom(*a, **k):
        raise ex.higgsfield_client.HiggsfieldClientError("Insufficient credits")
    monkeypatch.setattr(ex.higgsfield_client, "subscribe", boom)
    assert ex.main() == 1
    assert "API error: Insufficient credits" in capsys.readouterr().err


def test_network_errors_fail_cleanly(monkeypatch, capsys):
    monkeypatch.setenv("HF_KEY", FAKE_KEY)

    def boom(*a, **k):
        raise ConnectionError("CONNECT tunnel failed, response 403")
    monkeypatch.setattr(ex.higgsfield_client, "subscribe", boom)
    assert ex.main() == 1
    assert "ConnectionError" in capsys.readouterr().err


# ---------------------------------------------------------- credentials

def test_missing_key_does_not_call_the_api(monkeypatch, capsys):
    monkeypatch.setattr(ex.higgsfield_client, "subscribe",
                        lambda *a, **k: pytest.fail("called with no key"))
    assert ex.main() == 2
    assert "HF_KEY is not set" in capsys.readouterr().err


def test_a_half_pasted_key_is_refused_before_sending(monkeypatch, capsys):
    monkeypatch.setenv("HF_KEY", "just_the_id")
    monkeypatch.setattr(ex.higgsfield_client, "subscribe",
                        lambda *a, **k: pytest.fail("sent a malformed key"))
    assert ex.main() == 2
    assert "KEY_ID:KEY_SECRET" in capsys.readouterr().err


def test_the_split_key_form_is_accepted(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "keyid123456")
    monkeypatch.setenv("HF_API_SECRET", "secretABCDEF")
    assert ex.credentials_problem() is None


def test_the_key_is_loaded_from_env_local(monkeypatch, tmp_path):
    envf = tmp_path / ".env.local"
    envf.write_text(f"HF_KEY={FAKE_KEY}\n")
    monkeypatch.setattr(ex, "ENV_FILE", envf)
    _fake_subscribe(monkeypatch, {"status": "completed",
                                  "video": {"url": "https://v/x.mp4"}})
    assert ex.main() == 0


def test_the_key_never_reaches_the_terminal(monkeypatch, capsys):
    """Even when the API echoes it back inside an error."""
    monkeypatch.setenv("HF_KEY", FAKE_KEY)

    def boom(*a, **k):
        raise ex.higgsfield_client.HiggsfieldClientError(
            f"invalid credentials {FAKE_KEY} (id keyid123456)")
    monkeypatch.setattr(ex.higgsfield_client, "subscribe", boom)
    ex.main()
    out = capsys.readouterr()
    for secret in (FAKE_KEY, "keyid123456", "secretABCDEF"):
        assert secret not in out.out + out.err


def test_the_example_never_prints_the_environment():
    src = (ROOT / "main.py").read_text()
    assert "print(os.environ" not in src
    assert 'os.environ.get("HF_KEY")}' not in src


# ---------------------------------------------------------- the wait

def test_an_endless_queue_is_abandoned_and_canceled(monkeypatch, capsys):
    """subscribe() polls forever on its own. The example must not."""
    monkeypatch.setenv("HF_KEY", FAKE_KEY)
    monkeypatch.setattr(ex, "MAX_WAIT_SECONDS", -1)
    canceled = []
    monkeypatch.setattr(ex.higgsfield_client, "cancel", canceled.append)
    _fake_subscribe(monkeypatch, {"status": "completed",
                                  "video": {"url": "https://v/x.mp4"}},
                    statuses=("Queued",))
    assert ex.main() == 1
    assert canceled == ["req-1"]
    err = capsys.readouterr().err
    assert "may still complete and bill" in err


# ---------------------------------------------------------- git hygiene

def test_env_local_is_git_ignored():
    import subprocess
    r = subprocess.run(["git", "check-ignore", "-q", ".env.local"],
                       cwd=ROOT, timeout=30)
    assert r.returncode == 0, ".env.local would be committed"


def test_no_higgsfield_credential_is_committed_anywhere_tracked():
    import re
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                           text=True, timeout=30).stdout.split()
    pat = re.compile(r'^\s*(HF_KEY|HF_API_KEY|HF_API_SECRET|HF_CREDENTIALS)'
                     r'\s*=\s*["\']?[A-Za-z0-9_-]{8,}')
    for f in files:
        if not f.endswith((".py", ".env", ".example", ".txt", ".yml", ".yaml",
                           ".md", ".json", ".cfg", ".ini", ".toml")):
            continue
        path = ROOT / f
        if not path.is_file():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            assert not pat.search(line), f"{f}: looks like a committed key"
