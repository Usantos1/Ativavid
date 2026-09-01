# -*- coding: utf-8 -*-
"""Emoji na headline sai COLORIDO — não em caixinha.

Ele pediu em 31/08: "Eu quero Emoji na hedline sim — Foi Traído 2 Vezes
🐂🐂". Antes, a headline usava o caminho cego a emoji (`_mascara`), e a
fonte de marca não tem o glifo: saíam duas caixas no vídeo. As LEGENDAS já
desenhavam emoji certo (`_mascara_cor` + `_pintar_emoji`); a headline, o
bloco de várias linhas (manchete/moldura) e o cartão final passam agora
pelo mesmo par.

A largura também: `_larg_hl` media o emoji na fonte de marca — caixa de
.notdef por code point, FE0F e ZWJ inclusive — e a moldura sairia larga
demais. Agora cada trecho é medido na fonte que vai desenhá-lo.

Conferido com imagem (31/08): os dois bois coloridos dentro da caixa
vermelha do estilo dele, contorno acompanhando a silhueta, largura justa.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.render_proprio import EMOJI_FONT, Renderizador

REPO = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not EMOJI_FONT.exists(), reason="sem Segoe UI Emoji nesta máquina")


def _ed(hook: dict) -> dict:
    return {"width": 1080, "height": 1920, "fps": 30, "durationSec": 4,
            "hook": hook, "captions": {"enabled": False},
            "endCard": {"enabled": False}, "soundtrack": {"enabled": False},
            "transitions": [], "inserts": [], "behind": [],
            "camera": {"enabled": False, "zooms": [1]}}


def _render(tmp_path: Path, hook: dict) -> Renderizador:
    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True)
    return Renderizador(public, _ed(hook), frames=120, fps=30)


def _tem_pixel_colorido(cam) -> bool:
    """Pixel do emoji: saturado (canais bem diferentes) onde ha alpha.

    A tinta do texto e branca/vermelha chapada; o boi da Segoe e marrom —
    R, G e B diferentes entre si na regiao visivel.
    """
    for p in cam.palavras:
        vis = p.alpha > 0.5
        if not vis.any():
            continue
        rgb = p.rgb[vis]
        spread = rgb.max(axis=1) - rgb.min(axis=1)
        # marrom do boi: spread alto SEM ser o vermelho puro do fundo
        marrons = (spread > 30) & (rgb.max(axis=1) < 230) & (rgb.min(axis=1) > 8)
        if int(marrons.sum()) > 200:
            return True
    return False


def test_headline_com_emoji_sai_colorida(tmp_path):
    r = _render(tmp_path, {
        "enabled": True, "endSec": 3, "style": "blocos",
        "lines": ["Foi Traído", "2 Vezes 🐂🐂"], "accent": "#e30004"})
    assert r.camadas, "headline nao virou camada"
    assert _tem_pixel_colorido(r.camadas[0]), \
        "emoji saiu monocromatico (tinta do texto) — caminho cego de novo"


def test_headline_sem_emoji_nao_mudou(tmp_path):
    """A troca de _mascara por _mascara_cor tem atalho para texto puro —
    o retorno é o mesmo objeto de antes."""
    r = _render(tmp_path, {
        "enabled": True, "endSec": 3, "style": "blocos",
        "lines": ["Sem emoji", "nenhum aqui"], "accent": "#e30004"})
    assert r.camadas
    assert not _tem_pixel_colorido(r.camadas[0])


def test_largura_mede_na_fonte_do_emoji(tmp_path):
    r = _render(tmp_path, {"enabled": True, "endSec": 3, "style": "blocos",
                           "lines": ["x"], "accent": "#e30004"})
    so_texto = r._larg_hl("Vezes", 100)
    com_emoji = r._larg_hl("Vezes \U0001F402\U0001F402", 100)
    # dois bois avancam ~2 quadrados da fonte de emoji; na fonte de marca
    # cada code point viraria caixa de .notdef e a conta estourava
    assert com_emoji > so_texto + 100
    assert com_emoji < so_texto + 400, "largura de .notdef vazou para a conta"


def test_os_tres_desenhistas_usam_o_par_com_cor():
    s = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = s.index("def _hl_bloco_texto(")
    assert "_mascara_cor(f, texto" in s[i:i + 2600]
    j = s.index("def _hl_bloco_multi(")
    assert "_mascara_cor(f, l" in s[j:j + 2000]
    k = s.index("def _montar_endcard(")
    assert "_mascara_cor(f, t" in s[k:k + 2400]
