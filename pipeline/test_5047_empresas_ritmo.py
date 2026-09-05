# -*- coding: utf-8 -*-
"""5.0.47: o card da empresa diz o RITMO — quantos vídeos em 30 dias e a nota.

"307 vídeos · 3 presets" diz o tamanho da pilha, não se a empresa está
parada. Para quem atende várias, o que importa é "quantos saíram este mês"
e "como estão saindo". Vem do que a tela já tem (`state.jobs`: finishedAt,
status, score.overall), sem pedido novo ao servidor.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_card_conta_os_30_dias_e_a_nota():
    i = JS.index("function renderEmpresaCards")
    corpo = JS[i:i + 3000]
    assert "30 * 864e5" in corpo, "janela de 30 dias"
    assert 'x.status === "done"' in corpo, "so video pronto conta no ritmo"
    assert "x.score && x.score.overall" in corpo
    assert "em 30 dias" in corpo and "nota ${media}" in corpo


def test_sem_video_nao_inventa_ritmo():
    i = JS.index("function renderEmpresaCards")
    corpo = JS[i:i + 3000]
    assert 'const ritmo = n ? ' in corpo, "empresa sem video fica so com o total"
