# -*- coding: utf-8 -*-
"""Trilha de IA pedida e nao entregue NUNCA e muda.

Caso real (25/08): creditos do ElevenLabs esgotaram; o job das 18:58 saiu
sem musica com soundtrack.enabled=false e ZERO registro — nem timing, nem
card. So uma auditoria manual descobriu.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def test_pipeline_registra_a_falha_da_trilha():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert '"musicaSkip"' in s, "o registro da falha da trilha sumiu"
    assert "insufficient_credits" in s, \
        "a causa mais comum (creditos esgotados) precisa de mensagem propria"
    i = s.find('payload["musicaSkip"]')
    assert i > 0, "musicaSkip nao chega ao timing.json"


def test_card_avisa_sem_trilha(tmp_path):
    from app.jobs_view import _aviso_de_trilha

    (tmp_path / "timing.json").write_text(json.dumps(
        {"musicaSkip": "créditos do ElevenLabs esgotados — renove o plano"}),
        encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "Sem trilha" in job["trilhaNota"]
    assert "ElevenLabs" in job["trilhaNota"]

    (tmp_path / "timing.json").write_text(json.dumps({}), encoding="utf-8")
    job2 = {}
    _aviso_de_trilha(job2, tmp_path)
    assert "trilhaNota" not in job2

    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "trilhaNota" in js, "a ficha do card nao mostra a nota da trilha"
