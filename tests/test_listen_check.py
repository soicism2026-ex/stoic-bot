"""The listen-check: a narration that drops or garbles words never airs,
and a listener's spelling quirks never block a good one."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import listen_check as lc  # noqa: E402

SCRIPT = ("The thing blocking you is the path. That which is a hindrance is made a "
          "furtherance to an act; and that which is an obstacle on the road helps us on this road.")


def test_a_clean_read_passes():
    r = lc.compare(SCRIPT, SCRIPT.upper().replace(";", ","))
    assert r.ok and r.recall == 1.0 and r.extras == 0


def test_a_listener_splitting_or_misspelling_words_still_passes():
    heard = SCRIPT.replace("furtherance", "further ants").replace("hindrance", "hinderance")
    r = lc.compare(SCRIPT, heard)
    assert r.ok, r.summary()
    r = lc.compare("Epictetus said it best.", "Epic Titus said it best.")
    assert r.ok, r.summary()


def test_a_skipped_phrase_fails():
    heard = SCRIPT.replace("is made a furtherance to an act; and ", "")
    r = lc.compare(SCRIPT, heard)
    assert r.ok is False and r.longest_gap >= 2
    assert "furtherance" in r.missing


def test_one_garbled_word_in_a_short_line_fails_on_recall():
    r = lc.compare("Stop waiting to start.", "Stop wading to fart.")
    assert r.ok is False, r.summary()


def test_a_stutter_or_hallucinated_phrase_fails():
    heard = SCRIPT.replace("helps us on this road", "helps us helps us helps us on this road")
    r = lc.compare(SCRIPT, heard)
    assert r.ok is False and r.extras >= 3


def test_no_key_or_api_error_fails_open(monkeypatch, tmp_path):
    audio = tmp_path / "v.mp3"
    audio.write_bytes(b"x")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert lc.check(audio, SCRIPT).ok is None
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")

    def boom(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(lc.requests, "post", boom)
    r = lc.check(audio, SCRIPT)
    assert r.ok is None and "could not listen" in r.reason


def test_check_sends_the_audio_to_scribe(monkeypatch, tmp_path):
    audio = tmp_path / "v.mp3"
    audio.write_bytes(b"x")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"text": SCRIPT}

    def post(url, headers, data, files, timeout):
        seen.update(url=url, model=data["model_id"], key=headers["xi-api-key"])
        return Resp()
    monkeypatch.setattr(lc.requests, "post", post)
    assert lc.check(audio, SCRIPT).ok is True
    assert seen["url"].endswith("/v1/speech-to-text") and seen["model"].startswith("scribe")


def test_it_can_be_switched_off(monkeypatch, tmp_path):
    monkeypatch.setenv("LISTEN_CHECK", "0")
    assert lc.check(tmp_path / "missing.mp3", SCRIPT).ok is None
