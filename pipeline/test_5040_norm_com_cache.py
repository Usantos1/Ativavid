# -*- coding: utf-8 -*-
"""5.0.40: o caminho de cada projeto se resolve UMA vez por processo.

`Path.resolve()` é uma chamada de sistema (realpath) por caminho, e o hub
pede a lista de jobs a cada 2,5 s: com 331 projetos eram 332 resolves por
pedido — 0,12 s dos 0,25-0,5 s do `/api/jobs` (perfil de 05/09). A mesma
pasta chega como str do índice (barra normal) e como Path do job (barra
invertida); as duas têm de cair na mesma entrada do cache.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import apply_tasks as at  # noqa: E402

BARRA_INVERTIDA = chr(92)


def test_str_e_path_da_mesma_pasta_resolvem_uma_vez(monkeypatch, tmp_path):
    pasta = tmp_path / "Projetos" / "p1" / "edit"
    pasta.mkdir(parents=True)
    at._norm_cacheado.cache_clear()
    n = {"k": 0}
    original = Path.resolve

    def contando(self, *a, **k):
        n["k"] += 1
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "resolve", contando)
    a = at._norm(str(pasta))
    b = at._norm(pasta)
    c = at._norm(str(pasta).replace(BARRA_INVERTIDA, "/"))
    assert a == b == c
    assert n["k"] == 1, "cada forma do mesmo caminho pagou um resolve"


def test_vazio_continua_vazio_e_barra_vira_barra_normal():
    assert at._norm(None) == "" and at._norm("") == ""
    invertida = "E:" + BARRA_INVERTIDA + "x" + BARRA_INVERTIDA + "edit"
    assert BARRA_INVERTIDA not in at._norm(invertida)
    assert at._norm(invertida) == at._norm("E:/x/edit")
