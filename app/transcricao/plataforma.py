# -*- coding: utf-8 -*-
"""Onde estamos rodando, e com que aceleração — num lugar só.

Tudo que é específico de sistema operacional, arquitetura ou GPU mora aqui.
O objetivo é que a versão macOS não precise caçar `if Windows` espalhado: ela
adiciona um ramo neste arquivo e o resto do programa não muda.

Três coisas são decididas aqui e em nenhum outro lugar:

  1. **backend de aceleração** — `cuda` no Windows/Linux com GPU NVIDIA
     utilizável, `metal` no Apple Silicon quando o motor suportar, `cpu` como
     chão. Nunca levanta: se a aceleração não está utilizável, devolve `cpu`.
  2. **onde ficam os modelos** — uma pasta por usuário, fora do projeto, para
     sobreviver a reinstalação do app.
  3. **as DLLs de CUDA** — no Windows os pacotes `nvidia-*-cu12` instalam as
     DLLs dentro do `site-packages`, e o carregador do Windows não olha ali.
     Medido: sem registrar esses diretórios, o CTranslate2 falha com
     "Library cublas64_12.dll is not found or cannot be loaded" mesmo com os
     pacotes instalados.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Diretórios (dentro do site-packages) onde os pacotes nvidia-*-cu12 põem as
# DLLs. Ordem irrelevante; todos são registrados quando existem.
_DLLS_CUDA = ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin")

# VRAM mínima para valer a pena usar a GPU. Abaixo disso o modelo não cabe
# junto com o encoder de vídeo, que divide a mesma placa neste app.
_VRAM_MINIMA_MB = 2000


@dataclass(frozen=True)
class Maquina:
    """O que foi detectado. Imutável: detecta uma vez, usa em todo lugar."""

    sistema: str            # "windows" | "darwin" | "linux"
    arquitetura: str        # "x86_64" | "arm64"
    apple_silicon: bool
    gpu_nome: str           # "" quando não há
    vram_mb: int            # 0 quando desconhecida
    backend: str            # "cuda" | "metal" | "cpu" -- o que dá para usar AGORA
    motivo: str             # por que este backend, para o log técnico
    # O hardware SUPORTA aceleração, mesmo que as bibliotecas ainda não
    # estejam no disco. Sem separar isto de `backend`, a busca das bibliotecas
    # ficava circular: elas só eram baixadas se o backend já fosse "cuda", e o
    # backend só virava "cuda" se elas já estivessem lá. Numa RTX 3050 real
    # isso prendia a máquina em CPU + modelo pequeno para sempre.
    cuda_possivel: bool = False

    @property
    def compute_type(self) -> str:
        """Precisão que o CTranslate2 deve usar neste backend.

        `int8` na CPU não é economia de disco, é o que torna a CPU viável:
        medido, `float32` na CPU fica abaixo do tempo real.
        """
        return "float16" if self.backend == "cuda" else "int8"


def _arquitetura() -> str:
    m = (platform.machine() or "").lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x86_64"


def _gpu_nvidia() -> tuple[str, int]:
    """(nome, VRAM em MB) da primeira GPU NVIDIA, ou ("", 0).

    Usa `nvidia-smi`, que existe sempre que há driver NVIDIA. Nunca levanta:
    máquina sem NVIDIA simplesmente não tem o binário.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return "", 0
    try:
        r = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return "", 0
    # Uma linha por GPU. Fica com a de MAIOR VRAM: em notebook a primeira
    # costuma ser a integrada da Intel, que não serve.
    melhor = ("", 0)
    for linha in (r.stdout or "").splitlines():
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) < 2:
            continue
        try:
            mb = int(float(partes[1]))
        except ValueError:
            continue
        if mb > melhor[1]:
            melhor = (partes[0], mb)
    return melhor


