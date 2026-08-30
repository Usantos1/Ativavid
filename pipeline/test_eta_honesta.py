# -*- coding: utf-8 -*-
"""A Fila mostra o tempo corrido, não uma previsão errada.

Medido nos 172 vídeos do usuário, prevendo cada um com os outros como
histórico (deixa-um-de-fora):

    erro relativo:  mediana **47%**, média 58%
    dentro de 25%:  42 de 172 (**24%**)

Os extremos: disse *"~1 min restante"* num vídeo que levou **15 minutos**;
disse *"~9 min restantes"* num que levou 1,5. É a mesma conclusão que o
apply já tinha tirado, com o mesmo número — e a frase que ficou no código
de lá vale aqui: dizer "cerca de 2 minutos" e levar 40s é pior que não
dizer nada.

O tempo corrido responde à mesma pergunta de quem olha a Fila — "isso
travou?" — sem prometer nada.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.eta_estimate import attach_eta, format_elapsed  # noqa: E402

EE = (REPO / "app" / "eta_estimate.py").read_text(encoding="utf-8")


def _job(minutos: float, status: str = "processing") -> dict:
    quando = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    return {"status": status, "startedAt": quando.isoformat()}


def test_mostra_o_tempo_corrido():
    j = _job(7)
    attach_eta(j, [], None)
    assert j["etaLabel"] == "há 7 min"


def test_nao_fala_nos_primeiros_segundos():
    """"há 0 min" não informa nada."""
    j = _job(0.2)
    attach_eta(j, [], None)
    assert "etaLabel" not in j


def test_job_pronto_nao_ganha_rotulo():
    j = _job(3, status="done")
    attach_eta(j, [], None)
    assert "etaLabel" not in j


def test_nao_promete_quanto_falta():
    """A promessa saiu; nenhuma frase de 'restantes' pode voltar por aqui."""
    i = EE.index("def attach_eta(")
    corpo = EE[i:EE.index("def _segundos_rodando(", i)]
    assert "format_eta(" not in corpo
    assert "remaining_seconds(" not in corpo


def test_data_ilegivel_nao_derruba():
    for bruto in ("", "ontem", None):
        j = {"status": "processing", "startedAt": bruto}
        attach_eta(j, [], None)
        assert "etaLabel" not in j


def test_o_formato_e_curto():
    assert format_elapsed(19) is None
    assert format_elapsed(60) == "há 1 min"
    assert format_elapsed(3600) == "há 60 min"
