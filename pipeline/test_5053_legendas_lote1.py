# -*- coding: utf-8 -*-
"""5.0.53: oito legendas novas (lote 1 das 50 rodadas).

Quatro efeitos de letra (contorno, sombra3d, beast, sublinhado) e quatro
com fontes display reaproveitando modos que ja existem (gigante->traco,
quadrinhos->sticker, divertida->degrade, condensada->bloco). A regra dos
tres motores continua: catalogo, variante, superficie, maiuscula e altura
de linha tem de bater no template, no motor rapido e no editor.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.caption_styles import NOMES, USAM_COR_DA_ENFASE  # noqa: E402
from app.render_proprio import Renderizador  # noqa: E402

EFEITOS = ("contorno", "sombra3d", "beast", "sublinhado")
FONTES = {"gigante": "traco", "quadrinhos": "sticker", "divertida": "degrade", "condensada": "bloco"}
TODAS = EFEITOS + tuple(FONTES)
TSX = (REPO / "assets" / "shortform" / "src" / "SimpleCaptions.tsx").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_catalogo_e_enfase():
    for e in TODAS:
        assert e in NOMES, e
    for e in ("contorno", "sombra3d", "sublinhado", "divertida"):
        assert e in USAM_COR_DA_ENFASE, f"`{e}` pinta uma superficie: a cor e a da enfase"
    for e in ("beast", "gigante", "quadrinhos", "condensada"):
        assert e not in USAM_COR_DA_ENFASE, e


def test_motor_proprio_conhece_as_oito():
    for e in TODAS:
        assert e in Renderizador.SIMPLE_VARIANTES and e in Renderizador.SIMPLE_PESO, e
    for e, modo in FONTES.items():
        assert Renderizador.SIMPLE_VARIANTES[e][10] == modo, e
    for e in EFEITOS:
        assert Renderizador.SIMPLE_VARIANTES[e][10] == e
    assert "beast" in Renderizador.SIMPLE_MAIUSCULA
    for e in ("contorno", "sombra3d", "sublinhado"):
        assert e in Renderizador.SIMPLE_SUPERFICIE
    assert "beast" not in Renderizador.SIMPLE_SUPERFICIE, "o amarelo do beast e fixo"
    assert Renderizador.SIMPLE_PESO["beast"] == 900 and Renderizador.SIMPLE_PESO["gigante"] == 400


def test_template_desenha_e_aceita_no_tipo():
    for e in EFEITOS:
        assert f"V.modo === '{e}'" in TSX, f"o template nao desenha `{e}`"
        assert f"'{e}'" in MAIN, "fora do tipo — o tsc reprova o job"
    for e in TODAS:
        assert f"  {e}: {{" in TSX, f"`{e}` sem variante no template"
    assert "quadrinhos: {" in TSX and "sticker: true" in TSX.split("quadrinhos: {", 1)[1][:260]
    assert "block: true" in TSX.split("condensada: {", 1)[1][:260]
    for fam in ("BebasNeue", "Anton", "Bangers", "LuckiestGuy"):
        assert f"@remotion/google-fonts/{fam}" in TSX, f"fonte {fam} nao carregada no template"
    assert "'beast'" in TSX.split("const MAIUSCULA", 1)[1][:200]


def test_geometria_bate_nos_tres_motores():
    esperado = {"contorno": (74, 800), "sombra3d": (76, 800), "beast": (78, 800), "sublinhado": (64, 820),
                "gigante": (118, 860), "quadrinhos": (86, 820), "divertida": (80, 800), "condensada": (100, 760)}
    for e, (tam, maxw) in esperado.items():
        v = Renderizador.SIMPLE_VARIANTES[e]
        assert (v[2], v[9]) == (tam, maxw), e
        assert f"size: {tam}, maxWords" in TSX.split(f"  {e}: {{", 1)[1][:200], e
        # no editor, `sublinhado` tambem e MANCHETE (tabela de metricas com
        # `weights:`); a linha de legenda e a que comeca com `family:`
        assert f"size: {tam}, maxWords" in PJS.split(f"  {e}: {{family:", 1)[1][:200], e


def test_editor_lista_desenha_e_hub_nomeia():
    for e in TODAS:
        assert f"id: '{e}', name:" in PJS, f"editor nao lista `{e}`"
        assert f'{e}: "' in SJS.split("legenda: {", 1)[1][:1400], f"hub sem nome para `{e}`"
    for e in EFEITOS:
        assert f"V.modo === '{e}'" in PJS, f"editor nao desenha `{e}`"
    i = PJS.index("const CAP_EMPH_STYLES = [")
    for e in ("contorno", "sombra3d", "sublinhado", "divertida"):
        assert f"'{e}'" in PJS[i:i + 600], e
    assert "'beast'" in PJS.split("const CAP_MAIUSCULA", 1)[1][:200]


def test_mesma_conta_nos_dois_motores():
    src = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    # contorno 5,5% / beast 7,5% / sublinhado: barra 10%, gap 5%, sobra 4% / sombra3d n = 10%
    assert "tam * 0.055" in src and "V.size * 0.055" in TSX
    assert "tam * 0.075" in src and "V.size * 0.075" in TSX
    assert "round(tam * 0.10)" in src and "V.size * 0.10" in TSX
    assert "#ffe600" in src and "#ffe600" in TSX and "#ffe600" in PJS
    i = src.index('if modo == "sublinhado":')
    corpo = src[i:i + 1500]
    assert "tam * 0.05" in corpo and "tam * 0.04" in corpo
    assert "folga + h_m + gap" in corpo, "a barra fica logo abaixo do glifo"
