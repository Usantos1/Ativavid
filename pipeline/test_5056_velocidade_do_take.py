# -*- coding: utf-8 -*-
"""5.0.56: velocidade por take — câmera lenta e acelerado, como no CapCut.

"Falta poder acelerar um take, fazer câmera lenta tipo que tem no capcut"
(05/09).

A velocidade muda a DURAÇÃO do trecho, então tudo que mede tempo tem de
concordar: o mapa da linha do tempo (`_naive_spans`), o remapeamento das
legendas (fonte↔saída), a régua do editor (`draftLayout`) e o `-t` do
ffmpeg. Medido num take real: 0,25x/0,5x/1x/2x/4x saem exatamente em
8,00/4,00/2,00/1,00/0,50 s, vídeo e áudio.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app.caption_remap import map_interval, output_to_source, source_to_output  # noqa: E402
from app.timeline_map import (  # noqa: E402
    VELOCIDADES, build_timeline_map, tem_velocidade, velocidade_do_range,
)

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")

EDL = {"ranges": [
    {"source": "S", "start": 0, "end": 4, "beat": "HOOK"},
    {"source": "S", "start": 10, "end": 14, "speed": 0.5, "beat": "B1"},
    {"source": "S", "start": 20, "end": 24, "speed": 2, "beat": "CTA"},
]}


def test_velocidade_so_da_lista():
    assert VELOCIDADES == (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
    for bom in VELOCIDADES:
        assert velocidade_do_range({"speed": bom}) == bom
    for ruim in (0, -1, 0.3, 8, "rapido", None, "", 1e9):
        assert velocidade_do_range({"speed": ruim}) == 1.0, ruim
    assert velocidade_do_range({}) == 1.0


def test_o_mapa_estica_e_encurta():
    m = build_timeline_map(EDL, fps=30)
    spans = m["spans"]
    assert [round(s["outputStart"], 2) for s in spans] == [0.0, 4.0, 12.0]
    assert [round(s["outputEnd"], 2) for s in spans] == [4.0, 12.0, 14.0]
    assert round(m["videoDuration"], 2) == 14.0, "4 + 8 + 2"
    assert [s["speed"] for s in spans] == [1.0, 0.5, 2.0]


def test_legenda_acompanha_a_velocidade():
    # meio do trecho lento: 12s de fonte -> 8s de saida (4 + 4)
    assert round(source_to_output(12, EDL, "S"), 3) == 8.0
    assert output_to_source(8, EDL, "S") == ("S", 12.0)
    # dentro do acelerado: 13s de saida -> 22s de fonte (20 + 1*2)
    assert output_to_source(13, EDL, "S") == ("S", 22.0)
    # um intervalo de 1s de fonte no trecho 0,5x ocupa 2s de saida
    frags = map_interval(11, 12, EDL, "S")
    assert len(frags) == 1
    a, b = frags[0]
    assert round(b - a, 3) == 2.0 and round(a, 3) == 6.0


def test_jcut_antigo_nao_manda_quando_ha_velocidade():
    assert tem_velocidade(EDL["ranges"]) is True
    assert tem_velocidade([{"source": "S", "start": 0, "end": 1}]) is False
    src = (REPO / "app" / "timeline_map.py").read_text(encoding="utf-8")
    i = src.index("spans = (None if tem_velocidade(ranges)")
    assert "spans_from_jcut_timeline" in src[i:i + 200], (
        "com velocidade, a geometria gravada pelo render anterior nao vale mais")


def test_ffmpeg_recebe_setpts_atempo_e_a_duracao_da_saida():
    assert 'vf_parts.append(f"setpts={1.0 / vel:.6f}*PTS")' in RENDER
    i = RENDER.index('if abs(float(speed or 1.0) - 1.0) > 1e-6 and streams != "v":')
    corpo = RENDER[i:i + 700]
    assert 'af_parts.append("atempo=0.5")' in corpo and 'af_parts.append("atempo=2.0")' in corpo, (
        "atempo so aceita 0,5-2 por instancia — 0,25x precisa de dois")
    assert 'af_parts.append(f"atempo={_v:.6f}")' in corpo
    assert "dur_saida = duration / vel" in RENDER
    assert '"-t", f"{dur_saida:.6f}"' in RENDER, (
        "`-t` e opcao de SAIDA: com setpts ele cortava a camera lenta")
    assert "fade_out_start = max(0.0, dur_saida - 0.03)" in RENDER
    assert RENDER.count("speed=vel") == 3, "os dois lacos (video, audio e o normal)"


def test_o_editor_mostra_e_manda_a_velocidade():
    assert "const VELOCIDADES_DO_TAKE = [" in PJS
    for v in ("0,25x", "0,5x", "1,5x", "2x", "4x"):
        assert f"'{v}'" in PJS, v
    i = PJS.index("function camposDoTake(r)")
    assert "out.speed = +r.speed" in PJS[i:i + 400]
    j = PJS.index("function draftLayout()")
    corpo = PJS[j:j + 900]
    assert "const vel = +(r.speed || 1) || 1;" in corpo
    assert "(r.end - r.start) / vel" in corpo, "a regua tem de esticar junto"
    k = PJS.index("function edlDirty()")
    assert "+(r.speed || 1) !== +(r.orig.speed || 1)" in PJS[k:k + 500]


def test_herda_e_compara_no_apply():
    from app import quick_corrections as qc

    assert "speed" in qc._HERDAVEIS
    base = {"source": "S", "start": 0, "end": 2}
    assert qc._norm_range(base) != qc._norm_range(dict(base, speed=0.5))
    assert qc._norm_range(base) == qc._norm_range(dict(base, speed=1))


@pytest.mark.parametrize("vel,esperado", [(0.5, 4.0), (2.0, 1.0)])
def test_conta_da_duracao(vel, esperado):
    m = build_timeline_map({"ranges": [{"source": "S", "start": 0, "end": 2, "speed": vel}]}, fps=30)
    assert round(m["videoDuration"], 3) == esperado
