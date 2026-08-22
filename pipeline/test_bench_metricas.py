# -*- coding: utf-8 -*-
"""WER, CER e as métricas de produto — incluindo a regra que decide o benchmark.

A regra: formalizar a fala é ERRO. Um motor que transcreve "você" onde a
pessoa falou "cê" criou trabalho para o usuário desfazer, não economizou.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.bench_transcricao.metricas import (
    cer, correcoes_humanas, evaluate_text, is_colloquial_token,
    is_number_token, levenshtein_ops, operacoes_100w, tokens, wer)


def test_wer_zero_quando_igual():
    c = wer("cê vai fazer isso agora", "cê vai fazer isso agora")
    assert c.wer == 0.0 and c.accuracy == 1.0


def test_wer_conta_troca_omissao_e_invencao():
    c = wer("a b c d", "a x c d e")
    assert (c.sub, c.dele, c.ins) == (1, 0, 1)
    assert c.wer == 0.5


def test_formalizar_a_fala_e_penalizado():
    ref = "cê vai fazer isso agora"
    assert wer(ref, "você vai fazer isso agora").wer > 0.0
    assert wer(ref, "cê vai fazer isso agora").wer == 0.0


def test_pontuacao_e_caixa_nao_sao_erro():
    assert wer("bom dia mano", "Bom dia, mano!").wer == 0.0


def test_cer_e_mais_fino_que_wer():
    assert 0 < cer("primecamp", "primecmp") < wer("primecamp", "primecmp").wer


def test_operacoes_por_100_palavras_segue_o_wer():
    c = wer(" ".join(["x"] * 100), " ".join(["x"] * 97 + ["y", "y", "y"]))
    assert abs(operacoes_100w(c) - 3.0) < 1e-9


def _corr(ref, hip):
    c, ops = levenshtein_ops(tokens(ref), tokens(hip))
    return correcoes_humanas(ops, c.ref_len)


def test_erro_agrupado_custa_uma_correcao_so():
    """Quem conserta três palavras seguidas seleciona o trecho e digita UMA
    vez. O WER conta três; quem edita, não."""
    ref = "eu vendi quinze mil na PrimeCamp ontem à noite pra dois clientes"
    grudados = "eu vendi quinze mil no prime camp ontem à noite pra dois clientes"
    espalhados = "eu vendo quinze mil na PrimeCamp ontem à noites pra dois cliente"

    assert wer(ref, grudados).wer == wer(ref, espalhados).wer   # WER não separa
    assert _corr(ref, grudados)[0] == 1
    assert _corr(ref, espalhados)[0] == 3


def test_transcricao_perfeita_nao_pede_correcao():
    assert _corr("cê tá ligado", "cê tá ligado") == (0, 0.0)


def test_formalizar_a_fala_espalha_correcoes():
    """O padrão que separa os motores: quem normaliza erra em cada gíria, e
    cada uma obriga a parar num ponto diferente do vídeo."""
    ref = "cê vai lá e tá tudo certo pra gente né mano"
    formal = "você vai lá e está tudo certo para gente não é mano"
    n, _ = _corr(ref, formal)
    assert n >= 3


def test_deteccao_de_coloquial_e_numero():
    assert is_colloquial_token("tá") and is_colloquial_token("pra")
    assert is_number_token("quinze") and is_number_token("R$3.500")
    assert not is_number_token("casa")


def test_categorias_de_produto():
    ref = "eu vendi quinze mil na PrimeCamp tá ligado mano"
    hip = "eu vendi cinquenta mil na Prime Camp está ligado mano"
    r = evaluate_text(ref, hip, entities=["PrimeCamp"])
    assert r.counts.sub >= 1
    assert r.numbers.total >= 2 and r.numbers.rate < 1.0      # errou "quinze"
    assert r.colloquial.total >= 1 and r.colloquial.rate < 1.0  # formalizou "tá"
    assert r.entities.total == 1 and r.entities.correct == 0    # quebrou a marca
    assert r.edits_100w > 0
