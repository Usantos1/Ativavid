# -*- coding: utf-8 -*-
"""A primeira transcrição: preparar tudo, uma vez, sem o usuário saber de nada.

O que ele vê é isto, e só isto:

    Preparando transcrição local
    Baixando componentes necessários…   1,2 GB de 3,7 GB

Nem Whisper, nem CUDA, nem CTranslate2 aparecem na tela. O usuário pediu uma
legenda, não uma instalação.

A ordem é a que faz sentido físico, e cada passo depende do anterior:

    hardware  →  o que falta  →  baixar  →  validar  →  transcrever

Detectar o hardware primeiro não é detalhe: numa máquina sem GPU o total cai
de 3,7 GB para 703 MB, porque as bibliotecas de aceleração (1.986 MB) e o
modelo maior (1.458 contra 462 MB) simplesmente não entram na conta. Anunciar
3,7 GB para quem vai baixar 703 seria mentir na única tela que o usuário vê.

Depois da primeira vez isto sai do caminho: `ja_pronto()` responde em
milissegundos e nada é mostrado.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from app.transcricao import Cancelado
from app.transcricao import componentes, modelos
from app.transcricao.plataforma import detectar

# O que o usuário lê. Sem jargão de propósito.
TITULO = "Preparando transcrição local"
BAIXANDO = "Baixando componentes necessários…"
TRANSCREVENDO = "Transcrevendo áudio…"


@dataclass(frozen=True)
class Plano:
    """O que falta baixar nesta máquina, e quanto pesa."""

    pacotes_mb: int
    aceleracao_mb: int
    modelo_mb: int
    modelo: str
    backend: str

    @property
    def total_mb(self) -> int:
        return self.pacotes_mb + self.aceleracao_mb + self.modelo_mb

    @property
    def precisa_baixar(self) -> bool:
        return self.total_mb > 0

    def humano(self) -> str:
        """O tamanho como o usuário lê, não como o disco conta."""
        mb = self.total_mb
        return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"


# Peso dos pacotes Python do motor (CTranslate2, av, onnxruntime, tokenizers),
# medido num ambiente limpo: 241 MB.
PACOTES_MB = 241


def _motor_instalado() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def planejar() -> Plano:
    """O que ainda falta. Barato: só olha o disco e o `nvidia-smi`."""
    maq = detectar()
    modelo = modelos.escolher_modelo(maq.vram_mb, backend=maq.backend)
    return Plano(
        pacotes_mb=0 if _motor_instalado() else PACOTES_MB,
        aceleracao_mb=(componentes.MB_CUDA
                       if maq.backend == "cuda" and not componentes.cuda_presente()
                       else 0),
        modelo_mb=0 if modelos.instalado(modelo) else modelo.mb,
        modelo=modelo.chave,
        backend=maq.backend,
    )


def ja_pronto() -> bool:
    """Depois da primeira vez, responde na hora e nada é mostrado."""
    return not planejar().precisa_baixar


def preparar(
    *,
    progresso: Callable[[float, str], None] | None = None,
    cancelar: threading.Event | None = None,
) -> Plano:
    """Deixa a máquina pronta para transcrever. Idempotente.

    O progresso é ponderado pelo TAMANHO de cada peça, não pela contagem:
    o modelo de 1.458 MB e as bibliotecas de 1.986 MB não podem valer "metade
    cada" numa barra — ela andaria em solavancos.

    Levanta se não conseguir. Quem chamou decide o que dizer, mas o certo é
    oferecer nova tentativa: download interrompido não deixa nada quebrado,
    porque o modelo só é dado por bom depois de conferido.
    """
    plano = planejar()
    if not plano.precisa_baixar:
        return plano

    total = float(plano.total_mb)
    feito = 0.0

    def parcial(peso_mb: int) -> Callable[[float, str], None] | None:
        if progresso is None:
            return None

        def dentro(fracao: float, _rotulo: str) -> None:
            progresso(min(0.999, (feito + fracao * peso_mb) / total), BAIXANDO)

        return dentro

    if cancelar is not None and cancelar.is_set():
        raise Cancelado("cancelado antes de preparar")

    if plano.aceleracao_mb:
        ok, motivo = componentes.garantir_cuda(progresso=parcial(plano.aceleracao_mb),
                                               cancelar=cancelar)
        print(f"PRIMEIRO_USO aceleracao={'ok' if ok else 'nao'} ({motivo})",
              flush=True)
        # Sem aceleração NÃO é falha: a CPU transcreve. Mas o modelo muda —
        # `small` em vez de `medium` — e o plano precisa refletir isso.
        feito += plano.aceleracao_mb

    modelo = modelos.escolher_modelo(detectar().vram_mb,
                                     backend=detectar().backend)
    if not modelos.instalado(modelo):
        modelos.garantir(modelo, progresso=parcial(modelo.mb), cancelar=cancelar)
        feito += modelo.mb

    if progresso:
        progresso(1.0, BAIXANDO)
    print(f"PRIMEIRO_USO pronto modelo={modelo.chave} "
          f"backend={detectar().backend}", flush=True)
    return planejar()
