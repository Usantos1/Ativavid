# -*- coding: utf-8 -*-
"""5.0.42: o `/api/jobs` não carrega o que a tela não usa.

Medido em 05/09 no app dele (331 projetos): 877 KB por pedido, a cada
2,5 s com trabalho na fila. A legenda do post era 18% e o `score.json`
inteiro 10%. A tela usa a legenda só como "tem/não tem" — o botão Copiar
busca o arquivo FRESCO em `/api/jobs/<id>/legenda`, porque o retrato
envelhece (uma correção de palavra aplicada depois também conserta o
arquivo) — e do score só `overall` e a primeira dica.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.jobs_view import _aliviar_card  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_legenda_vira_tem_legenda():
    j = {"legenda": "texto do post " * 300}
    _aliviar_card(j)
    assert j["temLegenda"] is True and j["legenda"] == ""


def test_sem_legenda_nao_inventa():
    j = {"legenda": ""}
    _aliviar_card(j)
    assert "temLegenda" not in j


def test_score_fica_so_com_nota_e_primeira_dica():
    j = {"score": {"overall": 80, "hook": 86, "clarity": 84, "rhythm": 88, "cta": 56,
                   "tips": ["", "melhore o CTA", "outra"], "disclaimer": "x" * 200}}
    _aliviar_card(j)
    assert j["score"] == {"overall": 80, "tips": ["melhore o CTA"]}


def test_score_estranho_nao_derruba():
    j = {"score": "nao e dict"}
    _aliviar_card(j)
    assert j["score"] == "nao e dict"
    j = {"score": {"overall": 70, "tips": "string"}}
    _aliviar_card(j)
    assert j["score"] == {"overall": 70, "tips": []}


def test_a_tela_le_tem_legenda():
    assert JS.count("(j.temLegenda || j.legenda)") >= 2, (
        "o L da tabela e o botao Copiar precisam ler temLegenda")
    assert "fetch(`/api/jobs/${id}/legenda`)" in JS, "o Copiar busca o arquivo fresco"


def test_o_card_passa_pelo_alivio():
    src = (REPO / "app" / "jobs_view.py").read_text(encoding="utf-8")
    i = src.index('score_path = edit / "score.json"')
    assert "_aliviar_card(j)" in src[i:i + 400]
