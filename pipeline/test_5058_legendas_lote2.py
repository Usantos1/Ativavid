# -*- coding: utf-8 -*-
"""5.0.58: mais seis legendas (lote 2 das 50 rodadas).

Dois efeitos de letra novos — `duplo` (contorno preto grosso por fora e um
fino na cor da marca por dentro, o "double stroke" do CapCut) e
`sombradura` (sombra dura deslocada, sem borrão, o hard shadow de cartaz) —
e quatro variantes de fonte reaproveitando modos que já existem: `retro`
(Righteous + degradê), `minimal` (Inter 500, sem efeito), `grosso`
(Archivo Black + sticker) e `alerta` (Bangers + pílula).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.caption_styles import NOMES, USAM_COR_DA_ENFASE  # noqa: E402
from app.render_proprio import Renderizador  # noqa: E402

EFEITOS = ("duplo", "sombradura")
VARIANTES = {"retro": "degrade", "minimal": "", "grosso": "sticker", "alerta": "pilula"}
TODAS = EFEITOS + tuple(VARIANTES)
TSX = (REPO / "assets" / "shortform" / "src" / "SimpleCaptions.tsx").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")


def test_catalogo_e_enfase():
    for e in TODAS:
        assert e in NOMES, e
    for e in ("duplo", "retro", "alerta"):
        assert e in USAM_COR_DA_ENFASE, f"`{e}` pinta com a cor da marca"
    for e in ("sombradura", "minimal", "grosso"):
        assert e not in USAM_COR_DA_ENFASE, e


def test_motor_proprio_conhece_as_seis():
    for e in TODAS:
        assert e in Renderizador.SIMPLE_VARIANTES and e in Renderizador.SIMPLE_PESO, e
    for e, modo in VARIANTES.items():
        assert Renderizador.SIMPLE_VARIANTES[e][10] == modo, e
    for e in EFEITOS:
        assert Renderizador.SIMPLE_VARIANTES[e][10] == e
    # `retro` sobe a caixa pelo MODO dele (`degrade`), nao pelo id: a
    # lista e testada contra `modo`. O id estava la e nao fazia nada.
    assert Renderizador.SIMPLE_VARIANTES["retro"][10] in Renderizador.SIMPLE_MAIUSCULA
    assert "duplo" in Renderizador.SIMPLE_SUPERFICIE
    assert "sombradura" not in Renderizador.SIMPLE_SUPERFICIE, "a sombra dura e preta fixa"


def test_template_desenha_e_carrega_as_fontes():
    for e in EFEITOS:
        assert f"V.modo === '{e}'" in TSX, e
        assert f"'{e}'" in MAIN, "fora do tipo — o tsc reprova o job"
    for e in TODAS:
        assert f"  {e}: {{" in TSX, e
    for fam in ("Righteous", "ArchivoBlack"):
        assert f"@remotion/google-fonts/{fam}" in TSX, fam
    assert "sticker: true" in TSX.split("grosso: {", 1)[1][:260]
    assert "modo: 'pilula'" in TSX.split("alerta: {", 1)[1][:260]


def test_a_ordem_dos_contornos_no_duplo():
    """A PRIMEIRA sombra da lista fica por cima: o fino colorido antes do
    grosso preto, senao o preto cobre a cor da marca."""
    i = TSX.index("if (V.modo === 'duplo')")
    corpo = TSX[i:i + 900]
    assert "contornoCss(R2, g), ...contornoCss(R1, '#0b0d10')" in corpo
    assert "R1 = Math.max(5" in corpo and "R2 = Math.max(3" in corpo
    j = PROPRIO.index('if modo == "duplo":')
    py = PROPRIO[j:j + 1200]
    assert "rgb * (1 - meio[..., None]) + cor_m * meio[..., None]" in py
    assert py.index("meio[..., None]") < py.index("pad_m[..., None]"), (
        "a letra branca entra por ultimo, por cima dos dois contornos")


def test_mesma_conta_nos_tres_motores():
    for frac in ("0.085", "0.050", "0.055"):
        assert f"tam * {frac}" in PROPRIO, frac
        assert f"V.size * {frac}" in TSX, frac
        assert f"V.size * {frac} * s" in PJS, frac


def test_editor_e_hub():
    for e in TODAS:
        assert f"id: '{e}', name:" in PJS, e
        assert f'{e}: "' in SJS.split("legenda: {", 1)[1][:1800], e
    for e in EFEITOS:
        assert f"V.modo === '{e}'" in PJS, e
    # o editor tambem decide a caixa alta pelo MODO (`CAP_MAIUSCULA.has(V.modo)`),
    # entao quem sobe a caixa do `retro` e o `degrade` dele
    assert "'degrade'" in PJS.split("const CAP_MAIUSCULA", 1)[1][:220]
    assert "modo: 'degrade'" in PJS.split("  retro: {", 1)[1][:220]


def test_nomes_batem_com_o_catalogo():
    tela = SJS.split("legenda: {", 1)[1]
    tela = tela[:tela.index("},")]
    for e in TODAS:
        assert f'{e}: "{NOMES[e]}"' in tela, f"{e}: nome divergente da tela"