def registrar_dlls_cuda() -> list[str]:
    """Ensina o Windows a achar as DLLs de CUDA do site-packages.

    Sem isto o CTranslate2 não carrega, mesmo com os pacotes instalados —
    medido nesta máquina. Em Linux/macOS não faz nada: lá o carregador segue
    o RPATH do próprio wheel.
    """
    if sys.platform != "win32":
        return []
    registrados: list[str] = []
    for base in {Path(p) for p in sys.path if p}:
        for sub in _DLLS_CUDA:
            d = base / Path(sub)
            if not d.is_dir():
                continue
            try:
                os.add_dll_directory(str(d))
            except (OSError, AttributeError):
                continue
            os.environ["PATH"] = f"{d}{os.pathsep}{os.environ.get('PATH', '')}"
            registrados.append(sub)
    return registrados


def _cuda_utilizavel(vram_mb: int) -> tuple[bool, str]:
    if vram_mb <= 0:
        return False, "sem GPU NVIDIA"
    if vram_mb < _VRAM_MINIMA_MB:
        return False, f"VRAM insuficiente ({vram_mb} MB < {_VRAM_MINIMA_MB})"
    if not registrar_dlls_cuda() and sys.platform == "win32":
        return False, "bibliotecas CUDA ausentes (nvidia-cublas-cu12 / nvidia-cudnn-cu12)"
    return True, f"GPU {vram_mb} MB"


@lru_cache(maxsize=1)
def detectar() -> Maquina:
    """Detecta uma vez por processo. O resultado não muda em execução."""
    sistema = sys.platform
    sistema = ("windows" if sistema == "win32"
               else "darwin" if sistema == "darwin" else "linux")
    arq = _arquitetura()
    apple = sistema == "darwin" and arq == "arm64"

    forcado = (os.environ.get("ATIVAVID_WHISPER_BACKEND") or "").strip().lower()
    if forcado in ("cpu", "cuda", "metal"):
        gpu, vram = _gpu_nvidia()
        if forcado == "cuda":
            registrar_dlls_cuda()
        return Maquina(sistema, arq, apple, gpu, vram, forcado,
                       f"forçado por ATIVAVID_WHISPER_BACKEND={forcado}",
                       cuda_possivel=(forcado == "cuda"))

    if sistema == "darwin":
        # Apple Silicon: o CTranslate2 ainda não usa Metal, então a CPU ARM
        # (que é rápida) é o caminho honesto. Quando isso mudar, o ramo entra
        # AQUI e nada mais no programa precisa saber.
        return Maquina(sistema, arq, apple, "", 0, "cpu",
                       "macOS: CPU (CTranslate2 ainda não usa Metal)")

    gpu, vram = _gpu_nvidia()
    ok, motivo = _cuda_utilizavel(vram)
    # `cuda_possivel` olha SÓ o hardware: se há GPU NVIDIA com VRAM bastante.
    # `backend` olha o que dá para rodar agora, que também depende das DLLs.
    possivel = bool(gpu) and vram >= _VRAM_MINIMA_MB
    return Maquina(sistema, arq, apple, gpu, vram,
                   "cuda" if ok else "cpu", motivo, cuda_possivel=possivel)


def esquecer() -> None:
    """Joga fora a detecção em cache.

    Necessário depois de instalar as bibliotecas de CUDA: a detecção roda uma
    vez por processo, e sem isto o mesmo processo continuaria acreditando que
    está em CPU logo depois de ganhar a aceleração.
    """
    detectar.cache_clear()


def pasta_de_modelos() -> Path:
    """Onde os modelos ficam. Fora do projeto, para sobreviver a reinstalação.

    Respeita `ATIVAVID_WHISPER_MODELS` para quem quer pôr num disco maior —
    o modelo `medium` sozinho tem 1,4 GB.
    """
    env = (os.environ.get("ATIVAVID_WHISPER_MODELS") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "ATIVAVID" / "modelos-whisper"


def resumo_tecnico() -> str:
    """Uma linha para o log. Não vai para a tela do usuário."""
    m = detectar()
    gpu = f" gpu={m.gpu_nome} ({m.vram_mb} MB)" if m.gpu_nome else ""
    return (f"Whisper backend: {m.backend.upper()} — {m.motivo} "
            f"[{m.sistema}/{m.arquitetura}{gpu}]")
