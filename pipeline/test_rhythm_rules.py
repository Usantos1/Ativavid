"""Cada ritmo da UI resolve para regra própria no prompt — nunca no fallback."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))
from llm_cut_plan import _rhythm_rules  # noqa: E402


def _ritmo_section(rhythm: str) -> str:
    text = _rhythm_rules({"rhythm": rhythm, "editingIntent": "dynamic"})
    assert "RITMO=" in text, text[:200]
    return text.split("RITMO=")[1].split("\n")[0]


def test_ui_values_resolve_to_distinct_rules():
    dinamico = _ritmo_section("dinamico")
    # calmo→natural e rapido→viral pelos aliases; os novos são diretos.
    for r in ("calmo", "rapido", "cirurgico", "narrativa", "muito_rapido"):
        assert _ritmo_section(r) != dinamico, f"{r} caiu no fallback dinamico"


def test_aliases_match_their_targets():
    assert _ritmo_section("calmo") == _ritmo_section("natural")
    assert _ritmo_section("rapido") == _ritmo_section("viral")


def test_new_rhythms_have_their_intent():
    assert "frase" in _ritmo_section("cirurgico").lower()
    assert "hist" in _ritmo_section("narrativa").lower()
    assert "essencial" in _ritmo_section("muito_rapido").lower()
