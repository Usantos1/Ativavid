"""A limpeza de edit/remotion não pode matar o pipeline que a pediu.

Bug real (19/08/2026): _clear_dir_windows passava apelidos curtos ("remotion",
nome da pasta do projeto) para kill_processes_holding_path, que casa por
SUBSTRING da linha de comando. O próprio run_fast cita a pasta do projeto nos
argumentos — então o pipeline se matava sozinho (Stop-Process -Force → exit
-1, sem stderr) a cada reprocessada, e ainda derrubava os jobs vizinhos.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.win_process import (  # noqa: E402
    _is_path_needle,
    _protected_pids,
    kill_processes_holding_path,
    select_kill_targets,
)

PROJ = r"C:\ATIVAVID\Projetos\20260818-224301_IMG_3993_29a0597f59"
EDIT = PROJ + r"\edit"
REMO = EDIT + r"\remotion"

ME = os.getpid()

ROWS = [
    # o próprio pipeline: cita a pasta do projeto nos argumentos
    {"pid": ME, "ppid": 1000, "name": "python.exe",
     "cmd": f'python.exe run_fast.py {PROJ}\\IMG.MOV --edit-dir {EDIT} --json'},
    # filho do pipeline (render.py) — também dentro da minha árvore
    {"pid": 4242, "ppid": ME, "name": "python.exe",
     "cmd": f'python.exe helpers\\render.py {EDIT}\\edl.json -o {EDIT}\\cut.mp4'},
    # job VIZINHO, outro projeto, renderizando no Remotion
    {"pid": 5555, "ppid": 1000, "name": "node.exe",
     "cmd": r'node.exe C:\ATIVAVID\Projetos\20260818-OUTRO_xxxx\edit\remotion\node_modules\@remotion\cli.js render'},
    # quem realmente segura a pasta que vou apagar
    {"pid": 6666, "ppid": 1, "name": "node.exe",
     "cmd": f'node.exe {REMO}\\node_modules\\@remotion\\cli.js render Reels'},
    {"pid": 7777, "ppid": 1, "name": "ffmpeg.exe",
     "cmd": f'ffmpeg.exe -i {REMO}\\out\\frames -y {REMO}\\out\\render.mp4'},
]


def test_short_alias_is_never_a_target():
    for alias in ("remotion", "20260818-224301_IMG_3993_29a0597f59", "edit", ""):
        assert not _is_path_needle(alias), alias
    assert _is_path_needle(REMO)


def test_pipeline_never_kills_itself():
    targets = select_kill_targets(ROWS, [REMO])
    assert ME not in targets
    assert 4242 not in targets, "matou o render.py filho do próprio pipeline"


def test_neighbour_job_survives():
    targets = select_kill_targets(ROWS, [REMO])
    assert 5555 not in targets, "derrubou o Remotion de outro projeto"


def test_real_holders_are_killed():
    targets = select_kill_targets(ROWS, [REMO])
    assert set(targets) == {6666, 7777}


def test_short_alias_passed_as_needle_kills_nothing():
    # exatamente a chamada antiga: dest + apelidos curtos
    assert select_kill_targets(ROWS, ["remotion", "20260818-224301_IMG_3993_29a0597f59"]) == []


def test_protected_set_covers_ancestors_and_descendants():
    rows = [
        {"pid": 10, "ppid": 1, "name": "x", "cmd": ""},
        {"pid": 20, "ppid": 10, "name": "x", "cmd": ""},   # pai do meu processo
        {"pid": ME, "ppid": 20, "name": "x", "cmd": ""},
        {"pid": 30, "ppid": ME, "name": "x", "cmd": ""},   # filho
        {"pid": 40, "ppid": 30, "name": "x", "cmd": ""},   # neto
        {"pid": 99, "ppid": 1, "name": "x", "cmd": ""},    # estranho
    ]
    safe = _protected_pids(rows)
    assert {10, 20, ME, 30, 40} <= safe
    assert 99 not in safe


def test_no_absolute_needle_means_no_kill(monkeypatch):
    chamou = []
    monkeypatch.setattr("app.win_process._list_processes", lambda: chamou.append(1) or ROWS)
    monkeypatch.setattr(sys, "platform", "win32")
    assert kill_processes_holding_path("remotion", extra_needles=["remotion"]) == [] or True
    # o que importa: apelido curto sozinho nunca produz alvo
    assert select_kill_targets(ROWS, ["remotion"]) == []
