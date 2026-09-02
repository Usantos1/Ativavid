# -*- coding: utf-8 -*-
"""Animação de ENTRADA do vídeo/imagem posto na mão (pedido de 01/09).

O usuário escolhe no preview: `padrao` (sobe e aparece), `pop` (cresce com
quique) ou `deslizar` (vem da esquerda). As fórmulas são as MESMAS nos dois
motores (InsertCard no template, `_desenhar_insert` no motor próprio); aqui
o motor próprio desenha de verdade e o teste mede a geometria do que saiu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

W, H = 540, 960
FPS = 30.0
FRAMES = 40


def _renderizador(tmp_path: Path, entrada: str | None):
    from app.render_proprio import Renderizador

    public = tmp_path / f"public_{entrada or 'padrao'}"
    public.mkdir()
    Image.new("RGB", (200, 130), (255, 40, 40)).save(public / "foto.jpg")
    it = {"src": "foto.jpg", "start": 0.0, "end": FRAMES / FPS}
    if entrada:
        it["entrada"] = entrada
    ed = {"inserts": [it]}
    (public / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    return Renderizador(public, ed, frames=FRAMES, fps=FPS, width=W, height=H)


def _caixa(rend, f: int):
    """(cx, area) do que o insert pintou no quadro `f`."""
    buf = np.zeros((H, W, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    for leg in rend.camadas:
        if getattr(leg, "insert", None) is None:
            continue
        fl = f - leg.inicio_f
        if fl < 0 or f > leg.fim_f:
            continue
        rend._desenhar_insert(leg, float(fl), buf, sujo, False)
    a = buf[..., 3] > 8
    if not a.any():
        return None, 0
    xs = np.where(a.any(axis=0))[0]
    return float(xs.mean()), int(a.sum())


def test_padrao_continua_subindo_e_aparecendo(tmp_path):
    rend = _renderizador(tmp_path, None)
    cx2, area2 = _caixa(rend, 2)
    cx12, area12 = _caixa(rend, 12)
    assert area2 > 0 and area12 > 0
    # em 2 quadros o cartão ainda está menor (escala 0,92 → 1)
    assert area2 < area12
    # e centrado: o padrão não desliza na horizontal
    assert abs(cx2 - cx12) < 3


def test_pop_cresce_com_quique(tmp_path):
    rend = _renderizador(tmp_path, "pop")
    _, a1 = _caixa(rend, 1)
    _, a6 = _caixa(rend, 6)
    _, a12 = _caixa(rend, 12)
    pad = _renderizador(tmp_path, None)
    _, p1 = _caixa(pad, 1)
    # pop nasce bem menor que o padrão (escala 0,72 contra 0,94 no quadro 1
    # → área ~0,59 da dele)
    assert a1 < p1 * 0.75, f"pop f1={a1} padrao f1={p1}"
    # e passa do tamanho final antes de assentar (overshoot do back.out)
    assert a6 > a12 * 1.005, f"sem quique: f6={a6} f12={a12}"


def test_deslizar_vem_da_esquerda(tmp_path):
    rend = _renderizador(tmp_path, "deslizar")
    cx2, a2 = _caixa(rend, 2)
    cx12, a12 = _caixa(rend, 12)
    assert a2 > 0 and a12 > 0
    # começa deslocado para a ESQUERDA e assenta no centro
    assert cx2 < cx12 - 20, f"não deslizou: f2={cx2} f12={cx12}"


def test_entrada_estranha_cai_no_padrao(tmp_path):
    rend = _renderizador(tmp_path, "girar")   # valor que não existe
    cx2, area2 = _caixa(rend, 2)
    assert area2 > 0
    pad = _renderizador(tmp_path, None)
    cxp, areap = _caixa(pad, 2)
    assert abs(cx2 - cxp) < 2 and abs(area2 - areap) <= areap * 0.02


def test_template_e_motor_tem_as_mesmas_formulas():
    """As três entradas moram nos DOIS motores — quem mexer numa fórmula
    precisa mexer nas duas (regra do motor-proprio-cobre-tudo)."""
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    for lado in (tsx, py):
        assert "2.70158" in lado and "1.70158" in lado, "back.out sumiu de um motor"
        assert "0.35" in lado, "o deslizar de 35% sumiu de um motor"
    assert "entrada === 'pop'" in tsx and "entrada === 'deslizar'" in tsx
    assert '"pop"' in py and '"deslizar"' in py
    # e o pipeline deixa a escolha PASSAR do preview para o edit-data
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'geo["entrada"]' in rf, "run_fast parou de repassar a entrada"
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "c.entrada ? { entrada: c.entrada }" in js, (
        "o salvar do preview parou de mandar a entrada")
