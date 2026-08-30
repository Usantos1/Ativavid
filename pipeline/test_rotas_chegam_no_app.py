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


# A direcao INVERSA. Rota que so existe no `desktop_server` nao quebra o
# usuario — quebra quem esta consertando o app: no navegador a tela mente.
# Custou tempo em 30/08 com o card "Desempenho" preso em "Detectando GPU...",
# porque `loadHardwareCard` engole o erro e nao ha sintoma nenhum.
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_navegador_serve_o_que_o_studio_pede():
    chamadas = sorted(set(re.findall(r"[\"'`](/api/[a-zA-Z0-9_\-/]+)", JS)))
    assert len(chamadas) > 40, f"achei so {len(chamadas)} chamadas — mudou o padrao?"
    servidas = set(re.findall(r'path == "(/api/[^"]+)"', LOCAL))
    prefixos = set(re.findall(r'path\.startswith\("(/api/[^"]+)"\)', LOCAL))
    fora = [r for r in chamadas
            if r not in servidas
            and not any(r.startswith(px) or px.startswith(r) for px in prefixos)]
    assert not fora, (
        "rotas que o preview no navegador nao serve (a tela mente calada): "
        + ", ".join(fora))


def test_as_tres_que_faltavam_no_navegador():
    for rota in ("/api/hardware", "/api/hardware/bench", "/api/events"):
        assert f'path == "{rota}"' in LOCAL, rota


def test_as_duas_que_ja_morderam_estao_na_lista():
    for rota in ("/api/library/categoria", "/api/update/progresso"):
        assert f'"{rota}"' in DESKTOP, rota
