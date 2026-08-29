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


# Marca escrita SO no fim da instalacao. Sem ela, "instalado" era "a pasta
# existe" — e um download interrompido no meio do PyTorch (fechar o app,
# cair a internet) deixava o cliente presO em "IA local instalada" para
# sempre: o botao de instalar sumia e o motor nunca compunha nada.
MARCA = "pronto.json"


def instalado(raiz_projetos: Path | None = None) -> bool:
    pasta = pasta_motor(raiz_projetos)
    if not (pasta / "Scripts" / "python.exe").is_file():
        return False
    if (pasta / MARCA).is_file():
        return True
    # Instalacao anterior a esta versao (sem marca) conta como pronta se o
    # torch estiver mesmo la — e o que o launcher precisa.
    for padrao in ("Lib/site-packages/torch/__init__.py",
                   "lib/python*/site-packages/torch/__init__.py"):
        if any(pasta.glob(padrao)):
            try:
                (pasta / MARCA).write_text("{}", encoding="utf-8")
            except OSError:
                pass
            return True
    return False


def instalacao_incompleta(raiz_projetos: Path | None = None) -> bool:
    """Pasta existe mas o motor nao esta pronto — precisa de reparo."""
    return (pasta_motor(raiz_projetos).is_dir()
            and not instalado(raiz_projetos))


def _sem_janela() -> dict:
    """CREATE_NO_WINDOW: sem isto cada chamada abre um CMD preto na cara do
    cliente — e o estado e consultado a cada 3s enquanto instala."""
    try:
        from app.win_process import hide_console_kwargs

        return hide_console_kwargs()
    except Exception:  # noqa: BLE001
        return {}


_GPU_CACHE: dict = {}


def tem_gpu_nvidia() -> bool:
    """Cacheado: a resposta nao muda durante a sessao e o poll pergunta
    de 3 em 3 segundos."""
    if "tem" in _GPU_CACHE:
        return bool(_GPU_CACHE["tem"])
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20,
                           **_sem_janela())
        tem = r.returncode == 0 and bool((r.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        tem = False
    _GPU_CACHE["tem"] = tem
    return tem


def _uv() -> str | None:
    return shutil.which("uv")


def estado(raiz_projetos: Path | None = None) -> dict:
    """O que a tela de Configurações precisa saber."""
    pasta = pasta_motor(raiz_projetos)
    pronto = instalado(raiz_projetos)
    # O tamanho e enfeite e custa uma varredura do venv inteiro (~30 mil
    # arquivos): so quando ja esta pronto, nunca no poll da instalacao.
    gb = 0.0
    if pronto:
        try:
            gb = sum(f.stat().st_size for f in pasta.rglob("*")
                     if f.is_file()) / 1e9
        except OSError:
            gb = 0.0
    return {
        "instalado": pronto,
        "incompleta": instalacao_incompleta(raiz_projetos),
        "pasta": str(pasta),
        "gpu": tem_gpu_nvidia(),
        "mbTotal": MB_TOTAL,
        "gb": round(gb, 1),
        "uv": bool(_uv()),
    }


def _rodar(cmd: list[str], minutos: int = 60) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=minutos * 60, **_sem_janela())
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
    if instalacao_incompleta(raiz_projetos):
        # Pasta pela metade de uma tentativa interrompida: `uv venv` e
        # `uv pip install` sao idempotentes e completam o que falta.
        passo(0.01, "Retomando a instalação…")
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
        # O modelo pesa 2,3 GB e o launcher desiste em 240s: sem ele aqui, a
        # primeira musica de TODO video estouraria o prazo e a trilha cairia
        # para a biblioteca — parecendo que o motor nao funciona. Entao isto
        # e falha de instalacao, com reparo pela mesma tela.
        return False, f"o modelo não baixou: {motivo}"

    try:
        (pasta_motor(raiz_projetos) / MARCA).write_text(
            '{"ok": true}', encoding="utf-8")
    except OSError as e:
        return False, f"não consegui marcar como pronto: {e}"
    passo(1.0, "Motor de música pronto")
    return True, "instalado agora"
