# -*- coding: utf-8 -*-
"""O Aplicar da Edição leva junto o que foi mexido na aba Estilo.

Caso real (02/09): ele mudou coisas no Estilo, foi para a Edição e clicou
Aplicar — só a timeline foi; headline e card final saíram velhos. O estilo
vivia só na memória da tela até alguém clicar no botão da própria aba.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_payload_de_estilo_virou_funcao_reutilizavel():
    """O literal saiu do setupGo para montarPayloadDeEstilo() — o Aplicar e
    o botão da aba usam a MESMA montagem (dois literais divergiriam)."""
    assert "function montarPayloadDeEstilo()" in JS
    assert JS.count("type: 'style-setup'") == 1, (
        "o payload de estilo duplicou — dois literais vão divergir")
    i = JS.index("function montarPayloadDeEstilo()")
    corpo = JS[i:JS.index("function salvarEstiloDoProjeto", i)]
    # os campos que já morderam quando ficaram de fora (4.2x)
    for campo in ("contentType:", "endCardCopy:", "brandPresetId:",
                  "editingIntent:", "headlineAnimation:"):
        assert campo in corpo, f"{campo} sumiu do payload de estilo"


def test_mexer_no_estilo_marca_e_o_aplicar_leva():
    assert "styleTocado: false" in JS
    # qualquer mexida na aba marca
    i = JS.index("setup.addEventListener('change'")
    assert "S.styleTocado = true" in JS[i - 200:i + 200]
    # o pendente acende
    assert "style: !!d.style || !!S.styleTocado" in JS
    # o Aplicar da Edição considera estilo como sessão
    j = JS.index("const temSessao =")
    assert "S.styleTocado" in JS[j:j + 200]
    # e o salvar grava o estilo ANTES da fila, forçando Fase 2 completa
    k = JS.index("const tinhaEstilo = !!S.styleTocado;")
    assert "salvarEstiloDoProjeto()" in JS[k:k + 300]
    m = JS.index("const needsFullRerun =")
    assert "estiloSalvo" in JS[m:m + 160], (
        "estilo novo não pode cair no quick apply — ele não veste estilo")


def test_so_estilo_tambem_aplica():
    """Mexeu SÓ no estilo e clicou Aplicar: não pode cair no 'Nada para
    salvar' — o estilo salvo sozinho já justifica a fila."""
    i = JS.index("const algoNaTimeline =")
    trecho = JS[i:i + 400]
    assert "!algoNaTimeline && !estiloSalvo" in trecho
