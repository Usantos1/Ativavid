# -*- coding: utf-8 -*-
"""A barra do preview: uma linha só, e sem jargão de ilha de edição.

Print do usuário em 29/08: a barra quebrava em duas fileiras (o zoom caía
sozinho embaixo) e o botão de marcar dizia "IN" e depois "OUT". Ele pediu
tudo em uma linha e outro nome: "a bandeira de in e out? não quero eles,
pode ser outra coisa, mas não quero estes nomes".

Medido na própria tela: com todos os rótulos a barra pede ~1120px; a
janela dele dá ~1130. Por isso o encolhimento é medido em tempo real
(`ajustarBarraNumaLinha`) em vez de chutado por media query — quem manda
na largura é a coluna do editor, não a janela.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")


def _sem_comentarios(js: str) -> str:
    """O comentário que EXPLICA a mudança cita "IN" — ele não é rótulo."""
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", li) for li in js.splitlines())


def test_o_botao_nao_se_chama_mais_in_nem_out():
    assert ">IN<" not in HTML and ">OUT<" not in HTML
    js = _sem_comentarios(JS)
    for jargao in ("'IN'", '"IN"', "'OUT'", '"OUT"'):
        assert jargao not in js, jargao
    # e o nome novo está lá, nos dois estados do botão
    assert "'Marcar'" in js and "'Até aqui'" in js


def test_o_texto_de_ajuda_fala_a_mesma_lingua():
    i = HTML.index("<kbd>M</kbd>")
    trecho = HTML[i:i + 260]
    assert "IN" not in trecho and "OUT" not in trecho, trecho
    assert "começo" in trecho and "fim" in trecho


def test_a_barra_nao_quebra_em_duas_fileiras():
    i = CSS.index(".transport {")
    bloco = CSS[i:i + 700]
    assert "flex-wrap: nowrap" in bloco, bloco[:300]


def test_o_nome_do_botao_e_a_ultima_coisa_a_sair():
    """A 3.50 recolheu o rótulo primeiro e, na tela do usuário (125% de
    escala, coluna de ~906px), a barra virou uma fileira de símbolos. Ele
    mandou print: "coloca os nomes ali, não apenas os ícones". Medido:
    com nomes a barra pede 1118px; escondendo régua do zoom, apertando o
    texto e tirando − + , ela cabe em 830 — ainda com os nomes."""
    assert "function ajustarBarraNumaLinha" in JS
    assert "ResizeObserver" in JS
    i = JS.index("NIVEIS_DA_BARRA = [")
    escada = JS[i:JS.index("]", i)]   # ate o fim do ARRAY, nao 120 chars
    assert escada.index("sem-regua") < escada.index("apertada") <         escada.index("sem-zoom") < escada.index("so-icone"), escada
    # o rótulo só some no último degrau
    assert ".transport.so-icone .cover-btn > span:not([id])" in CSS
    for cedo in ("sem-regua", "apertada", "sem-zoom"):
        assert f".transport.{cedo} .cover-btn > span" not in CSS, cedo


def test_o_botao_de_ajustar_nao_diz_mais_fit():
    """Única palavra em inglês da barra, e ainda custava largura."""
    assert ">fit<" not in HTML
    i = HTML.index('id="btnFit"')
    assert 'aria-label="Ajustar à janela"' in HTML[i:i + 160]
    assert "$('btnFit').innerHTML = ICON.fit" in JS


def test_quem_observa_e_a_coluna_nao_a_barra():
    """Observar a própria barra realimentaria o laço: mexer na classe muda
    o tamanho dela, que chamaria o observador de novo."""
    i = JS.index("new ResizeObserver")
    trecho = JS[max(0, i - 220):i + 120]
    assert "editorCol" in trecho, trecho
