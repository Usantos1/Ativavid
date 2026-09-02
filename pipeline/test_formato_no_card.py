# -*- coding: utf-8 -*-
"""O card diz o formato DO JOB, não "9:16" para todo mundo.

Caso real de 02/09: vídeo de YouTube (fonte 1920x1080, exportPreset=
youtube) apareceu na Fila com "9:16" ao lado da duração. O rótulo era um
chumbo da tela; agora o backend calcula `formatLabel` do preset usado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.jobs_view import _formato_do_video  # noqa: E402


def _com_preset(tmp_path: Path, exp: str) -> dict:
    (tmp_path / "preset-used.json").write_text(
        json.dumps({"exportPreset": exp}), encoding="utf-8")
    job: dict = {}
    _formato_do_video(job, tmp_path)
    return job


def test_youtube_vira_16_9(tmp_path):
    assert _com_preset(tmp_path, "youtube")["formatLabel"] == "16:9"


def test_reels_segue_9_16(tmp_path):
    assert _com_preset(tmp_path, "reels")["formatLabel"] == "9:16"


def test_quadrado_e_feed(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _com_preset(tmp_path / "a", "square")["formatLabel"] == "1:1"
    assert _com_preset(tmp_path / "b", "feed")["formatLabel"] == "4:5"


def test_na_fila_ainda_sem_preset_usado_le_o_do_job(tmp_path):
    """Antes do render começar não existe preset-used.json — o job da fila
    carrega o preset pedido."""
    job = {"preset": {"exportPreset": "youtube"}}
    _formato_do_video(job, tmp_path)
    assert job.get("formatLabel") == "16:9"


def test_sem_dado_nenhum_nao_inventa(tmp_path):
    """Projeto velho sem nada: o backend fica calado e a tela usa o
    fallback legado (a maioria histórica é 9:16 de verdade)."""
    job: dict = {}
    _formato_do_video(job, tmp_path)
    assert "formatLabel" not in job


def test_a_tela_usa_o_rotulo_do_backend():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert js.count("j.formatLabel ||") >= 3, "a tela parou de ler o backend"
    # o placeholder da miniatura tambem segue o formato do job
    assert '${fmt || "9:16"}' in js
