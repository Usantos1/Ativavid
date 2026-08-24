# -*- coding: utf-8 -*-
"""O planejador tem a mesma rede do gateway: Groq quando a sessão morre.

Em 23/08 as sessões Gemini e ChatGPT expiraram JUNTAS (mesmo navegador, mesma
extensão) e um vídeo real saiu com o título cru — com a chave do Groq parada no
.env o tempo todo. O gateway do editor sempre teve essa queda; o planejador
chamava `llm_session.chat` direto e ficava sem nenhuma.

Provado ao vivo com as sessões mortas de verdade: 4 de 4 projetos reais saíram
com plano e headline pelo Groq ("Salve seu celular molhado", 4,6-7,2s cada).

O que se trava aqui:
  - a queda só existe COM a chave (sem ela, o erro de sessão continua)
  - o pedido ao Groq exige JSON garantido — sem `response_format` o modelo
    devolveu um plano com vírgula faltando e o parse caiu (plano real)
  - a falha dupla mostra as DUAS causas, e resposta vazia não passa adiante
  - com a sessão viva, o Groq nem é tocado (custo por engano é bug)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))

import app.llm_gateway as gw  # noqa: E402
import app.llm_session as ls  # noqa: E402
from llm_cut_plan import _chat_com_rede  # noqa: E402

MSGS = [{"role": "user", "content": "plano"}]


def _sessao_morta(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("As sessões Gemini e ChatGPT expiraram.")
    monkeypatch.setattr(ls, "chat", explode)


def test_sessao_viva_nao_toca_o_groq(monkeypatch):
    monkeypatch.setattr(ls, "chat", lambda *a, **k: ("texto", "gemini-web"))
    def nunca(*a, **k):
        raise AssertionError("Groq chamado com a sessão viva — custo por engano")
    monkeypatch.setattr(gw, "_groq_chat", nunca)
    assert _chat_com_rede(MSGS) == ("texto", "gemini-web")


def test_sessao_morta_cai_para_o_groq(monkeypatch):
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    visto = {}
    def groq(messages, model, extras=None):
        visto["extras"] = extras
        return {"choices": [{"message": {"content": '{"ranges": []}'}}]}
    monkeypatch.setattr(gw, "_groq_chat", groq)
    texto, backend = _chat_com_rede(MSGS)
    assert backend == "groq" and texto == '{"ranges": []}'
    assert visto["extras"] == {"response_format": {"type": "json_object"}}, (
        "sem JSON garantido o parse já caiu num plano real")


def test_sem_chave_o_erro_de_sessao_continua(monkeypatch):
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "")
    with pytest.raises(RuntimeError, match="expiraram"):
        _chat_com_rede(MSGS)


def test_falha_dupla_mostra_as_duas_causas(monkeypatch):
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    def groq_morto(*a, **k):
        raise RuntimeError("HTTP 429 rate limit")
    monkeypatch.setattr(gw, "_groq_chat", groq_morto)
    with pytest.raises(RuntimeError) as e:
        _chat_com_rede(MSGS)
    assert "expiraram" in str(e.value) and "429" in str(e.value)


def test_resposta_vazia_do_groq_nao_passa(monkeypatch):
    """Texto vazio viraria 'plano' e cairia adiante com erro pior de ler."""
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    monkeypatch.setattr(gw, "_groq_chat",
                        lambda *a, **k: {"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(RuntimeError, match="expiraram"):
        _chat_com_rede(MSGS)
