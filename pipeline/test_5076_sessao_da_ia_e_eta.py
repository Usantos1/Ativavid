# -*- coding: utf-8 -*-
"""5.0.76: dois defeitos vistos nos dados dele em 05/09.

1. **"~22min34s restantes" num refazer.** A previsão de tempo saiu na
   4.14, mas 41 jobs gravados na época ainda carregam `etaLabel` no blob
   do registro; ao refazer um deles, o card mostrava o número velho nos
   primeiros 20 s (até o "há 1 min" cobrir). O rótulo NUNCA vem do
   registro: `attach_eta` apaga o que veio gravado.

2. **Sessões da IA mortas sem ninguém ver.** No lote de 04/09 as sessões
   do Gemini e do ChatGPT expiraram: 17 vídeos saíram com plano via Groq e
   sem revisão, e o único rastro era `[warn]` no pipeline.log. A regra
   "erro mais novo que a captura" nunca disparava porque a extensão
   recaptura a cada 2 min. Agora o Doutor SONDA (pede o token de verdade)
   e a linha "Tudo funcionando corretamente" avisa, com botão para a tela
   IA. O painel IA fica como está (a recaptura restaura o estado dele —
   `test_licenca_gate` cobra isso); a verdade mora na checagem.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.eta_estimate import attach_eta  # noqa: E402


# ------------------------------------------------------------------ 1. ETA

def _job(minutos: float, status: str = "processing") -> dict:
    quando = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    return {"status": status, "startedAt": quando.isoformat(),
            "etaLabel": "~22min34s restantes"}


def test_rotulo_gravado_no_registro_nao_aparece_nos_primeiros_segundos():
    j = _job(0.2)
    attach_eta(j, [], None)
    assert "etaLabel" not in j


def test_rotulo_gravado_e_trocado_pelo_tempo_corrido():
    j = _job(7)
    attach_eta(j, [], None)
    assert j["etaLabel"] == "há 7 min"


def test_job_pronto_perde_o_rotulo_velho():
    j = _job(3, status="done")
    attach_eta(j, [], None)
    assert "etaLabel" not in j


# --------------------------------------------------------- 2. sessao da IA

PROVEDORES = {
    "gemini-web": {"id": "gemini-web", "name": "Gemini Web"},
    "chatgpt-web": {"id": "chatgpt-web", "name": "ChatGPT Web"},
    "claude-web": {"id": "claude-web", "name": "Claude Web"},
}


def _checar(monkeypatch, capturadas: list[str], sonda: dict):
    import doutor

    ls = types.ModuleType("app.local_server")
    ls.SESSION_PROVIDERS = PROVEDORES
    ls.load_sessions = lambda: {"providers": {
        p: {"capturedAt": "2026-09-05T17:50:01Z"} for p in capturadas}}
    monkeypatch.setitem(sys.modules, "app.local_server", ls)
    from app import llm_session
    monkeypatch.setattr(llm_session, "sondar", lambda pid: sonda.get(pid, (None, "sem sonda")))
    monkeypatch.setattr(llm_session, "saude_dos_provedores", lambda: {})
    doutor._itens.clear()
    doutor.checar_ia()
    itens = [dict(i) for i in doutor._itens]
    doutor._itens.clear()
    return itens


def test_as_duas_mortas_avisa_e_diz_o_que_esta_acontecendo(monkeypatch):
    itens = _checar(monkeypatch, ["gemini-web", "chatgpt-web", "claude-web"], {
        "gemini-web": (False, "Token Gemini ausente — abra gemini.google.com logado"),
        "chatgpt-web": (False, "ChatGPT sem accessToken"),
    })
    assert len(itens) == 1 and itens[0]["nivel"] == "aviso"
    assert itens[0]["titulo"] == "Sessao da IA expirada: Gemini Web e ChatGPT Web"
    assert "Groq" in itens[0]["solucao"] and "SEM a revisao" in itens[0]["solucao"]
    assert itens[0]["acao"] == "ia" and itens[0]["acaoTexto"] == "Abrir IA"
    assert "Claude" not in itens[0]["titulo"], "sem sonda, nao conta como viva nem como caida"


def test_uma_viva_basta_para_o_plano(monkeypatch):
    itens = _checar(monkeypatch, ["gemini-web", "chatgpt-web"], {
        "gemini-web": (True, ""), "chatgpt-web": (False, "sem accessToken"),
    })
    assert itens[0]["nivel"] == "aviso"
    assert itens[0]["titulo"].startswith("Uma sessao da IA expirou: ChatGPT Web")
    assert "Gemini Web" in itens[0]["detalhe"]


def test_tudo_vivo_e_ok(monkeypatch):
    itens = _checar(monkeypatch, ["gemini-web"], {"gemini-web": (True, "")})
    assert itens[0]["nivel"] == "ok"
    assert itens[0]["titulo"] == "IA principal respondendo: Gemini Web"


@pytest.mark.parametrize("capturadas", [[], ["claude-web"]])
def test_sem_sessao_do_planejador_avisa(monkeypatch, capturadas):
    itens = _checar(monkeypatch, capturadas, {})
    assert itens[0]["nivel"] == "aviso" and itens[0]["titulo"] == "IA principal sem sessao"
    assert itens[0]["acao"] == "ia"


def test_a_sonda_sem_cookies_e_sem_provedor_conhecido(monkeypatch):
    from app import llm_session as L

    monkeypatch.setattr(L, "_cookie_map", lambda pid: {})
    assert L.sondar("gemini-web") == (False, "sem sessao capturada")
    monkeypatch.setattr(L, "_cookie_map", lambda pid: {"x": "y"})
    assert L.sondar("claude-web") == (None, "sem sonda")


def test_o_doutor_sonda_em_vez_de_olhar_a_captura():
    src = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")
    corpo = src[src.index("def checar_ia("):src.index("def checar_espaco(")]
    assert "sondar(pid)" in corpo
    assert 'h.get("at")' not in corpo, "a captura de 2 em 2 min nao prova nada"
    main = src[src.index("def main("):]
    assert "checar_ia, checar_chaves" in main


def test_a_tela_abre_a_ia_pelo_botao_do_doutor():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    fn = js[js.index("function wireAcoesDoDoutor(out)"):][:700]
    assert 'if (acao === "ia") { setView("ia"); return; }' in fn
