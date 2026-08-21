# -*- coding: utf-8 -*-
"""Transcrição 100% local com faster-whisper (CTranslate2).

POR QUE ESTE MOTOR, medido nesta máquina contra a verdade acústica do próprio
repo (`speech_regions.py`), na mesma fonte:

    Scribe (nuvem, hoje)      100% das palavras dentro da fala, pior 0,06s
    faster-whisper medium      98%                                pior 0,25s
    faster-whisper small       96%                                pior 0,25s
    whisper.cpp (já no repo)   66%                                pior 2,50s

O whisper.cpp já existia aqui e foi reprovado por isso: o `-ml 1 -sow` dele é
uma heurística de corte de segmento, e o `-dtw`, que daria alinhamento de
verdade, não computa nada num build padrão (todo `t_dtw` volta -1). Um terço
das palavras fora da fala aparece na tela — a legenda karaokê lê estes tempos
direto. O faster-whisper alinha por cross-attention + DTW, que é o algoritmo
de referência, e por isso chega perto do serviço em nuvem.

O `Whisper.NET` foi descartado por herdar o whisper.cpp e por exigir .NET, que
este projeto não tem. O argumento de "evitar dependência de Python" não se
aplica: o instalador já provisiona `uv` e o app inteiro é Python.

VELOCIDADE, medida (áudio de 15,8s):
    CUDA  small   3,2x tempo real
    CUDA  medium  2,7x tempo real   (pico de 2.661 MiB de VRAM)
    CPU   small   1,1x tempo real
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.transcricao import (
    Cancelado, Palavra, ResultadoDeTranscricao, Segmento,
)
from app.transcricao import modelos as cat
from app.transcricao.plataforma import detectar, resumo_tecnico

# O modelo carregado fica vivo entre chamadas: carregar custa segundos e um
# lote de 12 vídeos pagaria isso 12 vezes. Guardado por (modelo, backend)
# porque trocar qualquer um dos dois exige recarregar de verdade.
_CARREGADO: dict[tuple[str, str], Any] = {}
_TRAVA = threading.Lock()


def liberar() -> None:
    """Solta o modelo e a VRAM. Chamado quando o render precisa da placa."""
    with _TRAVA:
        _CARREGADO.clear()
    try:
        import gc

        gc.collect()
    except Exception:  # noqa: BLE001
        pass


class MotorWhisperLocal:
    """Motor local. Não sai da máquina: nenhum áudio, nenhum texto."""

    nome = "whisper-local"

    def __init__(self, modelo: str | None = None) -> None:
        self._maquina = detectar()
        self._modelo = cat.escolher_modelo(self._maquina.vram_mb, modelo)

    @property
    def modelo(self) -> cat.Modelo:
        return self._modelo

    def disponivel(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, ("faster-whisper não instalado "
                           "(uv sync --extra transcricao)")
        return True, resumo_tecnico()

    # ------------------------------------------------------------------
    def _carregar(self, progresso: Callable[[float, str], None] | None,
                  cancelar: threading.Event | None) -> tuple[Any, float]:
        chave = (self._modelo.chave, self._maquina.backend)
        with _TRAVA:
            pronto = _CARREGADO.get(chave)
        if pronto is not None:
            return pronto, 0.0

        pasta = cat.garantir(self._modelo, progresso=progresso, cancelar=cancelar)
        from faster_whisper import WhisperModel

        t0 = time.perf_counter()
        try:
            m = WhisperModel(str(pasta), device=self._maquina.backend,
                             compute_type=self._maquina.compute_type)
        except Exception as e:  # noqa: BLE001
            # A aceleração NUNCA pode impedir a transcrição. Se a GPU recusa
            # (driver, VRAM ocupada pelo render, DLL faltando), a CPU entrega.
            if self._maquina.backend == "cpu":
                raise
            print(f"WHISPER_ACELERACAO_FALHOU {type(e).__name__}: "
                  f"{str(e)[:160]} — usando CPU", flush=True)
            # `replace` e não `object.__setattr__`: `detectar()` é um
            # `lru_cache`, então mexer no objeto congelado no lugar mudaria o
            # que TODO o processo enxerga — inclusive outros jobs.
            import dataclasses

            self._maquina = dataclasses.replace(
                self._maquina, backend="cpu", motivo="queda da aceleração")
            m = WhisperModel(str(pasta), device="cpu", compute_type="int8")
            chave = (self._modelo.chave, "cpu")
        dt = time.perf_counter() - t0
        with _TRAVA:
            _CARREGADO[chave] = m
        return m, dt

    def transcrever(
        self,
        audio: Path,
        *,
        idioma: str | None = None,
        cancelar: threading.Event | None = None,
        progresso: Callable[[float, str], None] | None = None,
    ) -> ResultadoDeTranscricao:
        ok, motivo = self.disponivel()
        if not ok:
            raise RuntimeError(motivo)
        print(resumo_tecnico(), flush=True)

        modelo, t_carga = self._carregar(progresso, cancelar)
        if cancelar is not None and cancelar.is_set():
            raise Cancelado("cancelado antes de transcrever")

        t0 = time.perf_counter()
        segs_it, info = modelo.transcribe(
            str(audio),
            language=idioma or None,
            word_timestamps=True,      # o dado que a legenda karaokê lê
            vad_filter=False,          # o corte já vem de speech_regions.py
        )
        total = float(getattr(info, "duration", 0.0) or 0.0)

        segmentos: list[Segmento] = []
        partes: list[str] = []
        # `transcribe` devolve um gerador: o trabalho acontece ao iterar. É
        # aqui, e só aqui, que dá para cancelar no meio e informar progresso.
        for s in segs_it:
            if cancelar is not None and cancelar.is_set():
                raise Cancelado("cancelado durante a transcrição")
            palavras = tuple(
                Palavra(texto=(w.word or "").strip(), inicio=float(w.start),
                        fim=float(w.end), confianca=float(w.probability))
                for w in (getattr(s, "words", None) or [])
                if w.start is not None and w.end is not None
            )
            segmentos.append(Segmento(
                texto=(s.text or "").strip(), inicio=float(s.start),
                fim=float(s.end),
                confianca=(float(s.avg_logprob)
                           if getattr(s, "avg_logprob", None) is not None else None),
                palavras=palavras,
            ))
            partes.append(s.text or "")
            if progresso and total > 0:
                progresso(min(0.99, float(s.end) / total), "Transcrevendo áudio…")
        t_tr = time.perf_counter() - t0
        if progresso:
            progresso(1.0, "Transcrevendo áudio…")

        return ResultadoDeTranscricao(
            texto=" ".join(partes).strip(),
            segmentos=segmentos,
            idioma=str(getattr(info, "language", "") or idioma or ""),
            duracao=total,
            motor=self.nome,
            modelo=self._modelo.chave,
            backend=self._maquina.backend,
            tempos={"carregar_modelo": round(t_carga, 3),
                    "transcrever": round(t_tr, 3)},
        )
