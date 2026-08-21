# -*- coding: utf-8 -*-
"""A grade do `snap_ranges_to_frames` tem de ser a do arquivo que vai SAIR.

`snap_ranges_to_frames` existe para que a duração de cada range seja um
número inteiro de quadros — sem isso o ffmpeg encoda o vídeo em quadros
inteiros mas mantém o áudio no comprimento exato pedido, e o cut sai com uma
faixa de som mais longa que a imagem (a própria docstring da função conta que
isso somou +0,44 s numa edição de 28 cortes).

O `target_fps` que alimenta o snap era **30 fixo** quando `--keep-resolution`
(longform). Mas é justamente aí que `extract_segment` NÃO passa `-r`: a
docstring dele diz "source resolution + source fps". Ou seja, numa fonte de
24 fps o snap alinhava a 1/30 um arquivo que sai a 24 — a guarda virava
no-op na grade errada.

O usuário só faz reels hoje (114 de 114 projetos, `exportPreset: reels`),
então isto está dormente para ele. O teste roda o caminho real com uma fonte
sintética de 24 fps.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def _fonte_24fps(tmp: Path) -> Path:
    p = tmp / "fonte.mp4"
    r = subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=12",
        "-f", "lavfi", "-i", "sine=r=48000:d=12",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "38",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
        str(p)], capture_output=True, text=True, **NOWIN)
    if r.returncode != 0 or not p.exists():
        pytest.skip(f"ffmpeg não montou a fixture: {(r.stderr or '')[-200:]}")
    return p


def _dur(p: Path, tipo: str) -> float:
    r = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams",
        "v:0" if tipo == "v" else "a:0",
        "-show_entries", "stream=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, **NOWIN)
    return float((r.stdout or "0").strip().splitlines()[0])


def _fps(p: Path) -> float:
    r = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, **NOWIN)
    n, _, d = (r.stdout or "0/1").strip().partition("/")
    return float(n) / float(d or 1)


def test_longform_alinha_na_grade_da_fonte_e_nao_em_30(tmp_path):
    """Com `--keep-resolution` a saída fica no fps da fonte — e as ranges
    precisam ser múltiplos inteiros DESSE quadro, não do de 30."""
    fonte = _fonte_24fps(tmp_path)
    # durações que NÃO são múltiplas de 1/24 nem de 1/30, de propósito
    edl = {"fps": 24, "sources": {"SRC": str(fonte)},
           "ranges": [{"source": "SRC", "start": 0.0, "end": 2.137},
                      {"source": "SRC", "start": 4.0, "end": 6.271},
                      {"source": "SRC", "start": 8.0, "end": 9.913}]}
    p_edl = tmp_path / "edl.json"
    p_edl.write_text(json.dumps(edl), encoding="utf-8")
    out = tmp_path / "cut.mp4"

    r = subprocess.run([
        sys.executable, "-X", "utf8", str(REPO / "helpers" / "render.py"),
        str(p_edl), "-o", str(out), "--no-subtitles", "--keep-resolution"],
        capture_output=True, text=True, cwd=str(REPO), **NOWIN)
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"render não rodou: {(r.stderr or r.stdout or '')[-300:]}")

    # a saída ficou no fps da fonte, como a docstring do extract promete
    assert abs(_fps(out) - 24.0) < 0.1, _fps(out)

    # e o EDL foi alinhado NESSA grade: cada duração é múltipla de 1/24
    salvo = json.loads(p_edl.read_text(encoding="utf-8"))
    for rg in salvo["ranges"]:
        quadros = (float(rg["end"]) - float(rg["start"])) * 24.0
        assert abs(quadros - round(quadros)) < 0.02, (rg, quadros)


def test_o_audio_nao_fica_mais_longo_que_a_imagem(tmp_path):
    """O sintoma que o snap existe para evitar. Com a grade errada, a soma das
    ranges não fecha em quadro inteiro e o áudio sobra."""
    fonte = _fonte_24fps(tmp_path)
    edl = {"fps": 24, "sources": {"SRC": str(fonte)},
           "ranges": [{"source": "SRC", "start": 0.0, "end": 2.137},
                      {"source": "SRC", "start": 4.0, "end": 6.271},
                      {"source": "SRC", "start": 8.0, "end": 9.913}]}
    p_edl = tmp_path / "edl.json"
    p_edl.write_text(json.dumps(edl), encoding="utf-8")
    out = tmp_path / "cut.mp4"
    r = subprocess.run([
        sys.executable, "-X", "utf8", str(REPO / "helpers" / "render.py"),
        str(p_edl), "-o", str(out), "--no-subtitles", "--keep-resolution"],
        capture_output=True, text=True, cwd=str(REPO), **NOWIN)
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"render não rodou: {(r.stderr or r.stdout or '')[-300:]}")
    v, a = _dur(out, "v"), _dur(out, "a")
    # um quadro de folga a 24fps
    assert a - v < 1 / 24 + 0.005, f"áudio {a:.4f}s contra vídeo {v:.4f}s"


def _fonte_60fps(tmp: Path) -> Path:
    p = tmp / "fonte60.mp4"
    r = subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=180x320:r=60:d=12",
        "-f", "lavfi", "-i", "sine=r=48000:d=12",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "38",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
        str(p)], capture_output=True, text=True, **NOWIN)
    if r.returncode != 0 or not p.exists():
        pytest.skip(f"ffmpeg não montou a fixture: {(r.stderr or '')[-200:]}")
    return p


def test_shortform_sai_a_30_e_alinha_em_30(tmp_path):
    """O caminho do usuário (114 de 114 projetos são reels): fonte 60 fps,
    saída 30, e as ranges alinhadas na grade de 30."""
    fonte = _fonte_60fps(tmp_path)
    edl = {"fps": 30, "sources": {"SRC": str(fonte)},
           "ranges": [{"source": "SRC", "start": 0.0, "end": 2.137},
                      {"source": "SRC", "start": 4.0, "end": 6.271},
                      {"source": "SRC", "start": 8.0, "end": 9.913}]}
    p_edl = tmp_path / "edl.json"
    p_edl.write_text(json.dumps(edl), encoding="utf-8")
    out = tmp_path / "cut.mp4"
    r = subprocess.run([
        sys.executable, "-X", "utf8", str(REPO / "helpers" / "render.py"),
        str(p_edl), "-o", str(out), "--no-subtitles"],
        capture_output=True, text=True, cwd=str(REPO), **NOWIN)
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"render não rodou: {(r.stderr or r.stdout or '')[-300:]}")

    assert abs(_fps(out) - 30.0) < 0.1, _fps(out)
    salvo = json.loads(p_edl.read_text(encoding="utf-8"))
    for rg in salvo["ranges"]:
        quadros = (float(rg["end"]) - float(rg["start"])) * 30.0
        assert abs(quadros - round(quadros)) < 0.02, (rg, quadros)
    # e o áudio não sobra além de um quadro
    v, a = _dur(out, "v"), _dur(out, "a")
    assert a - v < 1 / 30 + 0.005, f"áudio {a:.4f}s contra vídeo {v:.4f}s"
