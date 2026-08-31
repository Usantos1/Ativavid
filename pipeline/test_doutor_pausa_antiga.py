# -*- coding: utf-8 -*-
"""Pausa do canário não é aviso quando o modo é `default`.

Ele perguntou em 31/08: "porque esse erro? Desenho rapido pausado ·
Motivo: TRUE_PEAK -0.9>-1.0". Não era erro nenhum.

O que os dados da máquina dele diziam naquela hora: `overlayRollout` =
**default**, `paused` = true com motivo TRUE_PEAK -0,9 e **sem `pausedAt`**
(anterior ao código que grava a data), e os últimos vídeos — 07:50 e 08:00
do mesmo dia — saindo por `renderPath: OVERLAY`, o motor rápido. Ou seja: o
diagnóstico alarmava sobre um freio que não estava freando.

A pausa só é consultada em `canary_allows_attempt`, que devolve False antes
de olhar para ela quando o modo não é `canary`. Em `default` ela é apenas
uma anotação velha.

De quebra, -0,9 dBTP hoje nem pausaria: a folga (`TRUE_PEAK_TOLERADO`,
-0,5) entrega o vídeo assim, porque dos 174 vídeos medidos 13 dos 14
excessos ficaram nessa faixa e nenhum retrabalho corrigiu nenhum.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOUTOR = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")
CANARY = (REPO / "app" / "overlay_canary.py").read_text(encoding="utf-8")
FAST = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _checagem() -> str:
    i = DOUTOR.index("def checar_motor_rapido(")
    return DOUTOR[i:DOUTOR.index("\ndef main(", i)]


def test_default_com_pausa_nao_e_aviso():
    b = _checagem()
    i = b.index('if modo == "default"')
    ate_o_proximo = b[i:b.index('if modo == "off"', i)]
    assert "diz(OK," in ate_o_proximo, "pausa em default nao pode virar AVISO"
    assert "and not pausa" not in ate_o_proximo, "era isso que deixava cair no aviso"


def test_mas_a_anotacao_continua_visivel():
    """Silenciar nao e esconder: se ha pausa anotada, ela aparece — como
    informacao, dizendo que so valeria no modo canario."""
    b = _checagem()
    i = b.index('if modo == "default"')
    bloco = b[i:b.index('if modo == "off"', i)]
    assert "pausa['motivo']" in bloco
    assert "canario" in bloco


def test_a_pausa_realmente_so_vale_no_canario():
    """Se isto mudar, o silencio acima passa a esconder coisa de verdade."""
    i = CANARY.index("def canary_allows_attempt(")
    bloco = CANARY[i:CANARY.index("\ndef begin_overlay_attempt", i)]
    assert 'if overlay_rollout() != "canary":' in bloco
    assert bloco.index('!= "canary"') < bloco.index('st.get("paused")')


def test_o_pico_de_09_cabe_na_folga():
    assert "TRUE_PEAK_TOLERADO = -0.5" in FAST
    i = FAST.index("if tp is not None and float(tp) > -0.99:")
    bloco = FAST[i:i + 500]
    assert "if float(tp) <= TRUE_PEAK_TOLERADO:" in bloco
    assert "entregue assim" in bloco
