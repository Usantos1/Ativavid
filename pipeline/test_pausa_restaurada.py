# -*- coding: utf-8 -*-
"""A restauração de frase não devolve a pausa que o corte tiraria.

Três lugares do app decidem sobre a MESMA pausa e precisam concordar:

* `MIN_SILENCE_DROP` (run_fast): o corte separa trechos em pausa >= 0,40s;
* `COLA_PAUSA_S` (aqui): ao restaurar uma frase inteira, pedaços de fala
  separados por menos que isto entram juntos — com a pausa dentro;
* `_SILENCIO_MIN_S` (run_fast): a ficha ACUSA pausa sobrando >= 0,40s.

Com a cola em 0,80s eles discordavam: a restauração devolvia silêncio que
o corte tinha tirado e depois o app avisava o usuário sobre esse mesmo
silêncio. Medido no projeto C014 (a IA pediu dois blocos longos): sobravam
5 pausas somando 2,74s num corte de 40,7s.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.editing_intent import COLA_PAUSA_S, _speech_inside  # noqa: E402


def test_os_tres_limiares_de_pausa_concordam():
    from pipeline.run_fast import MIN_SILENCE_DROP, _SILENCIO_MIN_S
    assert COLA_PAUSA_S <= MIN_SILENCE_DROP, (
        "a restauração não pode colar pausa maior do que a que o corte tira")
    assert COLA_PAUSA_S <= _SILENCIO_MIN_S, (
        "o app avisaria sobre uma pausa que ele mesmo decidiu deixar")


def test_pausa_longa_separa_os_pedacos_restaurados():
    """Fala de 0 a 2s, pausa de 0,55s, fala de 2,55 a 5s."""
    regioes = [(0.0, 2.0), (2.55, 5.0)]
    pedacos = _speech_inside(0.0, 5.0, regioes)
    assert len(pedacos) == 2, pedacos
    assert abs(pedacos[0][1] - 2.0) < 1e-6
    assert abs(pedacos[1][0] - 2.55) < 1e-6


def test_respiracao_curta_continua_junta():
    """0,25s entre palavras é respiração, não pausa morta: cortar aqui
    picotaria a frase e deixaria o corte nervoso."""
    regioes = [(0.0, 2.0), (2.25, 5.0)]
    pedacos = _speech_inside(0.0, 5.0, regioes)
    assert len(pedacos) == 1, pedacos
    assert abs(pedacos[0][0]) < 1e-6 and abs(pedacos[0][1] - 5.0) < 1e-6


def test_sem_regiao_devolve_o_trecho_inteiro():
    """Sem dado de fala, preservar é mais seguro do que cortar."""
    assert _speech_inside(1.0, 3.0, []) == [(1.0, 3.0)]
    assert _speech_inside(1.0, 1.05, []) == []
