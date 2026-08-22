# -*- coding: utf-8 -*-
"""O Gemini corrige o texto; o Whisper continua mandando no tempo.

O invariante que estes testes protegem é o mesmo que a legenda karaokê
depende: `Palavra.inicio`/`fim` não se movem por causa de uma correção de
texto. Cada caso abaixo é uma forma diferente de o alinhamento poder escorregar.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra
from tools.bench_transcricao.alinhar import (
    aplicar, linha_do_tempo_preservada, repartir, retencao_de_fronteiras)


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


def test_texto_igual_nao_mexe_em_nada():
    src = [P("oi", 0.0, 0.4), P("mundo", 0.4, 1.0)]
    r = aplicar(src, ["oi", "mundo"])
    assert [p.texto for p in r.palavras] == ["oi", "mundo"]
    assert linha_do_tempo_preservada(src, r.palavras)


def test_troca_um_para_um_herda_tempo_exato():
    src = [P("praimcamp", 1.0, 1.8), P("agora", 1.8, 2.3)]
    r = aplicar(src, ["PrimeCamp", "agora"])
    assert (r.palavras[0].inicio, r.palavras[0].fim) == (1.0, 1.8)
    assert linha_do_tempo_preservada(src, r.palavras)


def test_divisao_de_uma_palavra_em_duas_crava_as_bordas():
    """PrimeCamp -> Prime Camp: o caso que quebraria o karaokê."""
    src = [P("PrimeCamp", 2.0, 3.0), P("beleza", 3.0, 3.5)]
    r = aplicar(src, ["Prime", "Camp", "beleza"])
    assert [p.texto for p in r.palavras] == ["Prime", "Camp", "beleza"]
    assert r.palavras[0].inicio == 2.0          # borda esquerda cravada
    assert r.palavras[1].fim == 3.0             # borda direita cravada
    assert r.palavras[0].fim == r.palavras[1].inicio   # sem buraco
    assert 2.0 < r.palavras[0].fim < 3.0        # divisão real
    assert linha_do_tempo_preservada(src, r.palavras)


def test_fusao_de_duas_palavras_em_uma():
    src = [P("Prime", 2.0, 2.5), P("Camp", 2.5, 3.0), P("tá", 3.0, 3.2)]
    r = aplicar(src, ["PrimeCamp", "tá"])
    assert (r.palavras[0].inicio, r.palavras[0].fim) == (2.0, 3.0)
    assert linha_do_tempo_preservada(src, r.palavras)


def test_troca_n_para_m_nao_escapa_do_bloco():
    src = [P("vinte", 0.0, 0.5), P("e", 0.5, 0.6), P("cinco", 0.6, 1.2),
           P("reais", 1.2, 1.8)]
    r = aplicar(src, ["R$", "25", "reais"])
    assert r.palavras[0].inicio == 0.0 and r.palavras[-1].fim == 1.8
    assert linha_do_tempo_preservada(src, r.palavras)


def test_remocao_absorve_o_tempo_sem_deixar_buraco():
    src = [P("eu", 0.0, 0.3), P("eu", 0.3, 0.6), P("vou", 0.6, 1.0)]
    r = aplicar(src, ["eu", "vou"])
    assert [p.texto for p in r.palavras] == ["eu", "vou"]
    assert r.palavras[0].fim == 0.6
    assert r.palavras[1].inicio == 0.6
    assert linha_do_tempo_preservada(src, r.palavras)


def test_insercao_e_recusada_por_padrao():
    src = [P("bom", 0.0, 0.4), P("dia", 0.4, 0.9)]
    r = aplicar(src, ["muito", "bom", "dia"])
    assert [p.texto for p in r.palavras] == ["bom", "dia"]
    assert len(r.recusadas) == 1
    assert linha_do_tempo_preservada(src, r.palavras)


def test_retranscricao_disfarcada_e_descartada():
    orig = ("alfa bravo charlie delta echo foxtrot golf hotel india julieta "
            "kilo lima mike november oscar papa quebec romeu sierra tango "
            "uniform victor whisky xis").split()
    src = [P(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(orig)]
    r = aplicar(src, [f"zulu{i}" for i in range(len(orig))])
    assert r.revisao_descartada
    assert "retranscrição" in r.motivo
    assert [p.texto for p in r.palavras] == orig


def test_divisao_em_intervalo_apertado_nao_gera_duracao_negativa():
    src = [P("x", 5.0, 5.03)]      # 30 ms para 4 tokens
    r = aplicar(src, ["a", "b", "c", "d"])
    assert r.palavras[0].inicio == 5.0 and r.palavras[-1].fim == 5.03
    assert all(p.fim >= p.inicio for p in r.palavras)
    for a, b in zip(r.palavras[:-1], r.palavras[1:]):
        assert b.inicio >= a.inicio


def test_repartir_pesa_pelo_tamanho_do_token():
    spans = repartir(0.0, 10.0, ["a", "bbbbbbbbb"])
    assert spans[0][0] == 0.0 and spans[-1][1] == 10.0
    assert spans[0][1] < 5.0


def test_acento_e_correcao_de_texto_sem_custo_temporal():
    src = [P("voce", 0.0, 0.5), P("ta", 0.5, 0.8)]
    r = aplicar(src, ["você", "tá"])
    assert [p.texto for p in r.palavras] == ["você", "tá"]
    assert linha_do_tempo_preservada(src, r.palavras)
    assert retencao_de_fronteiras(src, r.palavras) == 1.0


def test_conferir_derruba_se_o_tempo_escapar():
    """A rede de segurança: erro de alinhamento vira exceção, não legenda torta."""
    from tools.bench_transcricao.alinhar import conferir
    src = [P("a", 0.0, 1.0)]
    try:
        conferir(src, [P("a", 0.0, 2.0)])
    except AssertionError as e:
        assert "fim do bloco" in str(e)
    else:
        raise AssertionError("conferir deixou passar um fim deslocado")
