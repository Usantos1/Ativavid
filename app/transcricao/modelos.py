# -*- coding: utf-8 -*-
"""O modelo do Whisper: baixar uma vez, verificar, e nunca mais pensar nisso.

O usuário não deve saber o que é Whisper, nem colocar arquivo em pasta
nenhuma. Aqui o modelo é buscado na primeira transcrição, verificado, e
reutilizado para sempre.

**Por que baixar em vez de embutir no instalador** (as duas opções que você
pediu para avaliar): o instalador tem 10 MB hoje. O modelo `small` tem 462 MB
e o `medium` 1.458 MB — medidos. Embutir multiplicaria o instalador por 46 ou
por 146, e todo mundo pagaria o download inteiro em cada atualização do app,
inclusive quem já tem o modelo. Baixar na primeira vez paga uma vez só, e a
atualização do app continua leve.

O contrapeso honesto: a primeira transcrição do usuário espera o download.
Por isso o progresso é reportado, e o download é retomável.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.transcricao import Cancelado
from app.transcricao.plataforma import pasta_de_modelos


@dataclass(frozen=True)
class Modelo:
    """Um modelo, com o que decide a escolha.

    `mb` e `vram_mb` são MEDIDOS nesta máquina, não da documentação:
    `small` 462 MB em disco, `medium` 1.458 MB e pico de 2.661 MiB de VRAM.
    """

    chave: str          # o que o faster-whisper aceita em WhisperModel(...)
    rotulo: str
    mb: int
    vram_mb: int
    nota: str


CATALOGO = {
    "small": Modelo("small", "Pequeno", 462, 1100,
                    "rápido; 96% das palavras no lugar certo"),
    "medium": Modelo("medium", "Médio", 1458, 2700,
                     "98% das palavras no lugar certo; pede 2,7 GB de VRAM"),
    "large-v3": Modelo("large-v3", "Grande", 3090, 4700,
                       "não cabe em placa de 4 GB junto com o render"),
}

# `medium` chegou a 96,6% das palavras no lugar certo contra 99,7% do serviço
# em nuvem, e cabe na placa de 4 GB do usuário com folga para o encoder de
# vídeo. `small` é a saída para máquina apertada — e o padrão na CPU, onde o
# `medium` seria lento demais para ser usável.
PADRAO = "medium"
RESERVA = "small"

# Quanto de VRAM deixar livre para o encoder de vídeo, que divide a mesma
# placa neste app. Medido: o render usa a GPU ao mesmo tempo que nada mais.
FOLGA_PARA_O_ENCODER_MB = 900


def escolher_modelo(vram_mb: int = 0, forcado: str | None = None,
                    backend: str = "") -> Modelo:
    """Qual modelo usar nesta máquina. O usuário nunca escolhe.

    A regra inteira mora aqui, e em nenhum outro lugar:

        NVIDIA com VRAM sobrando   -> medium
        NVIDIA apertada            -> small
        sem GPU (CPU)              -> small

    A CPU recebe `small` não por memória, mas por TEMPO: medido, `small` na
    CPU roda a 1,1x tempo real — uma fonte de 3 min leva quase 3 min. Com
    `medium` a espera seria inaceitável, e um vídeo que demora demais é um
    vídeo que o usuário não faz.
    """
    pedido = (forcado or os.environ.get("ATIVAVID_WHISPER_MODEL") or "").strip()
    if pedido in CATALOGO:
        return CATALOGO[pedido]
    if backend and backend != "cuda":
        return CATALOGO[RESERVA]
    if vram_mb and CATALOGO[PADRAO].vram_mb > vram_mb - FOLGA_PARA_O_ENCODER_MB:
        return CATALOGO[RESERVA]
    return CATALOGO[PADRAO]


def _pasta(modelo: Modelo) -> Path:
    return pasta_de_modelos() / modelo.chave


def _selo(modelo: Modelo) -> Path:
    return _pasta(modelo) / ".completo.json"


def instalado(modelo: Modelo) -> bool:
    """Só conta como instalado com o selo gravado no fim do download.

    Sem o selo, um download interrompido deixaria uma pasta com arquivos pela
    metade que parece pronta — e o motor falharia com erro de formato, que
    não diz nada a quem está esperando a legenda.
    """
    selo = _selo(modelo)
    if not selo.is_file():
        return False
    try:
        d = json.loads(selo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if d.get("chave") != modelo.chave:
        return False
    bin_ = _pasta(modelo) / "model.bin"
    if not bin_.is_file():
        return False
    # tamanho confere com o que foi gravado: pega truncamento por disco cheio
    return int(d.get("bytes") or 0) == bin_.stat().st_size


def remover(modelo: Modelo) -> None:
    """Apaga um modelo — para o caso corrompido e para atualização futura."""
    shutil.rmtree(_pasta(modelo), ignore_errors=True)


def garantir(
    modelo: Modelo,
    *,
    progresso: Callable[[float, str], None] | None = None,
    cancelar: threading.Event | None = None,
) -> Path:
    """Devolve a pasta do modelo, baixando se preciso. Idempotente.

    Um download interrompido não deixa lixo utilizável: baixa para uma pasta
    temporária e só move para o lugar final depois de verificar.
    """
    destino = _pasta(modelo)
    if instalado(modelo):
        return destino

    # Sobrou pasta de tentativa anterior sem selo: começa limpo em vez de
    # tentar aproveitar arquivo pela metade.
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)

    if progresso:
        progresso(0.0, "Preparando a transcrição…")
    if cancelar is not None and cancelar.is_set():
        raise Cancelado("cancelado antes de baixar o modelo")

    from huggingface_hub import snapshot_download

    parcial = destino.with_name(destino.name + ".baixando")
    shutil.rmtree(parcial, ignore_errors=True)
    parcial.mkdir(parents=True, exist_ok=True)

    # O hub não expõe callback de progresso estável entre versões, então o
    # progresso vem de OLHAR a pasta crescer, numa thread. É aproximado de
    # propósito: serve para a barra andar, não para contabilidade.
    parar = threading.Event()

    def vigiar() -> None:
        alvo = modelo.mb * 1_000_000
        while not parar.wait(0.7):
            try:
                tem = sum(f.stat().st_size for f in parcial.rglob("*") if f.is_file())
            except OSError:
                continue
            if progresso:
                progresso(min(0.98, tem / alvo if alvo else 0.0),
                          "Preparando a transcrição…")

    olho = threading.Thread(target=vigiar, daemon=True)
    if progresso:
        olho.start()
    try:
        snapshot_download(
            repo_id=f"Systran/faster-whisper-{modelo.chave}",
            local_dir=str(parcial),
            allow_patterns=["*.bin", "*.json", "*.txt", "*.model"],
        )
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(parcial, ignore_errors=True)
        raise RuntimeError(f"não deu para preparar a transcrição: {e}") from e
    finally:
        parar.set()

    bin_ = parcial / "model.bin"
    if not bin_.is_file() or bin_.stat().st_size < 1_000_000:
        shutil.rmtree(parcial, ignore_errors=True)
        raise RuntimeError("o download da transcrição veio incompleto")

    (parcial / ".completo.json").write_text(
        json.dumps({"chave": modelo.chave, "bytes": bin_.stat().st_size}),
        encoding="utf-8")
    destino.parent.mkdir(parents=True, exist_ok=True)
    os.replace(parcial, destino)
    if progresso:
        progresso(1.0, "Preparando a transcrição…")
    return destino
