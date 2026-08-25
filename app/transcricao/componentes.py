# -*- coding: utf-8 -*-
"""Peças pesadas que NÃO vão no instalador: baixadas quando fizerem falta.

O instalador principal tem 10 MB. As bibliotecas de CUDA pesam **1.986 MB**
(medido: cuBLAS, cuDNN e nvRTC) e o modelo mais 462 ou 1.458 MB. Embutir isso
multiplicaria o instalador por duas ordens de grandeza, e faria todo mundo —
inclusive quem já tem tudo — rebaixar em cada atualização do app.

Então: o app instala leve, e na primeira vez que a transcrição local precisar
de aceleração, o componente é buscado. Depois disso funciona offline, e
atualizar o app não baixa nada de novo.

Quem não tem GPU NVIDIA nunca vê isto. Quem tem, mas onde o download falha,
transcreve na CPU — mais devagar, mas transcreve.

O usuário nunca instala CUDA Toolkit à mão: estas bibliotecas vêm como pacotes
Python normais (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`), que trazem as DLLs
já compiladas.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from app.transcricao.plataforma import (
    _DLLS_CUDA,
    dlls_cuda_completas,
    registrar_dlls_cuda,
)

# Os pacotes que trazem as DLLs. `nvidia-cuda-nvrtc-cu12` entra de carona como
# dependência do cuDNN; não precisa ser pedido.
PACOTES_CUDA = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12")
MB_CUDA = 1986        # medido nesta máquina


# O motor em si. Fica FORA das dependências base do app de propósito: quem
# transcreve pela nuvem não precisa dele. O instalador já o traz
# (`uv sync --extra transcricao`), e isto aqui é a rede para quem ATUALIZA de
# uma versão antiga sem passar pelo instalador — nesse caminho o `uv sync`
# não roda e o motor não apareceria sozinho.
PACOTES_MOTOR = ("faster-whisper>=1.2",)
MB_MOTOR = 241        # medido num ambiente limpo


def motor_presente() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def garantir_motor(
    *,
    progresso: Callable[[float, str], None] | None = None,
    cancelar: threading.Event | None = None,
) -> tuple[bool, str]:
    """(conseguiu?, motivo). Idempotente. Nunca levanta.

    Sem o motor a transcrição local não acontece de jeito nenhum — então este
    é o único componente cuja ausência é falha de verdade. CUDA e modelo têm
    saída (CPU, modelo menor); este não tem.
    """
    if motor_presente():
        return True, "já instalado"
    if cancelar is not None and cancelar.is_set():
        return False, "cancelado"
    if progresso:
        progresso(0.0, "Preparando transcrição…")
    ok, motivo = _instalar(PACOTES_MOTOR)
    if not ok:
        return False, motivo
    if progresso:
        progresso(1.0, "Preparando transcrição…")
    if not motor_presente():
        return False, "instalado mas não importou"
    return True, "instalado agora"


def cuda_presente() -> bool:
    """As DLLs estão no disco e o carregador as encontra?

    TODAS as essenciais, não qualquer uma: o `uv sync` do instalador removeu
    o cublas e deixou o cudnn (caso real, 25/08) — o check antigo achava o
    cudnn, dizia "já instalado", e o motor morria no runtime com "Library
    cublas64_12.dll is not found". cuBLAS e cuDNN são ambos obrigatórios
    para o CTranslate2 em CUDA; faltando um, reinstala.
    """
    return dlls_cuda_completas()


def _uv() -> str | None:
    import shutil

    return shutil.which("uv")


def _instalar(pacotes: tuple[str, ...]) -> tuple[bool, str]:
    """Busca pacotes NESTE ambiente. Um caminho so, usado por motor e CUDA.

    `--python sys.executable` de proposito: o app roda de um venv proprio, e
    sem isso o uv instalaria no que ele adivinhar.
    """
    uv = _uv()
    if not uv:
        return False, "uv nao encontrado — sem como buscar o componente"
    cmd = [uv, "pip", "install", "--python", sys.executable, *pacotes]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"falhou ao buscar: {type(e).__name__}: {e}"
    if proc.returncode != 0:
        return False, f"falhou ao buscar: {(proc.stderr or '')[-160:]}"
    return True, "ok"


def garantir_cuda(
    *,
    progresso: Callable[[float, str], None] | None = None,
    cancelar: threading.Event | None = None,
) -> tuple[bool, str]:
    """(conseguiu?, motivo). NUNCA levanta: sem CUDA a CPU transcreve.

    Idempotente — depois da primeira vez sai na hora.
    """
    if cuda_presente():
        return True, "já instalado"
    if sys.platform != "win32":
        # Em Linux/macOS o wheel do CTranslate2 resolve sozinho pelo RPATH.
        return False, "só o Windows precisa deste componente"
    if cancelar is not None and cancelar.is_set():
        return False, "cancelado"

    if progresso:
        progresso(0.0, "Preparando a aceleração…")
    ok, motivo = _instalar(PACOTES_CUDA)
    if not ok:
        return False, motivo

    if progresso:
        progresso(1.0, "Preparando a aceleração…")
    # Confere de verdade em vez de confiar no código de saída: pacote
    # instalado com DLL faltando levaria o motor a falhar depois, longe daqui.
    if not cuda_presente():
        return False, "componente instalado mas as bibliotecas não apareceram"
    return True, "instalado agora"


def estado() -> dict[str, object]:
    """O que existe no disco, para o log técnico e para o relatório."""
    achados = []
    for base in {Path(p) for p in sys.path if p}:
        for sub in _DLLS_CUDA:
            d = base / Path(sub)
            if d.is_dir():
                mb = sum(f.stat().st_size for f in d.glob("*") if f.is_file())
                achados.append({"onde": sub, "mb": round(mb / 1e6)})
    return {"cuda_presente": bool(achados), "diretorios": achados,
            "mb_declarado": MB_CUDA}
