# -*- coding: utf-8 -*-
"""Camadas manuais (pedido de 02/09: "hierarquias de edições").

Arrastar o bloco de mídia na VERTICAL troca ele de fileira, e a fileira é a
CAMADA: fileira de baixo pinta por cima no vídeo. A ordem de pintura vira
(camada, início) nos TRÊS lugares — motor próprio, template e preview — e
legenda/headline seguem sempre por cima de tudo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

W, H = 540, 960
FPS = 30.0
FRAMES = 60


def _render_par(tmp_path: Path, cam_vermelho, cam_azul, marca):
    """Dois cartões no MESMO lugar e mesma janela: a cor que sobra no
    buffer é a do cartão pintado por último."""
    from app.render_proprio import Renderizador

    public = tmp_path / f"public_{marca}"
    public.mkdir()
    Image.new("RGB", (400, 300), (255, 0, 0)).save(public / "verm.jpg")
    Image.new("RGB", (400, 300), (0, 0, 255)).save(public / "azul.jpg")
    janela = {"start": 0.0, "end": FRAMES / FPS, "entrada": "nenhum"}
    it_v = {"src": "verm.jpg", **janela}
    it_a = {"src": "azul.jpg", **janela}
    if cam_vermelho:
        it_v["camada"] = cam_vermelho
    if cam_azul:
        it_a["camada"] = cam_azul
    # o vermelho entra PRIMEIRO na lista: sem camada ele perderia sempre
    ed = {"inserts": [it_v, it_a]}
    (public / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    rend = Renderizador(public, ed, frames=FRAMES, fps=FPS, width=W, height=H)
    buf = np.zeros((H, W, 4), dtype=np.uint8)
    for leg in rend.camadas:
        if getattr(leg, "insert", None) is None:
            continue
        rend._desenhar_insert(leg, 30.0, buf, [0, 0, 0, 0], False)
    tinta = buf[..., 3] > 128
    r = float(buf[..., 0][tinta].mean())
    b = float(buf[..., 2][tinta].mean())
    return r, b


def test_camada_maior_pinta_por_cima(tmp_path):
    """Sem camada os dois empatam no start e vale a ordem da lista (azul,
    o segundo, ganha). camada=1 no vermelho inverte: ele pinta depois."""
    r0, b0 = _render_par(tmp_path, None, None, "sem")
    assert b0 > r0 * 2, f"sem camada o segundo da lista devia ganhar: r={r0:.0f} b={b0:.0f}"
    r1, b1 = _render_par(tmp_path, 1, None, "verm_na_frente")
    assert r1 > b1 * 2, f"camada=1 devia por o vermelho na frente: r={r1:.0f} b={b1:.0f}"


def test_pipeline_saneia_a_camada():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'geo["camada"] = cam' in rf
    assert "1 <= cam <= 4" in rf, "camada sem teto viraria z-index infinito"


def test_template_ordena_por_camada():
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "(a.camada ?? 0) - (b.camada ?? 0)" in tsx


def test_preview_arrasta_desenha_e_salva_a_camada():
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    # o bloco novo nasce na primeira fileira LIVRE (nao em cima de outro)
    assert "function camadaLivre" in js
    # o arrasto vertical: fileiras andadas viram camada, com teto
    i = js.index("} else if (drag.type === 'chip-move')")
    bloco = js[i:i + 1400]
    assert "drag.laneH" in bloco and "Math.min(4," in bloco, bloco[:300]
    # a pintura do preview espelha os motores
    assert "((a.camada | 0) - (b.camada | 0))" in js
    # o salvar manda a camada (so quando > 0, como zoom/srcIn)
    assert "camada: c.camada | 0" in js
    # mexer na camada de um insert JA aplicado arma o Aplicar (geoDoInsert)
    i2 = js.index("function geoDoInsert")
    assert "c.camada ?? null" in js[i2:i2 + 400]


def test_soltar_o_bloco_noutra_fileira_conta_como_mexida():
    """O pointerup decide se o gesto entra no histórico comparando start e
    end — um arrasto SÓ vertical (tempo igual, camada nova) tem de contar."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("const moved = drag.type === 'trim'")
    assert "camada | 0" in js[i:i + 400]
