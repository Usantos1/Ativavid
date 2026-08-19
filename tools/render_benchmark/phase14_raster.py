# -*- coding: utf-8 -*-
"""EXPERIMENTO 6 — rasterizador com caixa de texto de verdade.

O porte para ASS reprovou (0,72) porque o ASS nao tem o modelo de caixa do
CSS. Aqui a mesma logica de StackedCaptions.tsx e desenhada com um
rasterizador que controla metrica por glifo, gradiente e desfoque:

  - fitFont, lineStyles, letterSpacing, lineHeight, recuo de -0.34em
  - WHITE_GRAD (gradiente 180deg branco -> #cfcfcf) por mascara
  - drop-shadow(0 5px 9px rgba(0,0,0,.5)) por desfoque gaussiano
  - opacidade por palavra

Roda no venv isolado do benchmark. Nao toca o produto.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

BENCH = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad\bench")
OV = BENCH / "ov_remotion"
OUT = BENCH / "raster"
FONTS = BENCH / "fonts"
W, H, FPS = 1080, 1920, 30

OFFSET_Y, FONT_SCALE = 0.156, 1.0
SCALE = (W / 1080) * FONT_SCALE
AVAIL = W - 180
BASE_Y = round(H * OFFSET_Y)
LETTER_SPACING = -1.5
LINE_HEIGHT = 1.12
MARGIN_TOP_EM = -0.34
WORD_PAD_EM = 0.06          # padding: '0 0.06em' de cada palavra
SHADOW = (0, 5, 9, 0.5)     # dx, dy, blur, alpha

FONT_FILE = {
    0: ("Poppins-BlackItalic.ttf", None),
    1: ("Poppins-Regular.ttf", None),
    2: ("PlayfairDisplay-Italic[wght].ttf", "#ff5200"),
    3: ("Poppins-ExtraBold.ttf", None),
}
_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(idx: int, size: int) -> ImageFont.FreeTypeFont:
    name = FONT_FILE[idx][0]
    key = (name, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONTS / name), size)
    return _cache[key]


def fit_font(text: str, base: int = 86, avail: float = AVAIL / SCALE, factor: float = 0.58) -> int:
    n = max(1, len(text.strip()))
    return int(avail // (n * factor)) if n * base * factor > avail else base


def size_for(txt: str, idx: int, emph: bool, boost: bool) -> int:
    s = fit_font(txt)
    if idx == 1:
        s = round(s * 0.72)
    if idx == 2:
        s = round(s * 0.95)
    if emph:
        s = round(s * 1.12)
    if boost:
        s = round(s * 1.35)
    return s


def word_opacity(w: dict, cue: dict, fl: float, enter: int) -> float:
    st = ((w["fromMs"] - cue["startMs"]) / 1000) * FPS
    if fl <= st:
        return 0.0
    p = min(1.0, (fl - st) / max(1, enter))
    return 1 - (1 - p) ** 3


def text_width(f: ImageFont.FreeTypeFont, s: str) -> float:
    """Largura com letter-spacing aplicado entre glifos (como o CSS)."""
    if not s:
        return 0.0
    return f.getlength(s) + LETTER_SPACING * len(s)


def draw_tracked(d: ImageDraw.ImageDraw, xy, s: str, f, fill) -> None:
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + LETTER_SPACING


def gradient_mask(size: tuple[int, int]) -> Image.Image:
    """linear-gradient(180deg,#fff 0%,#fff 46%,#cfcfcf 100%)."""
    w, h = size
    g = Image.new("L", (1, h))
    px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        v = 255 if t <= 0.46 else 255 - int((t - 0.46) / 0.54 * (255 - 0xCF))
        px[0, y] = v
    return g.resize((w, h))


def render_state(cue: dict, fl: float, out: Path) -> Path:
    dur = (cue["endMs"] - cue["startMs"]) / 1000 * FPS
    enter = max(3, min(8, int(dur * 0.45)))

    linhas = []
    for li, line in enumerate(cue["lines"]):
        idx = (cue.get("lineStyles") or [None] * 9)[li]
        if idx is None:
            idx = (li + cue.get("styleOffset", 0)) % 4
        txt = " ".join(w["text"] for w in line)
        sz = size_for(txt, idx, (cue.get("lineEmph") or [False] * 9)[li],
                      (cue.get("lineBoost") or [False] * 9)[li])
        linhas.append({"idx": idx, "size": sz, "words": line})

    alturas = [ln["size"] * LINE_HEIGHT for ln in linhas]
    total = alturas[0] if alturas else 0
    for i in range(1, len(alturas)):
        total += alturas[i] + MARGIN_TOP_EM * linhas[i]["size"]
    top = (H / 2 + BASE_Y) - total / 2

    glyphs = Image.new("L", (W, H), 0)      # mascara do texto
    gd = ImageDraw.Draw(glyphs)
    colored: list[tuple[Image.Image, Image.Image]] = []

    y = top
    for li, ln in enumerate(linhas):
        if li > 0:
            y += MARGIN_TOP_EM * ln["size"]
        f = font(ln["idx"], ln["size"])
        pad = WORD_PAD_EM * ln["size"]
        # Entre palavras entra o espaco do texto alem do padding de cada span:
        # so o padding deixava as linhas ~13% estreitas frente a referencia.
        gap = f.getlength(" ")
        larguras = [text_width(f, w["text"]) + 2 * pad for w in ln["words"]]
        larguras = [wl + (gap if i < len(larguras) - 1 else 0)
                    for i, wl in enumerate(larguras)]
        x = (W - sum(larguras)) / 2
        asc, desc = f.getmetrics()
        # Meia-entrelinha do CSS: a caixa de linha tem lineHeight*S de altura e
        # o texto ocupa (ascent+descent), nao S. Usar S deslocava tudo ~20px.
        base = y + (alturas[li] - (asc + desc)) / 2
        for w, wl in zip(ln["words"], larguras):
            op = word_opacity(w, cue, fl, enter)
            if op > 0.01:
                tmp = Image.new("L", (W, H), 0)
                draw_tracked(ImageDraw.Draw(tmp), (x + pad, base), w["text"], f, 255)
                if op < 0.995:
                    tmp = tmp.point(lambda v, o=op: int(v * o))
                glyphs = ImageChops.lighter(glyphs, tmp)
                gd = ImageDraw.Draw(glyphs)
            x += wl
        y += alturas[li]

    # cor: gradiente branco ou cor chapada do estilo
    idx0 = linhas[0]["idx"] if linhas else 3
    cor_fixa = FONT_FILE[idx0][1]
    if cor_fixa:
        fill = Image.new("RGB", (W, H), cor_fixa)
    else:
        bbox = glyphs.getbbox()
        fill = Image.new("RGB", (W, H), "#ffffff")
        if bbox:
            gh = bbox[3] - bbox[1]
            grad = gradient_mask((W, gh)).convert("RGB")
            fill.paste(grad, (0, bbox[1]))

    # sombra: desfoque gaussiano deslocado
    dx, dy, blur, sa = SHADOW
    sh = glyphs.filter(ImageFilter.GaussianBlur(blur / 2))
    shadow_a = Image.new("L", (W, H), 0)
    shadow_a.paste(sh, (dx, dy))
    shadow_a = shadow_a.point(lambda v: int(v * sa))

    # Sombra: preto com o alpha desfocado. Texto: cor com alpha dos glifos.
    # `paste` com mascara NAO escreve o canal alpha — precisa de merge, senao
    # a camada de texto sai transparente e sobra so a sombra preta.
    shadow_img = Image.merge("RGBA", (
        Image.new("L", (W, H), 0), Image.new("L", (W, H), 0),
        Image.new("L", (W, H), 0), shadow_a))
    txt_layer = Image.merge("RGBA", (*fill.split(), glyphs))
    img = Image.alpha_composite(shadow_img, txt_layer)
    img.save(out)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cues = json.loads((OV / "public" / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = cues if isinstance(cues, list) else (cues.get("cues") or [])
    frames = sorted(set([0] + [int(c["startMs"] / 1000 * FPS) + 1 for c in cues]))
    import time

    t0 = time.perf_counter()
    n = 0
    for i, fr in enumerate(frames):
        cue = next((c for c in cues
                    if c["startMs"] / 1000 * FPS <= fr <= c["endMs"] / 1000 * FPS), None)
        if cue is None:
            continue
        render_state(cue, fr - cue["startMs"] / 1000 * FPS, OUT / f"rast_{i:03d}.png")
        n += 1
    el = time.perf_counter() - t0
    print(f"{n} estados em {el:.2f}s ({el / max(1, n) * 1000:.0f} ms cada)")
