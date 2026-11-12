"""The free provider (src/llm.py chat): comment replies run on Cloudflare's
Llama when the paid Anthropic key is empty (owner 2026-11-11: "getting
agents to do their work autonomously"). Only FREE_OK features may use it;
the generator and the reviewer stay paid-key-only; callers fail closed."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import llm  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "LLM_DISABLED", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(k, raising=False)


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


def test_only_replies_may_run_free(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    assert llm.available("replies") and llm.provider("replies") == "cloudflare"
    assert not llm.available() and not llm.available("content") and not llm.available("visual_qa")
    assert llm.reason("content") == "no ANTHROPIC_API_KEY" and llm.reason("replies") == ""
    monkeypatch.setenv("LLM_DISABLED", "1")
    assert not llm.available("replies") and llm.reason("replies") == "LLM_DISABLED=1"


def test_the_paid_key_still_comes_first(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    assert llm.provider("replies") == "anthropic" and llm.provider() == "anthropic"


def test_nothing_at_all_names_both(monkeypatch):
    assert llm.reason("replies") == "no ANTHROPIC_API_KEY and no Cloudflare key"
    assert "no Cloudflare key" in llm.skip_note("replies")
    with pytest.raises(llm.LLMError):
        llm.chat("s", "u")


def test_a_cloudflare_chat_sends_the_messages_and_logs_its_cost(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok456")
    sent, ledger = [], []

    def post(url, headers=None, json=None, timeout=None):
        sent.append((url, headers, json))
        return _Resp({"success": True, "result": {"response": "  Yeah. That one's hard.  ",
                                                   "usage": {"prompt_tokens": 400, "completion_tokens": 12}}})
    import requests
    monkeypatch.setattr(requests, "post", post)
    import imagegen
    monkeypatch.setattr(imagegen, "_ledger_add", lambda cache, n: ledger.append(n))
    out = llm.chat("be brief", "hello", max_tokens=50, feature="replies")
    assert out == "Yeah. That one's hard."
    url, headers, body = sent[0]
    assert url.endswith("/accounts/acct123/ai/run/" + llm.CF_MODEL)
    assert headers == {"Authorization": "Bearer tok456"}
    assert body["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hello"}]
    assert body["max_tokens"] == 50
    assert ledger and ledger[0] == pytest.approx(400 * llm.CF_NEURONS_IN + 12 * llm.CF_NEURONS_OUT)


def test_a_refusal_raises_without_the_keys_in_it(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok456")
    import requests
    for resp in (_Resp({"success": False, "errors": [{"code": 4006, "message": "daily allocation used up tok456"}]}, 429),
                 _Resp(ValueError("not json"), 502),
                 _Resp({"success": True, "result": {"response": "   "}})):
        monkeypatch.setattr(requests, "post", lambda *a, _r=resp, **k: _r)
        with pytest.raises(llm.LLMError) as err:
            llm.chat("s", "u")
        assert "tok456" not in str(err.value) and "acct123" not in str(err.value)


def test_the_replier_screens_and_writes_through_the_one_door(monkeypatch):
    import reply_to_comments as rc
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    calls = []

    def chat(system, user, max_tokens=200, feature="replies", **kw):
        calls.append((feature, max_tokens))
        return "ENGAGE" if max_tokens == 5 else '"That one took me years too."'
    monkeypatch.setattr(llm, "chat", chat)
    assert rc._is_receptive("This helped me more than you know, thank you.") is True
    assert rc._generate_reply("This helped me", "Stoic Shorts") == "That one took me years too."
    assert calls == [("replies", 5), ("replies", 200)]
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("down")))
    assert rc._is_receptive("Genuine question here?") is False          # fails closed
    assert rc._is_receptive("lol this is cringe") is False               # the cheap prefilter, no call


def test_the_reply_step_carries_the_free_keys():
    wf = (ROOT / ".github" / "workflows" / "daily-short.yml").read_text(encoding="utf-8")
    step = wf[wf.index("Reply to top comments"):wf.index("python scripts/reply_to_comments.py")]
    assert "CLOUDFLARE_ACCOUNT_ID" in step and "CLOUDFLARE_API_TOKEN" in step


def test_an_empty_paid_key_falls_to_the_free_provider_and_stays_down(monkeypatch):
    """The key is in GitHub but its credit is empty (the 2026-11-12 run printed
    the refusal four times and replied to nobody). The first refusal marks
    Anthropic down for the run; replies go to Cloudflare, the reviewer skips."""
    monkeypatch.setattr(llm, "_ANTHROPIC_DOWN", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    refusal = RuntimeError("Error code: 400 - {'message': 'Your credit balance is too low to access the Anthropic API.'}")
    monkeypatch.setattr(llm, "_anthropic_chat", lambda *a, **k: (_ for _ in ()).throw(refusal))
    monkeypatch.setattr(llm, "_cloudflare_chat", lambda s, u, m: "from the free model")
    assert llm.provider("replies") == "anthropic"
    assert llm.chat("s", "u", feature="replies") == "from the free model"
    assert llm.anthropic_down() and llm.provider("replies") == "cloudflare"
    assert not llm.available() and not llm.available("visual_qa")          # the reviewer skips now
    assert "no credit" in llm.skip_note("visual_qa")
    monkeypatch.setattr(llm, "_ANTHROPIC_DOWN", "")
    assert llm.note_failure(RuntimeError("Connection reset")) is False       # a blip is not "down"
    assert llm.provider() == "anthropic"
