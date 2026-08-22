# -*- coding: utf-8 -*-
"""Resposta do Gemini fora do esperado não pode derrubar a rodada.

Uma rodada leva horas e queima cota paga. Modelo devolve JSON em cerca de
código, com prosa antes, com índice errado, com correções que se sobrepõem —
e nada disso pode virar exceção no vídeo 7 nem, pior, corromper a palavra
errada em silêncio.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra
from tools.bench_transcricao.gemini_api import _json_da_resposta


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


BASE = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
        P("praimcamp", 0.85, 1.6), P("ontem", 1.6, 2.0)]


# ------------------------------------------------------- leitura da resposta

def test_json_em_cerca_de_codigo():
    txt = '```json\n{"correcoes": [{"indice": 3, "para": "PrimeCamp"}]}\n```'
    assert _json_da_resposta(txt)["correcoes"][0]["indice"] == 3


def test_json_com_prosa_antes_e_depois():
    txt = ('Claro! Analisei o áudio. Segue o resultado:\n'
           '{"correcoes": []}\n'
           'Espero ter ajudado.')
    assert _json_da_resposta(txt)["correcoes"] == []


def test_resposta_sem_json_levanta_com_a_resposta_no_erro():
    """A mensagem tem de mostrar o que veio, senão não dá para diagnosticar."""
    with pytest.raises(ValueError, match="sem JSON"):
        _json_da_resposta("Desculpe, não consigo ajudar com isso.")


def test_resposta_vazia_levanta():
    with pytest.raises(ValueError):
        _json_da_resposta("")


# ----------------------------------------------- aplicação das correções

def _aplicar(correcoes, palavras=None):
    """Usa a função REAL de motores.py — não uma cópia que pode divergir."""
    from tools.bench_transcricao.motores import aplicar_correcoes

    return aplicar_correcoes(palavras or BASE, correcoes)


def test_indice_negativo_e_ignorado():
    _, ap, ig = _aplicar([{"indice": -1, "para": "x"}])
    assert not ap and ig[0]["motivo"] == "índice fora do intervalo"


def test_n_que_estoura_o_fim_e_ignorado():
    _, ap, ig = _aplicar([{"indice": 4, "n": 5, "para": "x"}])
    assert not ap and ig[0]["motivo"] == "índice fora do intervalo"


def test_ancora_errada_nao_corrompe_outra_palavra():
    """O erro mais perigoso: o modelo acerta a palavra e erra o índice."""
    toks, ap, ig = _aplicar([{"indice": 0, "de": "praimcamp",
                              "para": "PrimeCamp"}])
    assert not ap and ig[0]["motivo"].startswith("âncora não bate")
    assert toks[0] == "eu"          # "eu" continua "eu"


def test_correcao_sem_ancora_e_aplicada_no_indice():
    """`de` é opcional: sem ele, confia-se no índice — e o alinhador ainda
    protege o tempo depois."""
    toks, ap, _ = _aplicar([{"indice": 3, "para": "PrimeCamp"}])
    assert toks[3] == "PrimeCamp" and len(ap) == 1


def test_varias_correcoes_nao_escorregam_de_indice():
    """Aplicar de trás para frente é o que impede a segunda de errar o alvo."""
    toks, ap, _ = _aplicar([
        {"indice": 1, "de": "vendi", "para": "vendi"},
        {"indice": 3, "de": "praimcamp", "para": "Prime Camp"},
    ])
    assert len(ap) == 2
    assert toks == ["eu", "vendi", "na", "Prime", "Camp", "ontem"]


def test_correcoes_sobrepostas_a_segunda_cai_pela_ancora():
    """Duas correções cobrindo a mesma palavra: a primeira aplicada muda o
    texto, então a âncora da outra deixa de bater e ela é descartada em vez
    de sobrescrever o que já foi corrigido."""
    toks, ap, ig = _aplicar([
        {"indice": 3, "n": 1, "de": "praimcamp", "para": "PrimeCamp"},
        {"indice": 2, "n": 2, "de": "na praimcamp", "para": "na Prime Camp"},
    ])
    assert len(ap) == 1 and len(ig) == 1
    assert ig[0]["motivo"].startswith("âncora não bate")
    assert "PrimeCamp" in toks and "Prime Camp" not in " ".join(toks)


def test_para_vazio_apaga_a_palavra_e_o_tempo_e_absorvido():
    from tools.bench_transcricao.alinhar import aplicar, linha_do_tempo_preservada

    toks, ap, _ = _aplicar([{"indice": 3, "de": "praimcamp", "para": ""}])
    assert len(ap) == 1
    r = aplicar(BASE, toks)
    assert linha_do_tempo_preservada(BASE, r.palavras)


def test_lista_de_correcoes_vazia_nao_muda_nada():
    from tools.bench_transcricao.alinhar import aplicar

    toks, ap, ig = _aplicar([])
    assert not ap and not ig
    r = aplicar(BASE, toks)
    assert [p.texto for p in r.palavras] == [p.texto for p in BASE]
    assert not r.alteracoes
