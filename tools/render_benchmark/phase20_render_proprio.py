# -*- coding: utf-8 -*-
"""EXPERIMENTO — renderizador proprio de legenda, sem navegador.

A pergunta nao e mais "da para imitar o Remotion pixel a pixel" (isso reprovou
em 0,823 e o motivo era perseguir o Chrome). A pergunta agora e: **sendo nos os
donos do visual, quanto tempo custa?**

Arquitetura medida aqui, que e a que um renderizador de verdade usaria:

  1. layout de cada legenda calculado UMA vez (fonte, tamanho, posicao) —
     nao por quadro;
  2. mascara de cada palavra rasterizada uma vez e guardada recortada;
  3. por quadro, so a composicao alpha DENTRO da caixa do texto — o resto do
     quadro e transparente e nao custa nada;
  4. quadro vai direto para o ffmpeg por pipe, sem PNG no disco.

O prototipo anterior fazia operacao de tela inteira por palavra: 113 ms por
quadro, e por isso parecia lento. Nao era o desenho, era o desperdicio.

Nao toca em producao: le insumos de um scaffold e escreve em area temporaria.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BENCH = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
FONTS = BENCH / "bench" / "fonts"
W, H, FPS = 1080, 1920, 30

# --- os mesmos parametros do estilo padrao (StackedCaptions) -----------------
OFFSET_Y, FONT_SCALE = 0.156, 1.0
SCALE = (W / 1080) * FONT_SCALE
AVAIL = W - 180
BASE_Y = round(H * OFFSET_Y)
LETTER_SPACING = -1.5
LINE_HEIGHT = 1.12
MARGIN_TOP_EM = -0.34
WORD_PAD_EM = 0.06
BLUR_K = 1.05
SHADOW = [(0, 5, 9, 0.5)]
SHADOW_STRONG = [(0, 5, 10, 0.55), (0, 2, 3, 0.55)]
ENTER_MIN, ENTER_MAX = 3, 8

FONT_FILE = {
    0: ("Poppins-BlackItalic.ttf", None),
    1: ("Poppins-Regular.ttf", None),
    2: ("PlayfairDisplay-Italic[wght].ttf", "#ff5200"),
    3: ("Poppins-ExtraBold.ttf", None),
}
FONT_WGHT = {2: 900}
FONT_FILE[4] = ("Poppins-Black.ttf", None)   # Recorte: Poppins 900 reto
# A cor de enfase e da MARCA, nao do codigo: vem de captions.emphasisAccent.
# Deixar o laranja padrao chumbado fazia a linha Playfair sair laranja onde o
# projeto pede vermelho.
def usar_config(edit_data: dict) -> None:
    caps = (edit_data or {}).get("captions") or {}
    accent = caps.get("emphasisAccent")
    if accent:
        FONT_FILE[2] = (FONT_FILE[2][0], accent)

_cache_font: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(idx: int, size: int) -> ImageFont.FreeTypeFont:
    nome = FONT_FILE[idx][0]
    chave = (nome, size)
    if chave not in _cache_font:
        f = ImageFont.truetype(str(FONTS / nome), size)
        if FONT_WGHT.get(idx):
            try:
                f.set_variation_by_axes([FONT_WGHT[idx]])
            except (OSError, AttributeError):
                pass
        _cache_font[chave] = f
    return _cache_font[chave]


def fit_font(texto: str, base: int = 86, avail: float = AVAIL / SCALE, fator: float = 0.58) -> int:
    n = max(1, len(texto.strip()))
    return int(avail // (n * fator)) if n * base * fator > avail else base


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


def gradiente(altura: int) -> np.ndarray:
    """linear-gradient(180deg,#fff 0%,#fff 46%,#cfcfcf 100%) como coluna."""
    t = np.linspace(0.0, 1.0, max(1, altura), dtype=np.float32)
    v = np.where(t <= 0.46, 255.0, 255.0 - (t - 0.46) / 0.54 * (255 - 0xCF))
    return v.astype(np.float32)


# ---------------------------------------------------------------- layout ----
@dataclass
class Palavra:
    """Mascara ja rasterizada e recortada; por quadro so muda a opacidade."""
    x0: int
    y0: int
    rgb: np.ndarray        # (h, w, 3) float32 — cor ja resolvida
    alpha: np.ndarray      # (h, w) float32 0..1 — glifo
    sombra: np.ndarray     # (h, w) float32 0..1 — sombra ja desfocada
    inicio_f: float        # quadro (relativo a cue) em que a palavra entra
    enter: int
    # Elemento que nao "entra" com fade e sim vale num intervalo de quadros —
    # e o caso do traco do Recorte, que e um estagio por quadro.
    janela: tuple[float, float] | None = None
    # Entrada do template: a palavra SOBE enquanto aparece (translate 46->0,
    # acoplado a opacidade). Ignorar isso deixava a entrada visivelmente dura.
    sobe: float = 46.0


@dataclass
class Legenda:
    inicio_f: int
    fim_f: int
    palavras: list[Palavra] = field(default_factory=list)
    # Saida da legenda inteira (exit "blur_up"): a partir de `saida_f` ela
    # sobe, desbota e desfoca. Sem isto a legenda ficava na tela depois da
    # hora — foi a primeira diferenca visivel contra o Remotion.
    saida_f: float = 1e9
    dur_f: float = 0.0
    exit_abrupto: bool = False
    exit_fade: bool = False        # headline: sai so com fade, sem subir/desfocar
    caixa: tuple[int, int, int, int] | None = None
    cache_chave: tuple | None = None
    cache_tela: np.ndarray | None = None
    cache_pronto: np.ndarray | None = None   # a mesma tela ja convertida (uint8)

    def saida(self, fl: float) -> tuple[float, float, float]:
        """(opacidade, deslocamento vertical, desfoque) no quadro `fl`."""
        if self.exit_abrupto:
            return (0.0 if fl >= self.dur_f - 2 else 1.0), 0.0, 0.0
        if fl <= self.saida_f:
            return 1.0, 0.0, 0.0
        p = min(1.0, (fl - self.saida_f) / max(1e-6, self.dur_f - self.saida_f))
        if self.exit_fade:
            return 1.0 - p, 0.0, 0.0
        return 1.0 - p, -55.0 * p, 14.0 * p


def _mascara_palavra(f, texto: str, ls: float = LETTER_SPACING) -> np.ndarray:
    """Rasteriza o texto com letter-spacing, recortado no bbox da tinta."""
    larg = int(f.getlength(texto) + ls * len(texto)) + 8
    asc, desc = f.getmetrics()
    img = Image.new("L", (max(1, larg), asc + desc + 8), 0)
    d = ImageDraw.Draw(img)
    x = 0.0
    for i, ch in enumerate(texto):
        d.text((x, 0), ch, font=f, fill=255)
        x = f.getlength(texto[: i + 1]) + ls * (i + 1)
    return np.asarray(img, dtype=np.float32) / 255.0


def montar(cue: dict) -> Legenda:
    """Todo o custo de layout acontece AQUI, uma vez por legenda."""
    ini_f = int(cue["startMs"] / 1000 * FPS)
    fim_f = int(cue["endMs"] / 1000 * FPS)
    dur = (cue["endMs"] - cue["startMs"]) / 1000 * FPS
    enter = max(ENTER_MIN, min(ENTER_MAX, int(dur * 0.45)))

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
    topo = (H / 2 + BASE_Y) - total / 2

    leg = Legenda(ini_f, fim_f)
    # exitStart do template: max(dur-EXIT, min(ultimaEntrada+ENTER, dur-2))
    EXIT = max(2, min(7, int(dur * 0.35)))
    ultima = max((w["fromMs"] - cue["startMs"]) / 1000 * FPS
                 for ln in cue["lines"] for w in ln)
    leg.dur_f = dur
    leg.exit_abrupto = cue.get("exit") == "abrupt"
    leg.saida_f = max(dur - EXIT, min(ultima + enter, dur - 2))
    y = topo
    for li, ln in enumerate(linhas):
        if li > 0:
            y += MARGIN_TOP_EM * ln["size"]
        f = font(ln["idx"], ln["size"])
        pad = WORD_PAD_EM * ln["size"]
        gap = f.getlength(" ")
        larguras = [f.getlength(w["text"]) + LETTER_SPACING * len(w["text"]) + 2 * pad
                    for w in ln["words"]]
        larguras = [wl + (gap if i < len(larguras) - 1 else 0)
                    for i, wl in enumerate(larguras)]
        x = (W - sum(larguras)) / 2
        asc, desc = f.getmetrics()
        base = y + (alturas[li] - (asc + desc)) / 2
        cor_fixa = FONT_FILE[ln["idx"]][1]
        for w, wl in zip(ln["words"], larguras):
            m = _mascara_palavra(f, w["text"])
            h_m, w_m = m.shape
            x0, y0 = int(round(x + pad)), int(round(base))
            # sombra: desfoque da propria mascara, com folga na borda
            folga = 24
            pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga), dtype=np.float32)
            pad_m[folga:folga + h_m, folga:folga + w_m] = m
            sombra = np.zeros_like(pad_m)
            for dx, dy, blur, sa in (SHADOW_STRONG if ln["idx"] == 1 else SHADOW):
                b = np.asarray(Image.fromarray((pad_m * 255).astype(np.uint8))
                               .filter(ImageFilter.GaussianBlur(blur * BLUR_K)),
                               dtype=np.float32) / 255.0
                deslocada = np.zeros_like(b)
                deslocada[max(0, dy):, max(0, dx):] = b[:b.shape[0] - max(0, dy),
                                                        :b.shape[1] - max(0, dx)]
                sombra = np.maximum(sombra, deslocada * sa)
            alpha = np.zeros_like(pad_m)
            alpha[folga:folga + h_m, folga:folga + w_m] = m
            # cor: chapada ou gradiente da CAIXA da linha
            if cor_fixa:
                c = np.array([int(cor_fixa[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32)
                rgb = np.broadcast_to(c, (*alpha.shape, 3)).copy()
            else:
                col = gradiente(int(round(alturas[li])))
                off = int(round(y0 - folga - y))
                idxs = np.clip(np.arange(alpha.shape[0]) + off, 0, len(col) - 1)
                rgb = np.repeat(col[idxs][:, None, None], 3, axis=2) * np.ones(
                    (1, alpha.shape[1], 1), dtype=np.float32)
            leg.palavras.append(Palavra(
                x0 - folga, y0 - folga, rgb, alpha, sombra,
                inicio_f=(w["fromMs"] - cue["startMs"]) / 1000 * FPS, enter=enter))
            x += wl
        y += alturas[li]
    return leg


def opacidade(p: Palavra, fl: float) -> float:
    if p.janela is not None:
        ini, fim = p.janela
        return 1.0 if ini <= fl < fim else 0.0
    if fl <= p.inicio_f:
        return 0.0
    t = min(1.0, (fl - p.inicio_f) / max(1, p.enter))
    return 1 - (1 - t) ** 3


def caixa_de(legendas: list["Legenda"], folga: int = 8) -> tuple[int, int, int, int]:
    """Uniao das caixas de TODAS as legendas, com folga.

    As legendas vivem sempre na mesma faixa da tela. Renderizar e transmitir a
    tela inteira e desperdicio puro: sao 8,3 MB por quadro no cano, contra ~2
    MB da faixa que realmente tem texto.
    """
    if not legendas:
        return 0, 0, W, H
    x0 = min(p.x0 for l in legendas for p in l.palavras)
    y0 = min(p.y0 for l in legendas for p in l.palavras)
    x1 = max(p.x0 + p.alpha.shape[1] for l in legendas for p in l.palavras)
    y1 = max(p.y0 + p.alpha.shape[0] for l in legendas for p in l.palavras)
    # largura par: o encoder reclama de dimensao impar
    x0, y0 = max(0, x0 - folga), max(0, y0 - folga)
    x1, y1 = min(W, x1 + folga), min(H, y1 + folga)
    if (x1 - x0) % 2:
        x1 = min(W, x1 + 1) if x1 < W else x1 - 1
    if (y1 - y0) % 2:
        y1 = min(H, y1 + 1) if y1 < H else y1 - 1
    return x0, y0, x1, y1


def _caixa_leg(leg: "Legenda") -> tuple[int, int, int, int]:
    """Caixa fixa da legenda inteira (todas as palavras) — e o dominio do
    cache: dimensao estavel permite reusar o composto entre quadros."""
    if leg.caixa is None:
        x0 = max(0, min(p.x0 for p in leg.palavras))
        y0 = max(0, min(p.y0 for p in leg.palavras))
        x1 = min(W, max(p.x0 + p.alpha.shape[1] for p in leg.palavras))
        y1 = min(H, max(p.y0 + p.alpha.shape[0] for p in leg.palavras))
        leg.caixa = (x0, y0, max(x0 + 1, x1), max(y0 + 1, y1))
    return leg.caixa


def _blend_palavra(tela: np.ndarray, p: "Palavra", op: float,
                   x0: int, y0: int) -> None:
    """Compoe uma palavra (sombra + texto) PRE-MULTIPLICADA em `tela`."""
    h, w = p.alpha.shape
    desloc = int(round(p.sobe * (1.0 - op))) if p.janela is None else 0
    py, px = p.y0 - y0 + desloc, p.x0 - x0
    alt_t, larg_t = tela.shape[0], tela.shape[1]
    ys0, xs0 = max(0, py), max(0, px)
    ys1, xs1 = min(alt_t, py + h), min(larg_t, px + w)
    if ys1 <= ys0 or xs1 <= xs0:
        return
    sy, sx = ys0 - py, xs0 - px
    alt, larg = ys1 - ys0, xs1 - xs0
    sub = tela[ys0:ys1, xs0:xs1]
    a_s = p.sombra[sy:sy + alt, sx:sx + larg] * op
    a_t = p.alpha[sy:sy + alt, sx:sx + larg] * op
    rgb = p.rgb[sy:sy + alt, sx:sx + larg]
    inv = 1.0 - a_s
    sub[..., :3] *= inv[..., None]
    sub[..., 3] = sub[..., 3] * inv + a_s
    inv = 1.0 - a_t
    sub[..., :3] = sub[..., :3] * inv[..., None] + rgb * a_t[..., None]
    sub[..., 3] = sub[..., 3] * inv + a_t


def _converter(tela: np.ndarray) -> np.ndarray:
    """Premultiplicado float -> RGBA alpha direto uint8."""
    a = np.clip(tela[..., 3:4], 0.0, 1.0)
    rgb = np.clip(tela[..., :3] / np.maximum(a, 1e-6), 0.0, 255.0)
    out = np.empty(tela.shape, dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = a[..., 0] * 255.0
    return out.astype(np.uint8)


def _blend_palavra_em(sub: np.ndarray, p: "Palavra", op: float,
                      abs_x0: int, abs_y0: int) -> None:
    """Como _blend_palavra, mas com origem absoluta arbitraria."""
    h, w = p.alpha.shape
    desloc = int(round(p.sobe * (1.0 - op))) if p.janela is None else 0
    py, px = p.y0 - abs_y0 + desloc, p.x0 - abs_x0
    ys0, xs0 = max(0, py), max(0, px)
    ys1, xs1 = min(sub.shape[0], py + h), min(sub.shape[1], px + w)
    if ys1 <= ys0 or xs1 <= xs0:
        return
    sy, sx = ys0 - py, xs0 - px
    alt, larg = ys1 - ys0, xs1 - xs0
    dst = sub[ys0:ys1, xs0:xs1]
    a_s = p.sombra[sy:sy + alt, sx:sx + larg] * op
    a_t = p.alpha[sy:sy + alt, sx:sx + larg] * op
    rgb = p.rgb[sy:sy + alt, sx:sx + larg]
    inv = 1.0 - a_s
    dst[..., :3] *= inv[..., None]
    dst[..., 3] = dst[..., 3] * inv + a_s
    inv = 1.0 - a_t
    dst[..., :3] = dst[..., :3] * inv[..., None] + rgb * a_t[..., None]
    dst[..., 3] = dst[..., 3] * inv + a_t


def _blit(pronto8: np.ndarray, leg: "Legenda", buf: np.ndarray,
          sujo: list[int], bx0: int, by0: int, bx1: int, by1: int,
          dy: int, mesclar: bool) -> None:
    """Escreve/mescla o retangulo pronto (uint8 alpha direto) no buffer."""
    dy0, dy1 = by0 + dy, by1 + dy
    corte0 = max(0, -dy0)
    dy0, dy1 = max(0, dy0), min(buf.shape[0], dy1)
    if dy1 <= dy0:
        return
    pedaco = pronto8[corte0:corte0 + (dy1 - dy0)]
    if mesclar:
        fundo = buf[dy0:dy1, bx0:bx1].astype(np.float32)
        pf = pedaco.astype(np.float32)
        a_f = pf[..., 3:4] / 255.0
        a_b = fundo[..., 3:4] / 255.0
        a_o = a_f + a_b * (1.0 - a_f)
        rgb = (pf[..., :3] * a_f + fundo[..., :3] * a_b * (1.0 - a_f))             / np.maximum(a_o, 1e-6)
        buf[dy0:dy1, bx0:bx1] = np.clip(
            np.concatenate([rgb, a_o * 255.0], axis=2), 0, 255).astype(np.uint8)
    else:
        buf[dy0:dy1, bx0:bx1] = pedaco
    sujo[0] = min(sujo[0], bx0) if sujo[2] > sujo[0] else bx0
    sujo[1] = min(sujo[1], dy0) if sujo[3] > sujo[1] else dy0
    sujo[2] = max(sujo[2], bx1)
    sujo[3] = max(sujo[3], dy1)


def desenhar(leg: "Legenda | None", fl: float, buf: np.ndarray,
             sujo: list[int], origem: tuple[int, int] = (0, 0),
             mesclar: bool = False) -> None:
    """Compoe a legenda no quadro `fl` dentro de `buf` (uint8 H x W x 4).

    Duas economias, ambas apontadas por perfil:
      - so a caixa da legenda e tocada, nunca a tela inteira;
      - as palavras JA ASSENTADAS (opacidade 1, sem deslocamento) sao
        compostas UMA vez e guardadas na propria legenda; por quadro so as
        que estao animando entram por cima. Sem isso, um quadro com uma
        palavra entrando recompunha as dez paradas junto.
    """
    if not mesclar:
        if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
            buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
        sujo[:] = [0, 0, 0, 0]
    if leg is None:
        return
    op_cue, dy_cue, blur_cue = leg.saida(fl)
    if op_cue <= 0.004:
        return

    assentadas: list[Palavra] = []
    animando: list[tuple[Palavra, float]] = []
    for p in leg.palavras:
        op = opacidade(p, fl)
        if op <= 0.004:
            continue
        if op >= 0.996 and (p.janela is None or True):
            assentadas.append(p)
        else:
            animando.append((p, op))
    if not assentadas and not animando:
        return

    ox, oy = origem
    x0, y0, x1, y1 = _caixa_leg(leg)
    # recorta ao buffer (que pode ser so a faixa da legenda)
    bx0, by0 = max(0, x0 - ox), max(0, y0 - oy)
    bx1 = min(buf.shape[1], x1 - ox)
    by1 = min(buf.shape[0], y1 - oy)
    if bx1 <= bx0 or by1 <= by0:
        return

    chave = tuple(id(p) for p in assentadas)
    if chave != leg.cache_chave:
        base = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.float32)
        for p in assentadas:
            _blend_palavra(base, p, 1.0, x0, y0)
        leg.cache_chave, leg.cache_tela = chave, base
        leg.cache_pronto = _converter(base)
    tela = leg.cache_tela

    # Caminho rapido: sem saida em curso, converter SO o retangulo das
    # palavras que estao animando — o perfil mostrou a conversao da caixa
    # inteira comendo 24 ms/quadro para animar uma palavra.
    if (not animando) and op_cue >= 0.996 and blur_cue <= 0.25 and abs(dy_cue) < 0.5:
        # tudo assentado: o retangulo convertido ja esta pronto no cache
        _blit(leg.cache_pronto, leg, buf, sujo, bx0, by0, bx1, by1, 0, mesclar)
        return
    if animando and op_cue >= 0.996 and blur_cue <= 0.25 and abs(dy_cue) < 0.5:
        pronto8 = leg.cache_pronto.copy()
        ax0 = min(max(0, p.x0 - x0) for p, _ in animando)
        ay0 = min(max(0, p.y0 - y0 - int(p.sobe)) for p, _ in animando)
        ax1 = max(min(x1 - x0, p.x0 - x0 + p.alpha.shape[1]) for p, _ in animando)
        ay1 = max(min(y1 - y0, p.y0 - y0 + p.alpha.shape[0] + int(p.sobe) + 1)
                  for p, _ in animando)
        if ax1 > ax0 and ay1 > ay0:
            sub = tela[ay0:ay1, ax0:ax1].copy()
            for p, op in animando:
                _blend_palavra_em(sub, p, op, x0 + ax0, y0 + ay0)
            pronto8[ay0:ay1, ax0:ax1] = np.clip(_converter(sub), 0, 255)
        _blit(pronto8, leg, buf, sujo, bx0, by0, bx1, by1, 0, mesclar)
        return

    if animando:
        tela = tela.copy()
        for p, op in animando:
            _blend_palavra(tela, p, op, x0, y0)

    if blur_cue > 0.25:
        tela = np.asarray(
            Image.fromarray(np.clip(tela * [1, 1, 1, 255], 0, 255).astype(np.uint8),
                            mode="RGBA").filter(ImageFilter.GaussianBlur(blur_cue / 2)),
            dtype=np.float32)
        tela[..., 3] /= 255.0

    # premultiplicado -> alpha direto, com a opacidade da cue aplicada
    a = np.clip(tela[..., 3:4], 0.0, 1.0)
    rgb = np.clip(tela[..., :3] / np.maximum(a, 1e-6), 0.0, 255.0)
    saida_px = np.empty((tela.shape[0], tela.shape[1], 4), dtype=np.float32)
    saida_px[..., :3] = rgb
    saida_px[..., 3] = a[..., 0] * (255.0 * op_cue)

    dy = int(round(dy_cue))
    dy0, dy1 = by0 + dy, by1 + dy
    corte0 = max(0, -dy0)
    dy0, dy1 = max(0, dy0), min(buf.shape[0], dy1)
    if dy1 <= dy0:
        return
    pronto = saida_px[corte0:corte0 + (dy1 - dy0)]
    if mesclar:
        fundo = buf[dy0:dy1, bx0:bx1].astype(np.float32)
        a_f = pronto[..., 3:4] / 255.0
        a_b = fundo[..., 3:4] / 255.0
        a_o = a_f + a_b * (1.0 - a_f)
        out_rgb = (pronto[..., :3] * a_f + fundo[..., :3] * a_b * (1.0 - a_f))             / np.maximum(a_o, 1e-6)
        buf[dy0:dy1, bx0:bx1] = np.clip(
            np.concatenate([out_rgb, a_o * 255.0], axis=2), 0, 255).astype(np.uint8)
        sujo[0] = min(sujo[0], bx0) if sujo[2] > sujo[0] else bx0
        sujo[1] = min(sujo[1], dy0) if sujo[3] > sujo[1] else dy0
        sujo[2] = max(sujo[2], bx1)
        sujo[3] = max(sujo[3], dy1)
    else:
        buf[dy0:dy1, bx0:bx1] = np.clip(pronto, 0, 255).astype(np.uint8)
        sujo[:] = [bx0, dy0, bx1, dy1]


def renderizar(cues: list[dict], n_frames: int, saida: Path) -> float:
    legendas = [montar(c) for c in cues]
    t0 = time.perf_counter()
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "prores_ks", "-profile:v", "4444",
         "-pix_fmt", "yuva444p10le", str(saida)],
        stdin=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    buf = np.zeros((H, W, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    atual = 0
    for f in range(n_frames):
        while atual < len(legendas) and legendas[atual].fim_f < f:
            atual += 1
        leg = (legendas[atual]
               if atual < len(legendas) and legendas[atual].inicio_f <= f else None)
        desenhar(leg, f - (leg.inicio_f if leg else 0), buf, sujo)
        ff.stdin.write(buf.tobytes())
    ff.stdin.close()
    ff.wait()
    return time.perf_counter() - t0


if __name__ == "__main__":
    public = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        BENCH / "prova_real" / "remotion" / "public")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    ed = public / "edit-data.json"
    if ed.exists():
        usar_config(json.loads(ed.read_text(encoding="utf-8-sig")))
    dados = json.loads((public / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = dados if isinstance(dados, list) else (dados.get("cues") or [])
    saida = BENCH / "overlay_nosso.mov"
    el = renderizar(cues, n, saida)
    mb = saida.stat().st_size / 1024 / 1024 if saida.exists() else 0
    print(f"  {n} quadros em {el:.2f}s  =  {el / n * 1000:.1f} ms/quadro  "
          f"({n / FPS / el:.1f}x tempo real)")
    print(f"  saida: {saida.name}  {mb:.0f} MB")
