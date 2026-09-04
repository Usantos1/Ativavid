# -*- coding: utf-8 -*-
"""Clicar num take NAO move a agulha; arrastar um intervalo ainda move.

Historia desta regra, porque ela ja virou duas vezes:

  27/08 — clicar no take passou a mover a agulha. A regua era uma tira de
          ~14px e, depois de um corte, os takes cobriam a faixa inteira:
          "fiz um corte e nao consigo arrastar a agulha pra cortar mais".
  04/09 — ele desfez: "se eu clicar em cima de um video nao e pra mover a
          agulha... a agulha deve ser movida so na linha da minutagem".
          A regua ficou mais alta (34px) e e o unico lugar que arrasta a
          agulha; a coluna de tempo e a mesma, entao posicionar para
          cortar e um clique logo acima do take.

O ARRASTO de intervalo (clip-range) continua levando a agulha junto: ali
o gesto e deliberado, e e o que mostra onde o corte vai cair.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
JS = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_clique_no_take_nao_posiciona_a_agulha():
    i = JS.index("if (clip && S.tab === 1) {")
    corpo = JS[i:JS.index("return;", i)]
    assert "seekDraft(" not in corpo, (
        "clicar no take voltou a mover a agulha (04/09: so a minutagem move)")
    assert "drag = { type: 'clip-range'" in corpo, "o arrasto de intervalo sumiu"


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


def test_a_conta_do_tempo_e_a_mesma_no_clique_e_no_arrasto():
    """A regua (onde a agulha comeca) e o arrasto (onde ela continua)
    precisam da MESMA formula, senao a agulha pula ao comecar a arrastar."""
    formula = "timelineEl.getBoundingClientRect()"
    i = JS.index("// SO A MINUTAGEM ARRASTA A AGULHA")
    trecho = JS[i:i + 1100]   # o comentario que explica a regra e longo
    assert formula in trecho and "LABEL_W) / S.pps" in trecho
    j = JS.index("if (drag.type === 'scrub') {")
    assert formula in JS[j:j + 300] and "LABEL_W) / S.pps" in JS[j:j + 300]


def test_o_cortar_continua_exigindo_agulha_dentro_do_take():
    i = JS.index("function splitAtPlayhead()")
    corpo = JS[i:i + 1200]
    # A mensagem mudou na 3.76: cortar passou a valer para a imagem e o
    # emoji selecionados, então pedir "um take" seria responder sobre outra
    # coisa (o usuário tinha a imagem marcada e ouvia "selecione um take").
    assert "Selecione um take, uma imagem ou um emoji para cortar" in corpo
    assert "Posicione a agulha dentro do take" in corpo
