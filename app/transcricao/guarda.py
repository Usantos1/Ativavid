# -*- coding: utf-8 -*-
"""Impede que o Whisper entregue texto que ninguém falou.

O caso concreto: num vídeo só com música, o motor devolveu
`"Legendas pela comunidade Amara.org"` — alucinação conhecida do Whisper em
áudio sem fala. Isso não pode chegar na legenda.

COMO **NÃO** DÁ PARA RESOLVER, tudo medido antes de escolher:

**Só a região acústica não basta.** O `speech_regions.py` usa `silencedetect`,
que mede NÍVEL e não fala: a música de teste (máx −17,6 dB) virou uma "região
de fala" de 12s inteiros, e o texto inventado caiu dentro dela.

**Nenhum sinal do Whisper funciona sozinho.** Medidos 177 segmentos de fala
real do usuário contra o material inventado:

| | fala real (pior) | inventado |
|---|---|---|
| `no_speech_prob` | 0,939 | 0,857 |
| `avg_logprob` | −0,691 | −0,613 |
| `compression_ratio` | 0,79 | 0,81 |

A fala real é PIOR que a alucinação nos três. Qualquer limiar por segmento que
pegue o inventado derruba pelo menos um segmento legítimo — testadas 8
combinações, todas derrubam o mesmo `"Eu vou rapidinho, se eu conser…"`.

**Filtrar palavra por região é pior ainda.** Medido: 3,4% das palavras REAIS
já caem fora das regiões acústicas (a pior desvia 1,63s). Um filtro por
palavra cortaria fala legítima — que é justamente o que não pode acontecer.

COMO RESOLVE: a diferença entre os dois casos não está em nenhum segmento
isolado, está no CONJUNTO. Na música, o único segmento é ruim. No vídeo real,
41 dos 42 são bons. Então a decisão é global:

  1. Se NENHUM segmento parece fala → o áudio não tem fala → nada é entregue.
  2. Um segmento ruim que ainda por cima cai fora de toda região acústica é
     descartado sozinho — é o caso da alucinação grudada no fim de uma
     gravação de verdade, que acontece no silêncio final.
  3. Palavra nenhuma é descartada por conta própria.

Com isso, os 177 segmentos reais passam inteiros e o inventado não passa.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.transcricao import ResultadoDeTranscricao, Segmento

# Limiares por segmento. Não são de referência do Whisper (`no_speech > 0.6 E
# logprob < -1.0`): aquele NÃO pega este caso, porque o inventado deu −0,613.
# Estes saem dos 177 segmentos reais medidos.
NAO_PARECE_FALA_NS = 0.70
NAO_PARECE_FALA_LP = -0.45

# Quanto da duração do segmento precisa cair em região acústica para ele
# contar como "tem som de verdade ali". Folga generosa de propósito: a regra 2
# só existe para o caso claro, e errar para o lado de MANTER é o lado certo.
FRACAO_ACUSTICA_MINIMA = 0.20

# Folga nas bordas da região, para não recusar palavra que atravessa a borda.
FOLGA_BORDA = 0.25


@dataclass
class Veredito:
    """O que a guarda fez, para o log técnico e para os testes."""

    entrou: int
    saiu: int
    motivo: str
    segmentos_descartados: int = 0

    @property
    def descartou_tudo(self) -> bool:
        return self.entrou > 0 and self.saiu == 0


def _parece_fala(s: Segmento, ns: float | None) -> bool:
    """Um segmento só é suspeito quando os DOIS sinais acusam.

    Cada um sozinho reprova fala real — medido.
    """
    if ns is None or s.confianca is None:
        return True          # sem sinal, não se acusa
    return not (ns > NAO_PARECE_FALA_NS and s.confianca < NAO_PARECE_FALA_LP)


def _fracao_acustica(s: Segmento, regioes: list[tuple[float, float]]) -> float:
    if not regioes or s.fim <= s.inicio:
        return 0.0
    dentro = 0.0
    for a, b in regioes:
        ini = max(s.inicio, a - FOLGA_BORDA)
        fim = min(s.fim, b + FOLGA_BORDA)
        if fim > ini:
            dentro += fim - ini
    return min(1.0, dentro / (s.fim - s.inicio))


def aplicar(
    resultado: ResultadoDeTranscricao,
    *,
    no_speech: dict[int, float] | None = None,
    regioes: list[tuple[float, float]] | None = None,
) -> tuple[ResultadoDeTranscricao, Veredito]:
    """Devolve o resultado limpo e o veredito. Nunca levanta.

    `no_speech` mapeia índice do segmento → `no_speech_prob`, que o
    `ResultadoDeTranscricao` não carrega por ser específico do Whisper.
    """
    segs = list(resultado.segmentos)
    entrou = sum(len(s.palavras) for s in segs)
    if not segs:
        return resultado, Veredito(0, 0, "sem segmentos")

    ns = no_speech or {}
    bons = [i for i, s in enumerate(segs) if _parece_fala(s, ns.get(i))]

    # 1) nenhum segmento parece fala: o áudio não tem fala nenhuma
    if not bons:
        vazio = ResultadoDeTranscricao(
            texto="", segmentos=[], idioma=resultado.idioma,
            duracao=resultado.duracao, motor=resultado.motor,
            modelo=resultado.modelo, backend=resultado.backend,
            tempos=dict(resultado.tempos),
        )
        return vazio, Veredito(entrou, 0, "nenhum segmento parece fala",
                               len(segs))

    # 2) segmento suspeito E acusticamente vazio sai sozinho
    regs = regioes or []
    mantidos: list[Segmento] = []
    fora = 0
    for i, s in enumerate(segs):
        if i in bons or not regs:
            mantidos.append(s)
            continue
        if _fracao_acustica(s, regs) >= FRACAO_ACUSTICA_MINIMA:
            mantidos.append(s)      # tem som ali: na dúvida, mantém
        else:
            fora += 1

    saiu = sum(len(s.palavras) for s in mantidos)
    limpo = ResultadoDeTranscricao(
        texto=" ".join(s.texto for s in mantidos).strip(),
        segmentos=mantidos, idioma=resultado.idioma,
        duracao=resultado.duracao, motor=resultado.motor,
        modelo=resultado.modelo, backend=resultado.backend,
        tempos=dict(resultado.tempos),
    )
    motivo = ("nada a descartar" if fora == 0
              else f"{fora} segmento(s) fora de região acústica")
    return limpo, Veredito(entrou, saiu, motivo, fora)


def regioes_de(video: Path) -> list[tuple[float, float]]:
    """As regiões acústicas, pelo detector que o projeto já usa.

    Nunca levanta: sem verdade acústica a guarda ainda funciona pela regra 1,
    e recusar a transcrição por causa do detector seria pior que o defeito.
    """
    try:
        import sys

        raiz = Path(__file__).resolve().parent.parent.parent
        h = str(raiz / "helpers")
        if h not in sys.path:
            sys.path.insert(0, h)
        from speech_regions import speech_regions

        return list(speech_regions(video, "-33dB", 0.10))
    except Exception as e:  # noqa: BLE001
        print(f"GUARDA_SEM_REGIOES {type(e).__name__}: {str(e)[:120]}", flush=True)
        return []
