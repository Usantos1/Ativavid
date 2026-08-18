"""Contador de lista (Top N) — detecta enumeração falada nas legendas.

Sem IA e sem rede: varre captions.json (já na timeline do corte) atrás de
ordinais em sequência ASCENDENTE começando no 1. É essa regra que mata os
falsos positivos clássicos do PT: "trinta segundos" não dispara porque
"segundo" só conta se o "primeiro" já apareceu; "quarto" (cômodo) idem.

Ativa só com 2+ marcadores — um "primeiro" solto não é lista.
"""
from __future__ import annotations

import unicodedata
from typing import Any

_ORDINALS = {
    1: {"primeiro", "primeira", "1º", "1ª", "1o", "1a"},
    2: {"segundo", "segunda", "2º", "2ª", "2o", "2a"},
    3: {"terceiro", "terceira", "3º", "3ª", "3o", "3a"},
    4: {"quarto", "quarta", "4º", "4ª", "4o", "4a"},
    5: {"quinto", "quinta", "5º", "5ª", "5o", "5a"},
    6: {"sexto", "sexta", "6º", "6ª"},
    7: {"setimo", "setima", "7º", "7ª"},
    8: {"oitavo", "oitava", "8º", "8ª"},
    9: {"nono", "nona", "9º", "9ª"},
    10: {"decimo", "decima", "10º", "10ª"},
}
# "número um / dois / três" também abre ou continua a sequência
_NUM_WORDS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
              "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10}
_NUM_PREFIX = {"numero", "top", "dica", "motivo", "passo"}


def _norm(t: str) -> str:
    t = str(t or "").strip(" .,!?;:…\"'-").lower()
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def detect_list_markers(words: list[dict[str, Any]]) -> list[dict[str, float]]:
    """[{n, atSec}] em sequência 1..N (N>=2), ou [] quando não há lista."""
    markers: list[dict[str, float]] = []
    prev_norm = ""
    for w in words:
        text = _norm(w.get("text"))
        start = w.get("startMs")
        if not text or not isinstance(start, (int, float)):
            prev_norm = text
            continue
        expected = len(markers) + 1
        hit = text in _ORDINALS.get(expected, set())
        if not hit and prev_norm in _NUM_PREFIX and _NUM_WORDS.get(text) == expected:
            hit = True
        if hit:
            markers.append({"n": expected, "atSec": round(float(start) / 1000.0, 3)})
        prev_norm = text
    return markers if len(markers) >= 2 else []
