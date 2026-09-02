# -*- coding: utf-8 -*-
"""A legenda do vídeo longo aparece — no editor E queimada no vídeo.

Pedido de 02/09 ("cade a legenda?"): o longform entregava só o .srt para o
CC do YouTube e o editor ficava sem a faixa. Decisão dele: queimar no
vídeo (estilo 16:9, embaixo, centralizada), mantendo o .srt. A fonte é o
captions.json — o mesmo arquivo que o editor corrige, então conserto de
texto vale para o vídeo e para o .srt.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO, REPO / "helpers"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from compose_longform import (  # noqa: E402
    _paginas_de_legenda,
    _t_ass,
    compor_longform,
)


def _palavra(texto: str, ini_ms: int, fim_ms: int) -> dict:
    return {"text": texto, "startMs": ini_ms, "endMs": fim_ms,
            "timestampMs": (ini_ms + fim_ms) // 2}


def test_paginas_quebram_em_pontuacao_e_pausa():
    palavras = [
        _palavra("Essa", 0, 200), _palavra("é", 200, 300),
        _palavra("a", 300, 400), _palavra("ferramenta.", 400, 900),
        _palavra("Dá", 1000, 1200), _palavra("uma", 1200, 1400),
        _palavra("olhada", 1400, 1800),
        # pausa de 1,5s força página nova mesmo sem pontuação
        _palavra("agora", 3300, 3700),
    ]
    pgs = _paginas_de_legenda(palavras)
    assert [p["texto"] for p in pgs] == [
        "Essa é a ferramenta.", "Dá uma olhada", "agora"]
    assert pgs[0]["t0"] == 0.0 and abs(pgs[0]["t1"] - 0.9) < 1e-6


def test_tempo_ass_e_centesimal():
    assert _t_ass(0.0) == "0:00:00.00"
    assert _t_ass(61.23) == "0:01:01.23"
    assert _t_ass(3600.5) == "1:00:00.50"


def test_legenda_queimada_no_video(tmp_path):
    """E2E: com captions.json no public, o quadro dentro da janela da
    legenda tem texto branco no terço de baixo; fora dela, não."""
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30:d=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(public / "cut.mp4")],
        check=True, capture_output=True)
    (public / "captions.json").write_text(json.dumps([
        _palavra("LEGENDA", 1000, 2000), _palavra("NO", 2000, 2500),
        _palavra("LONGO", 2500, 3400),
    ]), encoding="utf-8")
    ed = {"width": 1280, "height": 720, "fps": 30.0, "durationSec": 6.0,
          "accent": "#ff0004", "broll": [], "lowerThirds": [],
          "chapters": [], "callouts": [],
          "soundtrack": {"enabled": False, "file": "", "volume": 0.1}}
    saida = edit / "final.mp4"
    compor_longform(edit, public, ed, saida)
    assert saida.exists()
    # o .srt sai das MESMAS páginas
    srt = (edit / "captions.srt").read_text(encoding="utf-8")
    assert "LEGENDA NO LONGO" in srt and "00:00:01,000" in srt

    def _brancos(t: float, nome: str) -> int:
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t}", "-i", str(saida),
                        "-frames:v", "1", str(tmp_path / nome)],
                       check=True, capture_output=True)
        px = np.asarray(Image.open(tmp_path / nome).convert("RGB"))
        reg = px[480:720, :]
        return int(((reg > 200).all(axis=2)).sum())

    assert _brancos(2.0, "on.png") > 300, "a legenda não foi queimada"
    assert _brancos(5.0, "off.png") < 30, "a legenda vazou da janela dela"


def test_o_pipeline_gera_captions_json_no_longform():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = rf.index('"captions_srt.py"')
    bloco = rf[i:i + 1400]
    assert "captions_for_remotion.py" in bloco, \
        "o longform voltou a escrever captions.json vazio"
    # o "[]" só entra como RESERVA quando o gerador falhou
    i_vazio = bloco.split("caption-cues")[0].find('.write_text("[]"')
    if i_vazio >= 0:
        assert 'if not (public / "captions.json").exists()' in bloco[:i_vazio]
