# -*- coding: utf-8 -*-
"""Troca o MATIZ do logo sem tocar em forma, fonte ou qualidade.

Uso:  python tools/recolorir_logo.py [matiz-alvo] [compressao] [sufixo]

Aplicado em 21/08/2026 para virar o roxo em vermelho. Provado contra o
original: mesmas dimensoes, alfa IDENTICO, e saturacao e brilho com diferenca
maxima 0,0000 — so o matiz mudou.


COMO, e por que assim: so o MATIZ (H) e girado. Saturacao, brilho e sobretudo
o ALFA ficam byte a byte iguais — e o alfa e quem guarda o contorno das letras
e o antialiasing. Nada e redesenhado, redimensionado ou recomprimido com perda:
entra PNG, sai PNG.

O gradiente do logo ocupa 240-300 graus (azul-violeta -> violeta). Girar isso
sem mais nada jogaria a ponta para 330 e a outra para 30 — rosa de um lado,
laranja do outro. Entao o leque tambem e COMPRIMIDO, para caber na familia do
vermelho mantendo a mesma direcao de gradiente que o desenho ja tinha.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "assets" / "preview"
SAIDA = REPO / "installer" / "dist" / "logo-preview"

# O que foi aplicado em 21/08/2026: matiz 0 (vermelho puro), escolhido pelo
# dono da marca entre tres variantes.
ALVO = 0.0
# 0.45 aperta o leque de 60 para ~27 graus: continua tendo gradiente, sem
# escorregar para laranja de um lado e rosa do outro. Sem isso, girar um leque
# de 60 graus em volta do vermelho joga uma ponta para rosa e a outra para
# laranja.
COMPRIME = 0.45


def rgb_para_hsv(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = a[..., :3].max(axis=-1)
    mn = a[..., :3].min(axis=-1)
    dif = mx - mn
    h = np.zeros_like(mx)
    m = dif > 1e-9
    i = (mx == r) & m
    h[i] = ((g - b)[i] / dif[i]) % 6
    i = (mx == g) & m
    h[i] = ((b - r)[i] / dif[i]) + 2
    i = (mx == b) & m
    h[i] = ((r - g)[i] / dif[i]) + 4
    h *= 60.0
    s = np.where(mx > 0, dif / np.maximum(mx, 1e-9), 0.0)
    return h, s, mx


def hsv_para_rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    h = np.mod(h, 360.0) / 60.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [v, q, p, p, t, v])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [t, v, v, q, p, p])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)


def recolorir(src: Path, dest: Path, alvo: float = ALVO, comprime: float = COMPRIME) -> dict:
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im).astype(np.float64) / 255.0
    h, s, v = rgb_para_hsv(a)
    alpha = a[..., 3]

    # so os pixels COLORIDOS e visiveis. Cinza e branco ficam como estao —
    # senao um pixel quase-cinza do antialiasing ganharia cor do nada.
    mexer = (alpha > 0.02) & (s > 0.12)
    if not mexer.any():
        raise SystemExit(f"{src.name}: nada colorido para mexer")
    centro = float(np.median(h[mexer]))
    novo = h.copy()
    novo[mexer] = np.mod(alvo + (h[mexer] - centro) * comprime, 360.0)

    rgb = hsv_para_rgb(novo, s, v)
    fora = np.concatenate([rgb, alpha[..., None]], axis=-1)
    saida = np.clip(np.rint(fora * 255.0), 0, 255).astype(np.uint8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(saida, mode="RGBA").save(dest, format="PNG", optimize=True)

    # o alfa tem de sair IDENTICO: e ele que guarda o contorno
    conf = np.asarray(Image.open(dest).convert("RGBA"))[..., 3]
    igual = bool((conf == np.asarray(im)[..., 3]).all())
    return {
        "arquivo": dest.name, "tamanho": im.size, "centro_antes": round(centro, 1),
        "alfa_identico": igual, "pixels_mexidos": int(mexer.sum()),
    }


if __name__ == "__main__":
    alvo = float(sys.argv[1]) if len(sys.argv) > 1 else ALVO
    comp = float(sys.argv[2]) if len(sys.argv) > 2 else COMPRIME
    marca = sys.argv[3] if len(sys.argv) > 3 else ""
    for nome in ("ativa-vid-logo.png", "ativa-vid-icon.png"):
        r = recolorir(ASSETS / nome, SAIDA / f"{Path(nome).stem}{marca}.png", alvo, comp)
        print(r)
