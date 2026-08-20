# -*- coding: utf-8 -*-
"""O tempo restante respeita o relógio e o progresso.

O rótulo antigo era o total histórico, parado: "~23 min restantes" por horas
enquanto o trabalho corria. Estes testes prendem as três regras novas.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.eta_estimate import remaining_seconds  # noqa: E402


def _ha(segundos: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=segundos)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_previsto_encolhe_com_o_relogio():
    job = {"startedAt": _ha(300), "progress": 5}
    assert remaining_seconds(job, est_total=600) < 320, "tem de descontar os 5 min"


def test_nunca_fica_parado_no_total_historico():
    parado = remaining_seconds({"startedAt": _ha(0), "progress": 0}, 1400)
    depois = remaining_seconds({"startedAt": _ha(600), "progress": 0}, 1400)
    assert depois < parado - 500


def test_progresso_real_corrige_a_previsao():
    # 100 s decorridos com 50% feito -> ritmo observado diz ~100 s restantes,
    # mesmo que o histórico chutasse 1400
    r = remaining_seconds({"startedAt": _ha(100), "progress": 50}, 1400)
    assert r < 500, f"historico nao pode dominar com progresso real: {r}"


def test_progresso_alto_domina():
    r = remaining_seconds({"startedAt": _ha(200), "progress": 90}, 1400)
    assert r < 60


def test_sem_nada_devolve_none():
    assert remaining_seconds({}, None) is None


def test_so_historico_sem_relogio_continua_funcionando():
    assert remaining_seconds({}, 300) == 300
