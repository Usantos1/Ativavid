# -*- coding: utf-8 -*-
"""Camada de transcrição: o resto do programa fala só com isto.

O projeto é Python, não .NET — então o equivalente de `ITranscriptionEngine`
aqui é um `Protocol`, e o de `CancellationToken` é um `threading.Event`. A
ideia é a mesma: nenhuma chamada a motor de transcrição espalhada pelo
código, e trocar de motor não toca no resto.

    vídeo → ffmpeg → áudio → MotorDeTranscricao → ResultadoDeTranscricao

O que já existia continua valendo. `helpers/transcribe.py` mantém o cache por
assinatura, o cache entre projetos, a linha de comando e a conversão para o
schema que dez módulos consomem — esta camada entra como mais um motor lá
dentro, não como um caminho paralelo.

**Sobre o formato**: o programa inteiro lê o schema do ElevenLabs Scribe
(`{text, start, end, type, speaker_id}`). `para_schema_scribe()` converte, e é
o único ponto que precisa mudar se o formato interno mudar um dia.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class Palavra:
    """Uma palavra com o tempo em que é falada.

    É o dado mais importante do produto: a legenda karaokê acende palavra por
    palavra lendo `inicio`/`fim` diretamente. Erro aqui aparece na tela.
    """

    texto: str
    inicio: float
    fim: float
    confianca: float | None = None


@dataclass(frozen=True)
class Segmento:
    texto: str
    inicio: float
    fim: float
    confianca: float | None = None
    palavras: tuple[Palavra, ...] = ()


@dataclass
class ResultadoDeTranscricao:
    texto: str
    segmentos: list[Segmento] = field(default_factory=list)
    idioma: str = ""
    duracao: float = 0.0
    motor: str = ""
    modelo: str = ""
    backend: str = ""
    tempos: dict[str, float] = field(default_factory=dict)

    def palavras(self) -> list[Palavra]:
        return [p for s in self.segmentos for p in s.palavras]

    def para_schema_scribe(self) -> dict[str, Any]:
        """Converte para o formato que o resto do ATIVAVID já consome."""
        return schema_scribe(
            self.palavras(), self.texto, idioma=self.idioma,
            motor=self.motor, modelo=self.modelo, backend=self.backend,
        )


def schema_scribe(
    palavras: list[Palavra],
    texto: str,
    *,
    idioma: str = "",
    motor: str = "",
    modelo: str = "",
    backend: str = "",
) -> dict[str, Any]:
    """O schema do Scribe a partir de uma lista de palavras.

    Extraída de `ResultadoDeTranscricao.para_schema_scribe`, que agora delega
    para cá. Existe como função de módulo porque a revisão textual
    (`app/transcricao/revisao.py`) devolve palavras — não um
    `ResultadoDeTranscricao` — e precisa reemitir o payload com ESTA lógica em
    vez de uma cópia dela. Duas cópias divergiriam, e a que divergisse
    silenciosamente é a do `spacing`.

    Emite as entradas `spacing` entre palavras porque `pack_transcripts` e
    `timeline_view` as usam para detectar silêncio — um transcript sem elas
    passa nos testes e degrada a detecção de pausa.
    """
    saida: list[dict[str, Any]] = []
    anterior_fim: float | None = None
    for p in palavras:
        if anterior_fim is not None and p.inicio > anterior_fim + 1e-6:
            saida.append({
                "text": " ", "start": anterior_fim, "end": p.inicio,
                "type": "spacing", "speaker_id": "speaker_0",
            })
        saida.append({
            "text": p.texto, "start": p.inicio, "end": p.fim,
            "type": "word", "speaker_id": "speaker_0",
        })
        anterior_fim = p.fim
    return {
        "words": saida,
        "text": texto,
        "language_code": idioma or "por",
        "_motor": motor,
        "_modelo": modelo,
        "_backend": backend,
    }


class Cancelado(RuntimeError):
    """A transcrição foi interrompida a pedido. Não é erro de motor."""


@runtime_checkable
class MotorDeTranscricao(Protocol):
    """O contrato. Qualquer motor novo implementa isto e nada mais muda."""

    nome: str

    def disponivel(self) -> tuple[bool, str]:
        """(pode usar?, motivo). Nunca levanta — quem pergunta quer decidir."""
        ...

    def transcrever(
        self,
        audio: Path,
        *,
        idioma: str | None = None,
        cancelar: threading.Event | None = None,
        progresso: Callable[[float, str], None] | None = None,
    ) -> ResultadoDeTranscricao:
        ...
