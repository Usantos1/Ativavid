# -*- coding: utf-8 -*-
"""O Gemini corrige o texto. Os tempos continuam sendo do Whisper.

É o teste que justifica o cenário E existir em produção. A legenda karaokê lê
`start`/`end` palavra por palavra: um milissegundo inventado aqui aparece na
tela do cliente, e nenhum ganho de WER paga isso.

Cobre as sete políticas de bloco do alinhador com correções sintéticas —
incluindo `PrimeCamp` → `Prime Camp`, o caso de marca que originou o
benchmark inteiro.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transcricao import Palavra, alinhar, revisao


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


BASE = [P("eu", 0.0, 0.2), P("vendi", 0.2, 0.7), P("na", 0.7, 0.85),
        P("praimcamp", 0.85, 1.6), P("ontem", 1.6, 2.0)]

VAO = (BASE[0].inicio, BASE[-1].fim)


def _revisar(correcoes, palavras=None, monkeypatch=None):
    """Roda `revisar()` com o Gemini trocado por uma lista fixa."""
    palavras = palavras or BASE
    monkeypatch.setattr(revisao, "pedir_correcoes",
                        lambda p, t: list(correcoes))
    return revisao.revisar(palavras, " ".join(p.texto for p in palavras))


def _dentro_do_vao(palavras):
    return (palavras[0].inicio == VAO[0] and palavras[-1].fim == VAO[1]
            and all(p.inicio <= p.fim for p in palavras)
            and all(a.fim <= b.inicio + alinhar.EPS
                    for a, b in zip(palavras, palavras[1:])))


# --------------------------------------------------- as sete políticas

def test_divisao_a_marca_que_originou_o_benchmark(monkeypatch):
    """`praimcamp` → `Prime Camp`. Duas palavras dentro do tempo de uma.

    Nunca distribuir tempo por chute: a borda de entrada e a de saída do
    trecho original ficam EXATAS, e o corte no meio é proporcional ao
    tamanho de cada pedaço.
    """
    novas, meta = _revisar([{"indice": 3, "de": "praimcamp",
                             "para": "Prime Camp"}], monkeypatch=monkeypatch)
    assert meta["revisado"]
    assert [p.texto for p in novas] == ["eu", "vendi", "na", "Prime", "Camp",
                                        "ontem"]
    assert novas[3].inicio == 0.85, "a borda de entrada do trecho mudou"
    assert novas[4].fim == 1.6, "a borda de saída do trecho mudou"
    assert novas[3].fim == novas[4].inicio, "abriu um buraco no meio"
    assert _dentro_do_vao(novas)


def test_troca_1_para_1_herda_o_tempo_exato(monkeypatch):
    novas, meta = _revisar([{"indice": 3, "de": "praimcamp",
                             "para": "PrimeCamp"}], monkeypatch=monkeypatch)
    assert meta["revisado"]
    assert novas[3].texto == "PrimeCamp"
    assert (novas[3].inicio, novas[3].fim) == (0.85, 1.6)
    assert [(p.inicio, p.fim) for p in novas] == [(p.inicio, p.fim) for p in BASE]


def test_juncao_n_para_1_pega_o_inicio_do_primeiro_e_o_fim_do_ultimo(monkeypatch):
    novas, meta = _revisar([{"indice": 2, "n": 2, "de": "na praimcamp",
                             "para": "naPrimeCamp"}], monkeypatch=monkeypatch)
    assert meta["revisado"]
    juntada = [p for p in novas if p.texto == "naPrimeCamp"][0]
    assert (juntada.inicio, juntada.fim) == (0.7, 1.6)
    assert _dentro_do_vao(novas)


def test_troca_n_para_m(monkeypatch):
    novas, meta = _revisar([{"indice": 2, "n": 2, "de": "na praimcamp",
                             "para": "numa Prime Camp"}],
                           monkeypatch=monkeypatch)
    assert meta["revisado"]
    assert _dentro_do_vao(novas)


def test_remocao_o_tempo_orfao_e_absorvido_pelo_vizinho(monkeypatch):
    """Apagar uma palavra não pode abrir um buraco na linha do tempo."""
    novas, meta = _revisar([{"indice": 3, "de": "praimcamp", "para": ""}],
                           monkeypatch=monkeypatch)
    assert meta["revisado"]
    assert "praimcamp" not in [p.texto for p in novas]
    assert _dentro_do_vao(novas)
    assert alinhar.linha_do_tempo_preservada(BASE, novas)


def test_grafia_em_bloco_igual_nao_move_nada(monkeypatch):
    """Consertar a caixa de um nome próprio custa zero em tempo."""
    novas, meta = _revisar([{"indice": 0, "de": "eu", "para": "Eu"}],
                           monkeypatch=monkeypatch)
    assert meta["revisado"] and novas[0].texto == "Eu"
    assert [(p.inicio, p.fim) for p in novas] == [(p.inicio, p.fim) for p in BASE]


def test_insercao_e_recusada_por_padrao(monkeypatch):
    """Palavra que ninguém falou não tem tempo de onde sair.

    Sem áudio o Gemini não pode saber que ela existe, e inventar um intervalo
    para ela é exatamente o que este módulo existe para impedir.
    """
    novas, meta = _revisar([{"indice": 4, "de": "ontem",
                             "para": "ontem de manhã"}],
                           monkeypatch=monkeypatch)
    assert meta["revisado"]
    assert _dentro_do_vao(novas)
    assert meta["insercoes_recusadas"] >= 1


# ------------------------------------------------------------ os freios

def test_retranscricao_derruba_a_revisao_inteira(monkeypatch):
    """Trocar quase tudo não é revisão. Não pode virar `+rev1`."""
    muitas = [P(f"p{i}", i * 0.1, i * 0.1 + 0.09) for i in range(40)]
    correcoes = [{"indice": i, "para": f"x{i}"} for i in range(30)]
    novas, meta = _revisar(correcoes, palavras=muitas, monkeypatch=monkeypatch)
    assert not meta["revisado"], "revisão descartada não pode se dizer revisada"
    assert [p.texto for p in novas] == [p.texto for p in muitas]


def test_ancora_errada_nao_corrompe_outra_palavra(monkeypatch):
    """O erro mais perigoso: acertar a palavra e errar o índice."""
    novas, meta = _revisar([{"indice": 0, "de": "praimcamp",
                             "para": "PrimeCamp"}], monkeypatch=monkeypatch)
    assert novas[0].texto == "eu", "sobrescreveu a palavra errada"
    assert meta["ignoradas"] == 1


# ------------------------------------------- o gate, com o alinhador quebrado

def test_conferir_reprovando_derruba_a_revisao(monkeypatch):
    """Se o alinhador um dia deixar um tempo escapar, o gate segura.

    Simula a falha trocando `aplicar` por um que devolve tempo fora do vão.
    O resultado tem de ser Whisper puro, não legenda dessincronizada.
    """
    def aplicar_defeituoso(whisper, corrigido, **kw):
        return alinhar.Resultado(palavras=[P("x", 0.0, 99.0)])

    monkeypatch.setattr(alinhar, "aplicar", aplicar_defeituoso)
    novas, meta = _revisar([{"indice": 3, "para": "PrimeCamp"}],
                           monkeypatch=monkeypatch)
    assert not meta["revisado"]
    assert "AssertionError" in meta["motivo"], meta["motivo"]
    assert [(p.texto, p.inicio, p.fim) for p in novas] == \
           [(p.texto, p.inicio, p.fim) for p in BASE]


@pytest.mark.parametrize("correcoes", [
    [],
    [{"indice": 3, "de": "praimcamp", "para": "Prime Camp"}],
    [{"indice": 3, "de": "praimcamp", "para": ""}],
    [{"indice": 2, "n": 2, "de": "na praimcamp", "para": "naPrimeCamp"}],
    [{"indice": 0, "de": "eu", "para": "Eu"},
     {"indice": 3, "de": "praimcamp", "para": "Prime Camp"}],
])
def test_o_vao_externo_nunca_muda(correcoes, monkeypatch):
    """O invariante que vale para toda correção possível: o primeiro início e
    o último fim são os do Whisper, sempre."""
    novas, _ = _revisar(correcoes, monkeypatch=monkeypatch)
    assert (novas[0].inicio, novas[-1].fim) == VAO
