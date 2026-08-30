# -*- coding: utf-8 -*-
"""A legenda `impacto` tem DUAS sombras, e as duas pedem sigma = raio/2.

A da caixa da palavra quente (`box-shadow: 0 10px 26px`) e a do texto das
palavras brancas (`text-shadow: 0 4px 18px`). Só a primeira tinha sido
olhada — e por isso a divergência mudava de projeto para projeto: o halo a
mais das palavras brancas cresce com o NÚMERO delas.

    só a caixa em raio/4:  0,846 e 1,062
    só a caixa em raio/2:  1,032 e 1,174
    as duas  em raio/2:    **1,020 e 1,020**

Dois projetos, o mesmo número. Foi o que fechou o caso.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")


def test_a_sombra_da_caixa_usa_raio_por_dois():
    assert "GaussianBlur(26 * 0.5)" in RP


def test_a_sombra_do_texto_tambem():
    i = RP.index("especs=[(0, 4, 18, 0.6)]")
    assert "k_sombra=0.5" in RP[i:i + 80]


def test_o_padrao_compartilhado_nao_mudou():
    """`_palavra_texto` serve karaoke e stacked, que nasceram com o sigma de
    drop-shadow e medem saudaveis — mexer no padrao mudaria os dois."""
    i = RP.index("def _palavra_texto(")
    assert "k_sombra: float = BLUR_K" in RP[i:i + 400]


def test_a_medicao_dos_dois_projetos_fica_registrada():
    i = RP.index("GaussianBlur(26 * 0.5)")
    antes = RP[max(0, i - 2000):i]
    assert "1,020 e 1,020" in antes
    assert "SAO DUAS SOMBRAS" in antes
