# -*- coding: utf-8 -*-
"""EXPERIMENTO — o estilo `Recorte` (SOLO_OUTLINE) no renderizador proprio.

Este e o estilo dificil: nao e texto, e TRACO. Um caminho de bezier que se
desenha sozinho em volta da palavra, esticado sobre a caixa dela, com ponta
redonda e sombra. Se a arquitetura nao esticar para isto, o renderizador
proprio nasce cobrindo so um terco do catalogo.

O que o template faz (PencilOutline.tsx + StackedCaptions.tsx):
  - caminho fixo num viewBox 312x150, `preserveAspectRatio="none"` — ou seja,
    esticado sem manter proporcao sobre a caixa da palavra;
  - a caixa e a da palavra inflada: left -10%, top -22%, largura 120%,
    altura 150%;
  - traco de 9 px com `non-scaling-stroke` (a espessura NAO acompanha o
    esticamento), ponta e junta redondas;
  - `pathLength=1` + dashoffset: o traco avanca por COMPRIMENTO DE ARCO, nao
    por parametro da curva — desenhar por `t` daria velocidade errada nas
    partes curvas;
  - progresso de oStart = entrada da palavra + 2 ate no maximo +10 quadros.

Como a animacao dura ~10 quadros e depois fica parada, cada estagio e
rasterizado UMA vez e reaproveitado — mesma ideia do texto.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase20_render_proprio as R  # noqa: E402

NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

# --- o caminho do PencilOutline, ja parseado (viewBox 312 x 150) -------------
INICIO = (30.0, 78.0)
CURVAS = [
    ((26, 40), (120, 20), (190, 24)),
    ((262, 28), (300, 52), (288, 82)),
    ((276, 114), (150, 132), (78, 122)),
    ((28, 114), (8, 92), (34, 66)),
    ((50, 50), (96, 40), (150, 42)),
]
VB_W, VB_H = 312.0, 150.0
TRACO_PX = 9
COR_PADRAO = "#39E508"
SOMBRA_TRACO = (0, 3, 8, 0.45)   # drop-shadow(0 3px 8px rgba(0,0,0,.45))

# posicao da caixa em relacao a palavra
ESQ, TOPO, LARG, ALT = -0.10, -0.22, 1.20, 1.50


def _cubica(p0, p1, p2, p3, n: int = 24):
    """Achata uma cubica em pontos. n=24 por curva ja fica liso a 9 px."""
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        yield (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
               u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def pontos_do_caminho() -> list[tuple[float, float]]:
    pts = [INICIO]
    atual = INICIO
    for c1, c2, fim in CURVAS:
        pts.extend(_cubica(atual, c1, c2, fim))
        atual = fim
    return pts


def _mapear(pts, bx, by, bw, bh):
    """viewBox -> caixa, esticando sem manter proporcao (o SVG pede isso)."""
    return [(bx + x / VB_W * bw, by + y / VB_H * bh) for x, y in pts]


def _comprimentos(pts):
    acum = [0.0]
    for i in range(1, len(pts)):
        dx, dy = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        acum.append(acum[-1] + math.hypot(dx, dy))
    return acum


def traco_ate(pts, acum, frac: float) -> list[tuple[float, float]]:
    """Recorta a polilinha em `frac` do COMPRIMENTO total, interpolando o
    ponto final dentro do segmento — sem isso o traco anda aos saltos."""
    if frac <= 0:
        return []
    total = acum[-1]
    if frac >= 1:
        return list(pts)
    alvo = total * frac
    saida = [pts[0]]
    for i in range(1, len(pts)):
        if acum[i] < alvo:
            saida.append(pts[i])
            continue
        sobra = alvo - acum[i - 1]
        seg = acum[i] - acum[i - 1]
        t = sobra / seg if seg > 1e-9 else 0.0
        saida.append((pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
                      pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t))
        break
    return saida


def mascara_traco(pts, larg: int, alt: int, dx: int, dy: int) -> np.ndarray:
    """Desenha a polilinha com espessura e ponta redonda."""
    img = Image.new("L", (larg, alt), 0)
    if len(pts) >= 2:
        d = ImageDraw.Draw(img)
        desl = [(x - dx, y - dy) for x, y in pts]
        d.line(desl, fill=255, width=TRACO_PX, joint="curve")
        # ponta redonda nas duas extremidades (o line do Pillow corta reto)
        r = TRACO_PX / 2
        for x, y in (desl[0], desl[-1]):
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return np.asarray(img, dtype=np.float32) / 255.0


def montar_recorte(cue: dict, cor_traco: str = COR_PADRAO) -> "R.Legenda":
    """Monta a legenda do estilo Recorte: uma palavra + o traco animado."""
    ini_f = int(cue["startMs"] / 1000 * R.FPS)
    fim_f = int(cue["endMs"] / 1000 * R.FPS)
    dur = (cue["endMs"] - cue["startMs"]) / 1000 * R.FPS
    enter = max(R.ENTER_MIN, min(R.ENTER_MAX, int(dur * 0.45)))
    saida_inicio = max(dur - max(2, min(7, int(dur * 0.35))), min(enter, dur - 2))

    w = cue["lines"][0][0]
    texto = w["text"]
    # SOLO_OUTLINE: base 118, avail-80, fator 0.6, letterSpacing -2
    tam = R.fit_font(texto, 118, (R.AVAIL - 80) / R.SCALE, 0.6)
    f = R.font(4, tam)
    ls = -2.0
    m = R._mascara_palavra(f, texto, ls)
    h_m, w_m = m.shape

    pad = 0.1 * tam                       # padding '0 0.1em'
    larg_caixa = f.getlength(texto) + ls * len(texto) + 2 * pad
    alt_caixa = tam * R.LINE_HEIGHT
    x_caixa = (R.W - larg_caixa) / 2
    y_caixa = (R.H / 2 + R.BASE_Y) - alt_caixa / 2

    leg = R.Legenda(ini_f, fim_f)
    leg.dur_f = dur
    leg.exit_abrupto = cue.get("exit") == "abrupt"
    leg.saida_f = saida_inicio

    # ---- a palavra (mesma cadeia do texto: gradiente + sombra) -------------
    asc, desc = f.getmetrics()
    x0 = int(round(x_caixa + pad))
    y0 = int(round(y_caixa + (alt_caixa - (asc + desc)) / 2))
    folga = 24
    pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga), dtype=np.float32)
    pad_m[folga:folga + h_m, folga:folga + w_m] = m
    sombra = np.zeros_like(pad_m)
    for dx, dy, blur, sa in R.SHADOW:
        b = np.asarray(Image.fromarray((pad_m * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(blur * R.BLUR_K)),
                       dtype=np.float32) / 255.0
        desl = np.zeros_like(b)
        desl[max(0, dy):, max(0, dx):] = b[:b.shape[0] - max(0, dy),
                                           :b.shape[1] - max(0, dx)]
        sombra = np.maximum(sombra, desl * sa)
    col = R.gradiente(int(round(alt_caixa)))
    off = int(round(y0 - folga - y_caixa))
    idxs = np.clip(np.arange(pad_m.shape[0]) + off, 0, len(col) - 1)
    rgb = np.repeat(col[idxs][:, None, None], 3, axis=2) * np.ones(
        (1, pad_m.shape[1], 1), dtype=np.float32)
    leg.palavras.append(R.Palavra(
        x0 - folga, y0 - folga, rgb, pad_m, sombra,
        inicio_f=(w["fromMs"] - cue["startMs"]) / 1000 * R.FPS, enter=enter))

    # ---- o traco, um estagio por quadro ------------------------------------
    bx = x_caixa + ESQ * larg_caixa
    by = y_caixa + TOPO * alt_caixa
    bw, bh = LARG * larg_caixa, ALT * alt_caixa
    pts = _mapear(pontos_do_caminho(), bx, by, bw, bh)
    acum = _comprimentos(pts)

    local = (w["fromMs"] - cue["startMs"]) / 1000 * R.FPS
    o_ini = local + 2
    o_fim = min(o_ini + 10, saida_inicio - 1, dur - 2)
    o_fim = max(o_fim, o_ini + 3)

    marg = TRACO_PX + 20
    tx0 = int(min(x for x, _ in pts) - marg)
    ty0 = int(min(y for _, y in pts) - marg)
    tx1 = int(max(x for x, _ in pts) + marg)
    ty1 = int(max(y for _, y in pts) + marg)
    lt, at = tx1 - tx0, ty1 - ty0
    cor = np.array([int(cor_traco.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)],
                   dtype=np.float32)

    def _estagio(frac: float, janela: tuple[float, float]) -> None:
        alpha = mascara_traco(traco_ate(pts, acum, frac), lt, at, tx0, ty0)
        dx, dy, blur, sa = SOMBRA_TRACO
        b = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(blur * R.BLUR_K)),
                       dtype=np.float32) / 255.0
        som = np.zeros_like(b)
        som[max(0, dy):, max(0, dx):] = b[:b.shape[0] - max(0, dy),
                                          :b.shape[1] - max(0, dx)] * sa
        rgb_t = np.broadcast_to(cor, (at, lt, 3)).copy()
        leg.palavras.insert(0, R.Palavra(tx0, ty0, rgb_t, alpha, som,
                                         inicio_f=0, enter=1, janela=janela))

    # um estagio por quadro da animacao; depois, o traco inteiro ate o fim
    q = int(math.floor(o_ini))
    while q < o_fim:
        frac = min(1.0, max(0.0, (q - o_ini) / max(1e-6, o_fim - o_ini)))
        _estagio(frac, (q, q + 1))
        q += 1
    _estagio(1.0, (o_fim, float(fim_f - ini_f + 10)))
    return leg
