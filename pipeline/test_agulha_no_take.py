# -*- coding: utf-8 -*-
"""Clicar em cima de um take move a agulha.

Depois de um corte os takes cobrem a faixa inteira. Como o ramo do clique
no take saia sem mexer no tempo, so restava a regua (~14px no topo) para
posicionar a agulha — e o Cortar EXIGE a agulha dentro do take: "fiz um
corte e nao consigo arrastar a agulha pra cortar mais" (27/08).
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
JS = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_clique_no_take_posiciona_a_agulha():
    i = JS.index("if (clip && S.tab === 1) {")
    corpo = JS[i:JS.index("return;", i)]
    assert "seekDraft(" in corpo, "o clique no take nao move a agulha"
    assert corpo.index("seekDraft(") < corpo.index("drag = {"), \
        "a agulha tem de ir antes de comecar o arrasto"


def test_arrastar_sobre_o_take_leva_a_agulha_junto():
    i = JS.index("} else if (drag.type === 'clip-range') {")
    corpo = JS[i:i + 600]
    assert "seekDraft(" in corpo, "arrastando, a agulha fica para tras"


def test_o_clique_simples_continua_selecionando_o_take():
    """O Cortar precisa das duas coisas: take selecionado E agulha dentro
    dele. Mover a agulha nao pode ter custado a selecao."""
    i = JS.index("if (drag && drag.type === 'clip-range') {")
    corpo = JS[i:i + 300]
    assert "S.selected = drag.i" in corpo


def test_a_conta_do_tempo_e_a_mesma_da_regua():
    """Regua e take precisam usar a MESMA formula, senao a agulha pula ao
    trocar de lugar de clique."""
    formula = "timelineEl.getBoundingClientRect()"
    i = JS.index("// background / ruler → scrub")
    assert formula in JS[i:i + 300]
    j = JS.index("if (clip && S.tab === 1) {")
    assert formula in JS[j:JS.index("return;", j)]
    assert "LABEL_W) / S.pps" in JS[j:JS.index("return;", j)]


def test_o_cortar_continua_exigindo_agulha_dentro_do_take():
    i = JS.index("function splitAtPlayhead()")
    corpo = JS[i:i + 1200]
    # A mensagem mudou na 3.76: cortar passou a valer para a imagem e o
    # emoji selecionados, então pedir "um take" seria responder sobre outra
    # coisa (o usuário tinha a imagem marcada e ouvia "selecione um take").
    assert "Selecione um take, uma imagem ou um emoji para cortar" in corpo
    assert "Posicione a agulha dentro do take" in corpo
