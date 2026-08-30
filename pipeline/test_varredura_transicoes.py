# -*- coding: utf-8 -*-
"""A varredura passou a cobrir o flash do corte.

O flash aparece em quase todo vídeo do usuário — **mediana de 8 por
vídeo** — e nunca tinha sido comparado com o template: os três grupos da
varredura zeram `transitions` para isolar o desenho, e ninguém media o que
sobrava.

Duas armadilhas tiveram de cair primeiro:

1. o grupo `transicoes` não existia;
2. o arnês não aplicava o flash. Ele é um passo À PARTE, como o `dim` — a
   primeira medida deu **tinta 0,000** e teria acusado o motor de não
   desenhar nada. Mesma armadilha do `leg.dim`, que fazia o card final
   medir 0,087.

Com as duas resolvidas: **0,629**. O começo bate (tela cheia, 1,000) e a
cauda não. Registrado no código, não consertado no chute — duas hipóteses
foram testadas e descartadas.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

VD = (REPO / "tools" / "varrer_desenho.py").read_text(encoding="utf-8")
RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")


def test_o_grupo_existe():
    assert '"transicoes"' in VD
    i = VD.index('ap.add_argument("grupo"')
    assert "transicoes" in VD[i:i + 200]


def test_as_transicoes_sobrevivem_no_grupo_delas():
    i = VD.index('if grupo != "transicoes":')
    assert 'ed["transitions"] = []' in VD[i:i + 120]


def test_o_arnes_aplica_o_flash():
    """Sem isto a medida dá 0,000 e acusa o motor de não desenhar nada."""
    i = VD.index("def _monta(")
    corpo = VD[i:VD.index("\ndef varrer(", i)]
    assert "_flash_quadro(" in corpo and "_aplicar_flash(" in corpo


def test_o_achado_fica_no_codigo_do_flash():
    """Quem for mexer no flash precisa começar pelos números, não do zero."""
    i = RP.index("def _flash_quadro(")
    antes = RP[max(0, i - 1400):i]
    assert "MEDIDO E NAO CONSERTADO" in antes
    assert "0.258" in antes and "0.000" in antes
