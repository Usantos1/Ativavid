# -*- coding: utf-8 -*-
"""5.0.38: mais duas legendas de fundo colorido — Fita dupla e Etiqueta recortada.

Pedido de 04/09 ("fita dupla, etiqueta com canto recortado"). As duas são
variações das que já existem: a fita degradê ganha uma segunda fita escura
por baixo (o `box-shadow: 0 10px 0` do template); a etiqueta ganha o canto
superior direito cortado (`clip-path`, com a sombra no elemento de fora —
o clip cortaria o box-shadow junto).

A regra dos três motores continua: catálogo, variante, superfície,
maiúscula e altura de linha têm de bater nos três lugares.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.caption_styles import NOMES, USAM_COR_DA_ENFASE  # noqa: E402
from app.render_proprio import Renderizador  # noqa: E402

NOVAS = ("fitadupla", "etiquetacanto")
TSX = (REPO / "assets" / "shortform" / "src" / "SimpleCaptions.tsx").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_estao_no_catalogo_e_pintam_pela_enfase():
    for e in NOVAS:
        assert e in NOMES
        assert e in USAM_COR_DA_ENFASE, f"`{e}` pinta uma superfície: a cor é a da ênfase"


def test_o_motor_proprio_conhece_as_duas():
    for e in NOVAS:
        assert e in Renderizador.SIMPLE_VARIANTES
        assert e in Renderizador.SIMPLE_PAINEL and e in Renderizador.SIMPLE_SUPERFICIE
        assert e in Renderizador.SIMPLE_PESO
    assert "fitadupla" in Renderizador.SIMPLE_MAIUSCULA
    assert "etiquetacanto" not in Renderizador.SIMPLE_MAIUSCULA


def test_o_template_desenha_e_aceita_no_tipo():
    for e in NOVAS:
        assert f"V.modo === '{e}'" in TSX, f"o template não desenha `{e}`"
        assert f"  {e}: {{" in TSX, f"`{e}` sem variante no template"
        assert f"'{e}'" in MAIN, "fora do tipo — o tsc reprova o job"
    assert "clipPath: `polygon(0 0, calc(100% - ${canto}px) 0" in TSX
    assert "filter: 'drop-shadow(0 16px 36px" in TSX, (
        "sem o drop-shadow no elemento de fora, o clip-path corta a sombra")


def test_a_geometria_bate_nos_tres_motores():
    for e, (tam, maxw, linhas) in {"fitadupla": (62, 760, 1), "etiquetacanto": (52, 780, 2)}.items():
        v = Renderizador.SIMPLE_VARIANTES[e]
        assert (v[2], v[9], v[4]) == (tam, maxw, linhas), e
        assert f"size: {tam}, maxWords" in TSX.split(f"  {e}: {{", 1)[1][:200]
        assert f"size: {tam}, maxWords" in PJS.split(f"  {e}: {{", 1)[1][:200]


def test_o_editor_lista_desenha_e_o_hub_nomeia():
    for e, nome in (("fitadupla", "Fita dupla"), ("etiquetacanto", "Etiqueta recortada")):
        assert f"id: '{e}', name: '{nome}'" in PJS
        assert f"V.modo === '{e}'" in PJS
        assert f'{e}: "{nome}"' in SJS
    i = PJS.index("const CAP_EMPH_STYLES = [")
    assert all(f"'{e}'" in PJS[i:i + 400] for e in NOVAS)


def test_a_segunda_fita_fica_por_baixo():
    src = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = src.index('if modo == "fitadupla":')
    corpo = src[i:i + 900]
    assert "so_baixo = np.clip(a_baixo - a_cheio" in corpo, (
        "a fita escura passaria por cima da principal")
    assert "FITA_DUPLA_DY" in corpo and "FITA_DUPLA_ESCURO" in corpo
