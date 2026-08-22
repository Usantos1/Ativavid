# -*- coding: utf-8 -*-
"""Karaokê e cortes, medidos com os módulos de produção.

O conferidor de karaokê usa `helpers/captions_for_remotion.py` para gerar as
cues de verdade e cobra os mesmos invariantes que `tools/conferir_legendas.py`
cobra dos projetos reais — os defeitos que aquele arquivo documenta (palavra
duplicada em 73% dos projetos, ordem da fala invertida em 746 pares) são
exatamente os que uma correção de texto mal alinhada reintroduziria.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra
from tools.bench_transcricao.impacto import (
    Cortes, conferir_karaoke, cues_de, sobreposicao_de_planos)
from tools.bench_transcricao.motores import Saida


def S(palavras, granularidade="palavra"):
    return Saida(motor="t", palavras=palavras, granularidade=granularidade,
                 texto=" ".join(p.texto for p in palavras))


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


def test_legenda_sadia_passa():
    k = conferir_karaoke(S([P("cê", 0.0, 0.2), P("tá", 0.2, 0.45),
                            P("ligado", 0.45, 0.9)]))
    assert k.aprovado and k.cues == 3
    assert not k.problemas


def test_cues_saem_do_modulo_de_producao():
    """Se `captions_for_remotion` mudar de formato, isto falha aqui."""
    cues = cues_de(S([P("oi", 0.0, 0.4)]))
    assert cues and {"text", "startMs", "endMs"} <= set(cues[0])
    assert cues[0]["startMs"] == 0 and cues[0]["endMs"] == 400


def test_duracao_zero_reprova():
    k = conferir_karaoke(S([P("x", 1.0, 1.0), P("y", 1.0, 1.4)]))
    assert not k.aprovado and k.duracao_invalida == 1


def test_palavra_repetida_reprova():
    """O defeito que estava em 73% dos projetos reais."""
    k = conferir_karaoke(S([P("mesmo", 0.5, 0.9), P("mesmo", 0.5, 0.9)]))
    assert not k.aprovado and k.duplicadas == 1


def test_volta_no_tempo_reprova():
    k = conferir_karaoke(S([P("a", 1.0, 1.2), P("b", 0.3, 0.5)]))
    assert not k.aprovado and k.fora_de_ordem == 1


def test_palavra_curta_avisa_mas_nao_reprova():
    """Pisca na tela, mas é fala real: avisar sim, reprovar não."""
    k = conferir_karaoke(S([P("e", 0.0, 0.05), P("aí", 0.05, 0.4)]))
    assert k.aprovado and k.palavra_curta == 1


def test_motor_sem_timestamp_por_palavra_nao_finge_karaoke():
    k = conferir_karaoke(S([], granularidade="frase"))
    assert k.cues == 0 and "frase" in k.problemas[0]


def test_divisao_do_cenario_D_nao_quebra_o_karaoke():
    """PrimeCamp -> Prime Camp, o caminho inteiro até as cues."""
    from tools.bench_transcricao.alinhar import aplicar

    base = [P("praimcamp", 1.0, 2.0), P("beleza", 2.0, 2.5)]
    r = aplicar(base, ["Prime", "Camp", "beleza"])
    k = conferir_karaoke(S(r.palavras))
    assert k.aprovado and k.cues == 3 and k.sobreposicoes == 0


def test_sobreposicao_de_planos_mede_influencia_do_transcript():
    a = Cortes(n=2, trechos=[(0.0, 10.0), (20.0, 30.0)])
    assert sobreposicao_de_planos(a, a) == 1.0
    b = Cortes(n=1, trechos=[(0.0, 10.0)])
    assert abs(sobreposicao_de_planos(a, b) - 0.5) < 1e-9
    c = Cortes(n=1, trechos=[(50.0, 60.0)])
    assert sobreposicao_de_planos(a, c) == 0.0


def test_o_reparo_da_producao_e_medido_nao_escondido():
    """Transcript ruim não quebra a tela: a produção empurra a palavra.

    Cada milissegundo empurrado é a palavra acendendo fora do áudio. É esse
    número que distingue um transcript bom de um que só *parece* bom.
    """
    ruim = S([P("a", 1.0, 1.2), P("b", 0.3, 0.5), P("c", 0.31, 0.32)])
    k = conferir_karaoke(ruim)
    assert not k.intacto
    assert k.palavras_reparadas >= 1
    assert k.deslocamento_maximo_ms > 100      # "b" foi empurrado ~700 ms


def test_transcript_sadio_nao_precisa_de_reparo():
    k = conferir_karaoke(S([P("cê", 0.0, 0.2), P("tá", 0.2, 0.45),
                            P("ligado", 0.45, 0.9)]))
    assert k.intacto and k.deslocamento_total_ms == 0.0


def test_o_cenario_D_nao_pode_criar_reparo():
    """A prova de que revisar texto não tira a legenda de cima do áudio."""
    from tools.bench_transcricao.alinhar import aplicar

    base = [P("eu", 0.0, 0.3), P("praimcamp", 0.3, 1.1), P("beleza", 1.1, 1.6)]
    antes = conferir_karaoke(S(base))
    depois = conferir_karaoke(S(aplicar(base, ["eu", "Prime", "Camp",
                                              "beleza"]).palavras))
    assert antes.intacto and depois.intacto
    assert depois.deslocamento_total_ms == antes.deslocamento_total_ms == 0.0


# --------------------------------------------------------------- retomada

def test_retomada_reaproveita_rodada_anterior(tmp_path):
    """Uma rodada leva horas de GPU e queima cota paga. Morrer no vídeo 6 não
    pode obrigar a refazer os cinco primeiros — ainda mais com o cache de
    transcrição desligado de propósito, para medir a frio."""
    from tools.bench_transcricao.rodar import _ja_feito

    p = tmp_path / "scribe.json"
    assert _ja_feito(p) is None                      # não existe
    S([P("oi", 0.0, 0.3)]).salvar(p)
    r = _ja_feito(p)
    assert r is not None and [x.texto for x in r.palavras] == ["oi"]


def test_retomada_ignora_resultado_abortado(tmp_path):
    """Arquivo escrito por uma rodada que morreu no meio não é resultado."""
    import json

    from tools.bench_transcricao.rodar import _ja_feito

    p = tmp_path / "gemini_audio.json"
    S([]).salvar(p)
    assert _ja_feito(p) is None                      # sem palavra e sem texto

    p.write_text("{ isto não é json", encoding="utf-8")
    assert _ja_feito(p) is None                      # corrompido


def test_retomada_aceita_motor_sem_palavra_mas_com_texto(tmp_path):
    """O Gemini pode entregar só frase: tem texto, não tem palavra. É
    resultado legítimo e não pode ser refeito à toa."""
    from tools.bench_transcricao.rodar import _ja_feito

    p = tmp_path / "gemini_audio.json"
    Saida(motor="gemini_audio", palavras=[], granularidade="frase",
          texto="eu vendi quinze mil").salvar(p)
    assert _ja_feito(p) is not None
