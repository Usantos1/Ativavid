# -*- coding: utf-8 -*-
"""O carimbo e a fita giram para o lado do template.

Medido no par de quadros do `carimbo` (Remotion × motor próprio), pela
altura média do vermelho nas duas pontas da moldura:

    Remotion       y_esq=200  y_dir=166   SOBE para a direita  (−34px)
    motor próprio  y_esq=163  y_dir=197   DESCE para a direita (+35px)

Mesma magnitude, sinal trocado. O CSS diz `rotate(-6deg)` e o código
passava `-6.0` direto ao `Image.rotate` do Pillow — e **as duas convenções
são opostas**: no CSS o ângulo positivo gira no sentido horário; no
Pillow, no anti-horário.

A razão de TINTA não via nada (1,057, dentro da faixa): área igual, forma
espelhada. Quem gritou foi a diferença média de alfa — 107 de 255, a maior
de todo o catálogo. Depois da correção: `fita` 43,5 → **2,1**; `carimbo`
107,4 → 59,8 (sobra um deslocamento, medido e não perseguido).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(
    encoding="utf-8")


def test_o_giro_e_invertido_antes_de_ir_para_o_pillow():
    assert RP.count("_giro = -float(rot)") == 2, "um dos dois blocos ficou"
    # e ninguém mais chama rotate com o valor cru do parâmetro
    assert ".rotate(rot," not in RP


def test_os_dois_blocos_giram_pelo_valor_convertido():
    assert RP.count(".rotate(_giro,") == 4


def test_o_valor_continua_igual_ao_do_template():
    """Quem compara os dois arquivos tem de ler a mesma coisa."""
    assert "rotate(-6deg)" in TSX and "rot=-6.0" in RP
    assert "i === 0 ? -2.4 : 1.8" in TSX
    assert "rot=(-2.4 if i == 0 else 1.8)" in RP


def test_pillow_gira_ao_contrario_do_css():
    """A premissa da correção, verificada no próprio Pillow: um ângulo
    positivo sobe o lado direito (anti-horário)."""
    import numpy as np
    from PIL import Image

    a = np.zeros((60, 200), dtype=np.uint8)
    a[28:32, :] = 255                       # risco horizontal no meio
    g = np.asarray(Image.fromarray(a, "L").rotate(10, expand=False))
    ys, xs = np.nonzero(g > 40)
    y_esq = ys[xs < 40].mean()
    y_dir = ys[xs > 160].mean()
    assert y_dir < y_esq, "Pillow positivo deveria subir a direita"
