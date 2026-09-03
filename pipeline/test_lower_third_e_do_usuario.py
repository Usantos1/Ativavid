# -*- coding: utf-8 -*-
"""O lower third do vídeo longo mostra a marca DO USUÁRIO, nunca a nossa.

Caso real de 02/09 ("onde ta esse segue ativavid na tela?"): a linha 1 do
card final ("Segue @lojaprimecamp") virava name="Segue" (primeira palavra)
e o title caía num padrão chumbado "ATIVAVID" — o app carimbava o próprio
nome no vídeo do cliente. O @handle é o nome; sem @, a linha inteira; sem
linha nenhuma, o lower third nem entra.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pipeline.run_fast import build_longform_edit_data  # noqa: E402


def _montar(copy: dict) -> list[dict]:
    ed = build_longform_edit_data(
        Path("nao-existe.mp4"), {"endCardCopy": copy, "accent": "#ff0004"},
        duration=60.0, fps=30.0, edl_ranges=[])
    return ed["lowerThirds"]


def test_o_handle_da_linha_1_vira_o_nome():
    lts = _montar({"line1": "Segue @lojaprimecamp", "line2": ""})
    assert lts and lts[0]["name"] == "@lojaprimecamp"
    # sem linha 2, NAO existe title — nada de "ATIVAVID" chumbado
    assert "title" not in lts[0]


def test_linha_sem_arroba_entra_inteira():
    lts = _montar({"line1": "Prime Camp Assistência", "line2": "Centro"})
    assert lts[0]["name"] == "Prime Camp Assistência"
    assert lts[0]["title"] == "Centro"


def test_sem_marca_nenhuma_o_lower_third_nem_entra():
    assert _montar({"line1": "", "line2": ""}) == []
    assert _montar({}) == []


def test_o_nome_do_app_nao_e_padrao_de_ninguem():
    s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.index("def build_longform_edit_data")
    bloco = s[i:s.index("\ndef ", i + 10)]
    assert 'or "ATIVAVID"' not in bloco and '"Marca"' not in bloco
