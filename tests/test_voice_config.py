"""The voice is an owner-approved taste decision, not a tunable.

The owner listened to three real samples and picked variant B (2026-08-06):
0.45 exaggeration / 0.35 cfg_weight / 0.25s sentence gap = 180 wpm. Not the
slowest option — the gaps are the point, giving the viewer a beat to take in
the background clip between lines.

A later "optimisation" toward the textbook 120-150 wpm range would quietly
overrule an ear-level verdict, so it fails here instead.
"""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tts  # noqa: E402


# Variant B, exactly as generated in scripts/make_voice_samples.py.
VARIANT_B = {"exaggeration": 0.45, "cfg_weight": 0.35, "gap": 0.25}


def _reload(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    return importlib.reload(tts)


def test_defaults_are_variant_b():
    assert tts._CB_EXAGGERATION == VARIANT_B["exaggeration"]
    assert tts._CB_CFG_WEIGHT == VARIANT_B["cfg_weight"]
    assert tts._CB_GAP == VARIANT_B["gap"]


def test_self_hosted_voice_is_on_by_default(monkeypatch):
    """$0 voice. Off by default would silently put the bill back."""
    m = _reload(monkeypatch, CHATTERBOX_LOCAL=None)
    assert m._CB_LOCAL is True


@pytest.mark.parametrize("off", ["0", "false", "False"])
def test_can_be_turned_off_by_repo_variable(monkeypatch, off):
    m = _reload(monkeypatch, CHATTERBOX_LOCAL=off)
    assert m._CB_LOCAL is False


def test_pacing_is_env_overridable(monkeypatch):
    """The workflow pins these explicitly; they must actually take effect."""
    m = _reload(monkeypatch, CHATTERBOX_EXAGGERATION="0.10",
                CHATTERBOX_CFG_WEIGHT="0.20", CHATTERBOX_SENTENCE_GAP="0.90")
    assert (m._CB_EXAGGERATION, m._CB_CFG_WEIGHT, m._CB_GAP) == (0.10, 0.20, 0.90)
    _reload(monkeypatch, CHATTERBOX_EXAGGERATION=None,
            CHATTERBOX_CFG_WEIGHT=None, CHATTERBOX_SENTENCE_GAP=None)


def test_gap_is_nonzero():
    """Zero gap is variant A, which measured 222 wpm AND truncated the script."""
    assert tts._CB_GAP > 0


# ------------------------------------------------------------------ chunking

def test_sentences_splits_on_terminators():
    out = tts._sentences("One thing. Two things! Three things? Four.")
    assert out == ["One thing.", "Two things!", "Three things?", "Four."]


def test_sentences_handles_empty_and_whitespace():
    assert tts._sentences("") == []
    assert tts._sentences("   ") == []
    assert tts._sentences("No terminator") == ["No terminator"]


def test_sentences_drops_blank_fragments():
    assert "" not in tts._sentences("A.  \n\n  B.")


# ------------------------------------------------------------- workflow wiring

def test_workflow_enables_local_voice_and_pins_variant_b():
    """Config in code is worthless if the workflow overrides it."""
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    steps = wf["jobs"]["post"]["steps"]
    env = next(s["env"] for s in steps if "CHATTERBOX_LOCAL" in (s.get("env") or {}))
    assert env["CHATTERBOX_LOCAL"] == "${{ vars.CHATTERBOX_LOCAL || '1' }}"
    assert float(env["CHATTERBOX_EXAGGERATION"]) == VARIANT_B["exaggeration"]
    assert float(env["CHATTERBOX_CFG_WEIGHT"]) == VARIANT_B["cfg_weight"]
    assert float(env["CHATTERBOX_SENTENCE_GAP"]) == VARIANT_B["gap"]


def test_voice_step_conditions_force_a_string_comparison():
    """GitHub casts to NUMBER when operand types differ, so an unset variable
    (null -> 0) compares equal to the string '0'. Written the obvious way,
    `vars.X != '0'` is FALSE when X does not exist — which silently skipped
    the install steps and left the $0 voice off while everything else said on.
    format() forces both sides to strings."""
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    conds = [s["if"] for s in wf["jobs"]["post"]["steps"]
             if "CHATTERBOX_LOCAL" in str(s.get("if", ""))]
    assert conds, "no step is gated on CHATTERBOX_LOCAL"
    for c in conds:
        assert "format(" in c, (
            f"bare comparison {c!r} silently skips when the variable is unset")


def test_voice_dep_install_cannot_break_a_post():
    """A bad torch wheel must degrade the voice, never stop the channel."""
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows/daily-short.yml").read_text())
    step = next(s for s in wf["jobs"]["post"]["steps"]
                if "voice deps" in s.get("name", ""))
    assert step.get("continue-on-error") is True
