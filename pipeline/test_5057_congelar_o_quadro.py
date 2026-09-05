# -*- coding: utf-8 -*-
"""5.0.57: congelar o último quadro do take (o "congelar" do CapCut).

Usado para carimbar um número, uma seta, uma reação: o take termina e a
imagem fica parada por um instante. Teto de 5 s — acima disso é um cartão,
não um efeito de corte.

A cauda congelada soma tempo ao trecho, então o mapa, a régua do editor e
o `-t` do ffmpeg concordam. Dentro dela o tempo de FONTE não anda: tudo ali
é o mesmo último quadro, e o remapeamento das legendas precisa saber disso.

Medido num take real (2 s de fonte, draft): 1x+1s → 3,00 s; 0,5x+0,5s →
4,50 s; 2x+1s → 2,00 s. Vídeo e áudio na mesma duração.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app.caption_remap import output_to_source  # noqa: E402
from app.timeline_map import (  # noqa: E402
    CONGELAR_MAX, build_timeline_map, congelar_do_range, tem_velocidade,
)

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")

EDL = {"ranges": [
    {"source": "S", "start": 0, "end": 2, "freeze": 1},
    {"source": "S", "start": 10, "end": 12, "speed": 0.5, "freeze": 0.5},
]}


def test_valor_de_congelar_e_limitado():
    assert congelar_do_range({"freeze": 1.5}) == 1.5
    assert congelar_do_range({"freeze": 99}) == CONGELAR_MAX == 5.0
    for ruim in (-1, "muito", None, "", {}):
        assert congelar_do_range({"freeze": ruim}) == 0.0, ruim
    assert congelar_do_range({}) == 0.0


def test_o_mapa_soma_a_cauda():
    m = build_timeline_map(EDL, fps=30)
    a, b = m["spans"]
    assert (round(a["outputStart"], 2), round(a["outputEnd"], 2)) == (0.0, 3.0)
    assert (round(b["outputStart"], 2), round(b["outputEnd"], 2)) == (3.0, 7.5)
    assert round(m["videoDuration"], 2) == 7.5, "2+1 e 4+0,5"
    assert a["freeze"] == 1.0 and b["freeze"] == 0.5


def test_dentro_do_congelado_a_fonte_nao_anda():
    # 2,5 s de saida esta na cauda do primeiro take: a fonte parou em 2,0
    assert output_to_source(2.5, EDL, "S") == ("S", 2.0)
    assert output_to_source(1.0, EDL, "S") == ("S", 1.0), "antes da cauda anda normal"


def test_congelar_conta_como_geometria_nova():
    assert tem_velocidade([{"start": 0, "end": 1, "freeze": 1}]) is True, (
        "o jcut_timeline do render anterior nao descreve mais este take")


def test_ffmpeg_congela_video_e_completa_o_audio():
    assert 'vf_parts.append(f"tpad=stop_mode=clone:stop_duration={cong:.3f}")' in RENDER
    assert 'af_parts.append(f"apad=pad_dur={cong:.3f}")' in RENDER, (
        "sem o silencio, o audio acaba antes do video congelado")
    assert "dur_saida = (duration / vel if vel > 0 else duration) + cong" in RENDER
    i = RENDER.index("if cong > 0.001 and streams != \"a\":")
    j = RENDER.index("setpts=", max(0, i - 700))
    assert j < i, "o tpad vem DEPOIS do setpts — congelar 1s e 1s de video pronto"
    assert RENDER.count("freeze=cong") == 3, "os dois lacos (normal, video e audio do J-cut)"


def test_o_editor_oferece_e_manda():
    assert "'Congelar fim'" in PJS
    for rotulo in ("'0,5s'", "'1s'", "'2s'"):
        assert rotulo in PJS, rotulo
    i = PJS.index("function camposDoTake(r)")
    assert "out.freeze = +(+r.freeze).toFixed(2)" in PJS[i:i + 500]
    j = PJS.index("function draftLayout()")
    assert "+ (+(r.freeze || 0) || 0)" in PJS[j:j + 900], "a regua soma a cauda"
    k = PJS.index("function edlDirty()")
    assert "+(r.freeze || 0) !== +(r.orig.freeze || 0)" in PJS[k:k + 600]


def test_herda_no_apply():
    from app import quick_corrections as qc

    assert "freeze" in qc._HERDAVEIS
    base = {"source": "S", "start": 0, "end": 2}
    assert qc._norm_range(base) != qc._norm_range(dict(base, freeze=1))


@pytest.mark.parametrize("vel,cong,esperado", [(1.0, 1.0, 3.0), (0.5, 0.5, 4.5), (2.0, 1.0, 2.0)])
def test_conta_da_duracao_com_velocidade(vel, cong, esperado):
    m = build_timeline_map(
        {"ranges": [{"source": "S", "start": 0, "end": 2, "speed": vel, "freeze": cong}]}, fps=30)
    assert round(m["videoDuration"], 3) == esperado
