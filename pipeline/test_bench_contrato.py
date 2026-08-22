# -*- coding: utf-8 -*-
"""O contrato entre a saída do motor de produção e o adaptador do benchmark.

É aqui que uma mudança no schema quebraria o benchmark em silêncio: ele
continuaria rodando e mediria zero palavra. Estes testes usam os tipos e a
conversão REAIS do projeto (`ResultadoDeTranscricao.para_schema_scribe`), não
uma cópia — se aquele formato mudar, isto falha antes de alguém gastar uma
noite de GPU.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra, ResultadoDeTranscricao, Segmento
from tools.bench_transcricao.motores import _palavras_do_schema


def _resultado() -> ResultadoDeTranscricao:
    p1 = (Palavra("Cê", 0.00, 0.18, 0.91), Palavra("tá", 0.18, 0.36, 0.88),
          Palavra("ligado", 0.36, 0.80, 0.95))
    # Pausa de 0,4s: `para_schema_scribe` emite um `spacing` aqui.
    p2 = (Palavra("né", 1.20, 1.40, 0.77),)
    return ResultadoDeTranscricao(
        texto="Cê tá ligado né", idioma="pt", duracao=1.4,
        motor="whisper-local", modelo="medium", backend="cuda",
        segmentos=[Segmento("Cê tá ligado", 0.0, 0.8, -0.3, p1),
                   Segmento("né", 1.2, 1.4, -0.4, p2)])


def test_adaptador_le_o_schema_que_o_projeto_produz():
    palavras = _palavras_do_schema(_resultado().para_schema_scribe())
    assert [p.texto for p in palavras] == ["Cê", "tá", "ligado", "né"]
    assert palavras[0].inicio == 0.0 and palavras[-1].fim == 1.4


def test_spacing_nao_vira_palavra():
    """`spacing` existe para pack_transcripts detectar silêncio. Se o
    adaptador o tratasse como palavra, o WER contaria espaços como texto."""
    bruto = _resultado().para_schema_scribe()
    assert any(w["type"] == "spacing" for w in bruto["words"]), \
        "o projeto parou de emitir spacing — rever este teste"
    assert all(p.texto.strip() for p in _palavras_do_schema(bruto))


def test_o_adaptador_nao_perde_a_fronteira_da_pausa():
    palavras = _palavras_do_schema(_resultado().para_schema_scribe())
    assert palavras[2].fim == 0.80 and palavras[3].inicio == 1.20


def test_transcricao_vazia_nao_derruba_o_adaptador():
    vazio = ResultadoDeTranscricao(texto="", segmentos=[]).para_schema_scribe()
    assert _palavras_do_schema(vazio) == []


def test_o_cenario_D_preserva_os_tempos_do_schema_real():
    """Ponta a ponta sobre o schema de verdade: revisar não move tempo."""
    from tools.bench_transcricao.alinhar import (
        aplicar, linha_do_tempo_preservada)

    palavras = _palavras_do_schema(_resultado().para_schema_scribe())
    # O revisor separa "ligado" e conserta a grafia — o pior caso do karaokê.
    r = aplicar(palavras, ["Cê", "tá", "li", "gado", "né"])
    assert linha_do_tempo_preservada(palavras, r.palavras)
    assert r.palavras[0].inicio == 0.0 and r.palavras[-1].fim == 1.4
