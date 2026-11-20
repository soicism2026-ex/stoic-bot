"""Shared test setup.

Cicero's dated test "undo-nov16" (Nov 20-22, 2026) is live in the real ledger
and switches Fama's news tie-ins off and the comment ask back on. Every other
test describes the normal behaviour, so it runs with the test off, and only
tests/test_undo_nov16.py (which sets its own ledger) sees the real function.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def _undo_nov16_off(request, monkeypatch):
    if request.module.__name__.endswith("test_undo_nov16"):
        return
    import edits
    monkeypatch.setattr(edits, "undo_nov16_active", lambda day=None: False)
