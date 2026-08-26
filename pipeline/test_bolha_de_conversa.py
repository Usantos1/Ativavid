# -*- coding: utf-8 -*-
"""Estilo de legenda "Bolha de conversa" (WhatsApp) — pedido 26/08.

Cada frase vira uma bolha verde com hora + checks e pop.mp3, nos DOIS
motores, agrupada por CONTAGEM (12 palavras / pontuacao / respiro >450ms —
o MESMO spec do buildBubbles no Main.tsx, sem medir largura).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pipeline"))


def test_template_e_catalogo_tem_a_bolha():
    main = (RAIZ / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "BubbleCaptions" in main and "buildBubbles" in main
    assert "'bolha'" in main, "o switch de estilos nao conhece a bolha"
    assert "BUBBLE_MAX_WORDS = 12" in main and "BUBBLE_GAP_MS = 450" in main
    js = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "id: 'bolha'" in js, "a bolha sumiu do catalogo"
    assert "'bolha']" in js or "'bolha'," in js  # CAP_BASE_STYLES


def test_motor_proprio_desenha_a_bolha(tmp_path):
    from test_render_proprio import _ed, _public
    from app.render_proprio import Renderizador

    # 5 palavras: pontuacao fecha a 1a bolha em 3; respiro >450ms fecha a 2a
    words = [
        {"text": "Oi", "startMs": 0, "endMs": 200},
        {"text": "tudo", "startMs": 220, "endMs": 400},
        {"text": "bem?", "startMs": 420, "endMs": 700},
        {"text": "Chega", "startMs": 800, "endMs": 1000},
        {"text": "mais", "startMs": 1020, "endMs": 1200},
    ]
    public = _public(tmp_path, [])
    (public / "captions.json").write_text(json.dumps(words), encoding="utf-8")
    ed = _ed(endCard={"enabled": False})
    ed["captions"]["style"] = "bolha"
    r = Renderizador(public, ed, frames=90, fps=30.0)
    bolhas = [c for c in r.camadas if c.palavras
              and c.palavras[0].enter == 7 and c.palavras[0].sobe == 24.0]
    assert len(bolhas) == 2, f"esperava 2 bolhas, veio {len(bolhas)}"
    b1 = bolhas[0].palavras[0]
    assert b1.alpha.max() > 0.9, "a bolha nao pintou"
    # verde do fundo presente no bitmap (canal G > R e B)
    import numpy as np
    g = b1.rgb[..., 1][b1.alpha > 0.5]
    r_ = b1.rgb[..., 0][b1.alpha > 0.5]
    assert float(np.median(g)) > float(np.median(r_)), \
        "o fundo da bolha nao esta verde"
    pops = [e for e in r.eventos_sfx if e[0] == "pop.mp3"]
    assert len(pops) == 2, "pop.mp3 por bolha, nos dois motores"


def test_gate_do_motor_aceita_bolha():
    rp = (RAIZ / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = rp.find('permitidos = {"stacked"')
    assert '"bolha"' in rp[i:i + 200], \
        "sem a bolha no gate, todo job do estilo cai no caminho lento calado"


def test_tipos_do_template_conhecem_os_estilos_novos():
    """tsc --noEmit rodado num projeto real (26/08) acusou: a uniao de
    estilos nao tinha 'bolha' e CapCfg nao tinha emphasisStyle. O esbuild
    transpila sem checar, entao renderizava — mas tipo mentiroso e bomba
    para qualquer build estrito futuro."""
    main = (RAIZ / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "| 'bolha'" in main, "a uniao de estilos perdeu a bolha"
    st = (RAIZ / "assets" / "shortform" / "src" / "StackedCaptions.tsx").read_text(encoding="utf-8")
    assert "emphasisStyle?: 'circle' | 'marker'" in st, \
        "CapCfg perdeu o tipo do emphasisStyle"
