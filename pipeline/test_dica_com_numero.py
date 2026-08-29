# -*- coding: utf-8 -*-
"""Toda dica da nota diz ONDE e QUANTO — nunca só "está longo demais".

Varredura de 29/08 nos 185 vídeos entregues: a mesma frase genérica saiu
103 vezes ("a abertura está longa ou curta demais"), 74 ("tem um trecho
longo demais no meio") e 51 ("o fechamento está longo demais"). Nenhuma
dizia para que lado, de quanto, nem em que minuto.

Conselho que não dá para atender é conselho que se aprende a ignorar — e
o número já estava medido dentro da mesma função. É a mesma regra que
calou o aviso de pausa no modo "Sem cortes" e que fez o card do vídeo
dizer quantos segundos sobraram em vez de "tem pausa".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))

from video_score import score_structural  # noqa: E402


def _tips(ranges, **kw):
    d = score_structural(
        ranges=ranges, duration=float(ranges[-1]["end"]),
        transcript_ok=True, spoken="a" * 400, **kw)
    return d["tips"]


def _fala(n, ini, fim, beat="KEEP"):
    return {"beat": beat, "start": ini, "end": fim, "quote": f"fala {n} " * 4}


def test_a_dica_da_abertura_diz_o_tamanho_e_o_lado():
    longa = _tips([_fala(1, 0, 9, "HOOK"), _fala(2, 9, 13),
                   _fala(3, 13, 16, "CTA")])
    assert any("9,0s" in t and "corte antes" in t for t in longa), longa
    curta = _tips([_fala(1, 0, 0.5, "HOOK"), _fala(2, 0.5, 4),
                   _fala(3, 4, 7, "CTA")])
    assert any("0,5s" in t and "curta demais" in t for t in curta), curta


def test_a_dica_do_trecho_longo_diz_qual_e_onde():
    """Sem o minuto, achar o trecho no vídeo é procurar no olho."""
    tips = _tips([_fala(1, 0, 2, "HOOK"), _fala(2, 2, 20), _fala(3, 20, 23),
                  _fala(4, 23, 26, "CTA")])
    achou = [t for t in tips if "trecho" in t]
    assert achou, tips
    assert "18,0s" in achou[0] and re.search(r"\d+:\d\d", achou[0]), achou


def test_a_dica_do_fechamento_diz_o_tamanho():
    tips = _tips([_fala(1, 0, 2, "HOOK"), _fala(2, 2, 6),
                  _fala(3, 6, 20, "CTA")])
    assert any("14,0s" in t for t in tips), tips


def test_a_dica_da_pausa_diz_quantas():
    tips = _tips([_fala(1, 0, 2, "HOOK"), _fala(2, 2, 6),
                  _fala(3, 6, 9, "CTA")], silence_flags=3)
    assert any("3 pausas" in t for t in tips), tips


def test_nenhuma_dica_generica_sobrou():
    """As frases antigas, palavra por palavra: se alguma voltar, volta o
    conselho que não dá para atender."""
    fonte = (REPO / "helpers" / "video_score.py").read_text(encoding="utf-8")
    for velha in ('"A abertura está longa ou curta demais',
                  '"Tem um trecho longo demais no meio."',
                  '"O fechamento está longo demais."',
                  '"Vários takes sem fala clara."',
                  '"Há pausas longas que dá para enxugar."'):
        assert velha not in fonte, velha


def test_toda_dica_de_medida_carrega_numero():
    """Varre as dicas que a nota sabe emitir e cobra um número em cada uma
    que fala de tamanho, quantidade ou posição."""
    casos = [
        [_fala(1, 0, 9, "HOOK"), _fala(2, 9, 13), _fala(3, 13, 16, "CTA")],
        [_fala(1, 0, 2, "HOOK"), _fala(2, 2, 20), _fala(3, 20, 26, "CTA")],
        [_fala(1, 0, 2, "HOOK"), _fala(2, 2, 6), _fala(3, 6, 20, "CTA")],
        [_fala(1, 0, 12, "HOOK"), _fala(2, 12, 24), _fala(3, 24, 36, "CTA")],
    ]
    for rr in casos:
        for t in _tips(rr, silence_flags=2):
            if any(p in t for p in ("longo", "longa", "curta", "pausa",
                                    "takes", "trecho", "fechamento",
                                    "abertura", "Cortes")):
                assert re.search(r"\d", t), t
