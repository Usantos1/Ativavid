# -*- coding: utf-8 -*-
"""5.0.77: o ffmpeg lê o cano do desenho adiantado (`-thread_queue_size`).

MEDIDO no C005 real (1347 quadros, máquina livre): o desenho sozinho leva
11,8 s e o grafo do compose ~22 s, mas juntos pelo cano levavam 32 s — o
ffmpeg lia um quadro, filtrava, encodava e só então lia o próximo, e o
desenho ficava parado esperando. Com fila de 8 quadros os dois se
sobrepõem: 22,4 s; 16/32/64 dão 22,9/22,2/22,1 s. Saída bit a bit igual
(PSNR infinito entre as filas). 16 quadros = 133 MB de RAM no pior caso.

`overlaySec` era 87% do REMOTION_RENDER nos últimos 40 jobs; não era o
desenho, era a espera pelo cano.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import render_proprio as rp  # noqa: E402

SRC = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")


def test_a_fila_existe_e_cabe_na_memoria():
    assert 8 <= rp.PIPE_FILA_QUADROS <= 64, "8 ja da o ganho; 64 = 531 MB"
    assert rp.PIPE_FILA_QUADROS * 1080 * 1920 * 4 <= 600 * 1024 * 1024


def test_os_dois_canos_pedem_a_fila_antes_do_input():
    """A opcao e POR INPUT e so vale antes do `-i` a que se refere."""
    padrao = re.compile(
        r'"-thread_queue_size", str\(PIPE_FILA_QUADROS\)[^\n]*\n\s*"-f", "rawvideo", "-pix_fmt", "rgba"')
    assert len(padrao.findall(SRC)) == 2, "passada unica e _gravar_video"
    # e nenhum cano rawvideo sem a fila
    assert SRC.count('"-f", "rawvideo", "-pix_fmt", "rgba"') == 2
