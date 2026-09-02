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


def _renderizador(tmp_path: Path, entrada: str | None, saida: str | None = None):
    from app.render_proprio import Renderizador

    public = tmp_path / f"public_{entrada or 'padrao'}_{saida or 'suave'}"
    public.mkdir()
    Image.new("RGB", (200, 130), (255, 40, 40)).save(public / "foto.jpg")
    it = {"src": "foto.jpg", "start": 0.0, "end": FRAMES / FPS}
    if entrada:
        it["entrada"] = entrada
    if saida:
        it["saida"] = saida
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
    rend = _renderizador(tmp_path, "cambalhota")   # valor que não existe
    cx2, area2 = _caixa(rend, 2)
    assert area2 > 0
    pad = _renderizador(tmp_path, None)
    cxp, areap = _caixa(pad, 2)
    assert abs(cx2 - cxp) < 2 and abs(area2 - areap) <= areap * 0.02


def test_zoom_chega_de_longe_e_fade_nao_se_mexe(tmp_path):
    zoom = _renderizador(tmp_path, "zoom")
    _, z1 = _caixa(zoom, 1)
    pad = _renderizador(tmp_path, None)
    _, p1 = _caixa(pad, 1)
    # zoom nasce MAIOR que o final (1,25) — bem maior que o padrão (0,94)
    assert z1 > p1 * 1.3, f"zoom f1={z1} padrao f1={p1}"
    fade = _renderizador(tmp_path, "fade")
    cxa, _ = _caixa(fade, 1)
    cxb, _ = _caixa(fade, 12)
    assert abs(cxa - cxb) < 2, "fade não pode se mexer"


def test_saida_deslizar_vai_para_a_direita(tmp_path):
    rend = _renderizador(tmp_path, None, "deslizar")
    cx_meio, _ = _caixa(rend, FRAMES - 12)
    cx_fim, a_fim = _caixa(rend, FRAMES - 3)
    assert a_fim > 0
    assert cx_fim > cx_meio + 15, f"não saiu p/ direita: {cx_meio} -> {cx_fim}"


def test_saida_encolher_diminui(tmp_path):
    rend = _renderizador(tmp_path, None, "encolher")
    _, a_meio = _caixa(rend, FRAMES - 12)
    _, a_fim = _caixa(rend, FRAMES - 3)
    suave = _renderizador(tmp_path, None)
    _, s_fim = _caixa(suave, FRAMES - 3)
    assert a_fim < a_meio * 0.8, f"não encolheu: {a_meio} -> {a_fim}"
    assert a_fim < s_fim, "encolher deveria ser menor que a saída suave"


def test_saida_corte_segura_a_tinta_ate_o_fim(tmp_path):
    """Sem fade: no penúltimo quadro o cartão ainda está inteiro."""
    import numpy as np

    corte = _renderizador(tmp_path, None, "corte")
    suave = _renderizador(tmp_path, None)

    def alfa_max(rend, f):
        buf = np.zeros((H, W, 4), dtype=np.uint8)
        for leg in rend.camadas:
            if getattr(leg, "insert", None) is None:
                continue
            rend._desenhar_insert(leg, float(f - leg.inicio_f), buf, [0, 0, 0, 0], False)
        return int(buf[..., 3].max())

    f = FRAMES - 3
    assert alfa_max(corte, f) > 240, "corte seco não pode esmaecer"
    assert alfa_max(suave, f) < 160, "a saída suave deveria estar esmaecendo"


def test_entradas_novas_vem_do_lado_certo(tmp_path):
    dir_ = _renderizador(tmp_path, "direita")
    cx1, _ = _caixa(dir_, 1)
    cx12, _ = _caixa(dir_, 12)
    assert cx1 > cx12 + 15, f"'direita' não veio da direita: {cx1} -> {cx12}"

    def _cy(rend, f):
        import numpy as np

        buf = np.zeros((H, W, 4), dtype=np.uint8)
        for leg in rend.camadas:
            if getattr(leg, "insert", None) is None:
                continue
            rend._desenhar_insert(leg, float(f - leg.inicio_f), buf, [0, 0, 0, 0], False)
        a = buf[..., 3] > 8
        ys = np.where(a.any(axis=1))[0]
        return float(ys.mean()) if len(ys) else -1

    baixo = _renderizador(tmp_path, "baixo")
    assert _cy(baixo, 1) > _cy(baixo, 12) + 15, "'baixo' não subiu"
    saiu = _renderizador(tmp_path, None, "baixo")
    assert _cy(saiu, FRAMES - 3) > _cy(saiu, FRAMES - 12) + 10, "saída 'baixo' não caiu"


