# -*- coding: utf-8 -*-
"""`extract_segment` de verdade: quantos quadros saem e quais.

Os testes irmãos em `test_prepared_source.py` conferem a LINHA DE COMANDO com
o ffmpeg trocado por um espião. Isso não pega o que importa aqui: com `-ss`
caindo no meio de um quadro, um filtro `fps=` pode DUPLICAR o primeiro quadro
para preencher a posição 0 — um congelamento de um quadro no início de cada
corte, invisível num teste de comando.

O índice do quadro vai na GEOMETRIA (barra branca na coluna N), não no
brilho: já perdi um teste porque o tonemap esmagou um índice codificado em
luminância.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

import render  # noqa: E402

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
W, H, N, FPS_FONTE = 120, 214, 240, 60


def _fonte(tmp: Path) -> Path:
    """4s a 60fps; o quadro k tem uma barra branca na coluna k % W."""
    p = tmp / "fonte.mp4"
    bruto = bytearray()
    for k in range(N):
        q = np.zeros((H, W, 3), dtype=np.uint8)
        q[:, k % W, :] = 255
        bruto += q.tobytes()
    r = subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS_FONTE), "-i", "-",
        "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p",
        "-g", "30", str(p)], input=bytes(bruto), capture_output=True, **NOWIN)
    if r.returncode != 0 or not p.exists():
        pytest.skip("ffmpeg não montou a fixture")
    return p


def _indices(p: Path) -> list[int]:
    r = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(p),
        "-vf", f"scale={W}:{H}:flags=neighbor",
        "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, **NOWIN)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (W * H)
    if not n:
        return []
    a = a[:n * W * H].reshape(n, H, W)
    return [int(q.mean(axis=0).argmax()) for q in a]


def _extrai(tmp: Path, fonte: Path, inicio: float, dur: float,
            monkeypatch, cedo: bool) -> list[int]:
    monkeypatch.setenv("ATIVAVID_FPS_CEDO", "" if cedo else "0")
    monkeypatch.delenv("ATIVAVID_PREP_FPS", raising=False)
    out = tmp / f"seg_{'novo' if cedo else 'velho'}.mp4"
    out.unlink(missing_ok=True)
    render.extract_segment(fonte, inicio, dur, "", out, streams="v", draft=True)
    return _indices(out)


@pytest.mark.parametrize("inicio", [0.0, 1.0, 1.0166667, 1.7583333])
def test_o_segmento_sai_com_a_contagem_certa(tmp_path, monkeypatch, inicio):
    """1 segundo pedido, 30 quadros entregues — inclusive com o `-ss` caindo
    entre dois quadros da fonte."""
    idx = _extrai(tmp_path, _fonte(tmp_path), inicio, 1.0, monkeypatch, True)
    assert len(idx) == 30, f"início {inicio}: {len(idx)} quadros"


def test_nenhum_quadro_repetido_no_comeco(tmp_path, monkeypatch):
    """O risco do `fps=` na frente: preencher a posição 0 duplicando o
    primeiro quadro, o que congela um quadro no início de cada corte.

    Com o índice na geometria dá para ver: quadros repetidos aparecem como
    passo 0 entre índices vizinhos."""
    fonte = _fonte(tmp_path)
    for inicio in (1.0166667, 1.7583333):
        idx = _extrai(tmp_path, fonte, inicio, 1.0, monkeypatch, True)
        passos = [b - a for a, b in zip(idx, idx[1:])]
        assert 0 not in passos, f"início {inicio}: quadro repetido em {idx[:8]}"


def test_o_movimento_fica_mais_regular_que_antes(tmp_path, monkeypatch):
    """O ganho de quebra da mudança: descartando quadro na FRENTE, a escolha
    fica em passo constante. Com o `-r` da saída ela pegava os primeiros
    quadros em sequência e os exibia espaçados — meia velocidade no começo de
    cada segmento."""
    fonte = _fonte(tmp_path)
    novo = _extrai(tmp_path, fonte, 1.0, 1.0, monkeypatch, True)
    velho = _extrai(tmp_path, fonte, 1.0, 1.0, monkeypatch, False)
    assert len(novo) == len(velho) == 30
    p_novo = {b - a for a, b in zip(novo, novo[1:])}
    p_velho = {b - a for a, b in zip(velho, velho[1:])}
    assert len(p_novo) == 1, f"o novo devia ter passo único: {sorted(p_novo)}"
    assert len(p_velho) > 1, f"o velho devia ser irregular: {sorted(p_velho)}"
