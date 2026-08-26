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
    corpo = s[s.find("def begin_resize"):][:3200]
    for edge in ("left", "right", "top", "bottom", "topleft", "topright",
                 "bottomleft", "bottomright"):
        assert f'"{edge}"' in corpo, f"borda {edge} sumiu do mapa"
    assert "_is_app_maximized()" in corpo,         "maximizada a janela nao redimensiona — a API tem que recusar"
    # O loop e NOSSO, nao do Windows: WM_NCLBUTTONDOWN nao rodou nesta
    # maquina (captura do botao no processo do WebView2 — 26/08, duas
    # tentativas). GetCursorPos + GetAsyncKeyState sao globais e
    # SetWindowPos move tick a tick.
    assert "GetAsyncKeyState" in corpo, "o loop proprio de resize sumiu"
    assert "SetWindowPos" in corpo
    assert "GetCursorPos" in corpo
    assert "SendMessageW(hwnd, WM_NCLBUTTONDOWN" not in corpo,         "o loop modal do Windows voltou — ele NAO funciona com WebView2 aqui"
    assert "MIN_W, MIN_H = 900, 600" in corpo,         "o minimo tem que casar com o min_size do create_window"
    # Anti-flicker ("piscando tudo", 26/08): so SetWindowPos quando a
    # geometria mudou, clamp silenciado durante o laco e DWM uma vez no fim.
    assert "if novo != ultimo:" in corpo, "o skip de geometria identica sumiu"
    assert "_RESIZE_ATIVO = True" in corpo
    todo = (RAIZ / "app" / "launcher.py").read_text(encoding="utf-8")
    assert "if _RESIZE_ATIVO:\n        return" in todo, \
        "_clamp_to_work_area tem que calar durante o laco de resize"


def test_faixas_carregadas_nas_duas_telas():
    js = (RAIZ / "assets" / "preview" / "janela-resize.js")
    assert js.is_file(), "o script compartilhado sumiu"
    corpo = js.read_text(encoding="utf-8")
    assert "begin_resize" in corpo and "winResize" in corpo
    for pagina in ("assets/studio/index.html", "assets/preview/index.html"):
        html = (RAIZ / pagina).read_text(encoding="utf-8")
        assert '/assets/janela-resize.js' in html, f"{pagina} nao carrega as faixas"
