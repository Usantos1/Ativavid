# -*- coding: utf-8 -*-
"""Achar onde os motores discordam — e só isso vai para ouvido humano.

O que estes testes protegem: um ponto de divergência não pode passar
despercebido (viraria referência errada por consenso), e um trecho onde todos
concordam não pode virar trabalho manual à toa.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra
from tools.bench_transcricao.discordancia import (
    OMITIDO, encontrar, referencia_por_consenso)
from tools.bench_transcricao.validar import _embaralhar


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


def motores():
    base = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
            P("praimcamp", 0.85, 1.6), P("ontem", 1.6, 2.0)]
    scribe = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
              P("Prime", 0.85, 1.2), P("Camp", 1.2, 1.6), P("ontem", 1.6, 2.0)]
    gem = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
           P("PrimeCamp", 0.85, 1.6), P("ontem", 1.6, 2.0)]
    return {"whisper_local": base, "scribe": scribe, "gemini_audio": gem}


def test_acha_a_divergencia_e_ignora_o_consenso():
    pontos = encontrar(motores())
    assert len(pontos) == 1                 # só a marca diverge
    p = pontos[0]
    assert p.propostas["whisper_local"] == "praimcamp"
    assert p.propostas["scribe"] == "Prime Camp"     # inserção grudada
    assert p.propostas["gemini_audio"] == "PrimeCamp"


def test_carimbo_serve_para_a_pessoa_achar_no_audio():
    assert encontrar(motores())[0].carimbo() == "00:00.850"


def test_contexto_ajuda_a_ouvir_sem_abrir_o_video():
    p = encontrar(motores())[0]
    assert "vendi" in p.contexto_antes and "ontem" in p.contexto_depois


def test_omissao_aparece_como_candidato():
    m = motores()
    m["scribe"] = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
                   P("ontem", 1.6, 2.0)]        # engoliu a marca
    p = encontrar(m)[0]
    assert p.propostas["scribe"] == OMITIDO


def test_sem_divergencia_nao_gera_trabalho():
    base = [P("tudo", 0.0, 0.4), P("igual", 0.4, 0.9)]
    assert encontrar({"whisper_local": base, "scribe": list(base)}) == []


def test_referencia_marca_o_que_ninguem_verificou():
    m = motores()
    _, contagem = referencia_por_consenso(m, decisoes={})
    assert contagem["pendentes"] == 1        # a marca segue sem ouvido humano
    assert contagem["humano"] == 0
    assert contagem["consenso"] == 4

    texto, contagem = referencia_por_consenso(
        m, decisoes={"00:00.850": "PrimeCamp"})
    assert contagem["humano"] == 1 and contagem["pendentes"] == 0
    assert " ".join(texto) == "eu vendi na PrimeCamp ontem"


def test_ordem_das_opcoes_nao_entrega_de_qual_motor_veio():
    """A pessoa tem de ouvir, não votar em motor. Ordem estável entre aberturas."""
    cands = ["praimcamp", "Prime Camp", "PrimeCamp"]
    a = _embaralhar(cands, "00:00.850")
    b = _embaralhar(list(reversed(cands)), "00:00.850")
    assert a == b                       # não depende da ordem de entrada
    assert sorted(a) == sorted(cands)   # não perde nem inventa candidato


def test_teto_de_palavras_por_ponto():
    """Fala rápida com muitas divergências não vira uma pergunta gigante.

    Sem teto, a pessoa acabaria transcrevendo a frase inteira — o trabalho
    manual que este módulo existe para evitar.
    """
    a = [P(f"a{i}", i * 0.2, i * 0.2 + 0.18) for i in range(6)]
    b = [P(f"b{i}", i * 0.2, i * 0.2 + 0.18) for i in range(6)]
    pontos = encontrar({"whisper_local": a, "scribe": b})
    assert [len(p.indices) for p in pontos] == [4, 2]


def test_pausa_real_separa_os_pontos():
    a = [P("casa", 0.0, 0.2), P("moto", 0.9, 1.1)]
    b = [P("caza", 0.0, 0.2), P("mota", 0.9, 1.1)]
    assert len(encontrar({"whisper_local": a, "scribe": b})) == 2


def test_diferenca_so_de_caixa_nao_e_divergencia():
    """"Prime" e "prime" não são pergunta para ninguém — o WER também ignora."""
    a = [P("Prime", 0.0, 0.4)]
    b = [P("prime", 0.0, 0.4)]
    assert encontrar({"whisper_local": a, "scribe": b}) == []
