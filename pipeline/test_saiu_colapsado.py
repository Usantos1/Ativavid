# -*- coding: utf-8 -*-
""""O que saiu do corte" nasce fechado.

Aberto ele mostra 15+ linhas — medido numa copia isolada da tela: 553px
contra 34px fechado. Meia tela para uma lista de referencia, empurrando a
timeline e a legenda para fora ("deve vir colapsado pra nao quebrar a
timeline", 27/08).
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
JS = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_o_painel_nasce_fechado_no_proprio_html():
    """Fechado ja no HTML, nao so por JS: senao a tela abre com meia tela de
    lista e recolhe depois, na frente do usuario."""
    i = HTML.index('id="saiuPanel"')
    tag = HTML[HTML.rindex("<section", 0, i):HTML.index(">", i) + 1]
    assert "collapsed" in tag, tag
    j = HTML.index('id="saiuToggle"')
    botao = HTML[j:HTML.index(">", j)]
    assert 'aria-expanded="false"' in botao


def test_a_escolha_do_usuario_e_lembrada():
    assert "function setSaiuCollapsed(" in JS
    i = JS.index("function setSaiuCollapsed(")
    corpo = JS[i:i + 500]
    assert "ativavid-saiu-open" in corpo


def test_o_padrao_e_fechado_e_nao_aberto():
    """A leitura tem de exigir '1' para abrir — com `!== '0'` o padrao
    voltaria a ser aberto para quem nunca clicou."""
    i = JS.index("ativavid-saiu-open')")
    trecho = JS[i - 200:i + 200]
    assert "!== '1'" in trecho, trecho[:200]


def test_o_botao_usa_o_mesmo_caminho():
    i = JS.index("$('saiuToggle')?.addEventListener")
    corpo = JS[i:i + 300]
    assert "setSaiuCollapsed(" in corpo, "clique fora do caminho que lembra"


def test_a_legenda_do_post_segue_com_o_mesmo_desenho():
    """Os dois paineis vivem lado a lado; se um lembrar e o outro nao, a
    tela fica incoerente."""
    assert "function setPostCollapsed(" in JS
    assert "ativavid-post-open" in JS
