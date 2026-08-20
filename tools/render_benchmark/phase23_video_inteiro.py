# -*- coding: utf-8 -*-
"""EXPERIMENTO — o overlay do VIDEO INTEIRO pelo renderizador proprio.

Os pedacos ja provaram: o estilo padrao (12x no desenho) e o Recorte (traco
vetorial, 14,7s -> 1,0s). Este teste monta os 851 quadros com as 21 legendas e
os tres presets juntos, cronometra contra o Remotion renderizando o MESMO
overlay completo, e compara a tinta quadro a quadro.

O que fica DE FORA (e por isso a comparacao exclui essas faixas): headline
(gancho) e cartao final — elementos que o overlay de producao desenha e o
nosso ainda nao. A tinta e comparada so na faixa das legendas (y 750-1450) e
fora dos quadros do cartao final.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase20_render_proprio as R  # noqa: E402
import phase22_recorte as RC  # noqa: E402

NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def montar_solo_big(cue: dict) -> "R.Legenda":
    """SOLO_BIG: uma palavra gigante, Poppins 900 italico, gradiente branco."""
    ini_f = int(cue["startMs"] / 1000 * R.FPS)
    fim_f = int(cue["endMs"] / 1000 * R.FPS)
    dur = (cue["endMs"] - cue["startMs"]) / 1000 * R.FPS
    enter = max(R.ENTER_MIN, min(R.ENTER_MAX, int(dur * 0.45)))

    w = cue["lines"][0][0]
    texto = w["text"]
    tam = R.fit_font(texto, 150, R.AVAIL / R.SCALE, 0.6)
    f = R.font(0, tam)                     # Poppins-BlackItalic
    ls = -3.0
    from PIL import Image, ImageFilter

    m = R._mascara_palavra(f, texto, ls)
    h_m, w_m = m.shape
    pad = 0.14 * tam
    larg_caixa = f.getlength(texto) + ls * len(texto) + 2 * pad
    alt_caixa = tam * R.LINE_HEIGHT
    x_caixa = (R.W - larg_caixa) / 2
    y_caixa = (R.H / 2 + R.BASE_Y) - alt_caixa / 2

    leg = R.Legenda(ini_f, fim_f)
    leg.dur_f = dur
    leg.exit_abrupto = cue.get("exit") == "abrupt"
    EXIT = max(2, min(7, int(dur * 0.35)))
    local = (w["fromMs"] - cue["startMs"]) / 1000 * R.FPS
    leg.saida_f = max(dur - EXIT, min(local + enter, dur - 2))

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
        inicio_f=local, enter=enter))
    return leg


def montar_cue(cue: dict, cor_traco: str) -> "R.Legenda":
    preset = cue.get("preset") or "STACK_MIXED"
    if preset == "SOLO_OUTLINE":
        return RC.montar_recorte(cue, cor_traco)
    if preset == "SOLO_BIG":
        return montar_solo_big(cue)
    return R.montar(cue)


def render_nosso(cues: list[dict], cor_traco: str, n: int, saida: Path) -> float:
    legs = sorted((montar_cue(c, cor_traco) for c in cues), key=lambda l: l.inicio_f)
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
    atual = 0
    for f in range(n):
        while atual < len(legs) and legs[atual].fim_f < f:
            atual += 1
        leg = (legs[atual]
               if atual < len(legs) and legs[atual].inicio_f <= f else None)
        R.desenhar(leg, f - (leg.inicio_f if leg else 0), buf, sujo)
        ff.stdin.write(buf.tobytes())
    ff.stdin.close()
    ff.wait()
    return time.perf_counter() - t0


if __name__ == "__main__":
    pub = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 851
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8-sig"))
    R.usar_config(ed)
    cor = ((ed.get("captions") or {}).get("circleAccent")) or RC.COR_PADRAO
    d = json.loads((pub / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = d if isinstance(d, list) else (d.get("cues") or [])
    saida = R.BENCH / "overlay_nosso_completo.mov"
    el = render_nosso(cues, cor, n, saida)
    print(f"  NOSSO: {n} quadros, {len(cues)} legendas, 3 presets em {el:.1f}s "
          f"= {el / n * 1000:.0f} ms/quadro ({n / R.FPS / el:.1f}x tempo real)")
    print(f"  saida: {saida.stat().st_size / 1024 / 1024:.0f} MB")
