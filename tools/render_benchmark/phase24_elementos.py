# -*- coding: utf-8 -*-
"""EXPERIMENTO — o overlay COMPLETO: headline + cartao final + flashes.

Fecha o que faltava alem das legendas. Elementos do template reproduzidos:

  - headline `realce` (Main.tsx): duas linhas balanceadas por LARGURA MEDIDA
    (nao por contagem de palavras), cada uma num bloco da cor da marca com
    cantos arredondados e sombra; entrada fade+sobe 24px em 8 quadros; saida
    fade nos 9 ultimos quadros do gancho.
  - cartao final (EndCardInner): escurece a tela (dim 0.82), linha 1 na cor
    da marca com peso 900, linha 2 branca a 62%, tudo subindo 26px no fade de
    ~0,35s; SEM fade de saida (e a ultima coisa na tela).
  - flashes de corte (CutFlashes): facho de luz rotacionado -18 graus varrendo
    a tela em 7 quadros + clarao que cai EM CIMA do corte (VIDEO_LAG=1).

Multiplas camadas no mesmo quadro (headline + legenda, cartao + legenda)
compostas com o modo `mesclar` do desenhar.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase20_render_proprio as R  # noqa: E402
import phase22_recorte as RC  # noqa: E402
import phase23_video_inteiro as V  # noqa: E402

NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
VIDEO_LAG = 1
FLASH_LEAD, FLASH_LEN = 2, 7

# HL_STYLES.realce do template
REALCE = {"peso": 900, "cap": 86, "safe_w": 830, "lh": 1.04, "top": 300}
HL_MIN = 40


def _fonte_hl(tam: int):
    return R.font(4, tam)          # Poppins-Black (peso 900)


def _larg(texto: str, tam: int) -> float:
    f = _fonte_hl(tam)
    return f.getlength(texto) - 1.0 * max(0, len(texto) - 1)   # letterSpacing -1


def duas_linhas(texto: str) -> tuple[str, str]:
    """Quebra por largura MEDIDA — contar palavras quebraria no lugar errado."""
    palavras = texto.strip().split()
    if len(palavras) < 2:
        return (palavras[0] if palavras else "", "")
    melhor, dif = (palavras[0], " ".join(palavras[1:])), float("inf")
    for i in range(1, len(palavras)):
        a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
        d = abs(_larg(a, 100) - _larg(b, 100))
        if d < dif:
            melhor, dif = (a, b), d
    return melhor


def ajustar(linhas: tuple[str, str]) -> int:
    mais_larga = lambda t: max(_larg(linhas[0], t), _larg(linhas[1], t), 1.0)
    tam = int(REALCE["safe_w"] / mais_larga(100) * 100)
    tam = int(REALCE["safe_w"] / mais_larga(tam) * tam)
    return max(HL_MIN, min(REALCE["cap"], tam))


def montar_headline(hook: dict, fps: float) -> "R.Legenda":
    fim = int(float(hook.get("endSec") or 4.0) * fps)
    accent = hook.get("accent") or "#ff5200"
    texto = (hook.get("text") or " ".join(hook.get("lines") or [])).strip()
    linhas = [l for l in duas_linhas(texto) if l]
    tam = ajustar(tuple((linhas + ["", ""])[:2]))
    f = _fonte_hl(tam)

    leg = R.Legenda(0, fim)
    leg.dur_f = fim
    leg.saida_f = fim - 9
    leg.exit_fade = True           # saida so com fade (sem subir/desfocar)

    cor_bloco = np.array([int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)],
                         dtype=np.float32)
    y = float(REALCE["top"])
    for li, texto_l in enumerate(linhas):
        larg_t = _larg(texto_l, tam)
        pad_x, pad_top, pad_bot = 0.3 * tam, 0.08 * tam, 0.16 * tam
        asc, desc = f.getmetrics()
        larg_b = int(larg_t + 2 * pad_x)
        # A caixa CSS e line-height (1.04em) + paddings — NAO ascent+descent.
        # Poppins tem ascent+descent ~1.35em: usar isso deixava o bloco 13%
        # mais alto que o de producao (medido: 259 vs 229 px).
        alt_b = int(REALCE["lh"] * tam + pad_top + pad_bot)
        folga = 40                                  # sombra 0 10px 28px
        L, A = larg_b + 2 * folga, alt_b + 2 * folga

        bloco = Image.new("L", (L, A), 0)
        ImageDraw.Draw(bloco).rounded_rectangle(
            [folga, folga, folga + larg_b, folga + alt_b], radius=12, fill=255)
        a_bloco = np.asarray(bloco, dtype=np.float32) / 255.0

        m = R._mascara_palavra(f, texto_l, -1.0)
        h_m, w_m = m.shape
        tx = folga + int(pad_x)
        # texto centrado na caixa de linha (meia-entrelinha do CSS)
        ty = folga + int(pad_top + (REALCE["lh"] * tam - (asc + desc)) / 2)
        texto_a = np.zeros_like(a_bloco)
        texto_a[ty:ty + h_m, tx:tx + w_m] = m[:A - ty, :L - tx]

        # cor: bloco no accent, texto branco POR CIMA (over dentro da camada)
        rgb = np.broadcast_to(cor_bloco, (A, L, 3)).copy()
        rgb = rgb * (1 - texto_a[..., None]) + 255.0 * texto_a[..., None]
        alpha = np.maximum(a_bloco, texto_a)

        b = np.asarray(Image.fromarray((a_bloco * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(28 * 0.5)),
                       dtype=np.float32) / 255.0
        sombra = np.zeros_like(b)
        sombra[10:, :] = b[:-10, :] * 0.45

        x0 = int((R.W - larg_b) / 2) - folga
        leg.palavras.append(R.Palavra(
            x0, int(y) - folga, rgb, alpha, sombra,
            inicio_f=0, enter=8, sobe=24.0))
        y += alt_b + 10                            # gap 10 (lh ja esta em alt_b)
    return leg


def montar_endcard(ec: dict, hook_accent: str, total_f: int, fps: float) -> "R.Legenda":
    dur = int(round(float(ec.get("lastSec") or 2.5) * fps))
    ini = total_f - dur
    accent = ec.get("accent") or hook_accent or "#ff5200"
    dim = float(ec.get("dim") if ec.get("dim") is not None else 0.82)
    linhas = [l for l in (ec.get("lines") or []) if l]
    fade = min(round(0.35 * fps), dur // 2)

    leg = R.Legenda(ini, total_f + 10)
    leg.dur_f = dur + 20
    leg.saida_f = 1e9                              # sem fade de saida

    # O escurecimento NAO e uma camada: e preto constante sobre a tela
    # inteira, o que se reduz a multiplicar o quadro por (1-a). Como camada
    # de verdade custava 426 ms/quadro (mescla float de tela cheia); como
    # multiplicacao uint8 custa ~5 ms. Fica em leg.dim para o driver aplicar
    # ENTRE as legendas e o texto do cartao.
    leg.dim = dim
    leg.dim_fade = fade

    base = round(R.W * 0.058)
    safe_w = R.W * 0.70
    escala = [1.0, 0.62]
    pesos_f = [R.font(4, 1), None]                 # linha 1 Black, linha 2 ExtraBold
    ajuste = 1.0
    for i, t in enumerate(linhas[:2]):
        tam_i = int(base * escala[i])
        f = R.font(4 if i == 0 else 3, tam_i)
        w = f.getlength(t) - 1.0 * max(0, len(t) - 1)
        if w > safe_w:
            ajuste = min(ajuste, safe_w / w)
    tam = max(28, round(base * ajuste))

    cor1 = np.array([int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)],
                    dtype=np.float32)
    y = R.H / 2.0
    alturas = []
    mascaras = []
    for i, t in enumerate(linhas[:2]):
        tam_i = int(tam * escala[i])
        f = R.font(4 if i == 0 else 3, tam_i)
        m = R._mascara_palavra(f, t, -1.0)
        mascaras.append((m, f, tam_i, i))
        alturas.append(m.shape[0])
    gap = round(tam * 0.34)
    total_alt = sum(alturas) + gap * max(0, len(mascaras) - 1)
    y = (R.H - total_alt) / 2.0
    for m, f, tam_i, i in mascaras:
        h_m, w_m = m.shape
        folga = 32
        pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga), dtype=np.float32)
        pad_m[folga:folga + h_m, folga:folga + w_m] = m
        # textShadow 0 4px 24px rgba(0,0,0,.6)
        b = np.asarray(Image.fromarray((pad_m * 255).astype(np.uint8))
                       .filter(ImageFilter.GaussianBlur(24 * 0.5)),
                       dtype=np.float32) / 255.0
        sombra = np.zeros_like(b)
        sombra[4:, :] = b[:-4, :] * 0.6
        cor = cor1 if i == 0 else np.array([255.0, 255.0, 255.0], dtype=np.float32)
        rgb = np.broadcast_to(cor, (*pad_m.shape, 3)).copy()
        x0 = int((R.W - w_m) / 2) - folga
        leg.palavras.append(R.Palavra(
            x0, int(y) - folga, rgb, pad_m, sombra,
            inicio_f=0, enter=fade, sobe=26.0))
        y += h_m + gap
    return leg


_FLASH_CACHE: dict[int, np.ndarray] = {}


def flash_quadro(at_s: float, fps: float, f: int) -> np.ndarray | None:
    """Camada do flash no quadro f, ou None.

    A mascara depende so do INDICE do estagio (0..6) — a posicao do facho e
    funcao de p, igual para todos os cortes. Recalcular a rotacao PIL e
    mesclar em float custava 525 ms por quadro de flash; com o estagio em
    cache e a aplicacao em uint8 cai para poucos ms."""
    c = round(at_s * fps) + VIDEO_LAG
    if not (c - FLASH_LEAD <= f < c - FLASH_LEAD + FLASH_LEN):
        return None
    est = f - (c - FLASH_LEAD)
    p = est / (FLASH_LEN - 1)
    bloom = np.interp(f, [c - 1, c, c + 2], [0, 0.5, 0])
    if est in _FLASH_CACHE:
        return np.maximum(_FLASH_CACHE[est], np.float32(bloom))
    x = (-1.35 + 2.7 * p) * R.W
    beam = np.interp(p, [0, 0.35, 1], [0, 1, 0])

    img = Image.new("L", (R.W, R.H), 0)
    d = ImageDraw.Draw(img)
    # facho: barra rotacionada -18 graus com gradiente horizontal
    barra = Image.new("L", (int(R.W * 0.46), int(R.H * 1.6)), 0)
    grad = np.abs(np.linspace(-1, 1, barra.width))
    linha = ((1 - grad) * 0.95 * 255).astype(np.uint8)
    barra_np = np.repeat(linha[None, :], barra.height, axis=0)
    barra = Image.fromarray(barra_np, mode="L").rotate(
        -18, expand=True, resample=Image.BILINEAR)
    img.paste(barra, (int(x), int(-0.3 * R.H)), barra)
    a = np.clip(np.asarray(img, dtype=np.float32) / 255.0 * beam, 0.0, 1.0)
    _FLASH_CACHE[est] = a
    return np.maximum(a, np.float32(bloom))


def aplicar_dim(buf: np.ndarray, sujo: list[int], dim: float, fl: float,
                fade: int) -> None:
    """Preto constante por cima de tudo que ja foi composto no quadro."""
    t = min(1.0, max(0.0, fl / max(1, fade)))
    a = dim * (1 - (1 - t) ** 3)
    if a <= 0.004:
        return
    # sobre RGBA alpha direto: rgb' = rgb*(1-a); alpha' = alpha + a*(1-alpha)
    alpha = buf[..., 3].astype(np.float32) / 255.0
    buf[..., :3] = (buf[..., :3] * (1.0 - a)).astype(np.uint8)
    buf[..., 3] = ((alpha + a * (1.0 - alpha)) * 255.0).astype(np.uint8)
    sujo[:] = [0, 0, buf.shape[1], buf.shape[0]]


def aplicar_flash(buf: np.ndarray, sujo: list[int], a: np.ndarray) -> None:
    """Branco "over" no RGBA de alpha direto.

    A versao simplificada rgb+(255-rgb)*a erra onde o fundo e TRANSPARENTE:
    ali o resultado deve ser branco puro (o alpha de saida e o do flash), nao
    uma mistura com o rgb residual. Sao so 28 quadros: o over completo cabe.
    """
    a_b = buf[..., 3].astype(np.float32) / 255.0
    a_o = a + a_b * (1.0 - a)
    peso = (a_b * (1.0 - a))[..., None]
    rgb = (255.0 * a[..., None] + buf[..., :3].astype(np.float32) * peso)         / np.maximum(a_o[..., None], 1e-6)
    buf[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    buf[..., 3] = (np.clip(a_o, 0, 1) * 255.0).astype(np.uint8)
    sujo[:] = [0, 0, buf.shape[1], buf.shape[0]]


def render_completo(pub: Path, cut_frames: int, saida: Path) -> float:
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8-sig"))
    R.usar_config(ed)
    cor_traco = ((ed.get("captions") or {}).get("circleAccent")) or RC.COR_PADRAO
    d = json.loads((pub / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = d if isinstance(d, list) else (d.get("cues") or [])

    camadas: list[R.Legenda] = []
    hook = ed.get("hook") or {}
    if hook.get("enabled"):
        camadas.append(montar_headline(hook, R.FPS))
    camadas.extend(sorted((V.montar_cue(c, cor_traco) for c in cues),
                          key=lambda l: l.inicio_f))
    ec = ed.get("endCard") or {}
    if ec.get("enabled"):
        camadas.append(montar_endcard(ec, hook.get("accent"), cut_frames, R.FPS))
    flashes = [float(t["at"]) for t in (ed.get("transitions") or [])
               if t.get("type") == "flash"]

    t0 = time.perf_counter()
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{R.W}x{R.H}",
         "-r", str(R.FPS), "-i", "-",
         "-c:v", "prores_ks", "-profile:v", "4444",
         "-pix_fmt", "yuva444p10le", str(saida)],
        stdin=subprocess.PIPE, **NOWIN)
    buf = np.zeros((R.H, R.W, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    for f in range(cut_frames):
        # limpa a caixa do quadro anterior
        if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
            buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
        sujo[:] = [0, 0, 0, 0]
        for leg in camadas:
            if leg.inicio_f <= f <= leg.fim_f:
                d_val = getattr(leg, "dim", 0.0)
                if d_val:
                    aplicar_dim(buf, sujo, d_val, f - leg.inicio_f,
                                getattr(leg, "dim_fade", 10))
                R.desenhar(leg, f - leg.inicio_f, buf, sujo, mesclar=True)
        for at in flashes:
            a = flash_quadro(at, R.FPS, f)
            if a is not None:
                aplicar_flash(buf, sujo, a)
        ff.stdin.write(buf.tobytes())
    ff.stdin.close()
    ff.wait()
    return time.perf_counter() - t0


if __name__ == "__main__":
    pub = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 851
    saida = R.BENCH / "overlay_completo_elementos.mov"
    el = render_completo(pub, n, saida)
    print(f"  COMPLETO: {n} quadros (headline + legendas + cartao + flashes) "
          f"em {el:.1f}s = {el / n * 1000:.0f} ms/quadro")
    print(f"  saida: {saida.stat().st_size / 1024 / 1024:.0f} MB")
