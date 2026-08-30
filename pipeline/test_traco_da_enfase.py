# -*- coding: utf-8 -*-
"""O seletor "Traço da ênfase" precisa ter ouvinte.

Erro real no console da tela de Estilos:

    Uncaught TypeError: Cannot read properties of null
    (reading 'emphasisStyle') — app.js:3277

`wireEmphStyle` roda no `DOMContentLoaded`, quando `S.style` ainda não
existe. A ordem das linhas transformava um erro de tempo em defeito
permanente: marcava `wired = '1'`, estourava na linha seguinte, e o
`setTimeout(…, 800)` que existe para a segunda tentativa encontrava
`wired` e desistia. O seletor ficava vivo na tela e morto por dentro —
trocar entre "círculo" e "marca-texto" não mudava nada, calado.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def _corpo() -> str:
    i = APP.index("function wireEmphStyle() {")
    return APP[i:APP.index("\n}", i)]


def test_nao_marca_ligado_antes_de_poder_ligar():
    corpo = _corpo()
    guarda = corpo.index("if (!el ||")
    marca = corpo.index("el.dataset.wired = '1';")
    assert guarda < marca, "marca `wired` antes da guarda"
    assert "!S.style" in corpo[guarda:marca], "não confere se o estado chegou"


def test_o_estado_religa_o_seletor():
    """Estado que demora mais de 800ms nunca ligaria o seletor."""
    i = APP.index("$('setupNote').value = S.style.note")
    assert "wireEmphStyle();" in APP[i - 400:i]


def test_a_segunda_tentativa_continua_existindo():
    assert re.search(r"setTimeout\(wireEmphStyle,\s*\d+\)", APP)


def test_o_ouvinte_e_o_ponto():
    corpo = _corpo()
    assert "addEventListener('change'" in corpo
    assert "S.style.emphasisStyle" in corpo
