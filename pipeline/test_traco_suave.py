# -*- coding: utf-8 -*-
"""O traço de ênfase precisa de borda suave.

O `ImageDraw.line` do PIL desenha sem suavização: a borda sai em degraus, e
o círculo de ênfase é uma elipse deitada — justamente o ângulo onde o
serrilhado aparece. Medido em 29/08 contra o Remotion no mesmo quadro do
mesmo vídeo: o navegador tinha 649 pixels de meio-tom na borda do traço e o
motor próprio ZERO. Com o desenho em 3x reduzido por média de área: 541
(razão 0,18 contra 0,21 do navegador).
"""
import numpy as np

from app.render_proprio import _mascara_linha


def _meios_tons(mask) -> int:
    a = np.asarray(mask, dtype=np.int32)
    return int(((a > 10) & (a < 245)).sum())


def test_diagonal_tem_meio_tom_na_borda():
    pontos = [(10.0, 10.0), (190.0, 60.0)]
    m = _mascara_linha(pontos, 200, 80, 0, 0, 9)
    a = np.asarray(m, dtype=np.int32)
    assert a.max() > 240, "não desenhou o traço"
    assert _meios_tons(m) > 100, "borda dura: sem suavização"


def test_a_suavizacao_e_uma_fatia_de_verdade_do_traco():
    """Nao basta "ter algum meio-tom": a borda suave tem de ser uma parcela
    real do traco. No navegador a razao medida foi 0,21 (649 meio-tons para
    3099 de nucleo); abaixo de 0,05 o traco esta praticamente duro."""
    m = _mascara_linha([(10.0, 10.0), (190.0, 60.0)], 200, 80, 0, 0, 9)
    a = np.asarray(m, dtype=np.int32)
    nucleo = int((a >= 245).sum())
    assert nucleo > 500, "traco fino demais para julgar"
    assert _meios_tons(m) / nucleo > 0.05, "borda quase dura"


def test_traco_vazio_nao_quebra():
    m = _mascara_linha([], 50, 50, 0, 0, 9)
    assert np.asarray(m).max() == 0
    m = _mascara_linha([(1.0, 1.0)], 50, 50, 0, 0, 9)
    assert np.asarray(m).max() == 0


def test_caixa_minima_nao_quebra():
    m = _mascara_linha([(0.0, 0.0), (1.0, 1.0)], 0, 0, 0, 0, 9)
    assert m.size == (1, 1)


def test_os_dois_desenhos_usam_o_mesmo_caminho():
    """Traço (círculo) e marca-texto compartilham a rasterização — se um
    voltar a desenhar direto no PIL, o serrilhado volta só nele."""
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "app" / "render_proprio.py"
         ).read_text(encoding="utf-8")
    assert s.count("_mascara_linha(sub") == 2
    assert "dr.line(desl" not in s.split("def _mascara_linha")[1].split(
        "def ", 1)[1], "sobrou desenho sem suavização fora do ajudante"
