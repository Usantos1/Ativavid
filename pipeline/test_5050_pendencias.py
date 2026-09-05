# -*- coding: utf-8 -*-
"""5.0.50: o Início diz o que espera por alguém; Projetos filtra "Com pendência".

Correção salva e não aplicada ficava escondida no menu de cada card (7
projetos, o mais velho de 18/08); vídeo parado idem. Agora uma linha no
Início conta os dois, com atalho para o filtro certo em Projetos.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")


def test_inicio_tem_a_linha_e_projetos_o_filtro():
    assert 'id="homePendencias"' in HTML
    assert 'data-proj="pendentes"' in HTML
    assert 'if (f === "pendentes") return !!j.pedidoTipo;' in JS


def test_a_linha_conta_pendentes_e_parados_e_some_quando_zero():
    i = JS.index("function renderPendencias()")
    corpo = JS[i:i + 1400]
    assert "j.pedidoTipo" in corpo
    assert 'j.status === "error" || j.status === "needs_review"' in corpo
    assert 'el.classList.add("hidden")' in corpo, "zero pendencias = linha some"
    assert 'data-ir-projetos="pendentes"' in corpo and 'data-ir-projetos="parados"' in corpo
    assert "el.dataset.sig === sig" in corpo, "nao repinta a cada poll sem mudanca"


def test_o_atalho_troca_o_filtro_e_a_tela():
    i = JS.index("function irParaProjetosCom(filtro)")
    corpo = JS[i:i + 700]
    assert "state.projFilter = filtro" in corpo
    assert "[data-view=\"projetos\"]" in corpo and "nav.click()" in corpo
    assert 'aria-selected' in corpo, "o chip certo acende"
    assert "renderPendencias();" in JS[JS.index('renderInto("jobListRecent"') - 200:JS.index('renderInto("jobListRecent"')]
