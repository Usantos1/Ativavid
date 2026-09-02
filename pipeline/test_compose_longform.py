# -*- coding: utf-8 -*-
"""O vídeo longo sai pelo compose próprio, não por horas de Chrome.

Caso real de 02/09: 11min35 de 1080p60 passaram HORAS no Remotion por 9,5
segundos de arte (um lower third + um capítulo). O compose próprio pinta só
os quadros das janelas (Pillow, espelhando o template) e um ffmpeg único
faz overlay + encode + mixagem. B-roll segue no Remotion.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO, REPO / "helpers"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from compose_longform import (  # noqa: E402
    compor_longform,
    motivo_nao_elegivel,
)

ED = {
    "width": 1280, "height": 720, "fps": 30.0, "durationSec": 6.0,
    "accent": "#ff0004",
    "broll": [],
    "lowerThirds": [{"name": "Uander", "title": "Prime Camp",
                     "start": 2.5, "dur": 2.5}],
    "chapters": [{"title": "Abertura", "start": 0.0, "dur": 2.2}],
    "callouts": [],
    "soundtrack": {"enabled": True, "file": "trilha.mp3", "volume": 0.1},
}


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "color=c=gray:s=1280x720:r=30:d=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(public / "cut.mp4")],
        check=True, capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "sine=frequency=220:duration=8",
         "-c:a", "libmp3lame", str(public / "trilha.mp3")],
        check=True, capture_output=True)
    return edit, public


def _quadro(video: Path, t: float, destino: Path) -> np.ndarray:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(video),
         "-frames:v", "1", str(destino)],
        check=True, capture_output=True)
    return np.asarray(Image.open(destino).convert("RGB"), dtype=np.int16)


def _tem_accent(px: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> int:
    reg = px[y0:y1, x0:x1]
    m = (reg[..., 0] > 180) & (reg[..., 1] < 90) & (reg[..., 2] < 90)
    return int(m.sum())


def test_compose_monta_o_final_com_arte_e_audio(tmp_path):
    edit, public = _fixture(tmp_path)
    saida = edit / "final.mp4"
    info = compor_longform(edit, public, ED, saida)
    assert saida.exists() and info["quadrosPintados"] > 0
    pr = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "csv=p=0", str(saida)],
        capture_output=True, text=True, check=True)
    assert abs(float(pr.stdout.strip()) - 6.0) < 0.25
    pr2 = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(saida)], capture_output=True, text=True)
    tipos = set((pr2.stdout or "").split())
    assert {"video", "audio"} <= tipos

    # lower third assentado (t=4,0): barra accent no canto inferior esquerdo
    q_on = _quadro(saida, 4.0, tmp_path / "on.png")
    assert _tem_accent(q_on, 60, 400, 430, 700) > 60, \
        "a barra do lower third não apareceu"
    # depois da janela (t=5,6): quadro limpo de novo
    q_off = _quadro(saida, 5.7, tmp_path / "off.png")
    assert _tem_accent(q_off, 60, 400, 430, 700) < 10, \
        "o lower third ficou preso na tela"


def test_entrada_desliza_da_esquerda(tmp_path):
    """O easing do template: no começo da janela a barra está ~40px à
    esquerda da posição assentada (translateX de -40 → 0)."""
    edit, public = _fixture(tmp_path)
    saida = edit / "final.mp4"
    compor_longform(edit, public, ED, saida)

    def borda_esq(t: float, nome: str) -> int:
        px = _quadro(saida, t, tmp_path / nome)
        for x in range(0, 400):
            col = px[430:700, x]
            m = (col[..., 0] > 180) & (col[..., 1] < 90) & (col[..., 2] < 90)
            if m.sum() > 3:
                return x
        return -1

    cedo = borda_esq(2.5 + 2 / 30.0, "cedo.png")     # 2 quadros na janela
    tarde = borda_esq(4.0, "tarde.png")
    assert cedo >= 0 and tarde >= 0
    assert tarde - cedo > 8, f"sem deslize de entrada: {cedo} -> {tarde}"


def test_broll_segue_no_remotion():
    assert motivo_nao_elegivel(ED) is None
    com_broll = dict(ED, broll=[{"kind": "image", "src": "x.jpg",
                                 "start": 1, "dur": 3}])
    assert "b-roll" in (motivo_nao_elegivel(com_broll) or "")


def test_o_limiter_respeita_o_teto_da_casa():
    """0.95 entregou o primeiro vídeo real em -0,44 dBTP (alvo ≤ -1,0,
    medido no arquivo entregue em 02/09): o teto é 0.87 (~-1,2 dB), com
    folga para o overshoot de true peak do encoder."""
    s = (REPO / "helpers" / "compose_longform.py").read_text(encoding="utf-8")
    assert "alimiter=limit=0.87" in s
    assert "alimiter=limit=0.95" not in s


def test_o_pipeline_liga_o_compose_no_longform():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = rf.index('_RENDER_META["overlaySkip"] = "longform"')
    bloco = rf[i:i + 3000]
    assert "compor_longform" in bloco and "motivo_nao_elegivel" in bloco
    assert "LONGFORM_COMPOSE_DONE" in bloco
    assert "FALLBACK_FULL_REMOTION" in bloco, "sem rede: falha viraria job morto"
    assert '"renderPath"] = "LONGFORM_COMPOSE"' in bloco
    # o pico de audio passa pela MESMA conferencia dos outros caminhos
    assert "garantir_true_peak" in bloco
