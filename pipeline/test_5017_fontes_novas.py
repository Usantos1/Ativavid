# -*- coding: utf-8 -*-
"""5.0.17: onze fontes novas — o catalogo tem de bater em TODOS os lugares.

Ele (04/09): "adicionar mais fontes". Uma fonte que existe num lugar e
nao no outro e o defeito classico daqui (a lista vivia repetida em
quatro lugares — ver caption_styles.py).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "pipeline"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app import render_proprio as rp  # noqa: E402
import run_fast as rf  # noqa: E402

PHTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
FTS = (REPO / "assets" / "shortform" / "src" / "fonts.ts").read_text(encoding="utf-8")

NOVAS = ["oswald", "robotocond", "nunito", "rubik", "spartan", "kanit", "barlow",
         "bangers", "righteous", "titan", "luckiest"]


def test_toda_fonte_do_catalogo_tem_arquivo_no_motor_proprio():
    for fid in NOVAS:
        assert fid in rp.MARCA_FONTES, fid
        arq, teto = rp.MARCA_FONTES[fid]
        assert (rp.FONTES / arq).is_file(), f"{fid}: {arq} nao esta em assets/fonts-render"
        assert teto in (None, 400, 700, 900), (fid, teto)
    assert set(NOVAS) <= rf._FONT_IDS, "o run_fast descartaria o id como desconhecido"


def test_o_motor_proprio_abre_cada_fonte_com_o_peso_pedido():
    from PIL import ImageFont
    for fid in NOVAS:
        arq, teto = rp.MARCA_FONTES[fid]
        f = ImageFont.truetype(str(rp.FONTES / arq), 40)
        assert f.getname()[0], fid
        if "[" in arq:  # variavel: o eixo de peso existe e aceita o teto/900
            f.set_variation_by_axes([teto or 900])


def test_a_tela_e_o_template_conhecem_as_mesmas_fontes():
    for fid in NOVAS:
        assert PHTML.count(f'<option value="{fid}">') == 2, f"{fid}: precisa estar nos dois menus (legenda e headline)"
        assert re.search(rf"\n    {fid}: \"'[^\"]+\"", PJS), f"{fid}: sem FONT_CSS no preview"
        assert f"case '{fid}':" in FTS, f"{fid}: sem loader em fonts.ts"
    assert "family=Oswald:wght@400;600;700" in PHTML and "family=Luckiest+Guy" in PHTML, "o preview carrega a fonte do Google para mostrar"


def test_o_fator_de_altura_vale_nos_dois_lados():
    esperado = {"oswald": 0.877, "bangers": 0.947, "kanit": 1.092, "spartan": 1.076}
    for fid, fa in esperado.items():
        assert rf._FATOR_ALTURA_CATALOGO.get(fid) == fa, fid
        assert f"{fid}: {fa}" in PJS, f"{fid}: preview com fator diferente do render"
    for fid in ("robotocond", "nunito", "rubik", "titan", "righteous", "barlow", "luckiest"):
        assert fid not in rf._FATOR_ALTURA_CATALOGO, f"{fid} esta dentro de 4% da Poppins"
