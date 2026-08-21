# -*- coding: utf-8 -*-
"""A nota só vira corte quando é ordem explícita de remover.

O fluxo documentado do usuário é: marcar IN/OUT com **M** na timeline, escrever
a nota (ex.: "legenda errada, devia ser X") e salvar. Uma nota que vira corte
por engano apaga o trecho E o texto que ele escreveu.

`noteLooksLikeRemove` casava por SUBSTRING: `fora` pegava "fora de foco",
`cort` pegava "aqui o corte ficou estranho", `tir[ae]` pegava "tira o zoom
daqui" — e esta última é a pior, porque a ordem era sobre o zoom e o app
apagava o take inteiro.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

ORDENS = [
    "corta isso", "corte isso", "corta esse pedaço", "tira isso aqui",
    "tire esse trecho", "remove esse take", "remova aqui", "apaga",
    "apague isso", "exclui esse", "deleta", "descarta esse pedaco",
    "joga fora", "fora daqui", "sem isso",
]

COMENTARIOS = [
    "legenda errada, devia ser Prime Camp",
    "essa parte ficou fora de foco",
    "aqui o corte ficou estranho",
    "o corte ficou seco demais",
    "nesse corte a imagem tremeu",
    "tira o zoom daqui",
    "corta a musica nesse trecho",
    "o texto da manchete esta errado",
    "a trilha ficou alta",
    "gostei desse trecho",
    "acelera um pouco",
    "trocar a capa",
]


def _classificar(notas: list[str]) -> list[bool]:
    src = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = src.index("const NOTA_ELEMENTOS")
    j = src.index("\n}\n", src.index("function noteLooksLikeRemove(")) + 3
    prog = (src[i:j] + "\nconst N = " + json.dumps(notas, ensure_ascii=False)
            + ";\nconsole.log(JSON.stringify(N.map((t) => !!noteLooksLikeRemove(t))));")
    exe = "node.exe" if sys.platform == "win32" else "node"
    r = subprocess.run([exe, "-e", prog], capture_output=True, text=True, **NOWIN)
    if r.returncode != 0:
        pytest.fail(f"node falhou: {r.stderr[-500:]}")
    return json.loads(r.stdout)


def test_ordem_explicita_continua_cortando():
    """O recurso tem de continuar funcionando para o que ele existe."""
    falhas = [n for n, ok in zip(ORDENS, _classificar(ORDENS)) if not ok]
    assert not falhas, falhas


def test_comentario_nao_vira_corte():
    falhas = [n for n, ok in zip(COMENTARIOS, _classificar(COMENTARIOS)) if ok]
    assert not falhas, falhas


def test_ordem_sobre_um_elemento_nao_apaga_o_take():
    """"tira o zoom daqui" manda tirar o ZOOM. O app apagava o trecho todo."""
    notas = ["tira o zoom daqui", "corta a legenda", "remove a trilha",
             "apaga o emoji", "tira o texto da manchete"]
    assert not any(_classificar(notas)), notas


def test_a_nota_so_some_se_o_corte_aconteceu():
    """Quando a marca não pega nenhum take, a nota sumia levando junto o texto
    que o usuário escreveu."""
    src = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = src.index("if (noteLooksLikeRemove(text)) {")
    bloco = src[i:i + 700]
    assert "if (removeDraftTimeRange(start, end))" in bloco, bloco[:400]
    assert bloco.index("if (removeDraftTimeRange") < bloco.index("S.notes = S.notes.filter")
