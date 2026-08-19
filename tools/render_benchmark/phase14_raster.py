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
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

BENCH = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad\bench")
OV = BENCH / "ov_remotion3"
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
# drop-shadow por estilo (SHADOW / SHADOW_STRONG do template): dx, dy, blur, alpha
BLUR_K = float(os.environ.get("RAST_BLUR_K", "1.05"))
SHADOW = [(0, 5, 9, 0.5)]
SHADOW_STRONG = [(0, 5, 10, 0.55), (0, 2, 3, 0.55)]

FONT_FILE = {
    0: ("Poppins-BlackItalic.ttf", None),
    1: ("Poppins-Regular.ttf", None),
    2: ("PlayfairDisplay-Italic[wght].ttf", "#ff5200"),
    3: ("Poppins-ExtraBold.ttf", None),
}
_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


# Peso do eixo variavel por estilo (LINE_STYLES do template).
FONT_WGHT = {2: 900}


def font(idx: int, size: int) -> ImageFont.FreeTypeFont:
    name = FONT_FILE[idx][0]
    key = (name, size)
    if key not in _cache:
        f = ImageFont.truetype(str(FONTS / name), size)
        w = FONT_WGHT.get(idx)
        if w:
            try:
                f.set_variation_by_axes([w])
            except (OSError, AttributeError):
                pass
        _cache[key] = f
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
    """Posiciona cada glifo pelo avanco COM kerning.

    Somar getlength(ch) ignora os pares de kerning, enquanto a largura usada
    para centralizar (getlength da string inteira) os inclui: o desenho saia
    fora do centro que a propria medida pediu.
    """
    x, y = xy
    for i, ch in enumerate(s):
        d.text((x, y), ch, font=f, fill=fill)
        x = xy[0] + f.getlength(s[: i + 1]) + LETTER_SPACING * (i + 1)


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

    glyphs = Image.new("L", (W, H), 0)      # mascara do texto (para a sombra)
    # No template cada LINHA tem o proprio fill (LINE_STYLES): gradiente branco
    # ou a cor do estilo. Pintar a imagem toda com o estilo da 1a linha deixava
    # a linha Playfair branca em vez de laranja.
    # (mascara, estilo, topo da caixa de linha, altura da caixa) por PALAVRA:
    # no template o filter e o background-clip:text estao no span de cada
    # palavra, e o gradiente usa a CAIXA da linha, nao a mancha de tinta.
    por_palavra: list[tuple[Image.Image, int, float, float]] = []

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
                por_palavra.append((tmp, ln["idx"], y, alturas[li]))
            x += wl
        y += alturas[li]

    def camada_cor(idx: int, topo: float, alt: float) -> Image.Image:
        cor_fixa = FONT_FILE[idx][1]
        if cor_fixa:
            return Image.new("RGB", (W, H), cor_fixa)
        c = Image.new("RGB", (W, H), "#ffffff")
        h = max(1, int(round(alt)))
        c.paste(gradient_mask((W, h)).convert("RGB"), (0, int(round(topo))))
        return c

    def sombra(mask_w: Image.Image, idx: int) -> Image.Image:
        """Empilha os drop-shadows do estilo; o estilo 1 leva dois no template."""
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if os.environ.get("RAST_NO_SHADOW") == "1":
            return out
        for dx, dy, blur, sa in (SHADOW_STRONG if idx == 1 else SHADOW):
            a = Image.new("L", (W, H), 0)
            a.paste(mask_w.filter(ImageFilter.GaussianBlur(blur * BLUR_K)), (dx, dy))
            a = a.point(lambda v, k=sa: int(v * k))
            preto = Image.new("L", (W, H), 0)
            out = Image.alpha_composite(out, Image.merge("RGBA", (preto, preto, preto, a)))
        return out

    # Cada linha pinta sombra + texto na ordem do DOM: com o recuo negativo as
    # linhas se sobrepoem, e a de baixo cobre a sombra da de cima.
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for mask_w, idx, topo, alt in por_palavra:
        if not mask_w.getbbox():
            continue
        img = Image.alpha_composite(img, sombra(mask_w, idx))
        img = Image.alpha_composite(
            img, Image.merge("RGBA", (*camada_cor(idx, topo, alt).split(), mask_w)))
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
