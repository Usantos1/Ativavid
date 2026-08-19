# -*- coding: utf-8 -*-
"""ffprobe repete o stream quando o arquivo tem stream group.

Defeito real, v2.19: dois vídeos de câmera do usuário falharam com
`could not convert string to float: '1\\n24/1'`. O ffprobe 9 imprime o bloco
do stream DUAS vezes — uma dentro de [STREAM_GROUP] e outra solta — e o
`noprint_wrappers=1` tira só os marcadores. Quem lia a saída como um valor
único quebrava (ou, pior, respondia errado em silêncio).

As saídas abaixo são as que o ffprobe 9.0 realmente devolveu nos arquivos do
usuário.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "helpers"))

from ffprobe_util import (  # noqa: E402
    all_records,
    first_record,
    fps_of,
    parse_rate,
    size_of,
)

# saída medida em A001_08191420_C007.mov (câmera, com stream group)
CAMERA_FPS = "24/1\n24/1\n"
CAMERA_WH_CSV = "1080,1920\n1080,1920\n"
CAMERA_FRAMES = "899\n899\n"
# saída medida em IMG_3987.mov (iPhone, sem stream group)
IPHONE_FPS = "30/1\n"


# ------------------------------------------------- o que quebrava em produção
def test_o_parse_antigo_de_fps_quebrava():
    """Prova o defeito: era exatamente este split que derrubava o vídeo."""
    out = CAMERA_FPS.strip()
    a, b = out.split("/", 1)
    assert b == "1\n24/1", "esta é a string que apareceu no erro do usuário"
    try:
        float(b)
        raise AssertionError("deveria ter falhado")
    except ValueError as e:
        # a mensagem traz a string em repr — foi assim que apareceu na fila
        assert repr(b) in str(e)


def test_fps_de_arquivo_com_stream_group():
    assert parse_rate(first_record(CAMERA_FPS), default=30.0) == 24.0


def test_fps_de_arquivo_sem_stream_group_continua_igual():
    assert parse_rate(first_record(IPHONE_FPS), default=30.0) == 30.0


def test_largura_e_altura_nao_colam_com_a_repeticao():
    partes = first_record(CAMERA_WH_CSV).split(",")
    assert [int(partes[0]), int(partes[1])] == [1080, 1920]


def test_contagem_de_frames_nao_vira_zero():
    """Antes dava int('899\\n899') -> ValueError -> 0 frames em silêncio."""
    assert int(first_record(CAMERA_FRAMES)) == 899


# ------------------------------------------------------------------- parse
def test_parse_rate_aceita_fracao_e_inteiro():
    assert parse_rate("30000/1001") == 30000 / 1001
    assert parse_rate("24") == 24.0


def test_parse_rate_devolve_padrao_no_que_nao_da_para_ler():
    for ruim in ("", "   ", "N/A", "0/0", None):
        assert parse_rate(ruim, default=30.0) == 30.0


def test_parse_rate_come_a_repeticao_sozinho():
    assert parse_rate(CAMERA_FPS, default=0.0) == 24.0


def test_first_record_ignora_linha_vazia_no_comeco():
    assert first_record("\n\n24/1\n24/1\n") == "24/1"


def test_all_records_corta_as_repeticoes():
    saida = "yuv420p\ntv\nbt709\nyuv420p\ntv\nbt709\n"
    assert all_records(saida, 3) == ["yuv420p", "tv", "bt709"]


# ------------------------------------------------- sonda em JSON (a definitiva)
def _runner_falso(saida: str):
    return lambda argv: saida


def test_sonda_json_nao_repete():
    saida = '{"streams":[{"r_frame_rate":"24/1","width":1080,"height":1920}]}'
    assert fps_of("x.mov", runner=_runner_falso(saida)) == 24.0
    assert size_of("x.mov", runner=_runner_falso(saida)) == (1080, 1920)


def test_sonda_json_sem_stream_devolve_padrao():
    assert fps_of("x.mov", default=30.0, runner=_runner_falso('{"streams":[]}')) == 30.0
    assert size_of("x.mov", runner=_runner_falso('{"streams":[]}')) == (0, 0)


def test_sonda_json_com_saida_invalida_nao_levanta():
    assert fps_of("x.mov", default=30.0, runner=_runner_falso("nao e json")) == 30.0


# ------------------------------------ o pipeline usa mesmo a leitura corrigida
def test_run_fast_le_fps_pela_regra_nova():
    from pipeline import run_fast as rf

    chamadas = []

    class _Saida:
        stdout = CAMERA_FPS

    rf_run = rf._run_tool
    try:
        rf._run_tool = lambda *a, **k: (chamadas.append(a) or _Saida())
        assert rf._ffprobe_fps(Path("camera.mov")) == 24.0
    finally:
        rf._run_tool = rf_run


def test_render_le_fps_pela_regra_nova():
    import render

    class _Saida:
        stdout = CAMERA_FPS

    orig = render._run
    try:
        render._run = lambda *a, **k: _Saida()
        render.source_fps.cache_clear() if hasattr(render.source_fps, "cache_clear") else None
        assert render.parse_rate(render.first_record(CAMERA_FPS)) == 24.0
    finally:
        render._run = orig
