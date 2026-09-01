# -*- coding: utf-8 -*-
"""Primeiros testes de watch_edits e media_probe — zero cobertura até 31/08.

`watch_edits.py` é o daemon que transforma as marcações do preview em
pedido de correção: se ele quebrar, a correção que o usuário marcou
"não acontece" em silêncio — defeito que ele já viveu (a memória manda
checar `ps aux | grep watch_edits` antes de qualquer outra coisa).

`media_probe.py` lê o vídeo-fonte; é a base que já teve o bug do stream
group (ffprobe imprimindo o mesmo stream duas vezes).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "helpers") not in sys.path:
    sys.path.insert(0, str(REPO / "helpers"))

import watch_edits as we  # noqa: E402
from app.media_probe import probe_video  # noqa: E402


# ---------------------------------------------------------------- watch_edits

def test_digest_descreve_as_marcacoes(tmp_path):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({
        "savedAt": "2026-08-31T20:00:00",
        "notes": [{"start": 2.0, "end": 5.5, "phase": 2,
                   "text": "legenda errada, devia ser Película"}],
        "edl": {"changes": [{"i": 0}], "removed": []},
    }), encoding="utf-8")
    d = we.digest(p)
    assert "1 marcação(ões)" in d and "1 take(s) reajustado(s)" in d
    assert "legenda errada, devia ser Película" in d
    assert "Aplique-os" in d


def test_digest_de_arquivo_quebrado_pede_para_salvar_de_novo(tmp_path):
    """JSON truncado (processo morto no meio do save) não pode derrubar o
    daemon — vira recado recuperável."""
    p = tmp_path / "preview_edits.json"
    p.write_text('{"notes": [', encoding="utf-8")
    d = we.digest(p)
    assert "ilegível" in d and "salvar de novo" in d


def test_singleton_impede_dois_daemons(tmp_path):
    """Dois watch_edits no mesmo root aplicariam a mesma correção duas
    vezes (a família do 'segundo Worker rouba a fila'). O MESMO processo
    re-adquirir é permitido de propósito — o dono de outro PID vivo, não."""
    import os

    (tmp_path / ".watch_edits.pid").write_text(str(os.getppid()),
                                               encoding="utf-8")
    assert we.acquire_singleton(tmp_path) is None, \
        "PID vivo de OUTRO processo tinha de barrar"
    assert we.acquire_singleton.__doc__  # o contrato mora na docstring


def test_singleton_recupera_lock_de_processo_morto(tmp_path):
    (tmp_path / ".watch_edits.pid").write_text("999999999", encoding="utf-8")
    assert we.acquire_singleton(tmp_path) is not None, \
        "lock de PID morto não pode prender o daemon para sempre"


# ---------------------------------------------------------------- media_probe

@pytest.fixture(scope="module")
def clipe(tmp_path_factory):
    """29,97 fps de VERDADE (30000/1001) — o parque dele é 29,97 e nenhum
    teste da suíte exercitava a fração."""
    import shutil

    if not shutil.which("ffmpeg"):
        pytest.skip("sem ffmpeg")
    f = tmp_path_factory.mktemp("probe") / "fonte.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30000/1001:duration=1",
         "-c:v", "libx264", "-preset", "ultrafast", str(f)],
        check=True, capture_output=True, timeout=120)
    return f


def test_probe_le_o_29_97(clipe):
    d = probe_video(clipe)
    assert d["ok"] is True
    assert abs(d["fps"] - 29.97) < 0.01, d["fps"]
    assert d["width"] == 320 and d["height"] == 240
    assert 0.9 < d["durationSec"] < 1.2


def test_probe_de_arquivo_inexistente_nao_explode(tmp_path):
    d = probe_video(tmp_path / "nao-existe.mp4")
    assert d["ok"] is False and "não encontrado" in d["error"]
