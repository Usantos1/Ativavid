# -*- coding: utf-8 -*-
"""As quatro cores do estilo ficam numa fileira só.

O bloco Visual era um grid de UMA coluna, então cada cartão de cor virava
uma faixa da largura inteira com duas bolinhas no canto esquerdo e o resto
vazio — quatro faixas empilhadas. Print do usuário em 29/08: "na imagem
deve ser 4 widgets na mesma linha e não um em cada linha".

Medido NA TELA, e no lugar certo: quem manda não é a coluna do editor
(~906px) e sim a grade dentro do bloco Visual, que recebe 840 — o respiro
do bloco come 66. Medir pela coluna deixava o cartão com 206px, e a
fileira quebrava em 3+1 na frente dele mesmo com o teste passando. Quatro
cartões com 12px de vão pedem 201 cada, e o cartão encolhe até isso sem
cortar nada (campo do hexadecimal e respiro mais curtos). Abaixo de 840 a
grade vira 2×2 sozinha, sem media query.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")

CORES = ("optAccent", "optEmphasisAccent", "optCaptionAccent", "optCircleAccent")


def _bloco_das_cores() -> str:
    """Do abre da grade até o primeiro grupo largo depois dela."""
    i = HTML.index('<div class="cores-grid">')
    return HTML[i:HTML.index("setup-group--wide", i)]


def test_as_quatro_cores_estao_na_mesma_grade():
    bloco = _bloco_das_cores()
    for alvo in CORES:
        assert f'id="{alvo}"' in bloco, alvo


def test_a_grade_poe_quatro_lado_a_lado():
    i = CSS.index(".cores-grid {")
    bloco = CSS[i:i + 400]
    m = re.search(r"minmax\((\d+)px", bloco)
    assert m, bloco
    largura = int(m.group(1))
    # 840, não 906: a coluna do editor tem ~906px na tela do usuário, mas o
    # bloco Visual come 66px de respiro e a grade recebe 840 — medido na
    # tela. Com o número da coluna o teste passava e a fileira quebrava em
    # 3+1 na frente dele.
    assert largura * 4 + 36 <= 840, largura
    assert "auto-fit" in bloco, bloco


def test_nao_sobrou_a_coluna_antiga():
    """`.setup-col` empilhava dois cartões por coluna — era ela que fazia a
    fileira de quatro virar duas de dois (e, no hub, quatro de um)."""
    assert "setup-col" not in HTML
    assert "setup-col" not in CSS


def test_o_traco_da_enfase_ficou_com_a_legenda():
    """Quem recebe o risco é a palavra realçada da legenda. Dentro do cartão
    da cor ele ainda deixava aquele cartão mais alto que os outros três."""
    assert 'id="optEmphStyle"' not in _bloco_das_cores()
    assert HTML.index('id="optCaptions"') < HTML.index('id="optEmphStyle"')


def test_a_nota_nao_disputa_a_linha_com_o_titulo():
    """Num cartão estreito, "aplicada" ao lado quebrava "COR DA / HEADLINE"."""
    i = CSS.index(".cores-grid .group-head")
    assert "flex-direction: column" in CSS[i:i + 200]
