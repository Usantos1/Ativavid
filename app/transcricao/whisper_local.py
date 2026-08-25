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
from app.transcricao import guarda
from app.transcricao import modelos as cat
from app.transcricao.plataforma import detectar, resumo_tecnico

# Quantos trechos de fala vão para a GPU de uma vez. 8 foi medido na placa de
# 4 GB do usuário junto com o modelo `medium`, sem estourar. Número maior não
# acelera muito e arrisca ficar sem memória bem na hora do render, que divide
# a mesma placa.
_LOTE = 8

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
        self._anunciado: tuple[str, str] = ("", "")
        self._pedido = modelo
        self._maquina = detectar()
        self._modelo = cat.escolher_modelo(
            self._maquina.vram_mb, modelo, backend=self._maquina.backend)

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

        # A aceleracao e um COMPONENTE, nao parte do instalador: 1.986 MB de
        # DLLs de CUDA sao buscados aqui, na primeira vez que fazem falta. Se
        # nao der, a CPU transcreve -- mais devagar, mas transcreve.
        if self._maquina.backend == "cuda":
            from app.transcricao import componentes

            ok, motivo = componentes.garantir_cuda(progresso=progresso,
                                                   cancelar=cancelar)
            print(f"WHISPER_COMPONENTE_CUDA {'ok' if ok else 'indisponivel'}: "
                  f"{motivo}", flush=True)
            if not ok:
                import dataclasses

                self._maquina = dataclasses.replace(
                    self._maquina, backend="cpu",
                    motivo=f"sem componente CUDA ({motivo})")
                # Sem GPU o modelo muda: `medium` na CPU roda a menos de 1x
                # tempo real. A regra e uma so, e mora em `modelos`.
                self._modelo = cat.escolher_modelo(
                    self._maquina.vram_mb, self._pedido, backend="cpu")
                chave = (self._modelo.chave, "cpu")

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
            self._modelo = cat.escolher_modelo(
                self._maquina.vram_mb, self._pedido, backend="cpu")
            pasta = cat.garantir(self._modelo, progresso=progresso,
                                 cancelar=cancelar)
            m = WhisperModel(str(pasta), device="cpu", compute_type="int8")
            chave = (self._modelo.chave, "cpu")
        dt = time.perf_counter() - t0
        with _TRAVA:
            _CARREGADO[chave] = m
        return m, dt

    def _queda_para_cpu_no_runtime(self, e: RuntimeError, progresso, cancelar):
        """Reconstrói o motor em CPU quando a GPU quebra DEPOIS da carga.

        Só para falha de biblioteca/aceleração (DLL, CUDA, cuBLAS/cuDNN) e
        só se ainda estamos em GPU — qualquer outro RuntimeError sobe."""
        txt = str(e).lower()
        de_gpu = any(t in txt for t in ("dll", "cublas", "cudnn", "cuda"))
        if self._maquina.backend == "cpu" or not de_gpu:
            raise e
        print(f"WHISPER_ACELERACAO_FALHOU_RUNTIME {type(e).__name__}: "
              f"{str(e)[:160]} — refazendo em CPU", flush=True)
        import dataclasses

        self._maquina = dataclasses.replace(
            self._maquina, backend="cpu", motivo="queda da aceleração (runtime)")
        self._modelo = cat.escolher_modelo(
            self._maquina.vram_mb, self._pedido, backend="cpu")
        modelo, _dt = self._carregar(progresso, cancelar)
        print(f"TRANSCRIPTION ENGINE local model={self._modelo.chave} "
              f"device=cpu (revisto no runtime)", flush=True)
        return modelo

    def _transcrever_rapido(self, modelo: Any, audio: Path,
                            idioma: str | None) -> tuple[Any, Any]:
        """Transcreve pulando o silêncio e processando em lote na GPU.

        DUAS otimizações que só funcionam juntas — o lote exige o VAD, que é
        quem define os trechos ("No clip timestamps found" sem ele):

          1. **não transcrever silêncio.** Nas fontes do usuário metade do
             áudio é pausa: numa de 171s, só 87s são fala.
          2. **lote na GPU**, em vez de um trecho por vez.

        MEDIDO em 10 fontes reais: mediana **1,8x** mais rápido, chegando a
        4,2x nas longas — que são justamente aquelas em que se espera. Uma
        fonte só tinha dado 2,8x; a amostra maior corrigiu para baixo.

        E não custa qualidade: palavras estranhas caíram de 7,7% para 7,2% na
        mediana, e das 10 fontes só 2 pioraram — nessas, as palavras "novas"
        eram português legítimo (`acordou`, `produção`, `tão`), não invenção.

        O texto MUDA (semelhança de 68% a 100% com o modo antigo). É um
        transcript diferente e igualmente bom, não o mesmo mais rápido.

        Cai para o modo antigo se o lote falhar: velocidade não pode custar a
        transcrição.
        """
        comum = dict(language=idioma or None, word_timestamps=True)
        try:
            from faster_whisper import BatchedInferencePipeline

            lote = BatchedInferencePipeline(model=modelo)
            return lote.transcribe(str(audio), vad_filter=True,
                                   batch_size=_LOTE, **comum)
        except Exception as e:  # noqa: BLE001
            print(f"WHISPER_LOTE_INDISPONIVEL {type(e).__name__}: "
                  f"{str(e)[:120]} — modo sequencial", flush=True)
            return modelo.transcribe(str(audio), vad_filter=False, **comum)

    def transcrever(
        self,
        audio: Path,
        *,
        idioma: str | None = None,
        cancelar: threading.Event | None = None,
        progresso: Callable[[float, str], None] | None = None,
        fonte_original: Path | None = None,
    ) -> ResultadoDeTranscricao:
        ok, motivo = self.disponivel()
        if not ok:
            raise RuntimeError(motivo)
        # A linha que o log tecnico usa para acompanhar os primeiros usos.
        self._anunciado = (self._maquina.backend, self._modelo.chave)
        print(f"TRANSCRIPTION ENGINE local model={self._modelo.chave} "
              f"device={self._maquina.backend}", flush=True)
        print(resumo_tecnico(), flush=True)

        modelo, t_carga = self._carregar(progresso, cancelar)
        # Reconfere: `_carregar` pode ter caido para CPU, e ai o modelo certo
        # e o `small`. A linha de log acima seria mentira sem isto.
        if (self._maquina.backend, self._modelo.chave) != self._anunciado:
            print(f"TRANSCRIPTION ENGINE local model={self._modelo.chave} "
                  f"device={self._maquina.backend} (revisto)", flush=True)
        if cancelar is not None and cancelar.is_set():
            raise Cancelado("cancelado antes de transcrever")

        t0 = time.perf_counter()
        try:
            segs_it, info = self._transcrever_rapido(modelo, audio, idioma)
            total = float(getattr(info, "duration", 0.0) or 0.0)
        except RuntimeError as e:
            modelo = self._queda_para_cpu_no_runtime(e, progresso, cancelar)
            segs_it, info = self._transcrever_rapido(modelo, audio, idioma)
            total = float(getattr(info, "duration", 0.0) or 0.0)

        segmentos: list[Segmento] = []
        partes: list[str] = []
        # `no_speech_prob` e do Whisper, nao do contrato -- fica de lado, por
        # indice, para a guarda usar sem sujar `ResultadoDeTranscricao`.
        nao_fala: dict[int, float] = {}
        # `transcribe` devolve um gerador: o trabalho acontece ao iterar. É
        # aqui, e só aqui, que dá para cancelar no meio e informar progresso.
        # E é AQUI que a GPU quebra de verdade: a construção do modelo passa
        # e o primeiro encode explode ("Library cublas64_12.dll is not
        # found" — caso real de 25/08, uv sync removeu o cublas). A queda
        # para CPU da carga não cobria este ponto; o job inteiro morria.
        try:
            primeiro = next(segs_it, None)
        except RuntimeError as e:
            modelo = self._queda_para_cpu_no_runtime(e, progresso, cancelar)
            segs_it, info = self._transcrever_rapido(modelo, audio, idioma)
            total = float(getattr(info, "duration", 0.0) or 0.0)
            primeiro = next(segs_it, None)
        import itertools as _it

        if primeiro is not None:
            segs_it = _it.chain([primeiro], segs_it)
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
            nao_fala[len(segmentos) - 1] = float(
                getattr(s, "no_speech_prob", 0.0) or 0.0)
            partes.append(s.text or "")
            if progresso and total > 0:
                progresso(min(0.99, float(s.end) / total), "Transcrevendo áudio…")
        t_tr = time.perf_counter() - t0
        if progresso:
            progresso(1.0, "Transcrevendo áudio…")

        bruto = ResultadoDeTranscricao(
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

        # A guarda contra texto que ninguem falou. Roda SEMPRE: e barata
        # quando nao ha o que descartar, e o defeito que ela evita (legenda
        # inventada) chega ao video publicado.
        t_g = time.perf_counter()
        regioes = guarda.regioes_de(fonte_original or audio)
        limpo, veredito = guarda.aplicar(bruto, no_speech=nao_fala,
                                         regioes=regioes)
        limpo.tempos["guarda"] = round(time.perf_counter() - t_g, 3)
        # Marcador para a telemetria: a guarda entrou em acao neste video?
        limpo.tempos["_guarda_cortou"] = float(veredito.entrou != veredito.saiu)
        if veredito.entrou != veredito.saiu:
            print(f"WHISPER_GUARDA {veredito.entrou} -> {veredito.saiu} palavras "
                  f"({veredito.motivo})", flush=True)
        return limpo
