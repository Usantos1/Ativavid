# -*- coding: utf-8 -*-
"""O resto do ATIVAVID não pode saber que a revisão existe.

Dez módulos consomem o schema do Scribe (`{text, start, end, type,
speaker_id}`). A revisão troca palavras no meio dele, e o payload que sai tem
de ser indistinguível de um transcript comum — inclusive nas entradas
`spacing`, que `pack_transcripts` e `timeline_view` usam para detectar
silêncio e que um transcript sem elas perde sem quebrar nenhum teste.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.transcricao import (Palavra, Segmento, ResultadoDeTranscricao,
                             revisao, schema_scribe)


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


# Com um silêncio de propósito entre "na" e "praimcamp": é ali que a entrada
# `spacing` tem de aparecer, antes e depois da revisão.
PALAVRAS = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
            P("praimcamp", 1.30, 1.9), P("ontem", 1.9, 2.3)]
TEXTO = "eu vendi na praimcamp ontem"

PURO = ResultadoDeTranscricao(
    texto=TEXTO, idioma="por", duracao=2.3, motor="whisper-local",
    modelo="medium", backend="cuda",
    segmentos=[Segmento(TEXTO, 0.0, 2.3, palavras=tuple(PALAVRAS))],
).para_schema_scribe()


def _revisado(monkeypatch, correcoes):
    monkeypatch.setattr(revisao, "pedir_correcoes", lambda p, t: list(correcoes))
    palavras = revisao.palavras_do_schema(PURO)
    novas, meta = revisao.revisar(palavras, PURO["text"])
    assert meta["revisado"]
    return schema_scribe(novas, " ".join(p.texto for p in novas),
                         idioma=PURO["language_code"], motor=PURO["_motor"],
                         modelo=PURO["_modelo"], backend=PURO["_backend"])


def test_o_payload_puro_e_o_revisado_tem_a_mesma_forma(monkeypatch):
    rev = _revisado(monkeypatch, [{"indice": 3, "de": "praimcamp",
                                   "para": "PrimeCamp"}])
    assert set(rev) == set(PURO)
    assert [w["type"] for w in rev["words"]] == [w["type"] for w in PURO["words"]]
    assert all(w["speaker_id"] == "speaker_0" for w in rev["words"])
    assert rev["language_code"] == "por"


def test_o_spacing_do_silencio_sobrevive_a_revisao(monkeypatch):
    """A entrada que some sem quebrar teste nenhum, e leva a detecção de
    pausa junto."""
    assert [w["type"] for w in PURO["words"]].count("spacing") == 1
    rev = _revisado(monkeypatch, [{"indice": 3, "de": "praimcamp",
                                   "para": "Prime Camp"}])
    vazios = [w for w in rev["words"] if w["type"] == "spacing"]
    assert len(vazios) == 1, "perdeu o silêncio entre `na` e a marca"
    assert (vazios[0]["start"], vazios[0]["end"]) == (0.85, 1.30)


def test_a_divisao_nao_inventa_um_spacing_novo(monkeypatch):
    """`praimcamp` → `Prime Camp` reparte um intervalo contínuo. As duas
    metades se encostam, então não pode nascer silêncio entre elas."""
    rev = _revisado(monkeypatch, [{"indice": 3, "de": "praimcamp",
                                   "para": "Prime Camp"}])
    palavras = [w for w in rev["words"] if w["type"] == "word"]
    i = [w["text"] for w in palavras].index("Prime")
    assert palavras[i + 1]["text"] == "Camp"
    entre = [w for w in rev["words"]
             if w["type"] == "spacing"
             and palavras[i]["end"] <= w["start"] < palavras[i + 1]["end"]]
    assert not entre


def test_o_karaoke_nao_repara_mais_do_que_ja_reparava(monkeypatch):
    """`captions_for_remotion._word_items` conserta em silêncio: força início
    crescente e duração mínima. O que ele conserta é defeito temporal, e a
    revisão não pode acrescentar nenhum."""
    from captions_for_remotion import _word_items

    rev = _revisado(monkeypatch, [{"indice": 3, "de": "praimcamp",
                                   "para": "Prime Camp"}])
    antes = _word_items(PURO)
    depois = _word_items(rev)
    assert [round(a["start"], 6) for a in antes[:3]] == \
           [round(d["start"], 6) for d in depois[:3]]
    assert depois[0]["start"] == antes[0]["start"]
    assert depois[-1]["end"] == antes[-1]["end"]
    assert all(d["end"] > d["start"] for d in depois)
    assert all(a["start"] <= b["start"] for a, b in zip(depois, depois[1:]))


def test_palavras_do_schema_ignora_spacing_e_volta_ao_original():
    """A ida e a volta têm de fechar, senão a revisão trabalharia sobre uma
    lista que não é a que o Whisper produziu."""
    voltou = revisao.palavras_do_schema(PURO)
    assert [(p.texto, p.inicio, p.fim) for p in voltou] == \
           [(p.texto, p.inicio, p.fim) for p in PALAVRAS]
