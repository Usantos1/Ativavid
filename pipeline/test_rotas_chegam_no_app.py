# -*- coding: utf-8 -*-
"""Toda rota do studio precisa chegar ao app empacotado.

O app não roda o `local_server` direto: ele roda o `desktop_server`, que
tem LISTAS de rotas para repassar. Rota nova criada no studio e esquecida
na lista simplesmente não existe para o usuário — e o sintoma é o pior
possível: um toast "unknown route", que não diz nada.

Aconteceu duas vezes comigo no mesmo dia: `/api/library/categoria` (3.31,
trocar a categoria de um arquivo da Biblioteca — o usuário mandou print do
erro) e `/api/update/progresso` (3.45, a barra de progresso da
atualização, que nunca teria funcionado no app).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCAL = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
DESKTOP = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
PREVIEW = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")


def test_nenhuma_rota_do_studio_fica_invisivel_no_app():
    rotas = sorted(set(re.findall(r'path == "(/api/[^"]+)"', LOCAL)))
    assert len(rotas) > 40, f"achei so {len(rotas)} rotas — o padrao mudou?"
    fora = [r for r in rotas
            if f'"{r}"' not in DESKTOP and f'"{r}"' not in PREVIEW]
    assert not fora, (
        "rotas que o app nao repassa (o usuario ve 'unknown route'): "
        + ", ".join(fora))


def test_as_duas_que_ja_morderam_estao_na_lista():
    for rota in ("/api/library/categoria", "/api/update/progresso"):
        assert f'"{rota}"' in DESKTOP, rota
