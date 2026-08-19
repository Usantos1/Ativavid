# -*- coding: utf-8 -*-
"""EXPERIMENTO 4 — prova de conceito com fidelidade real.

Poppins de verdade (OFL, baixada), corpo e posicao CALIBRADOS ate baterem
com o quadro do Remotion, e so entao SSIM. Sem geometria igual, o SSIM
anterior nao significava nada.

Nada e implementado no produto: tudo em area temporaria.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bbox import alpha_bbox  # noqa: E402
from bench_lib import BENCH, save  # noqa: E402

REF = BENCH / "stills_ov" / "state_005.png"
OUT = BENCH / "poc"
FONTS = BENCH / "fonts"
POPPINS = str(FONTS / "Poppins-Black.ttf").replace("\\", "/").replace(":", r"\:")
TXT = "Pode"
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def draw(out: Path, size: int, x: str, y: str, *, grad: bool = False,
         shadow: bool = False) -> Path:
    vf = (f"drawtext=fontfile='{POPPINS}':text='{TXT}':fontcolor=white:"
          f"fontsize={size}:x={x}:y={y}")
    if shadow:
        vf += ":shadowcolor=black@0.35:shadowx=0:shadowy=5"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=black@0.0:s=1080x1920:d=1,format=rgba",
         "-vf", vf, "-frames:v", "1", str(out)],
        capture_output=True, **_NOWIN)
    if grad and out.exists():
        tmp = out.with_name(out.stem + "_g.png")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "lavfi", "-i",
             "gradients=s=1080x1920:c0=0xffffff:c1=0xcfcfcf:type=linear:"
             "nb_colors=2:x0=0:y0=1218:x1=0:y1=1292:d=1",
             "-i", str(out),
             "-filter_complex", "[1:v]alphaextract[a];[0:v][a]alphamerge[v]",
             "-map", "[v]", "-frames:v", "1", str(tmp)], capture_output=True, **_NOWIN)
        if tmp.exists():
            out.unlink(missing_ok=True)
            tmp.rename(out)
    return out


def ssim_band(a: Path, b: Path) -> float:
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=1",
         "-i", str(a), "-i", str(b),
         "-filter_complex",
         "[0:v]split=2[b1][b2];"
         "[b1][1:v]overlay=0:0:format=auto,crop=400:160:380:1180,format=gray[x];"
         "[b2][2:v]overlay=0:0:format=auto,crop=400:160:380:1180,format=gray[y];"
         "[x][y]ssim",
         "-frames:v", "1", "-f", "null", "-"],
        capture_output=True, text=True, **_NOWIN)
    m = re.search(r"All:([0-9.]+)", r.stderr or "")
    return float(m.group(1)) if m else -1.0


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ref = alpha_bbox(REF)
    if not ref:
        print("referencia vazia")
        sys.exit(0)
    rx, ry, rw, rh = ref
    print(f"referencia (Remotion): x={rx} y={ry} w={rw} h={rh}\n")

    # ---- 1. calibrar o corpo pela LARGURA do texto ----
    size = 100
    for it in range(8):
        p = draw(OUT / "cal.png", size, "(w-text_w)/2", "1200")
        bb = alpha_bbox(p)
        if not bb:
            break
        _, _, w, h = bb
        if abs(w - rw) <= 2:
            break
        size = max(10, round(size * rw / w))
    print(f"corpo calibrado: fontsize={size}  (largura {w} vs {rw} da referencia)")

    # ---- 2. calibrar a posicao ----
    p = draw(OUT / "cal.png", size, "(w-text_w)/2", "1200")
    bx, by, bw, bh = alpha_bbox(p)  # type: ignore[misc]
    dx, dy = rx - bx, ry - by
    x_expr = f"(w-text_w)/2+{dx}"
    y_expr = str(1200 + dy)
    p = draw(OUT / "cal.png", size, x_expr, y_expr)
    bb2 = alpha_bbox(p)
    print(f"posicao calibrada: x={x_expr} y={y_expr} -> caixa {bb2}\n")

    rows: list[dict] = []
    variantes = [
        ("p1_poppins_calibrada", dict(grad=False, shadow=False), "Poppins real, corpo e posicao iguais"),
        ("p2_com_sombra", dict(grad=False, shadow=True), "+ sombra"),
        ("p3_com_gradiente", dict(grad=True, shadow=False), "+ gradiente nas letras"),
        ("p4_completa", dict(grad=True, shadow=True), "+ gradiente e sombra"),
    ]
    for name, kw, nota in variantes:
        out = draw(OUT / f"{name}.png", size, x_expr, y_expr, **kw)  # type: ignore[arg-type]
        s = ssim_band(REF, out)
        bb = alpha_bbox(out)
        print(f"  {name:24s} SSIM {s:.4f}   caixa={bb}   {nota}")
        rows.append({"variante": name, "ssim": round(s, 4),
                     "caixa": str(bb), "fontsize": size, "nota": nota})

    # linha de base: o que tinhamos antes (fonte substituta, sem calibrar)
    old = BENCH / "fidelity" / "v5_grad.png"
    if old.exists():
        s_old = ssim_band(REF, old)
        print(f"  {'(antes: Segoe, sem calibrar)':24s} SSIM {s_old:.4f}")
        rows.append({"variante": "antes_sem_calibrar", "ssim": round(s_old, 4),
                     "nota": "Segoe UI Black, geometria diferente"})
    rows.append({"variante": "teto (ref x ref)", "ssim": round(ssim_band(REF, REF), 4),
                 "nota": "controle"})
    save(rows, "phase9_poc.csv")
