# -*- coding: utf-8 -*-
"""A ficha do card tem de ser legível nos DOIS temas.

Eu escrevi `color: var(--txt, #e8e8ea)`. O token `--txt` **não existe** — o do
projeto é `--text` — então valia sempre o fallback `#e8e8ea`, um cinza quase
branco, nos dois temas. No escuro isso dava 14,7:1 e passou despercebido; no
claro dava **1,2:1** contra o card branco (o mínimo do WCAG AA é 4,5:1) e a
ficha ficava invisível. O usuário viu antes de mim.

Medido depois do conserto, no navegador: rótulo 10:1 e valor 18,4:1 no claro;
6,5:1 e 16,4:1 no escuro.

O teste é de CSS, não de pixel: garante que a cor sai de um token que os dois
temas redefinem, em vez de um literal que só serve para um.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSS = REPO / "assets" / "studio" / "studio.css"


def _bloco(seletor: str) -> str:
    css = CSS.read_text(encoding="utf-8")
    i = css.index(seletor + " {")
    return css[i:css.index("}", i)]


def test_a_ficha_usa_tokens_do_tema_e_nao_cor_fixa():
    for seletor in (".pc-ficha dt", ".pc-ficha dd"):
        bloco = _bloco(seletor)
        cor = re.search(r"color:\s*([^;]+);", bloco)
        assert cor, f"{seletor} sem cor declarada"
        valor = cor.group(1).strip()
        assert valor.startswith("var(--"), (
            f"{seletor} usa cor fixa ({valor}) — não acompanha o tema"
        )
        assert "," not in valor, (
            f"{seletor} tem fallback ({valor}); um fallback literal vale nos "
            "DOIS temas e foi exatamente o que deixou a ficha invisível no claro"
        )


def test_os_tokens_usados_existem_nos_dois_temas():
    """`--txt` não existia: o fallback é que pintava tudo."""
    css = CSS.read_text(encoding="utf-8")
    usados = set()
    for seletor in (".pc-ficha dt", ".pc-ficha dd", ".pc-periodo"):
        usados.update(re.findall(r"var\((--[\w-]+)", _bloco(seletor)))
    assert usados, "nenhum token encontrado — a busca quebrou"

    escuro = css[css.index(":root {"):css.index("}", css.index(":root {"))]
    i_claro = css.index(':root[data-theme="light"] {')
    claro = css[i_claro:css.index("}", i_claro)]
    for token in sorted(usados):
        assert f"{token}:" in escuro, f"{token} não existe no tema escuro"
        assert f"{token}:" in claro, f"{token} não existe no tema claro"


def test_a_ficha_nao_apaga_o_texto_com_opacity():
    """`opacity` sobre um token já esmaecido derruba o contraste sem aparecer
    na cor — some do olho de quem lê o CSS."""
    for seletor in (".pc-ficha dt", ".pc-ficha dd"):
        assert "opacity" not in _bloco(seletor), (
            f"{seletor} voltou a esmaecer por opacity"
        )
