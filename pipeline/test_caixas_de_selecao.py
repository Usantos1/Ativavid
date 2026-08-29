# -*- coding: utf-8 -*-
"""As caixas de seleção seguem o tema escuro e têm a mesma cara.

A lista que abre num `<select>` é desenhada pelo SISTEMA, não pelo CSS:
sem `color-scheme` ela abre BRANCA sobre o app escuro (print do usuário em
29/08, na tela de Marca). E havia quatro estilos diferentes espalhados
pelas telas — alturas, bordas e setas que não batiam entre si.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "assets" / "studio"
       / "studio.css").read_text(encoding="utf-8")


def _bloco(seletor: str) -> str:
    i = CSS.index(seletor)
    corpo = CSS[i:CSS.index("}", i)]
    return re.sub(r"/\*.*?\*/", " ", corpo, flags=re.S)


def test_o_tema_declara_o_esquema_de_cor():
    """É isso que faz o Windows desenhar a lista do select escura."""
    assert "color-scheme: dark" in _bloco(":root {")
    assert "color-scheme: light" in _bloco(':root[data-theme="light"] {')


def test_um_lugar_so_decide_o_esquema():
    """Duas declarações acabam discordando: a de Marca ficava dizendo
    `dark` mesmo com o app no tema claro."""
    assert CSS.count("color-scheme: dark") == 1, CSS.count("color-scheme: dark")


def test_toda_caixa_tem_a_mesma_cara():
    b = _bloco("\nselect {")
    for regra in ("appearance: none", "border-radius: 10px",
                  "background-image: url", "background-position"):
        assert regra in b, (regra, b)


def test_nenhuma_regra_de_select_apaga_a_seta():
    """`background:` (atalho) zera o background-image — a seta some.
    Aconteceu em Marca, Importar e Chaves de uma vez."""
    for i, linha in enumerate(CSS.splitlines(), 1):
        if re.match(r"\s*background:\s*var\(", linha):
            trecho = "\n".join(CSS.splitlines()[max(0, i - 8):i])
            assert "select" not in trecho, f"linha {i}: {linha.strip()}"
