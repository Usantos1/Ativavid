# -*- coding: utf-8 -*-
"""Liberar espaco: dedup por hardlink (sempre) + intermediarios (entregues 7d+).

Medido (25/08): 127 GB em 145 projetos; ~575 MB de duplicatas byte a byte
por projeto entregue (final em 3 lugares, cut em 2) + ~700 MB regeneraveis.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))

from liberar_espaco import liberar, medir  # noqa: E402

MB2 = b"x" * 2_000_000


def _projeto(root: Path, nome: str, *, dias: float) -> Path:
    proj = root / nome
    edit = proj / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "remotion" / "out").mkdir()
    (edit / "clips_graded").mkdir()
    (proj / "publicar" / "Video Legal").mkdir(parents=True)
    (edit / "cut.mp4").write_bytes(MB2)
    (edit / "remotion" / "public" / "cut.mp4").write_bytes(MB2)
    (edit / "Video Legal.mp4").write_bytes(MB2 + b"f")
    (edit / "final.mp4").write_bytes(MB2 + b"f")
    (proj / "publicar" / "Video Legal" / "Video Legal.mp4").write_bytes(MB2 + b"f")
    (edit / "remotion" / "out" / "overlay.mov").write_bytes(MB2)
    (edit / "clips_graded" / "c0.mp4").write_bytes(MB2)
    (proj / "fonte.MOV.prep.mp4").write_bytes(MB2)
    (edit / "state.json").write_text(json.dumps(
        {"finalVideo": "Video Legal.mp4"}), encoding="utf-8")
    r = edit / "result.json"
    r.write_text(json.dumps({"status": "done"}), encoding="utf-8")
    t = time.time() - dias * 86400
    os.utime(r, (t, t))
    return proj


def test_dedup_e_intermediarios(tmp_path):
    velho = _projeto(tmp_path, "p_velho", dias=30)
    novo = _projeto(tmp_path, "p_novo", dias=1)

    m = medir(tmp_path)
    assert m["duplicatasGb"] > 0 and m["intermediariosGb"] > 0

    r = liberar(tmp_path)
    assert r["erros"] == 0, r

    for proj in (velho, novo):
        edit = proj / "edit"
        # dedup valeu nos DOIS (sem gate de idade): mesmo inode
        assert os.stat(edit / "cut.mp4").st_ino == \
            os.stat(edit / "remotion" / "public" / "cut.mp4").st_ino
        assert os.stat(edit / "Video Legal.mp4").st_ino == \
            os.stat(proj / "publicar" / "Video Legal" / "Video Legal.mp4").st_ino
        # o essencial esta intacto
        assert (edit / "Video Legal.mp4").stat().st_size == len(MB2) + 1
        assert (edit / "cut.mp4").is_file()
        assert (edit / "state.json").is_file()

    # intermediarios: so o projeto VELHO perdeu
    assert not (velho / "edit" / "remotion" / "out").exists()
    assert not (velho / "edit" / "clips_graded").exists()
    assert not (velho / "fonte.MOV.prep.mp4").exists()
    assert (novo / "edit" / "remotion" / "out").exists(), \
        "projeto recente nao pode perder intermediarios (apply/refazer usam)"
    assert (novo / "fonte.MOV.prep.mp4").exists()


def test_projeto_nao_entregue_fica_intacto(tmp_path):
    proj = _projeto(tmp_path, "p_erro", dias=30)
    r = proj / "edit" / "result.json"
    r.write_text(json.dumps({"status": "error"}), encoding="utf-8")
    t = time.time() - 30 * 86400
    os.utime(r, (t, t))
    liberar(tmp_path)
    assert (proj / "edit" / "clips_graded").exists(), \
        "projeto com erro pode precisar de reprocesso completo"


def test_rotas_e_botao_existem():
    srv = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    assert '"/api/espaco"' in srv and '"/api/espaco/liberar"' in srv
    ds = (RAIZ / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/espaco"' in ds and '"/api/espaco/liberar"' in ds, \
        "a rota nova precisa entrar na whitelist do desktop_server"
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnLiberarEspaco"' in html
