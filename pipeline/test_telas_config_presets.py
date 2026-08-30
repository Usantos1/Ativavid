# -*- coding: utf-8 -*-
"""Configurações e Presets — as duas telas de 30/08.

DIAGNÓSTICO: "quero que deixa expandido o resultado da checagem em cards
profissionais e apenas um botão de checar novamente, a gente tem muito
espaco ali em uma tela full hd que pode ser usado... auto ajustar a todas
as telas."

Medido no navegador: em 1920px a coluna passou de 1160px para 1590px e os
cards do topo de 3 para 4 por linha; o Diagnóstico ocupa a linha inteira e
mostra 4-5 itens por linha, 1 por linha em 560px, sem barra lateral em
nenhuma das larguras.

PRESETS: "qual a finalidade desta tela? se nao da pra criar outros? nao e a
mesma coisa que marca?" — a tela não respondia nada disso.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")


def test_a_checagem_roda_ao_abrir_a_tela():
    """O card mostrava duas ações e nenhum resultado. Quem chega ali quer
    saber se está tudo bem, não apertar um botão para descobrir."""
    i = JS.index('if (name === "sistema") {')
    bloco = JS[i:i + 420]
    assert "runDoutor()" in bloco


def test_um_botao_so_e_o_copiar_e_discreto():
    i = HTML.index('id="doutorCard"')
    bloco = HTML[i:i + 900]
    assert "Checar novamente" in bloco
    assert "Rodar checagem" not in bloco
    # o copiar continua existindo (o suporte pede), mas nasce escondido e
    # só aparece quando há relatório
    assert 'id="btnDoutorCopy"' in bloco and "hidden" in bloco
    assert 'ghost-btn--sm doutor-copy' in bloco


def test_o_resultado_nasce_aberto_e_com_veredito():
    i = JS.index("async function runDoutor()")
    bloco = JS[i:i + 2600]
    assert 'class="doutor-item' in bloco
    assert "doutor-dot" in bloco and "doutor-tag" in bloco
    # o resumo diz o veredito em uma linha, e o que IMPEDE vem primeiro
    assert "conta.bloqueio" in bloco
    assert bloco.index("conta.bloqueio\n") < bloco.index("conta.aviso\n") \
        or bloco.index("impedem o funcionamento") < bloco.index("merecem atenção")


def test_a_tela_usa_a_largura_do_monitor():
    """Em 1920px sobravam ~490px de tela vazia à direita."""
    i = CSS.index(".sys-shell,")
    bloco = CSS[i:CSS.index("\n}", i)]
    assert "max-width: 1160px" not in bloco, "o teto voltou"
    assert ".sys-card--wide { grid-column: 1 / -1; }" in CSS
    # e os itens se acomodam sozinhos, sem media query
    i = CSS.index(chr(10) + ".doutor {")   # a regra propria, nao uma descendente
    bloco = CSS[i:CSS.index("}", i)]
    assert "auto-fill" in bloco and "minmax(min(100%, 260px), 1fr)" in bloco


def test_a_tela_de_presets_diz_o_que_e_um_preset():
    """"nao e a mesma coisa que marca?" — a tela não respondia isso."""
    i = HTML.index('id="view-presets"')
    bloco = HTML[i:i + 1600]
    assert "Preset é um jeito de cortar" in bloco
    assert "<strong>Marca</strong> é quem" in bloco
    assert "uma marca tem vários presets" in bloco
    assert "Criar preset novo" in bloco


def test_cada_preset_mostra_o_que_ele_decide():
    """A linha mostrava só um rótulo solto ("viral"): não dava para saber o
    que muda de um preset para o outro sem abrir os dois."""
    i = JS.index("// O que este preset DECIDE")
    bloco = JS[i:i + 1200]
    for rot in ('chip("layout", st.edit)', 'chip("legenda", st.captions)',
                'chip("manchete", st.headline)', 'chip("ritmo", st.rhythm)'):
        assert rot in bloco, rot
    assert 'cor("cor", st.accent)' in bloco
    # a cor entra como amostra, não como texto solto
    assert 'class="preset-cor"' in bloco
    assert ".preset-chips {" in CSS and ".preset-cor {" in CSS


def test_o_texto_diz_como_criar_outro():
    """Ele perguntou "se nao da pra criar outros?" — dava, por Duplicar."""
    i = JS.index("preset(s) da marca ${marca}")
    assert "Duplicar" in JS[i:i + 260]
