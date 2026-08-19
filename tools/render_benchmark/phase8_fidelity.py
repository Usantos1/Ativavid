# -*- coding: utf-8 -*-
"""EXPERIMENTO 3 — fidelidade visual fora do Chromium.

A velocidade ja esta provada (11,6 s vs 310 s). Falta saber QUANTO do design
sobrevive. Compara, por SSIM, o quadro que o Remotion desenha contra
reproducoes progressivas feitas so com FFmpeg.

Nao implementa nada no produto: escreve PNGs numa area temporaria.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, save  # noqa: E402

REF = BENCH / "stills_ov" / "state_005.png"   # "Pode" — estilo stacked
OUT = BENCH / "fidelity"
FONT_BLACK = r"C\:/Windows/Fonts/seguibl.ttf"   # Segoe UI Black (substituta da Poppins 900)
FONT_BOLD = r"C\:/Windows/Fonts/arialbd.ttf"
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def ssim(a: Path, b: Path) -> float:
    """SSIM entre dois PNGs, achatados sobre o MESMO fundo preto."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=1",
         "-i", str(a), "-i", str(b),
         "-filter_complex",
         # SSIM no quadro inteiro nao discrimina: 1080x1920 quase todo
         # transparente empata em ~0,99. Recorta a FAIXA DO TEXTO.
         "[0:v]split=2[bg1][bg2];"
         "[bg1][1:v]overlay=0:0:format=auto,crop=1080:340:0:1120,format=gray[x];"
         "[bg2][2:v]overlay=0:0:format=auto,crop=1080:340:0:1120,format=gray[y];"
         "[x][y]ssim",
         "-frames:v", "1", "-f", "null", "-"],
        capture_output=True, text=True, **_NOWIN,
    )
    m = re.search(r"All:([0-9.]+)", r.stderr or "")
    return float(m.group(1)) if m else -1.0


def draw(name: str, vf: str) -> Path:
    p = OUT / f"{name}.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=black@0.0:s=1080x1920:d=1,format=rgba",
         "-vf", vf, "-frames:v", "1", str(p)],
        capture_output=True, **_NOWIN)
    return p


if __name__ == "__main__":
    if not REF.exists():
        print("still de referencia ausente — rode o experimento 2 antes")
        sys.exit(0)
    OUT.mkdir(parents=True, exist_ok=True)
    TXT, Y, SIZE = "Pode", "h*0.645", 118
    rows: list[dict] = []

    variantes = [
        ("v1_texto_simples",
         f"drawtext=fontfile='{FONT_BOLD}':text='{TXT}':fontcolor=white:fontsize={SIZE}:"
         f"x=(w-text_w)/2:y={Y}",
         "Arial Bold, branco chapado, sem sombra"),
        ("v2_fonte_pesada",
         f"drawtext=fontfile='{FONT_BLACK}':text='{TXT}':fontcolor=white:fontsize={SIZE}:"
         f"x=(w-text_w)/2:y={Y}",
         "Segoe UI Black (mais perto da Poppins 900)"),
        ("v3_com_sombra",
         f"drawtext=fontfile='{FONT_BLACK}':text='{TXT}':fontcolor=white:fontsize={SIZE}:"
         f"shadowcolor=black@0.45:shadowx=0:shadowy=6:x=(w-text_w)/2:y={Y}",
         "+ sombra suave"),
        ("v4_sombra_e_espacamento",
         f"drawtext=fontfile='{FONT_BLACK}':text='{TXT}':fontcolor=white:fontsize={SIZE}:"
         f"shadowcolor=black@0.45:shadowx=0:shadowy=6:x=(w-text_w)/2:y={Y}",
         "+ tracking negativo (drawtext nao suporta — igual a v3)"),
    ]
    for name, vf, nota in variantes:
        p = draw(name, vf)
        s = ssim(REF, p) if p.exists() else -1
        print(f"  {name:26s} SSIM {s:.4f}   {nota}")
        rows.append({"variante": name, "ssim": round(s, 4), "nota": nota})

    # v5: gradiente DENTRO das letras (o recurso "so de navegador")
    #     texto branco vira mascara alpha sobre um degrade vertical
    mask = draw("v5_mask", f"drawtext=fontfile='{FONT_BLACK}':text='{TXT}':fontcolor=white:"
                           f"fontsize={SIZE}:x=(w-text_w)/2:y={Y}")
    grad = OUT / "v5_grad.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "gradients=s=1080x1920:c0=0xffffff:c1=0xcfcfcf:type=linear:nb_colors=2:x0=0:y0=0:x1=0:y1=1920:d=1",
         "-i", str(mask),
         "-filter_complex", "[1:v]alphaextract[a];[0:v][a]alphamerge[v]",
         "-map", "[v]", "-frames:v", "1", str(grad)], capture_output=True, **_NOWIN)
    s5 = ssim(REF, grad) if grad.exists() else -1
    print(f"  {'v5_gradiente_nas_letras':26s} SSIM {s5:.4f}   degrade via mascara alpha (recurso 'so de navegador')")
    rows.append({"variante": "v5_gradiente_nas_letras", "ssim": round(s5, 4),
                 "nota": "gradiente dentro das letras REPRODUZIDO com alphamerge"})

    # referencia contra si mesma = teto do metodo
    rows.append({"variante": "teto (ref vs ref)", "ssim": round(ssim(REF, REF), 4),
                 "nota": "controle"})
    print(f"  {'teto (ref vs ref)':26s} SSIM {rows[-1]['ssim']:.4f}")
    save(rows, "phase8_fidelity.csv")
