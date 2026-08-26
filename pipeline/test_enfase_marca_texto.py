# -*- coding: utf-8 -*-
"""Enfase "marca-texto": pinta o fundo em vez de circular (pedido 26/08).

Mesmas cues SOLO_OUTLINE, mesmo tempo, mesmo caption-scratch nos DOIS
motores — so a tinta muda. Opt-in via emphasisStyle; o padrao segue o
circulo riscado.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def test_knob_viaja_do_preset_ao_edit_data():
    from app.brand_presets import STYLE_KEYS

    assert "emphasisStyle" in STYLE_KEYS
    rf = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'ed["captions"]["emphasisStyle"] = "marker"' in rf
    assert 'captions == "stacked"' in rf[rf.find('emphasisStyle'):][:600], \
        "marca-texto e do estilo empilhado, como o circulo"


def test_template_tem_o_ramo_e_o_componente():
    comp = RAIZ / "assets" / "shortform" / "src" / "MarkerHighlight.tsx"
    assert comp.is_file()
    c = comp.read_text(encoding="utf-8")
    assert "strokeDashoffset={1 - p}" in c, \
        "o marcador precisa se pintar com o MESMO contrato de progresso do lapis"
    assert "0 0 312 150" in c, "viewBox diferente quebra a paridade dos motores"
    st = (RAIZ / "assets" / "shortform" / "src" / "StackedCaptions.tsx").read_text(encoding="utf-8")
    assert "MarkerHighlight" in st and "EMPH_MARKER" in st
    assert "PencilOutline" in st, "o circulo continua sendo o padrao"


def test_motor_proprio_acompanha_o_template():
    """Regra da casa (motor-proprio-cobre-tudo): mexeu no .tsx, porta no
    render_proprio — senao o job cai no caminho lento calado."""
    rp = (RAIZ / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert "enfase_marcador" in rp
    assert "MARCADOR_PONTOS" in rp and "MARCADOR_LARG_VB = 92.0" in rp, \
        "geometria do marcador tem que casar com o MarkerHighlight.tsx"
    assert "MARCADOR_ALPHA = 0.85" in rp, "opacity 0.85 e a do tsx"
    # o scratch continua por preset SOLO_OUTLINE (nao por tipo de tinta)
    assert 'caption-scratch.mp3' in rp


def test_ui_oferece_o_traco_da_enfase():
    html = (RAIZ / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="optEmphStyle"' in html
    assert 'value="marker"' in html
    js = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert js.count("emphasisStyle: S.style.emphasisStyle || 'circle'") >= 3, \
        "o knob tem que ir nos TRES payloads (padrao, refazer e snapshot)"
    assert "emphasisStyle: 'circle'" in js, "o default do estilo sumiu"


def test_marcador_pinta_de_verdade(tmp_path):
    """Funcional: com emphasisStyle=marker a camada do SOLO_OUTLINE ganha a
    banda amarela (tinta translucida, sem sombra) ALEM do texto — e com
    'circle' o desenho continua o traco verde de sempre."""
    sys.path.insert(0, str(RAIZ / "pipeline"))
    from test_render_proprio import _ed, _public  # fixtures do motor
    from app.render_proprio import MARCADOR_ALPHA, Renderizador

    cues = [{"i": 0, "preset": "SOLO_OUTLINE", "startMs": 0, "endMs": 900,
             "lines": [[{"text": "AGORA", "fromMs": 0}]]}]

    ed_m = _ed(endCard={"enabled": False})
    ed_m["captions"]["emphasisStyle"] = "marker"
    rm = Renderizador(_public(tmp_path, cues), ed_m, frames=40, fps=30.0)
    # camadas[0] pode ser a HEADLINE (ordenacao por inicio_f) — procurar a
    # banda em TODAS as camadas
    banda = [p for cam in rm.camadas for p in cam.palavras
             if p.alpha.max() > 0
             and abs(float(p.alpha.max()) - MARCADOR_ALPHA) < 0.02]
    assert banda, "nenhuma camada com a tinta translucida do marcador"
    assert all(float(p.sombra.max()) == 0.0 for p in banda), \
        "marca-texto nao tem sombra (o traco tem)"
    assert rm.enfase_marcador is True

    ed_c = _ed(endCard={"enabled": False})
    rc = Renderizador(_public(tmp_path, cues), ed_c, frames=40, fps=30.0)
    assert rc.enfase_marcador is False
    assert not [p for cam in rc.camadas for p in cam.palavras
                if abs(float(p.alpha.max()) - MARCADOR_ALPHA) < 0.02], \
        "sem o knob, o marcador nao pode aparecer"
    # o scratch dispara nos dois modos — o som e da CUE, nao da tinta
    assert [e for e in rm.eventos_sfx if e[0] == "caption-scratch.mp3"]
    assert [e for e in rc.eventos_sfx if e[0] == "caption-scratch.mp3"]
