# -*- coding: utf-8 -*-
"""EXPERIMENTO 4b — mesma prova, agora com libass (que o FFmpeg ja embute).

libass faz o que o drawtext nao faz: desfoque real, espacamento entre
letras e posicionamento por glifo. Calibra corpo e posicao contra o quadro
do Remotion e mede SSIM.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bbox import alpha_bbox  # noqa: E402
from bench_lib import BENCH, save  # noqa: E402
from phase9_poc import ssim_band  # noqa: E402

REF = BENCH / "stills_ov" / "state_005.png"
OUT = BENCH / "poc"
FONTS = BENCH / "fonts"
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,Poppins ExtraBold,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,{spacing},0,1,0,0,5,0,0,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.00,0:00:05.00,Cap,,0,0,0,,{{\\pos({px},{py}){tags}}}Pode
"""


def render(name: str, size: int, px: int, py: int, *, blur: float = 0.0,
           spacing: float = 0.0, shadow: bool = False) -> Path:
    tags = ""
    if blur:
        tags += f"\\blur{blur}"
    if shadow:
        tags += "\\4c&H000000&\\shad4"
    ass = OUT / f"{name}.ass"
    ass.write_text(ASS.format(size=size, spacing=spacing, px=px, py=py, tags=tags),
                   encoding="utf-8")
    out = OUT / f"{name}.png"
    sub = str(ass).replace("\\", "/").replace(":", r"\:")
    fdir = str(FONTS).replace("\\", "/").replace(":", r"\:")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "color=c=black@0.0:s=1080x1920:d=1,format=rgba",
         "-vf", f"subtitles='{sub}':fontsdir='{fdir}':alpha=1",
         "-frames:v", "1", str(out)], capture_output=True, **_NOWIN)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    rx, ry, rw, rh = alpha_bbox(REF)  # type: ignore[misc]
    print(f"referencia (Remotion): x={rx} y={ry} w={rw} h={rh}\n")

    size, px, py = 86, 541, 1251
    for _ in range(8):
        p = render("cal", size, px, py)
        bb = alpha_bbox(p)
        if not bb:
            break
        x, y, w, h = bb
        if abs(w - rw) <= 2:
            break
        size = max(10, round(size * rw / w))
    x, y, w, h = alpha_bbox(render("cal", size, px, py))  # type: ignore[misc]
    px += rx - x
    py += ry - y
    print(f"calibrado: fontsize={size} pos=({px},{py}) -> caixa {alpha_bbox(render('cal', size, px, py))}\n")

    rows: list[dict] = []
    testes = [
        ("l1_libass_simples", dict(), "Poppins real, sem efeito"),
        ("l2_desfoque_2", dict(blur=2.0), "+ desfoque 2 (o que o drawtext nao faz)"),
        ("l3_desfoque_3", dict(blur=3.0), "+ desfoque 3"),
        ("l4_desfoque_e_tracking", dict(blur=2.5, spacing=-1.5), "+ tracking -1,5 (como no TSX)"),
    ]
    best = ("", -1.0)
    for name, kw, nota in testes:
        out = render(name, size, px, py, **kw)  # type: ignore[arg-type]
        s = ssim_band(REF, out)
        print(f"  {name:24s} SSIM {s:.4f}   {nota}")
        rows.append({"variante": name, "ssim": round(s, 4), "fontsize": size, "nota": nota})
        if s > best[1]:
            best = (name, s)

    rows.append({"variante": "melhor drawtext (p4)", "ssim": 0.8622,
                 "nota": "gradiente + sombra, medido antes"})
    rows.append({"variante": "antes de tudo (Segoe, sem calibrar)", "ssim": 0.5874, "nota": ""})
    print(f"\n  melhor: {best[0]} com SSIM {best[1]:.4f}")
    save(rows, "phase9b_libass.csv")
