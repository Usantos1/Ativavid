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
    """Sem a bolha no gate, todo job do estilo cai no caminho lento.

    O literal que estava aqui virou `app/caption_styles.TODOS` — a
    lista passou a ter um dono só, e é ela que este teste consulta.
    """
    import sys
    sys.path.insert(0, str(RAIZ))
    from app import caption_styles
    assert "bolha" in caption_styles.TODOS
    rp = (RAIZ / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert "permitidos = CAPTION_STYLES.TODOS" in rp


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


def test_a_bolha_tem_sombra_de_verdade():
    """A bolha saía SEM sombra no motor próprio — 126 pixels de halo contra
    23.279 do template (medido em 140 quadros).

    O borrão era calculado num quadro do tamanho exato do balão e ficava
    preso dentro dele, onde o próprio balão o cobre. Todos os outros estilos
    já reservavam folga; este era o único sem. Depois do conserto: razão de
    tinta 0,964 (era 0,743) e halo 0,927 (era 0,005).
    """
    rp = (RAIZ / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = rp.index("def _montar_bolha")
    bloco = rp[i:rp.index("def _montar_karaoke", i)]
    assert "folga_b = 70" in bloco, "sem folga a sombra fica presa no balão"
    assert "base_pad = _com_folga(base_a)" in bloco
    # `box-shadow` pede sigma = raio/2, não o raio inteiro do drop-shadow
    assert "self._sombra_de(base_pad, [(0, 8, 26, 0.45)], k=0.5)" in bloco
    # e a posição desconta a folga, senão o balão desce 70px
    assert "- folga_b" in bloco


def test_a_bolha_usa_o_peso_que_o_chrome_usa():
    """O índice 4 é o `Poppins-Black.ttf`, arquivo de peso único: pedir 500
    nele não muda nada e a bolha saía em 900. O template pede 500 numa
    família com 400/600/900 carregados, e a regra do CSS para 500 escolhe o
    menor peso ≤ 500 — 400."""
    rp = (RAIZ / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = rp.index("def _montar_bolha")
    bloco = rp[i:rp.index("def _montar_karaoke", i)]
    assert 'self.fonte(1, tam, 400, marca="cap")' in bloco
    assert 'self.fonte(4,' not in bloco


def test_o_overlay_conhece_a_bolha():
    """`Overlay.tsx` é a rede de segurança (o `overlayRollout` está em
    `default`). Sem o ramo, a bolha caía no `else` — `<Karaoke/>` — e o
    vídeo saía com outra legenda, sem uma linha de aviso."""
    ov = (RAIZ / "assets" / "overlay-proto" / "Overlay.tsx").read_text(encoding="utf-8")
    assert "BubbleCaptions" in ov
    assert "D.captions.style === 'bolha'" in ov
    # e o proto precisa exportar o componente, senão nem compila
    op = (RAIZ / "app" / "overlay_path.py").read_text(encoding="utf-8")
    i = op.index('for name in ("Karaoke"')
    assert '"BubbleCaptions"' in op[i:i + 200]
