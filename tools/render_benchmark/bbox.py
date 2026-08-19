# -*- coding: utf-8 -*-
"""Caixa delimitadora do texto num PNG com alpha, sem dependencia externa.

Usa o proprio FFmpeg para exportar o canal alpha como PGM e varre os bytes.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def alpha_bbox(png: Path, thresh: int = 24) -> tuple[int, int, int, int] | None:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(png), "-vf", "alphaextract,format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, **_NOWIN,
    )
    data = r.stdout
    if not data:
        return None
    pr = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(png)],
        capture_output=True, text=True, **_NOWIN,
    )
    w, h = (int(x) for x in (pr.stdout or "0,0").strip().split(",")[:2])
    if w * h != len(data):
        return None
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = data[y * w:(y + 1) * w]
        if max(row) < thresh:
            continue
        for x in range(w):
            if row[x] >= thresh:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
        if y < y0:
            y0 = y
        if y > y1:
            y1 = y
    if x1 < 0:
        return None
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1


if __name__ == "__main__":
    for p in sys.argv[1:]:
        b = alpha_bbox(Path(p))
        if b:
            x, y, w, h = b
            print(f"{Path(p).name:26s} x={x:4d} y={y:4d} w={w:4d} h={h:4d}  centro_x={x + w // 2}")
        else:
            print(f"{Path(p).name:26s} (vazio)")
