"""
One place that decides whether a paid language-model call may be made.

OWNER DECISION 2026-09-18: "i dont want to pay for the separate claude api
anymore and i just want to use higgfield." So the pipeline must run to
completion with no `ANTHROPIC_API_KEY` at all — not crash, not fabricate, and
not fail open in a way that looks like a real result.

Before this module, six call sites each invented their own behaviour when the
key was missing or out of credit, and one of them recorded a fabricated
`pacing=5.0` into QA_LOG.md for 51 runs. The rule is now single and explicit:

    ASK `available()` FIRST. If it says no, SKIP and SAY SO.
    Never call and catch. Never substitute a made-up value for a missing one.

`LLM_DISABLED=1` forces off even when a key is present, so the no-API path can
be exercised deliberately — in tests, and by the owner, without deleting the
secret from GitHub.

WHAT HIGGSFIELD DOES NOT REPLACE: it generates pictures, video and voice. It
does not write Stoic scripts and it cannot verify a quote against a
public-domain translation. The channel's words come from `data/stories.json`,
which is hand-written and human-approved by design (see src/stories.py), so
dropping the API costs the channel a *generator*, not its content.
"""
from __future__ import annotations

import os

# Features that call a language model, and what the channel loses without one.
# Used for the honest one-line skip notices, so a silent run is never mistaken
# for a working one.
FEATURES = {
    "content": "generated posts (the hand-written story bank is unaffected)",
    "visual_qa": "the reviewer that watches each render",
    "qa_vision": "the vision half of the QA check (ffmpeg checks still run)",
    "replies": "auto-replies to viewer comments",
    "strategy": "the daily strategy rewrite",
}


# A SECOND, FREE PROVIDER (owner 2026-11-11: "improve the stoics channel by
# getting agents to do their work autonomously"): Cloudflare Workers AI, whose
# free 10,000 neurons a day already paint the Shorts. Llama 3.3 70B there
# costs ~27 neurons per 1,000 words in and ~200 per 1,000 words out, so a
# day's comment replies cost under 1% of the allowance. It is allowed ONLY
# for features in FREE_OK: short conversational text that a person reads
# (replies). It never generates posts (quotes must be verbatim public-domain
# text, which no model is trusted to produce) and never reviews video.
FREE_OK = {"replies"}
CF_MODEL = os.environ.get("CLOUDFLARE_TEXT_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
CF_TIMEOUT = 60
# Neurons per token on Workers AI (developers.cloudflare.com pricing, 2026-11-11).
CF_NEURONS_IN, CF_NEURONS_OUT = 26_668 / 1e6, 204_805 / 1e6


def disabled_by_config() -> bool:
    return os.environ.get("LLM_DISABLED", "0") not in ("0", "false", "False")


def key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def cloudflare_keys() -> tuple[str, str]:
    return ((os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip(),
            (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip())


def free_available() -> bool:
    return all(cloudflare_keys()) and not disabled_by_config()


def available(feature: str | None = None) -> bool:
    """True only when a call may actually be attempted. With no feature named,
    only the paid Anthropic key counts (the generator, the reviewer); a
    feature in FREE_OK may also run on the free provider."""
    if disabled_by_config():
        return False
    if key() and not _ANTHROPIC_DOWN:
        return True
    return feature in FREE_OK and free_available()


def reason(feature: str | None = None) -> str:
    """Why calls are off, in words fit for a log line."""
    if disabled_by_config():
        return "LLM_DISABLED=1"
    if _ANTHROPIC_DOWN and not (feature in FREE_OK and free_available()):
        return _ANTHROPIC_DOWN
    if not key() or _ANTHROPIC_DOWN:
        if feature in FREE_OK and not free_available():
            return "no ANTHROPIC_API_KEY and no Cloudflare key"
        if feature in FREE_OK:
            return ""
        return "no ANTHROPIC_API_KEY"
    return ""


def provider(feature: str | None = None) -> str:
    """"anthropic", "cloudflare" or "" (nothing may be called)."""
    if not available(feature):
        return ""
    return "anthropic" if key() and not _ANTHROPIC_DOWN else "cloudflare"


class LLMError(RuntimeError):
    """The provider refused or answered nothing usable. Callers fail CLOSED."""


# The paid key can be present and still unusable (empty credit, revoked).
# The first such refusal in a process marks Anthropic down for the rest of
# it: later callers skip instead of failing the same way (the 2026-11-12 run
# printed the "credit balance is too low" error four times), and FREE_OK
# features go straight to the free provider.
_ANTHROPIC_DOWN = ""
_CREDIT_SIGNS = ("credit balance", "billing", "insufficient", "authentication", "invalid x-api-key",
                 "permission_error", "401", "403")


def anthropic_down() -> str:
    return _ANTHROPIC_DOWN


def note_failure(exc: BaseException) -> bool:
    """Remember an Anthropic refusal that will not fix itself this run. True
    when it was one (callers may then skip the feature for the rest)."""
    global _ANTHROPIC_DOWN
    text = str(exc).lower()
    if any(sign in text for sign in _CREDIT_SIGNS):
        _ANTHROPIC_DOWN = "the Anthropic key has no credit or was refused"
        return True
    return False


def _anthropic_chat(system: str, user: str, max_tokens: int, model: str) -> str:
    import anthropic  # noqa: PLC0415
    client = anthropic.Anthropic(api_key=key())
    msg = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}])
    text = "".join(getattr(b, "text", "") for b in msg.content).strip()
    if not text:
        raise LLMError("Anthropic returned no text")
    return text


