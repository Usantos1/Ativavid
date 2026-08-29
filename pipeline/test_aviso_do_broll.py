# -*- coding: utf-8 -*-
"""A Biblioteca avisa quando os takes guardados não vão entrar no vídeo.

No estilo do usuário (layout limpo + b-roll em "Quando necessário") o
pipeline ZERA os inserts de propósito — é o talking-head limpo. Sem aviso,
ele guardaria takes na Biblioteca, renderizaria, não veria nada e
procuraria defeito onde só havia configuração.

O teste roda a função de verdade no node: texto certo não garante regra
certa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
JS = REPO / "assets" / "studio" / "studio.js"


def _rodar(estilo, aba="clip", quantos=2) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node nesta máquina")
    fonte = JS.read_text(encoding="utf-8")
    i = fonte.index("function libAvisoDoBroll")
    j = fonte.index("\nfunction libTamanho", i)
    corpo = fonte[i:j]
    prog = (
        "const state = " + json.dumps({"libEstilo": estilo}) + ";\n"
        + corpo
        + f"\nprocess.stdout.write(libAvisoDoBroll({json.dumps(aba)}, {quantos}));\n"
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        f = tmp / "t.mjs"
        f.write_text(prog, encoding="utf-8")
        r = subprocess.run([node, str(f)], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        assert r.returncode == 0, r.stderr[-400:]
        return r.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_avisa_no_estilo_do_usuario():
    """Layout limpo + b-roll no padrão = nenhum insert."""
    out = _rodar({"edit": "limpa", "brollMode": "quando_necessario"})
    assert "não vão entrar" in out and "Sempre" in out, out


def test_avisa_com_broll_desligado_em_qualquer_layout():
    out = _rodar({"edit": "moldura", "brollMode": "off"})
    assert "desligado" in out, out


def test_nao_avisa_quando_o_broll_vai_entrar():
    for estilo in ({"edit": "limpa", "brollMode": "sempre"},
                   {"edit": "limpa", "brollMode": "raro"}):
        assert _rodar(estilo) == "", estilo


def test_nao_avisa_sem_take_nem_fora_da_aba_de_video():
    st = {"edit": "limpa", "brollMode": "quando_necessario"}
    assert _rodar(st, quantos=0) == ""
    assert _rodar(st, aba="track") == ""
    assert _rodar(st, aba="image") == ""


def test_sem_estilo_carregado_fica_calado():
    """Não saber o estilo não autoriza assustar o usuário."""
    assert _rodar(None) == ""


def test_concordancia_no_singular():
    out = _rodar({"edit": "limpa", "brollMode": "quando_necessario"}, quantos=1)
    assert "Este take não vai entrar" in out and "usá-lo" in out, out
