# -*- coding: utf-8 -*-
"""5.0.74: `_converter` e `_aplicar_flash` fazem as MESMAS contas em menos
passagens — bit a bit iguais ao que era.

Perfil de 900 quadros do C005 (28,7 s de desenho): `_aplicar_flash` 6,3 s
(149 ms por quadro de flash — nos 3 quadros do "bloom" a máscara cobre o
quadro inteiro), `_converter` + `astype` 7,3 s (a caixa da legenda ia
float32 → uint8 → float32 → uint8 só para aplicar a opacidade de saída no
alfa). Os dois foram reescritos sem mudar uma conta: a soma em IEEE é
comutativa, o clip da cor era redundante (média ponderada fica em 0..255)
e o cast na atribuição trunca como o `astype`.

Este arquivo guarda as implementações ANTIGAS e exige igualdade exata em
buffers aleatórios — inclusive máscara cheia (bloom), cor não branca e
opacidade de saída parcial.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.render_proprio import Renderizador  # noqa: E402


def _converter_antigo(tela):
    a = np.clip(tela[..., 3:4], 0.0, 1.0)
    rgb = np.clip(tela[..., :3] / np.maximum(a, 1e-6), 0.0, 255.0)
    out = np.empty(tela.shape, dtype=np.float32)
    out[..., :3] = rgb
    out[..., 3] = a[..., 0] * 255.0
    return out.astype(np.uint8)


def _flash_antigo(buf, a, cor):
    vivo = a > (0.5 / 255.0)
    linhas = np.flatnonzero(vivo.any(axis=1))
    if linhas.size == 0:
        return
    colunas = np.flatnonzero(vivo.any(axis=0))
    y0, y1 = int(linhas[0]), int(linhas[-1]) + 1
    x0, x1 = int(colunas[0]), int(colunas[-1]) + 1
    sub = buf[y0:y1, x0:x1]
    a_c = a[y0:y1, x0:x1]
    a_b = sub[..., 3].astype(np.float32) / 255.0
    a_o = a_c + a_b * (1.0 - a_c)
    peso = (a_b * (1.0 - a_c))[..., None]
    c3 = np.asarray(cor, dtype=np.float32)[None, None, :]
    rgb = (c3 * a_c[..., None] + sub[..., :3].astype(np.float32) * peso) \
        / np.maximum(a_o[..., None], 1e-6)
    sub[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    sub[..., 3] = (np.clip(a_o, 0, 1) * 255.0).astype(np.uint8)


def _tela(rng, h=64, w=80):
    """Canvas premultiplicado como o das legendas: alfa 0..1 (com sobras
    fora da faixa, como o blur deixa) e cor <= alfa*255 (com sobras)."""
    a = rng.uniform(-0.05, 1.05, (h, w, 1)).astype(np.float32)
    rgb = (rng.uniform(0, 1, (h, w, 3)).astype(np.float32) * np.clip(a, 0, 1) * 255.0
           * rng.uniform(0.9, 1.1, (h, w, 3)).astype(np.float32))
    return np.concatenate([rgb, a], axis=2).astype(np.float32)


@pytest.mark.parametrize("semente", range(6))
def test_converter_e_bit_a_bit_o_antigo(semente):
    rng = np.random.default_rng(semente)
    tela = _tela(rng)
    esperado = _converter_antigo(tela)
    saida = Renderizador._converter(tela)
    assert saida.dtype == np.uint8 and saida.shape == tela.shape
    assert np.array_equal(saida, esperado)


@pytest.mark.parametrize("op", [0.0, 0.13, 0.5, 0.996, 0.999])
def test_opacidade_de_saida_igual_ao_caminho_antigo(op):
    """O chamador fazia uint8 -> float32 -> *op -> uint8 nos QUATRO canais;
    agora so o alfa passa por isso — a cor nao mudava mesmo."""
    rng = np.random.default_rng(99)
    tela = _tela(rng)
    antigo = _converter_antigo(tela).astype(np.float32)
    antigo[..., 3] *= op
    esperado = antigo.astype(np.uint8)
    assert np.array_equal(Renderizador._converter(tela, op), esperado)


def _buf(rng, h=90, w=70):
    buf = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
    # overlay real: muito pixel transparente, alguns opacos, bordas parciais
    tipo = rng.integers(0, 3, (h, w))
    buf[..., 3] = np.where(tipo == 0, 0, np.where(tipo == 1, 255, buf[..., 3]))
    return buf


@pytest.mark.parametrize("cor", [(255.0, 255.0, 255.0), (0.0, 0.0, 0.0),
                                 (231.0, 76.0, 60.0)])
@pytest.mark.parametrize("cheia", [False, True])
def test_flash_e_bit_a_bit_o_antigo(cor, cheia):
    rng = np.random.default_rng(7 if cheia else 3)
    buf = _buf(rng)
    a = rng.uniform(0, 1, buf.shape[:2]).astype(np.float32)
    if cheia:
        a = np.maximum(a, np.float32(0.5))          # o "bloom": quadro inteiro
    else:
        a[:20] = 0.0
        a[:, :15] = 0.0
        a[a < 0.3] = 0.0                            # feixe com borda
    esperado = buf.copy()
    _flash_antigo(esperado, a, cor)
    r = Renderizador.__new__(Renderizador)
    sujo = [0, 0, 0, 0]
    r._aplicar_flash(buf, sujo, a, cor)
    assert np.array_equal(buf, esperado)
    assert sujo[2] > sujo[0] and sujo[3] > sujo[1]


def test_mascara_vazia_nao_toca_o_buffer():
    rng = np.random.default_rng(1)
    buf = _buf(rng)
    antes = buf.copy()
    r = Renderizador.__new__(Renderizador)
    sujo = [0, 0, 0, 0]
    r._aplicar_flash(buf, sujo, np.zeros(buf.shape[:2], dtype=np.float32))
    assert np.array_equal(buf, antes) and sujo == [0, 0, 0, 0]


def test_o_chamador_nao_faz_mais_a_dupla_conversao():
    src = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert "self._converter(tela).astype(np.float32)" not in src
    assert "self._blit(self._converter(tela, op_cue)" in src
    i = src.index("def _aplicar_flash(")
    corpo = src[i:i + 2600]
    assert "np.clip(rgb, 0, 255)" not in corpo and "np.clip(a_o, 0, 1)" not in corpo
    assert "if cor[0] == cor[1] == cor[2]:" in corpo, "flash branco: cor*a_c uma vez"
