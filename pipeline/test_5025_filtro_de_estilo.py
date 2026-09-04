# -*- coding: utf-8 -*-
"""5.0.25: filtro nas listas de estilo.

Depois de 04/09 a tela tem 19 cartões de manchete e 23 de legenda. A lista
deixou de ser uma vitrine e virou uma busca — e sem filtro o caminho para
achar de novo o estilo que ele gostou é rolar tudo.

O filtro nasce DENTRO do grid (o host é limpo a cada pintura, então não
duplica) e só aparece nos grupos grandes.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")


def _radios():
    i = JS.index("  const radios = (host, group, chosen) => {")
    return JS[i:JS.index("\n  };", i)]


def test_o_filtro_so_aparece_onde_a_lista_e_grande():
    c = _radios()
    assert "if (opts.length > 12)" in c, (
        "o filtro apareceria em grupo de 4 cartões, onde só atrapalha")


def test_o_filtro_nasce_dentro_do_grid():
    """Fora do host ele seria recriado a cada pintura e duplicaria."""
    c = _radios()
    i = c.index("filtro = el('input', 'opt-filtro', host)")
    assert i > c.index("host.innerHTML = ''"), (
        "o filtro é criado antes da limpeza e some na primeira pintura")


def test_o_que_ele_digitou_sobrevive_a_repintura():
    c = _radios()
    assert "FILTRO_DE_ESTILO[group]" in c, "perder o filtro no meio da busca"
    assert "const FILTRO_DE_ESTILO = {}" in JS, "o estado do filtro não existe"


def test_o_filtro_casa_pelo_nome_do_cartao():
    c = _radios()
    assert "querySelector('.opt-name')" in c
    assert "nome.toLowerCase().includes(q)" in c


def test_lista_vazia_avisa_em_vez_de_ficar_em_branco():
    assert "Nenhum estilo com esse nome." in JS
    assert ".opt-filtro-vazio" in CSS


def test_o_filtro_ocupa_a_linha_inteira_do_grid():
    i = CSS.index(".opt-filtro {")
    assert "grid-column: 1 / -1" in CSS[i:i + 260], (
        "o filtro entraria como mais um cartão no meio dos estilos")
