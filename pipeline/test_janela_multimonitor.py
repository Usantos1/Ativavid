# -*- coding: utf-8 -*-
"""A janela funciona em monitor com escala diferente.

Caso real (25/08): "num monitor maior nao da pra arrastar e ajustar o
tamanho". O pywebview deixa o processo apenas system-DPI aware; em monitor
com escala diferente o Windows virtualiza as coordenadas e o hit-test das
bordas (hook WM_NCHITTEST) + o arrasto caem deslocados.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

SRC = (RAIZ / "app" / "launcher.py").read_text(encoding="utf-8")


def test_pmv2_declarado_antes_da_janela():
    assert "_declarar_dpi_por_monitor" in SRC
    i_decl = SRC.find("_declarar_dpi_por_monitor()")
    i_win = SRC.find("webview.create_window(")
    assert 0 < i_decl < i_win, \
        "PMv2 tem que ser declarado ANTES do primeiro HWND"
    assert "SetProcessDpiAwarenessContext" in SRC
    assert "SetProcessDpiAwareness(2)" in SRC, "fallback shcore sumiu"


def test_borda_do_hittest_escala_com_dpi():
    assert "GetDpiForWindow" in SRC, \
        "borda fixa de 8px fica fina demais em monitor 150%"
    assert "BORDER = 8" not in SRC, "a constante fixa voltou"


def test_find_hwnd_tem_fallback_por_pid():
    """FindWindowW por titulo exato quebra se o document.title de outra
    pagina vazar para a janela — e TODO o maquinario (resize, clamp,
    maximize) depende do hwnd."""
    i = SRC.find("def _find_hwnd")
    corpo = SRC[i:i + 1800]
    assert "EnumWindows" in corpo and "GetWindowThreadProcessId" in corpo
