# -*- coding: utf-8 -*-
"""A ferramenta de seleção (laço) na linha do tempo.

"quero um ponteiro de mouse pra poder selecionar varias legendas, takes ou
qualquer coisa da timeline pra apagar se eu quiser, ou selecionar pra
arrastar se quiser" (30/08).

Provado no navegador com a linha do tempo montada: um retângulo marcou
2 takes + 2 legendas + 1 bloco de uma vez; Delete apagou os cinco e **um
único** Ctrl+Z devolveu tudo; arrastar um bloco marcado moveu 2,00s
(80px ÷ 40pps) preservando a duração.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")


def test_as_duas_ferramentas_existem():
    assert 'id="btnLaco"' in HTML and 'id="lacoBox"' in HTML
    assert "ferramenta: 'agulha'," in JS      # a agulha continua o padrão
    assert "function trocarFerramenta(" in JS


def test_o_laco_marca_as_tres_especies():
    """A seleção é de take, legenda e bloco ao mesmo tempo, porque é assim
    que o usuário vê a linha: uma coisa só."""
    i = JS.index("function marcarPeloRetangulo(")
    bloco = JS[i:i + 1400]
    assert "S.takeSel.push(i)" in bloco
    assert "S.capSel.push(i)" in bloco
    assert "S.blocosSel.push(i)" in bloco


def test_marca_por_intersecao_e_nao_por_conter():
    """Num zoom fechado um take ocupa mais que a tela: exigir envolvê-lo
    inteiro tornaria o laço inútil justamente onde ele mais serve."""
    i = JS.index("const bate = (el) => {")
    bloco = JS[i:i + 300]
    assert "b.right < r.left || b.left > r.right" in bloco
    assert "b.bottom < r.top || b.top > r.bottom" in bloco


def test_apagar_e_um_gesto_so_no_historico():
    """O Ctrl+Z tem de desfazer o gesto inteiro, não um terço dele."""
    i = JS.index("function apagarSelecaoMultipla(")
    bloco = JS[i:i + 1100]
    assert bloco.count("pushHistory()") == 1
    assert "apagarLegendas(S.capSel, true)" in bloco     # sem histórico próprio
    assert "function apagarLegendas(indices, semHistorico = false)" in JS
    assert "if (!semHistorico) pushHistory();" in JS


def test_so_move_o_que_tem_tempo_proprio():
    """Take é uma SEQUÊNCIA (não flutua sem empurrar os outros) e legenda
    segue a FALA (deslocá-la é dessincronizá-la da boca)."""
    i = JS.index("function moverSelecaoNoTempo(")
    bloco = JS[i:JS.index("\n}", i)]
    assert "S.blocosSel" in bloco
    assert "S.draft[" not in bloco and "S.captions[" not in bloco
    # e o arrasto do conjunto só começa quando há bloco marcado
    assert "if (iDentro && S.blocosSel.length) {" in JS


def test_a_tecla_v_troca_a_ferramenta():
    i = JS.index("(e.key === 'v' || e.key === 'V')")
    assert "trocarFerramenta(" in JS[i:i + 220]


def test_o_delete_do_laco_vem_antes_dos_outros():
    """Com o laço marcado, o Delete não pode cair no ramo de um take só."""
    i = JS.index("(S.takeSel.length || S.blocosSel.length)")
    j = JS.index("&& S.blocoSel >= 0) {", i)
    assert j > i, "o ramo do laço tem de vir antes do ramo de um bloco só"
    assert "apagarSelecaoMultipla();" in JS[i:j]


def test_a_bandeira_e_o_marcador_do_capcut():
    """A bandeirinha de mastro não é o desenho que o usuário reconhece."""
    i = JS.index("  flag: '<svg")
    icone = JS[i:JS.index("\n", i)]
    assert "M4.4 1.8h7.2" in icone and "L8 11.3" in icone   # fita com entalhe
    assert "<rect" not in icone                              # sem mastro


def test_o_cursor_diz_qual_ferramenta_esta_ligada():
    """Sem isso o mesmo arrasto faria duas coisas diferentes sem aviso."""
    assert ".timeline-panel.modo-laco { cursor: crosshair; }" in CSS
    assert ".laco-box {" in CSS and ".clip.laco-sel {" in CSS
    assert ".btn.icon.ativo {" in CSS
