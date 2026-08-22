# -*- coding: utf-8 -*-
"""Revisão que falha entrega Whisper puro. Nunca Scribe, nunca meio resultado.

A revisão é melhoria opcional sobre uma transcrição que já está pronta e
correta. Sessão web não capturada, Gemini fora do ar, JSON quebrado: em todos
o job segue, com o resultado do motor local intacto.

**Nunca cai para o Scribe.** É serviço pago, e cair nele sozinho gastaria a
cota do usuário sem ele pedir — a mesma decisão que `app/transcricao/modo.py`
já tinha tomado quando tirou a queda automática para o Scribe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transcricao import Palavra, revisao


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


BASE = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
        P("praimcamp", 0.85, 1.6), P("ontem", 1.6, 2.0)]
TEXTO = "eu vendi na praimcamp ontem"


def _com_gemini(monkeypatch, fn):
    monkeypatch.setattr(revisao, "pedir_correcoes", fn)
    return revisao.revisar(BASE, TEXTO)


def _intacto(novas):
    return [(p.texto, p.inicio, p.fim) for p in novas] == \
           [(p.texto, p.inicio, p.fim) for p in BASE]


# ------------------------------------------------- as falhas, uma por uma

def test_sessao_nao_capturada(monkeypatch):
    """Quem nunca instalou a extensão nunca revisa — e não vê erro nenhum."""
    def morto(p, t):
        raise revisao.RevisaoIndisponivel("gateway: capture a sessão")

    novas, meta = _com_gemini(monkeypatch, morto)
    assert not meta["revisado"] and _intacto(novas)
    assert "capture a sessão" in meta["motivo"]


def test_json_quebrado(monkeypatch):
    def lixo(p, t):
        raise revisao.RevisaoIndisponivel("resposta do Gemini sem JSON: oi")

    novas, meta = _com_gemini(monkeypatch, lixo)
    assert not meta["revisado"] and _intacto(novas)


def test_excecao_inesperada_tambem_e_absorvida(monkeypatch):
    """O `except` é largo de propósito: qualquer coisa que aconteça aqui tem
    a mesma resposta certa, que é entregar a transcrição e seguir o job."""
    def explode(p, t):
        raise KeyError("choices")

    novas, meta = _com_gemini(monkeypatch, explode)
    assert not meta["revisado"] and _intacto(novas)
    assert "KeyError" in meta["motivo"]


def test_transcricao_vazia_nao_chama_o_gemini(monkeypatch):
    chamou = []
    monkeypatch.setattr(revisao, "pedir_correcoes",
                        lambda p, t: chamou.append(1) or [])
    novas, meta = revisao.revisar([], "")
    assert not meta["revisado"] and novas == [] and not chamou


def test_fonte_longa_e_pulada_e_diz_que_foi(monkeypatch):
    """Guarda conservadora: o prompt manda todas as palavras indexadas, e o
    benchmark rodou em vídeo curto. Fonte longa sai com Whisper puro em vez
    de sair com um resultado que ninguém mediu."""
    chamou = []
    monkeypatch.setattr(revisao, "pedir_correcoes",
                        lambda p, t: chamou.append(1) or [])
    monkeypatch.setattr(revisao, "MAXIMO_DE_PALAVRAS", 3)
    novas, meta = revisao.revisar(BASE, TEXTO)
    assert not meta["revisado"] and _intacto(novas)
    assert meta["pulada"] is True and not chamou, "chamou o Gemini mesmo assim"
    assert "fonte longa" in meta["motivo"]


# ------------------------------------ nada disso pode virar chamada paga

def test_nenhuma_falha_menciona_scribe_ou_elevenlabs():
    """Guarda de código, não de comportamento.

    O módulo inteiro não pode ter caminho para o motor pago. É barato de
    verificar e caro de descobrir depois, na fatura de outra pessoa.
    """
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "app" / "transcricao" / "revisao.py").lower()
    for proibido in ("elevenlabs", "scribe", "groq", "api_key", "apikey"):
        assert proibido not in codigo, (
            f"`{proibido}` aparece no código da revisão — o caminho de falha "
            f"tem de terminar em Whisper puro, nunca em serviço pago")


def test_o_prompt_proibe_formalizar_a_fala():
    """`cê` continua `cê`. Está no prompt e tem de continuar estando: foi a
    regra que o benchmark cobrou do ground truth do começo ao fim."""
    assert '"cê" por "você" é ERRO' in revisao.PROMPT
    assert "NÃO retranscreva do zero" in revisao.PROMPT
