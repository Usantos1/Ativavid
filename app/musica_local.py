# -*- coding: utf-8 -*-
"""Instalação do motor local de música (MusicGen), sob demanda.

Mesma ideia dos componentes da transcrição: peça pesada NÃO vai no
instalador — ele tem ~6 MB e este motor pesa ~2,5 GB (PyTorch com CUDA) mais
2,3 GB de modelo. Quem usa a nuvem nunca baixa nada disso.

Duas diferenças em relação à transcrição:

1. **Ambiente separado.** O motor vive num venv próprio
   (`ATIVAVID/MotorMusica`), não no ambiente do app. PyTorch é grande e tem
   opinião sobre versões; misturá-lo com o resto faria toda atualização do
   app arrastar 2,5 GB e transformaria um conflito de versão do torch em app
   quebrado. Isolado, o pior caso é "a música local não compõe".
2. **Não se instala no meio de um render.** A transcrição pode se preparar
   na hora porque é caminho obrigatório; aqui um download de gigabytes no
   meio do [7/9] seguraria o vídeo. Então: botão em Configurações, com
   progresso, e o render só usa o motor se ele já estiver pronto.

Exige GPU NVIDIA: medido em 27/08 numa RTX 3050, compor 30 s leva 67 s na
GPU e 9 minutos na CPU — na CPU o recurso não vale a pena e não é oferecido.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

MB_TOTAL = 4800          # torch+cuda (~2500) + modelo (~2300), medido
PY_VERSAO = "3.12"
INDICE_CUDA = "https://download.pytorch.org/whl/cu126"
PACOTES = ("transformers", "scipy", "accelerate")
MODELO = "facebook/musicgen-small"


def pasta_motor(raiz_projetos: Path | None = None) -> Path:
    """Irmã da Biblioteca — a mesma raiz que o resto do app usa (resolve o
    junction quando os Projetos moram em outro disco)."""
    try:
        from app.broll_library import library_root

        return library_root(raiz_projetos).parent / "MotorMusica"
    except Exception:  # noqa: BLE001
        return Path.home() / "ATIVAVID" / "MotorMusica"


def python_do_motor(raiz_projetos: Path | None = None) -> Path:
    return pasta_motor(raiz_projetos) / "Scripts" / "python.exe"


def instalado(raiz_projetos: Path | None = None) -> bool:
    return python_do_motor(raiz_projetos).is_file()


def tem_gpu_nvidia() -> bool:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and bool((r.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        return False


def _uv() -> str | None:
    return shutil.which("uv")


def estado(raiz_projetos: Path | None = None) -> dict:
    """O que a tela de Configurações precisa saber."""
    pasta = pasta_motor(raiz_projetos)
    gb = 0.0
    if pasta.is_dir():
        try:
            gb = sum(f.stat().st_size for f in pasta.rglob("*")
                     if f.is_file()) / 1e9
        except OSError:
            gb = 0.0
    return {
        "instalado": instalado(raiz_projetos),
        "pasta": str(pasta),
        "gpu": tem_gpu_nvidia(),
        "mbTotal": MB_TOTAL,
        "gb": round(gb, 1),
        "uv": bool(_uv()),
    }


def _rodar(cmd: list[str], minutos: int = 60) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=minutos * 60)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"
    if p.returncode != 0:
        return False, ((p.stderr or p.stdout or "")[-200:]).strip()
    return True, "ok"


def instalar(
    *,
    raiz_projetos: Path | None = None,
    progresso: Callable[[float, str], None] | None = None,
    cancelar: threading.Event | None = None,
) -> tuple[bool, str]:
    """(conseguiu?, motivo). Idempotente e nunca levanta.

    Os pesos do progresso são os tamanhos reais: o torch é a maior parte da
    espera, e uma barra que anda em passos iguais mentiria por minutos.
    """
    def passo(fracao: float, texto: str) -> None:
        if progresso:
            progresso(min(0.999, fracao), texto)

    if instalado(raiz_projetos):
        return True, "já instalado"
    if not tem_gpu_nvidia():
        return False, ("sem GPU NVIDIA — na CPU a música local levaria "
                       "cerca de 9 minutos por trilha")
    uv = _uv()
    if not uv:
        return False, "uv não encontrado — reinstale o ATIVAVID"
    if cancelar is not None and cancelar.is_set():
        return False, "cancelado"

    pasta = pasta_motor(raiz_projetos)
    passo(0.02, "Criando o ambiente do motor…")
    ok, motivo = _rodar([uv, "venv", str(pasta), "--python", PY_VERSAO],
                        minutos=10)
    if not ok:
        return False, f"ambiente: {motivo}"

    py = str(python_do_motor(raiz_projetos))
    if cancelar is not None and cancelar.is_set():
        return False, "cancelado"
    passo(0.06, "Baixando o PyTorch (a maior parte, ~2,5 GB)…")
    ok, motivo = _rodar([uv, "pip", "install", "--python", py, "torch",
                         "--index-url", INDICE_CUDA], minutos=90)
    if not ok:
        return False, f"pytorch: {motivo}"

    passo(0.55, "Baixando as bibliotecas de música…")
    ok, motivo = _rodar([uv, "pip", "install", "--python", py, *PACOTES],
                        minutos=60)
    if not ok:
        return False, f"bibliotecas: {motivo}"

    if cancelar is not None and cancelar.is_set():
        return False, "cancelado"
    # O modelo vem AGORA, não no primeiro vídeo: 2,3 GB no meio de um render
    # seria uma espera sem explicação na tela.
    passo(0.70, "Baixando o modelo de música (~2,3 GB)…")
    ok, motivo = _rodar(
        [py, "-c",
         "from huggingface_hub import snapshot_download as s;"
         f"s('{MODELO}', allow_patterns=['*.json','*.txt','*.safetensors',"
         "'*.model','*.bin'])"], minutos=90)
    if not ok:
        # Modelo é o único passo com saída: ele se baixa sozinho na primeira
        # música, só que devagar e sem aviso. Melhor instalado que abortado.
        passo(0.99, "Modelo ficará para a primeira música…")
        return True, f"instalado (o modelo virá depois: {motivo})"

    passo(1.0, "Motor de música pronto")
    return True, "instalado agora"
