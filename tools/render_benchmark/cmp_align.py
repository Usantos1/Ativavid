# -*- coding: utf-8 -*-
"""Teto do rasterizador: SSIM com o MELHOR deslocamento inteiro.

Separa "desenhei o glifo diferente" de "posicionei o bloco alguns px fora".
O deslocamento e uma busca exaustiva pequena; o vencedor e reportado.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

import cmp_rast as C

S = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
REF, GOT = S / "bench" / "stills_settled", S / "bench" / "rast_settled"

if __name__ == "__main__":
    res, brutos, tetos = [], [], []
    for i in range(11):
        r, g = REF / f"state_{i:03d}.png", GOT / f"rast_{i:03d}.png"
        if not (r.exists() and g.exists()):
            continue
        ra, ga = C.alpha(r), C.alpha(g)
        if ra.max() < 8 and ga.max() < 8:
            continue
        ys, xs = np.nonzero((ra > 8) | (ga > 8))
        y0, y1 = max(0, ys.min() - 24), min(ra.shape[0], ys.max() + 25)
        x0, x1 = max(0, xs.min() - 24), min(ra.shape[1], xs.max() + 25)
        base = C.ssim(ra[y0:y1, x0:x1], ga[y0:y1, x0:x1])
        melhor, arg = base, (0, 0)
        for dy in range(-14, 15):
            for dx in range(-6, 7):
                sub = ga[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
                if sub.shape != (y1 - y0, x1 - x0):
                    continue
                v = C.ssim(ra[y0:y1, x0:x1], sub)
                if v > melhor:
                    melhor, arg = v, (dx, dy)
        print(f"  estado {i:02d}  bruto {base:.4f} -> alinhado {melhor:.4f}   "
              f"desloc {arg[0]:+d},{arg[1]:+d}")
        brutos.append(base)
        tetos.append(melhor)
        res.append({"i": i, "bruto": round(base, 4), "alinhado": round(melhor, 4),
                    "desloc": arg})
    print(f"\n  MEDIA bruto {np.mean(brutos):.4f}  ->  alinhado {np.mean(tetos):.4f}")
    stack = [x for x in res if x["i"] not in (0, 10)]
    print(f"  So STACK_MIXED: bruto {np.mean([x['bruto'] for x in stack]):.4f}"
          f"  ->  alinhado {np.mean([x['alinhado'] for x in stack]):.4f}")
    json.dump(res, open(S / "bench" / "rast_teto.json", "w"), indent=2)
