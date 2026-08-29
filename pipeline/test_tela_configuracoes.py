# -*- coding: utf-8 -*-
"""A grade de Configurações fica alinhada.

O usuário reclamou (29/08): "cards jogados fora de medidas e padrões". Era
verdade e tinha três causas somadas — cards da mesma linha terminando em
alturas diferentes, a última linha com cards do dobro da largura dos de
cima, e a barra "Avançado" atravessando a tela enquanto a grade parava
700px antes.
"""
from __future__ import annotations

from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "assets" / "studio"
       / "studio.css").read_text(encoding="utf-8")


def _bloco(seletor: str) -> str:
    """O bloco SEM comentarios — eles citam o que foi descartado (o texto
    explica por que `auto-fit` saiu) e o teste leria isso como codigo."""
    import re
    i = CSS.index(seletor)
    corpo = CSS[i:CSS.index("}", i)]
    return re.sub(r"/\*.*?\*/", " ", corpo, flags=re.S)


def test_a_ultima_linha_nao_estica_os_cards():
    """`auto-fit` colapsa a coluna vazia e estica quem sobrou."""
    b = _bloco(".sys-grid,")
    assert "repeat(auto-fill" in b, b
    assert "auto-fit" not in b, b


def test_cards_da_mesma_linha_tem_a_mesma_altura():
    b = _bloco(".sys-grid,")
    assert "align-items: stretch" in b, b


def test_a_acao_desce_para_o_rodape_do_card():
    """É o que alinha os botões de cards com textos de tamanhos diferentes."""
    b = _bloco(".sys-card .panel-actions:last-of-type,")
    assert "margin-top: auto" in b, b


def test_a_coluna_inteira_tem_a_mesma_largura():
    """Grade e barra "Avançado" precisam terminar na mesma linha."""
    b = _bloco(".sys-shell,")
    assert "max-width: 1160px" in b, b
    assert "max-width" not in _bloco(".sys-grid,"), "dois tetos discordando"


def test_card_de_uma_frase_nao_nasce_achatado():
    b = _bloco(".sys-card,")
    assert "min-height" in b, b
