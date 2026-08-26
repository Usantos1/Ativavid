# -*- coding: utf-8 -*-
"""Redimensionar a janela sem moldura: as bordas moram na PAGINA.

O miolo e do WebView2 (outro processo): o WM_NCHITTEST do pai quase nunca
dispara ("so apareceu uma vez na esquerda", 25-26/08) e subclassificar o
filho e impossivel cross-process. Faixas em JS + WM_NCLBUTTONDOWN (Tauri
faz igual) — nativo, com DPI e Aero Snap certos.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def test_api_begin_resize_existe_com_todas_as_bordas():
    s = (RAIZ / "app" / "launcher.py").read_text(encoding="utf-8")
    assert "def begin_resize" in s
    corpo = s[s.find("def begin_resize"):][:1800]
    for edge in ("left", "right", "top", "bottom", "topleft", "topright",
                 "bottomleft", "bottomright"):
        assert f'"{edge}"' in corpo, f"borda {edge} sumiu do mapa HT"
    assert "WM_NCLBUTTONDOWN" in corpo
    assert "_is_app_maximized()" in corpo, \
        "maximizada a janela nao redimensiona — a API tem que recusar"


def test_faixas_carregadas_nas_duas_telas():
    js = (RAIZ / "assets" / "preview" / "janela-resize.js")
    assert js.is_file(), "o script compartilhado sumiu"
    corpo = js.read_text(encoding="utf-8")
    assert "begin_resize" in corpo and "winResize" in corpo
    for pagina in ("assets/studio/index.html", "assets/preview/index.html"):
        html = (RAIZ / pagina).read_text(encoding="utf-8")
        assert '/assets/janela-resize.js' in html, f"{pagina} nao carrega as faixas"
