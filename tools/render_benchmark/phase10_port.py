# -*- coding: utf-8 -*-
"""EXPERIMENTO 5 — PORTE do estilo `stacked` para fora do Chromium.

Ate aqui a reproducao era "as cegas". Aqui a logica de layout de
StackedCaptions.tsx e PORTADA (fitFont, lineStyles, letterSpacing,
lineHeight, offset vertical, animacao por palavra) e alimentada pelos
MESMOS dados (caption-cues.json). Renderiza com libass e compara os 22
estados contra os stills do Remotion.

Continua sendo benchmark: nada disso toca o produto.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, save  # noqa: E402

OV = BENCH / "ov_remotion"
STILLS = BENCH / "stills_ov"
OUT = BENCH / "port"
FONTS = BENCH / "fonts"
W, H, FPS = 1080, 1920, 30
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

# --- constantes portadas do TSX ---
OFFSET_Y = 0.156
FONT_SCALE = 1.0
SCALE = (W / 1080) * FONT_SCALE
AVAIL = W - 180
BASE_Y = round(H * OFFSET_Y)
# Ajuste de linha de base: o ASS ancora o texto pelo centro da caixa de
# linha, o CSS pelo fluxo do bloco. Medido contra o Remotion: 19 px.
BASELINE_FIX = 19
LETTER_SPACING = -1.5
# O \fs do ASS nao usa a mesma unidade que o font-size do CSS: calibrando
# contra o quadro do Remotion, a Poppins precisou de 155 onde o CSS pedia 86.
# Sem esta razao o texto sai com metade do tamanho.
ASS_FS_RATIO = 155 / 86
LINE_HEIGHT = 1.12
MARGIN_TOP_EM = -0.34

# 0=bold-italic, 1=regular(small), 2=serif-orange, 3=bold
FONT_OF_STYLE = {
    0: ("Poppins Black", 1),      # 900 italic
    1: ("Poppins", 0),            # 400
    2: ("Playfair Display", 1),   # 900 italic (laranja)
    3: ("Poppins ExtraBold", 0),  # 800
}
COLOR_OF_STYLE = {0: "&H00FFFFFF", 1: "&H00FFFFFF", 2: "&H000052FF", 3: "&H00FFFFFF"}


def fit_font(text: str, base: int = 86, avail: float = AVAIL / SCALE, factor: float = 0.58) -> int:
    n = max(1, len(text.strip()))
    est = n * base * factor
    return int(avail // (n * factor)) if est > avail else base


def size_for(line_text: str, style_idx: int, emph: bool, boost: bool) -> int:
    s = fit_font(line_text)
    if style_idx == 1:
        s = round(s * 0.72)
    if style_idx == 2:
        s = round(s * 0.95)
    if emph:
        s = round(s * 1.12)
    if boost:
        s = round(s * 1.35)
    return s


def word_opacity(w: dict, cue: dict, frame_local: float, enter: int) -> float:
    start = ((w["fromMs"] - cue["startMs"]) / 1000) * FPS
    if frame_local <= start:
        return 0.0
    p = min(1.0, (frame_local - start) / max(1, enter))
    return 1 - (1 - p) ** 3  # easeOut cubico, como o Easing.out do Remotion


def build_ass(cue: dict, frame_local: float) -> str:
    dur_frames = (cue["endMs"] - cue["startMs"]) / 1000 * FPS
    enter = max(3, min(8, int(dur_frames * 0.45)))

    linhas = []
    for li, line in enumerate(cue["lines"]):
        idx = (cue.get("lineStyles") or [None] * 9)[li]
        if idx is None:
            idx = (li + cue.get("styleOffset", 0)) % 4
        txt = " ".join(w["text"] for w in line)
        size = size_for(txt, idx, (cue.get("lineEmph") or [False] * 9)[li],
                        (cue.get("lineBoost") or [False] * 9)[li])
        linhas.append({"idx": idx, "size": size, "words": line, "text": txt})

    # altura do bloco: soma das caixas de linha com o recuo negativo
    alturas = [ln["size"] * LINE_HEIGHT for ln in linhas]
    total = alturas[0] if alturas else 0
    for i in range(1, len(alturas)):
        total += alturas[i] + MARGIN_TOP_EM * linhas[i]["size"]
    top = (H / 2 + BASE_Y) - total / 2

    ev = []
    y = top
    for li, ln in enumerate(linhas):
        if li > 0:
            y += MARGIN_TOP_EM * ln["size"]
        cy = y + alturas[li] / 2 + BASELINE_FIX
        fname, italic = FONT_OF_STYLE[ln["idx"]]
        partes = []
        for w in ln["words"]:
            op = word_opacity(w, cue, frame_local, enter)
            if op <= 0.01:
                continue
            alpha = int(round((1 - op) * 255))
            partes.append(f"{{\\alpha&H{alpha:02X}&}}{w['text']}")
        if partes:
            # sombra: drop-shadow(0 5px 9px rgba(0,0,0,.5)) do TSX
            tags = (f"\\pos({W // 2},{cy:.0f})\\fn{fname}\\fs{ln['size'] * ASS_FS_RATIO:.0f}"
                    f"\\i{italic}\\fsp{LETTER_SPACING}\\c{COLOR_OF_STYLE[ln['idx']]}"
                    f"\\4c&H000000&\\4a&H80&\\xshad0\\yshad5\\blur9")
            ev.append(f"Dialogue: 0,0:00:00.00,0:00:05.00,D,,0,0,0,,{{{tags}}}"
                      + " ".join(partes))
        y += alturas[li]

    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\n"
            "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
            "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,"
            "BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            "Style: D,Poppins,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,"
            "100,100,0,0,1,0,0,5,0,0,0,1\n\n[Events]\n"
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    return head + "\n".join(ev) + "\n"


def render(ass_text: str, out: Path) -> Path:
    a = out.with_suffix(".ass")
    a.write_text(ass_text, encoding="utf-8")
    sub = str(a).replace("\\", "/").replace(":", r"\:")
    fdir = str(FONTS).replace("\\", "/").replace(":", r"\:")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=black@0.0:s={W}x{H}:d=1,format=rgba",
         "-vf", f"subtitles='{sub}':fontsdir='{fdir}':alpha=1",
         "-frames:v", "1", str(out)], capture_output=True, **_NOWIN)
    return out


def ssim_full(a: Path, b: Path) -> float:
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-y",
         "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:d=1",
         "-i", str(a), "-i", str(b),
         "-filter_complex",
         "[0:v]split=2[b1][b2];"
         "[b1][1:v]overlay=0:0:format=auto,crop=1080:600:0:1000,format=gray[x];"
         "[b2][2:v]overlay=0:0:format=auto,crop=1080:600:0:1000,format=gray[y];"
         "[x][y]ssim",
         "-frames:v", "1", "-f", "null", "-"],
        capture_output=True, text=True, **_NOWIN)
    m = re.search(r"All:([0-9.]+)", r.stderr or "")
    return float(m.group(1)) if m else -1.0


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cues = json.loads((OV / "public" / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = cues if isinstance(cues, list) else (cues.get("cues") or [])
    frames = sorted(set([0] + [int(c["startMs"] / 1000 * FPS) + 1 for c in cues]))

    rows, scores = [], []
    for i, fr in enumerate(frames):
        ref = STILLS / f"state_{i:03d}.png"
        if not ref.exists():
            continue
        cue = None
        for c in cues:
            if c["startMs"] / 1000 * FPS <= fr <= c["endMs"] / 1000 * FPS:
                cue = c
                break
        if cue is None:
            continue
        local = fr - cue["startMs"] / 1000 * FPS
        out = render(build_ass(cue, local), OUT / f"port_{i:03d}.png")
        s = ssim_full(ref, out)
        preset = cue.get("preset", "?")
        scores.append(s)
        rows.append({"estado": i, "frame": fr, "preset": preset, "ssim": round(s, 4)})
        print(f"  estado {i:2d} (f{fr:4d}) {preset:12s} SSIM {s:.4f}")

    if scores:
        print(f"\n  media {statistics.mean(scores):.4f} | mediana {statistics.median(scores):.4f} "
              f"| pior {min(scores):.4f} | melhor {max(scores):.4f}  ({len(scores)} estados)")
        rows.append({"estado": "MEDIA", "ssim": round(statistics.mean(scores), 4)})
        rows.append({"estado": "MEDIANA", "ssim": round(statistics.median(scores), 4)})
    save(rows, "phase10_port.csv")
