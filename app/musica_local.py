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

# Onde o driver da NVIDIA poe o nvidia-smi quando ele NAO esta no PATH.
# Caso do cliente (04/09): "ele tem placa de video sim", e a tela dizia
# "precisa de placa NVIDIA" — `subprocess.run(["nvidia-smi"])` levanta
# OSError e a resposta virava "sem GPU", sem dizer que placa havia.
_NVIDIA_SMI = (
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
)


def _nvidia_smi() -> str:
    """O caminho do nvidia-smi: PATH primeiro, depois os lugares do driver."""
    achado = shutil.which("nvidia-smi")
    if achado:
        return achado
    for c in _NVIDIA_SMI:
        if Path(c).is_file():
            return c
    return ""


def _placa_pelo_sistema() -> tuple[bool, str]:
    """(e NVIDIA?, nome da placa) pelo mesmo detector do resto do app.

    `system_info` le a Win32_VideoController e os encoders do ffmpeg — nao
    depende do nvidia-smi estar instalado. E o que a tela Sistema mostra,
    entao os dois cartoes passam a dizer a mesma coisa.
    """
    try:
        from app.system_info import detect_machine

        gpus = detect_machine().get("gpus") or []
    except Exception:  # noqa: BLE001 — deteccao nunca derruba a tela
        return False, ""
    nomes = [str(g.get("name") or "").strip() for g in gpus if g.get("name")]
    # O notebook dele lista a Intel PRIMEIRO e a NVIDIA depois: pegar
    # nomes[0] diria "Intel UHD" numa maquina que tem a placa boa.
    nvidia = next((n for n in nomes if "nvidia" in n.lower()), "")
    return bool(nvidia), (nvidia or (nomes[0] if nomes else ""))


def gpu_do_motor() -> tuple[bool, str]:
    """(da para compor aqui?, nome da placa). Cacheado: o poll da tela
    pergunta de 3 em 3 segundos e a resposta nao muda na sessao."""
    if "tem" in _GPU_CACHE:
        return bool(_GPU_CACHE["tem"]), str(_GPU_CACHE.get("nome") or "")
    tem, nome = False, ""
    smi = _nvidia_smi()
    if smi:
        try:
            r = subprocess.run([smi, "--query-gpu=name",
                                "--format=csv,noheader"],
                               capture_output=True, text=True, timeout=20,
                               **_sem_janela())
            if r.returncode == 0 and (r.stdout or "").strip():
                tem = True
                nome = (r.stdout or "").strip().splitlines()[0].strip()
        except (OSError, subprocess.SubprocessError):
            pass
    if not tem:
        # Sem nvidia-smi ainda pode haver placa NVIDIA — e havendo outra,
        # o nome dela e o que a tela precisa dizer.
        tem, nome_sis = _placa_pelo_sistema()
        nome = nome or nome_sis
    _GPU_CACHE["tem"] = tem
    _GPU_CACHE["nome"] = nome
    return tem, nome


def tem_gpu_nvidia() -> bool:
    return gpu_do_motor()[0]


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
    tem, nome = gpu_do_motor()
    return {
        "instalado": pronto,
        "incompleta": instalacao_incompleta(raiz_projetos),
        "pasta": str(pasta),
        "gpu": tem,
        "gpuNome": nome,
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
    tem_gpu, nome_gpu = gpu_do_motor()
    if not tem_gpu:
        achada = f"encontrei {nome_gpu}" if nome_gpu else "não encontrei placa"
        return False, (f"a IA local precisa de placa NVIDIA — {achada}. "
                       "Na CPU cada trilha levaria uns 9 minutos")
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
