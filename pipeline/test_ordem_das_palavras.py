# -*- coding: utf-8 -*-
"""A ordem da FALA manda; o timestamp com jitter não pode trocá-la.

MEDIDO nos 178 transcripts reais do usuário: 133 tinham palavra "voltando" no
tempo (746 pares, até 0,98 s). A ordem do array é a ordem da fala — é a ordem
do próprio texto transcrito; o timestamp é a parte com jitter. Quem consome
ordena por start, então a legenda saía com palavras TROCADAS: "Olha jeito!"
onde a fala diz "jeito! Olha".

O clamp existe nos DOIS lados de propósito: na escrita (transcribe.py, vídeos
novos) e na leitura (_word_items, porque os transcripts já gravados carregam a
inversão e passam por lá a cada rebuild de legenda).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def test_leitura_prende_a_ordem_do_array():
    from helpers.captions_for_remotion import _word_items

    raw = {"words": [
        {"type": "word", "text": "jeito!", "start": 2.10, "end": 2.60},
        # o jitter real: a proxima "comeca" 0,18s antes da anterior
        {"type": "word", "text": "Olha", "start": 1.92, "end": 2.30},
        {"type": "word", "text": "que", "start": 2.40, "end": 2.55},
    ]}
    ws = _word_items(raw)
    assert [w["text"] for w in ws] == ["jeito!", "Olha", "que"]
    starts = [w["start"] for w in ws]
    assert starts == sorted(starts), f"starts ainda regridem: {starts}"
    assert all(b > a for a, b in zip(starts, starts[1:])), "empate quebraria o sort"
    for w in ws:
        assert w["end"] >= w["start"] + 0.04 - 1e-9, "palavra com duracao negativa"


def test_leitura_nao_mexe_em_quem_ja_esta_em_ordem():
    from helpers.captions_for_remotion import _word_items

    raw = {"words": [
        {"type": "word", "text": "um", "start": 0.0, "end": 0.5},
        {"type": "word", "text": "dois", "start": 0.5, "end": 1.0},
    ]}
    ws = _word_items(raw)
    assert [(w["start"], w["end"]) for w in ws] == [(0.0, 0.5), (0.5, 1.0)]


def test_escrita_prende_a_ordem_nos_dois_backends():
    from helpers.transcribe import _el_to_scribe_words, _to_scribe_words

    el = _el_to_scribe_words([
        {"type": "word", "text": "jeito!", "start": 2.10, "end": 2.60},
        {"type": "word", "text": "Olha", "start": 1.92, "end": 2.30},
    ], offset=0.0)
    starts = [w["start"] for w in el if w["type"] == "word"]
    assert starts == sorted(starts) and starts[1] > starts[0]

    groq = _to_scribe_words([
        {"word": "jeito!", "start": 2.10, "end": 2.60},
        {"word": "Olha", "start": 1.92, "end": 2.30},
    ], offset=0.0)
    palavras = [w for w in groq if w["type"] == "word"]
    assert [w["text"] for w in palavras] == ["jeito!", "Olha"]
    assert palavras[1]["start"] > palavras[0]["start"]


def test_a_legenda_montada_sai_na_ordem_da_fala(tmp_path):
    """Fim a fim: transcript com jitter → legenda com o texto na ordem certa."""
    import json

    from helpers.captions_for_remotion import build_captions

    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "f.json").write_text(json.dumps({"words": [
        {"type": "word", "text": "jeito!", "start": 2.10, "end": 2.60},
        {"type": "word", "text": "Olha", "start": 1.92, "end": 2.30},
        {"type": "word", "text": "que", "start": 2.40, "end": 2.55},
    ]}), encoding="utf-8")
    edl = {"ranges": [{"source": "f", "start": 0.0, "end": 4.0}]}
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    caps = build_captions(edl, edit)
    assert [c["text"] for c in caps] == ["jeito!", "Olha", "que"], (
        "o jitter do timestamp trocou as palavras da legenda"
    )