def test_girar_desenha_o_cartao_torto_na_entrada(tmp_path):
    """Cartão reto tem toda linha com a mesma largura; girado, as larguras
    variam linha a linha — é a prova de que a rotação foi desenhada."""
    import numpy as np

    def larguras(rend, f):
        buf = np.zeros((H, W, 4), dtype=np.uint8)
        for leg in rend.camadas:
            if getattr(leg, "insert", None) is None:
                continue
            rend._desenhar_insert(leg, float(f - leg.inicio_f), buf, [0, 0, 0, 0], False)
        # BORDA ESQUERDA por linha: num cartão reto ela é vertical (x
        # constante); girado, ela escorrega linha a linha (tan 8° ~ 0,15).
        # A largura da fatia não serve: retângulo inclinado tem fatias de
        # largura ~constante no miolo.
        # No quadro 1 a opacidade ainda está em ~0,3 — limiar baixo.
        a = buf[..., 3] > 40
        xs = [int(np.where(r)[0][0]) for r in a if r.any()]
        n = len(xs)
        # só o MEIO: cantos arredondados entortam a borda nas pontas
        return xs[n // 4:(3 * n) // 4] or xs

    rend = _renderizador(tmp_path, "girar")
    torto = larguras(rend, 1)
    reto = larguras(rend, 14)
    assert torto and reto
    assert (max(torto) - min(torto)) > 10, f"não girou: {min(torto)}..{max(torto)}"
    assert (max(reto) - min(reto)) < 4, f"assentou torto: {min(reto)}..{max(reto)}"


def test_saida_zoom_cresce_enquanto_some(tmp_path):
    """Largura do CORPO do cartão, não área total: o fade derruba a franja
    da sombra abaixo do limiar e mascararia o crescimento."""
    import numpy as np

    def largura(rend, f):
        buf = np.zeros((H, W, 4), dtype=np.uint8)
        for leg in rend.camadas:
            if getattr(leg, "insert", None) is None:
                continue
            rend._desenhar_insert(leg, float(f - leg.inicio_f), buf, [0, 0, 0, 0], False)
        corpo = buf[..., 3] > 60
        xs = np.where(corpo.any(axis=0))[0]
        return int(xs.max() - xs.min() + 1) if len(xs) else 0

    rend = _renderizador(tmp_path, None, "zoom")
    meio = largura(rend, FRAMES - 12)
    fim = largura(rend, FRAMES - 3)
    assert fim > meio * 1.1, f"saída zoom não cresceu: {meio} -> {fim}"


def test_template_e_motor_tem_as_mesmas_formulas():
    """As três entradas moram nos DOIS motores — quem mexer numa fórmula
    precisa mexer nas duas (regra do motor-proprio-cobre-tudo)."""
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    for lado in (tsx, py):
        assert "2.70158" in lado and "1.70158" in lado, "back.out sumiu de um motor"
        assert "0.35" in lado, "o deslizar de 35% sumiu de um motor"
    assert "entrada === 'pop'" in tsx and "entrada === 'deslizar'" in tsx
    assert "entrada === 'zoom'" in tsx and "saida === 'encolher'" in tsx
    assert "saida === 'corte'" in tsx and "saida === 'deslizar'" in tsx
    for novo in ("'direita'", "'baixo'", "'cima'", "'girar'", "'esquerda'"):
        assert novo in tsx, f"efeito {novo} sumiu do template"
    assert '"pop"' in py and '"deslizar"' in py
    assert '"zoom"' in py and '"encolher"' in py and '"corte"' in py
    for novo in ('"direita"', '"baixo"', '"cima"', '"girar"', '"esquerda"'):
        assert novo in py, f"efeito {novo} sumiu do motor proprio"
    # rotacao: CSS gira em graus horarios, Pillow anti-horario
    assert "rotate(-ang" in py and "rotate: Math.abs(ang)" in tsx
    # e o pipeline deixa a escolha PASSAR do preview para o edit-data
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'geo["entrada"]' in rf, "run_fast parou de repassar a entrada"
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "c.entrada ? { entrada: c.entrada }" in js, (
        "o salvar do preview parou de mandar a entrada")
