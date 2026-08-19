# -*- coding: utf-8 -*-
"""Fidelidade do rasterizador Pillow contra os stills do Remotion.

Compara SÓ nos frames "assentados" (todas as palavras já entraram), sobre o
recorte da UNIÃO das caixas de texto — comparar a tela inteira infla o SSIM
com área vazia.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, r"E:\Code\ativa-vid\tools\render_benchmark")
import phase14_raster as R

S = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
REF = S / "bench" / "stills_settled"
OUT = S / "bench" / "rast_settled"
FPS = 30


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM global com janela 8x8 (média das janelas), escala 0..1."""
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    h, w = a.shape
    k = 8
    h, w = (h // k) * k, (w // k) * k
    A = a[:h, :w].reshape(h // k, k, w // k, k).transpose(0, 2, 1, 3).reshape(-1, k * k)
    B = b[:h, :w].reshape(h // k, k, w // k, k).transpose(0, 2, 1, 3).reshape(-1, k * k)
    ma, mb = A.mean(1), B.mean(1)
    va, vb = A.var(1), B.var(1)
    cov = ((A - ma[:, None]) * (B - mb[:, None])).mean(1)
    s = ((2 * ma * mb + C1) * (2 * cov + C2)) / ((ma**2 + mb**2 + C1) * (va + vb + C2))
    return float(s.mean())


def alpha(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGBA").split()[3], dtype=np.float64)


if __name__ == "__main__":
    frames = [int(x) for x in (S / "bench" / "settled.txt").read_text().strip().split(",")]
    cues = json.loads((R.OV / "public" / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = cues if isinstance(cues, list) else (cues.get("cues") or [])
    OUT.mkdir(parents=True, exist_ok=True)

    linhas, res = [], []
    for i, fr in enumerate(frames):
        ref = REF / f"state_{i:03d}.png"
        if not ref.exists():
            continue
        cue = next((c for c in cues
                    if c["startMs"] / 1000 * FPS <= fr <= c["endMs"] / 1000 * FPS), None)
        if cue is None:
            continue
        got = R.render_state(cue, fr - cue["startMs"] / 1000 * FPS, OUT / f"rast_{i:03d}.png")
        ra, ga = alpha(ref), alpha(got)
        if ra.max() < 8 and ga.max() < 8:
            continue                       # ambos vazios: 1,0 de graça, não conta
        ys, xs = np.nonzero((ra > 8) | (ga > 8))
        y0, y1 = max(0, ys.min() - 8), min(ra.shape[0], ys.max() + 9)
        x0, x1 = max(0, xs.min() - 8), min(ra.shape[1], xs.max() + 9)
        v = ssim(ra[y0:y1, x0:x1], ga[y0:y1, x0:x1])
        # divergência de geometria: caixa de cada um
        rb = [xs.min(), ys.min()]
        rys, rxs = np.nonzero(ra > 8)
        gys, gxs = np.nonzero(ga > 8)
        dw = (gxs.max() - gxs.min()) - (rxs.max() - rxs.min()) if len(gxs) and len(rxs) else 0
        dh = (gys.max() - gys.min()) - (rys.max() - rys.min()) if len(gys) and len(rys) else 0
        dy = (gys.min() - rys.min()) if len(gys) and len(rys) else 0
        n_pal = sum(len(l) for l in cue["lines"])
        res.append({"i": i, "frame": fr, "ssim": round(v, 4), "dW": int(dw),
                    "dH": int(dh), "dY": int(dy), "linhas": len(cue["lines"]),
                    "palavras": n_pal})
        print(f"  estado {i:02d} f{fr:4d}  SSIM {v:.4f}   dW {dw:+5d}  dH {dh:+4d}  dY {dy:+4d}"
              f"   {len(cue['lines'])}L/{n_pal}p")
        linhas.append(v)

    print(f"\n  MEDIA SSIM: {np.mean(linhas):.4f}   (n={len(linhas)})")
    json.dump({"media": round(float(np.mean(linhas)), 4), "estados": res},
              open(S / "bench" / "rast_fidelidade.json", "w"), indent=2)
