# -*- coding: utf-8 -*-
"""Marcar um trecho na timeline remove SÓ aquele trecho.

É o fluxo que o usuário usa todo dia: marcar IN/OUT com **M** na timeline do
preview, escrever a nota e salvar.

A janela marcada está em tempo de SAÍDA, e cada remoção ENCURTA a saída —
tudo que vinha depois desliza para dentro da janela. O laço antigo relia o
layout a cada volta com `tStart`/`tEnd` fixos e ia comendo o que escorregava
para lá, até 64 vezes.

Medido com 10 takes de 6 s (60 s de vídeo): marcar de 10,0 s a 12,0 s — dois
segundos — removia **50 dos 60**, tudo da marca até o fim, em 25 pedaços.

O teste roda a função DE VERDADE, extraída do app.js, dentro do node.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

FUNCOES = ("jcutGeom", "draftLayout", "draftTimeToSource", "removeDraftTimeRange")


def _pega(src: str, nome: str) -> str:
    i = src.index("function " + nome + "(")
    return src[i:src.index("\n}\n", i) + 3]


def _rodar(casos: list[tuple[float, float]]) -> list[dict]:
    """Roda `removeDraftTimeRange` no node com um rascunho de 10 takes de 6s."""
    src = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    prog = "\n".join([
        "const S = { draft: [], jcut: null, selected: -1 };",
        "const MIN_SEG = 0.2;",
        "function pushHistory() {}",
        "function renderAll() {}",
        "function refreshHeader() {}",
        *[_pega(src, n) for n in FUNCOES],
        "function montar() {",
        "  S.draft = [];",
        "  for (let i = 0; i < 10; i++) S.draft.push({ source: 'SRC',",
        "    start: i * 10, end: i * 10 + 6, beat: null, removed: false,",
        "    srcIdx: i, orig: { start: i * 10, end: i * 10 + 6 } });",
        "}",
        "const total = () => draftLayout().reduce((a, d) => a + d.dur, 0);",
        f"const CASOS = {json.dumps(casos)};",
        "const saida = [];",
        "for (const [a, b] of CASOS) {",
        "  montar();",
        "  const antes = total();",
        "  removeDraftTimeRange(a, b);",
        "  saida.push({ a, b, antes, depois: total(),",
        "               pedacos: S.draft.filter((r) => r.removed).length });",
        "}",
        "console.log(JSON.stringify(saida));",
    ])
    exe = "node.exe" if sys.platform == "win32" else "node"
    r = subprocess.run([exe, "-e", prog], capture_output=True, text=True, **NOWIN)
    if r.returncode != 0:
        pytest.fail(f"node falhou: {r.stderr[-600:]}")
    return json.loads(r.stdout)


def test_remove_exatamente_a_janela_marcada():
    casos = [(10.0, 12.0), (10.0, 20.0), (0.0, 3.0), (57.0, 60.0)]
    for res in _rodar(casos):
        pedido = min(res["b"], res["antes"]) - res["a"]
        removido = res["antes"] - res["depois"]
        assert abs(removido - pedido) < 0.5, res


def test_a_marca_pequena_nao_come_o_video_inteiro():
    """O caso exato que reproduziu o defeito: 2 s marcados num vídeo de 60 s."""
    res = _rodar([(10.0, 12.0)])[0]
    assert res["antes"] - res["depois"] < 3.0, res
    # e não vira uma penca de pedaços
    assert res["pedacos"] <= 2, res


def test_marca_fora_do_video_nao_mexe_em_nada():
    res = _rodar([(90.0, 95.0)])[0]
    assert res["depois"] == res["antes"], res
    assert res["pedacos"] == 0, res
