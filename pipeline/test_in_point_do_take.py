# -*- coding: utf-8 -*-
"""In-point (srcIn) do take de vídeo inserido — "recortar o vídeo".

Pedido de 02/09: arrastar a borda ESQUERDA do bloco de vídeo corta o
COMEÇO do arquivo (escolhe qual trecho entra), como num editor
profissional. `srcIn` viaja preview → run_fast → os dois motores; no motor
próprio ele entra como `-ss` na extração e na CHAVE do cache de quadros.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

W, H, FPS, FRAMES = 540, 960, 30.0, 40


def _video_vermelho_depois_azul(pasta: Path) -> Path:
    """2s de vídeo: 1s vermelho, 1s azul — o in-point decide a cor."""
    out = pasta / "take.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=red:d=1:s=160x120:r=10",
         "-f", "lavfi", "-i", "color=blue:d=1:s=160x120:r=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-pix_fmt", "yuv420p", str(out)],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"ffmpeg indisponível para o fixture: {r.stderr[:120]}")
    return out


def _cor_do_cartao(tmp_path: Path, src_in):
    from app.render_proprio import Renderizador

    public = tmp_path / f"public_{str(src_in).replace('.', '_')}"
    public.mkdir()
    _video_vermelho_depois_azul(public)
    it = {"src": "take.mp4", "start": 0.0, "end": FRAMES / FPS}
    if src_in is not None:
        it["srcIn"] = src_in
    ed = {"inserts": [it]}
    (public / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    rend = Renderizador(public, ed, frames=FRAMES, fps=FPS, width=W, height=H)
    buf = np.zeros((H, W, 4), dtype=np.uint8)
    for leg in rend.camadas:
        if getattr(leg, "insert", None) is None:
            continue
        rend._desenhar_insert(leg, 14.0, buf, [0, 0, 0, 0], False)
    tinta = buf[..., 3] > 128
    if not tinta.any():
        pytest.skip("take não extraído nesta máquina")
    return float(buf[..., 0][tinta].mean()), float(buf[..., 2][tinta].mean())


def test_src_in_pula_o_comeco_do_arquivo(tmp_path):
    r0, b0 = _cor_do_cartao(tmp_path, None)     # sem in-point: começa VERMELHO
    r1, b1 = _cor_do_cartao(tmp_path, 1.2)      # in-point 1,2s: já é AZUL
    assert r0 > b0 * 2, f"sem srcIn deveria abrir no vermelho: r={r0:.0f} b={b0:.0f}"
    assert b1 > r1 * 2, f"srcIn=1,2 deveria abrir no azul: r={r1:.0f} b={b1:.0f}"


def test_src_in_viaja_pelos_tres_lugares():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'geo["srcIn"]' in rf
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "startFrom={Math.max(0, Math.round((srcIn ?? 0) * qFps))}" in tsx
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert '"-ss", f"{src_in:.3f}"' in py
    assert "i{src_in:.2f}" in py, "o in-point tem de entrar na chave do cache"
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "c.srcIn = +Math.max(0, (drag.c.srcIn || 0)" in js, (
        "o trim esquerdo parou de mover o in-point")
    assert "srcIn: +c.srcIn" in js, "o salvar não manda o srcIn"
