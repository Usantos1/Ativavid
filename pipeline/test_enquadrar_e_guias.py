# -*- coding: utf-8 -*-
"""Enquadramento (fx/fy) e guias de arrasto (pedidos de 02/09).

"ainda não dá pra recortar uma imagem ou vídeo": o cartão corta em `cover`
e fx/fy escolhem QUE PARTE aparece (object-position no template, crop com
offset no motor próprio). E no arrasto: trava no centro com linha de
alinhamento + medidas das margens de cada lado ("87 img 87").
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

W, H = 540, 960
FPS = 30.0
FRAMES = 40


def _render_com_foco(tmp_path: Path, fx):
    from app.render_proprio import Renderizador

    public = tmp_path / f"public_{str(fx).replace('.', '_')}"
    public.mkdir()
    # metade esquerda VERMELHA, direita AZUL — fonte larga (cover corta na
    # horizontal), então o fx decide a cor que sobra no cartão
    im = Image.new("RGB", (800, 120), (255, 0, 0))
    im.paste(Image.new("RGB", (400, 120), (0, 0, 255)), (400, 0))
    im.save(public / "foto.jpg")
    it = {"src": "foto.jpg", "start": 0.0, "end": FRAMES / FPS}
    if fx is not None:
        it["fx"] = fx
    ed = {"inserts": [it]}
    (public / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    rend = Renderizador(public, ed, frames=FRAMES, fps=FPS, width=W, height=H)
    buf = np.zeros((H, W, 4), dtype=np.uint8)
    for leg in rend.camadas:
        if getattr(leg, "insert", None) is None:
            continue
        rend._desenhar_insert(leg, 20.0, buf, [0, 0, 0, 0], False)
    tinta = buf[..., 3] > 128
    r = float(buf[..., 0][tinta].mean())
    b = float(buf[..., 2][tinta].mean())
    return r, b


def test_fx_escolhe_a_parte_visivel(tmp_path):
    r0, b0 = _render_com_foco(tmp_path, 0.0)    # borda esquerda = vermelho
    r1, b1 = _render_com_foco(tmp_path, 1.0)    # borda direita = azul
    assert r0 > b0 * 2, f"fx=0 deveria mostrar o vermelho: r={r0:.0f} b={b0:.0f}"
    assert b1 > r1 * 2, f"fx=1 deveria mostrar o azul: r={r1:.0f} b={b1:.0f}"


def test_sem_foco_continua_no_centro(tmp_path):
    """Projeto antigo (sem fx) não muda: o crop segue centrado — as duas
    cores aparecem por igual."""
    r, b = _render_com_foco(tmp_path, None)
    assert abs(r - b) < max(r, b) * 0.2, f"centro desequilibrado: r={r:.0f} b={b:.0f}"


def test_fx_zero_nao_vira_centro():
    """`or 0.5` seria armadilha: fx=0.0 é falsy. O helper testa None."""
    from app.render_proprio import _foco_do_insert

    assert _foco_do_insert({"fx": 0.0}, "fx") == 0.0
    assert _foco_do_insert({}, "fx") == 0.5
    assert _foco_do_insert({"fx": "podre"}, "fx") == 0.5
    assert _foco_do_insert({"fx": 7}, "fx") == 1.0


def test_take_de_video_ganha_foco_na_extracao():
    """O crop do ffmpeg sai do centro para o enquadramento, e o foco entra
    na CHAVE do cache (mudar o enquadramento re-extrai os quadros)."""
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert "(iw-ow)*{fx:.4f}" in py and "(ih-oh)*{fy:.4f}" in py
    assert "marca_foco" in py, "o cache dos quadros ignora o enquadramento"


def test_o_pipeline_repassa_o_enquadramento():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'for foco in ("fx", "fy"):' in rf
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    i = tsx.index("const InsertCard")
    bloco = tsx[i:tsx.index("\nconst Inserts", i)]
    assert "objectPosition" in bloco, "o template parou de aplicar fx/fy"
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "c.fx != null ? { fx: +c.fx }" in js, "o salvar não manda o fx"


def test_arrasto_tem_trava_de_centro_e_medidas():
    """As guias: iman de 8px no centro, linha acesa só no snap, e as
    medidas das margens em pixels do VÍDEO (1080x1920), fora do cartão."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function atualizarGuias")
    bloco = js[i:i + 1600]
    assert "* 1080" in bloco and "* 1920" in bloco, (
        "as medidas têm de ser em pixels do vídeo, não da tela")
    i2 = js.index("const snapX =")
    assert "< 8" in js[i2:i2 + 120], "o imã do centro sumiu"
    # a limpeza: soltar o mouse esconde as guias — no soltar do CARTAO
    # (a alça tem um `soltar` próprio antes dele no arquivo)
    i3 = js.index("const soltar = (e) => {", js.index("function cartaoArrastavel"))
    assert "esconderGuias(box)" in js[i3:i3 + 400]
