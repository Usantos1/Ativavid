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


def test_nota_groq_distingue_parse_de_sessao(tmp_path):
    """"Se da tudo OK, por que da isso?" (26/08): a nota mandava recapturar
    com o Gemini saudavel — o Groq tinha entrado por PARSE quebrado, nao por
    sessao morta. O conselho segue o motivo."""
    from app.jobs_view import _aviso_de_ia

    (tmp_path / "result.json").write_text(json.dumps(
        {"llm": {"ok": True, "backend": "groq", "groqVia": "parse"}}),
        encoding="utf-8")
    job = {"status": "done"}
    _aviso_de_ia(job, tmp_path)
    assert "ilegível" in job["iaNota"] and "Recapture" not in job["iaNota"]

    (tmp_path / "result.json").write_text(json.dumps(
        {"llm": {"ok": True, "backend": "groq"}}), encoding="utf-8")
    job2 = {"status": "done"}
    _aviso_de_ia(job2, tmp_path)
    assert "Recapture" in job2["iaNota"]


def test_meta_do_plano_carrega_o_motivo_do_groq():
    s = (RAIZ / "helpers" / "llm_cut_plan.py").read_text(encoding="utf-8")
    assert "groqVia" in s, "o motivo do groq nao chega ao result.json"
    assert 'ULTIMO_GROQ_MOTIVO = "parse"' in s
    gw = (RAIZ / "app" / "llm_gateway.py").read_text(encoding="utf-8")
    assert 'ULTIMO_GROQ_MOTIVO = "sessao"' in gw


def test_testar_elevenlabs_avisa_creditos():
    s = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    assert "character_limit" in s, \
        "o Testar dizia OK com a carteira zerada — chave valida != creditos"
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "res.hint" in js, "a UI descarta o hint do teste de chave"


def test_refazer_reaproveita_a_trilha():
    """346k creditos do ElevenLabs evaporaram em dias (26/08): CADA render
    gerava musica nova — refazer, Gerar 5 versoes, reprocesso. A trilha do
    render anterior agora e reaproveitada quando cobre o corte novo e o
    clima (vibe) nao mudou; so ai se paga geracao nova."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "soundtrack REAPROVEITADA" in s
    assert "vibe_antigo == music_vibe.strip()" in s, \
        "trocar o clima da musica tem que gerar de novo"
    assert "dur_antiga + 0.5 >= planned_keep" in s, \
        "corte mais longo que a trilha tem que gerar de novo"
    assert "and not reuso" in s, "o reuso tem que PULAR a geracao"
    assert '.vibe.txt' in s, "sem gravar o vibe usado nao ha chave de reuso"


def test_marca_vazia_desliga_o_card_final_em_vez_de_bloquear(tmp_path):
    """Cliente novo (26/08): 5 de 5 primeiros jobs travados no REVISAR com
    'Falta o texto da marca' — pessimo onboarding. Sem endCardCopy o video
    sai SEM o card final e a ficha avisa onde preencher."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'raise NeedsReview("missing_brand_copy"' not in s, \
        "o bloqueio de marca vazia voltou"
    assert '"endCardSkip"' in s and 'elems["endCard"] = False' in s

    from app.jobs_view import _aviso_de_trilha

    (tmp_path / "timing.json").write_text(json.dumps(
        {"endCardSkip": "sem texto da marca — preencha em Estilos"}),
        encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "Card final desligado" in job["cardFinalNota"]
