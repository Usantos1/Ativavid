# -*- coding: utf-8 -*-
"""O decode na GPU é pedido pelo NOME, não torcido pelo `-hwaccel`.

`-hwaccel cuda` é um pedido: quando o ffmpeg não consegue usar o NVDEC naquele
fluxo, ele decodifica na CPU e não avisa. Medido numa fonte 4K60 HEVC 10-bit
real do usuário, 20s de decode puro, 7 voltas intercaladas, máquina livre:

    -hwaccel cuda   mediana 59,5s   faixa 42,2-84,6s
    hevc_cuvid      mediana 39,4s   faixa 32,5-60,8s

A mediana do cuvid fica abaixo da melhor volta do `-hwaccel` — é isso que faz o
ganho sobreviver à variância desta máquina, que chega a 2,3x no mesmo trabalho.
A imagem sai bit a bit idêntica (PSNR infinito) e a rotação é preservada.

Isso vale para os dois lugares que decodificam vídeo inteiro: o prep do corte
(`render.prepared_source`) e a detecção de cor.

O QUE NÃO SERVE, e por isso está travado aqui: manter o quadro na GPU com
`-hwaccel_output_format cuda`. O ffmpeg não auto-rotaciona quadro de hardware, e
as fontes de iPhone trazem `rotation=-90` — o vídeo sai deitado, calado. Medido:
1920x1080 onde o caminho certo dá 1920x3414.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))

from ffprobe_util import entrada_nvdec  # noqa: E402
from pipeline.leitura_de_codigo import apenas_codigo  # noqa: E402


def _sonda(codec: str):
    """Finge um ffprobe que devolve esse codec."""
    import json

    return lambda argv: json.dumps({"streams": [{"codec_name": codec}]})


@pytest.mark.parametrize("codec,esperado", [
    ("hevc", "hevc_cuvid"),      # o que o usuário grava
    ("h264", "h264_cuvid"),
    ("vp9", "vp9_cuvid"),
    ("av1", "av1_cuvid"),
])
def test_codec_conhecido_pede_o_decodificador_pelo_nome(codec, esperado):
    assert entrada_nvdec("x.mov", runner=_sonda(codec)) == ["-c:v", esperado]


@pytest.mark.parametrize("codec", ["prores", "mpeg4", "", "codec-inventado"])
def test_codec_sem_nvdec_cai_no_pedido_generico(codec):
    """Sem decodificador dedicado, o comportamento antigo continua valendo."""
    assert entrada_nvdec("x.mov", runner=_sonda(codec)) == ["-hwaccel", "cuda"]


def test_sonda_quebrada_nao_derruba_o_render():
    """ffprobe falhando não pode impedir o vídeo de sair."""
    def explode(argv):
        raise OSError("ffprobe sumiu")

    assert entrada_nvdec("x.mov", runner=explode) == ["-hwaccel", "cuda"]


def test_interruptor_volta_ao_comportamento_antigo(monkeypatch):
    monkeypatch.setenv("ATIVAVID_CUVID", "0")
    assert entrada_nvdec("x.mov", runner=_sonda("hevc")) == ["-hwaccel", "cuda"]


@pytest.mark.parametrize("arquivo", [
    "helpers/render.py",
    "helpers/detect_color.py",
])
def test_os_dois_decodes_usam_o_helper(arquivo):
    """Os dois lugares que decodificam vídeo inteiro precisam ir junto.

    Se um ficar para trás, ele volta a degradar em silêncio — que é
    exatamente o defeito que esta mudança conserta.
    """
    codigo = apenas_codigo(RAIZ / arquivo)
    assert "entrada_nvdec(" in codigo, f"{arquivo} não usa o helper"


@pytest.mark.parametrize("arquivo", [
    "helpers/render.py",
    "helpers/detect_color.py",
])
def test_ninguem_mantem_o_quadro_na_gpu(arquivo):
    """A armadilha: quadro de GPU perde a rotação e o vídeo sai deitado."""
    codigo = apenas_codigo(RAIZ / arquivo)
    assert "hwaccel_output_format" not in codigo, (
        f"{arquivo} mantém o quadro na GPU — as fontes de iPhone têm "
        "rotation=-90 e sairiam deitadas")