def _cloudflare_chat(system: str, user: str, max_tokens: int) -> str:
    import requests  # noqa: PLC0415
    acct, tok = cloudflare_keys()
    r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{CF_MODEL}",
                      headers={"Authorization": f"Bearer {tok}"},
                      json={"messages": [{"role": "system", "content": system},
                                         {"role": "user", "content": user}],
                            "max_tokens": max_tokens, "temperature": 0.6}, timeout=CF_TIMEOUT)
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code >= 400 or payload.get("success") is False:
        errs = payload.get("errors") or []
        msg = "; ".join(str((e or {}).get("message", e)) for e in errs)[:200] if errs else f"HTTP {r.status_code}"
        raise LLMError(f"Cloudflare: {msg}".replace(tok, "<token>").replace(acct, "<account>"))
    result = payload.get("result") or {}
    text = result.get("response")
    if not isinstance(text, str):
        choices = result.get("choices") or [{}]
        text = (((choices[0] or {}).get("message") or {}).get("content")) or ""
    text = text.strip()
    if not text:
        raise LLMError("Cloudflare returned no text")
    usage = result.get("usage") or {}
    neurons = (float(usage.get("prompt_tokens") or 0) * CF_NEURONS_IN
               + float(usage.get("completion_tokens") or 0) * CF_NEURONS_OUT)
    if neurons:
        try:
            import imagegen  # noqa: PLC0415  the paintings' day ledger, shared
            imagegen._ledger_add(imagegen.still_cache_dir(), neurons)
        except Exception:  # noqa: BLE001
            pass
    return text


def chat(system: str, user: str, max_tokens: int = 200, feature: str = "replies",
         anthropic_model: str = "claude-haiku-4-5-20251001") -> str:
    """One short completion on whichever provider `feature` may use. Raises
    LLMError (or the provider's own error) when nothing usable came back:
    callers skip and say so, never substitute."""
    which = provider(feature)
    if not which:
        raise LLMError(reason(feature) or "no provider")
    if which == "anthropic":
        try:
            return _anthropic_chat(system, user, max_tokens, anthropic_model)
        except Exception as e:  # noqa: BLE001
            # A key with no credit behind it: fall to the free provider when
            # this feature may use it, and remember for the rest of the run.
            if note_failure(e) and feature in FREE_OK and free_available():
                print(f"  [llm] Anthropic refused ({str(e)[:80]}); using Cloudflare for {feature}", flush=True)
                return _cloudflare_chat(system, user, max_tokens)
            raise
    return _cloudflare_chat(system, user, max_tokens)


def skip_note(feature: str) -> str:
    """The standard one-line notice. Every caller prints the same shape, so
    `grep '\\[llm\\]'` in a workflow log shows everything that was skipped."""
    lost = FEATURES.get(feature, feature)
    return f"  [llm] {feature} skipped ({reason(feature) or reason()}) — {lost}"
