# -*- coding: utf-8 -*-
"""Copiar o estilo de um vídeo e colar em outros (pedido de 03/09).

Sem servidor novo: o estilo por projeto já vive em <edit>/preview_style.json
(o que a aba Estilo salva via /p/<pasta>/api/save, type=style-setup) e o
"Aplicar" já refaz o visual por /api/jobs/requeue-folder. Copiar lê o
arquivo do card de origem; colar grava o MESMO payload no destino e manda
o vídeo à fila. A área de transferência sobrevive à recarga (localStorage).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_menu_do_card_oferece_copiar_e_colar():
    i = JS.index("function cardMenuHtml")
    bloco = JS[i:JS.index("\nfunction ", i + 10)]
    assert 'data-act="copystyle"' in bloco and "Copiar estilo" in bloco
    assert 'data-act="pastestyle"' in bloco and "Colar estilo (de " in bloco
    # colar nao aparece no proprio video de origem
    assert "estiloCopiado().folder !== pastaDoProjeto(j)" in bloco


def test_copiar_le_o_estilo_salvo_e_recusa_quem_nao_tem():
    i = JS.index("async function copiarEstiloDoCard")
    bloco = JS[i:JS.index("\nasync function colarEstiloNoCard", i)]
    assert "/media/preview_style.json" in bloco
    assert 'payload.type !== "style-setup"' in bloco, \
        "sem estilo salvo o copiar tem de explicar, nao copiar lixo"
    assert "localStorage.setItem(ESTILO_COPIADO_KEY" in bloco


def test_colar_grava_no_destino_e_manda_a_fila():
    i = JS.index("async function colarEstiloNoCard")
    bloco = JS[i:JS.index("\nfunction cardMenuHtml", i)]
    assert "/api/save" in bloco and '"style-setup"' in bloco
    assert "/api/jobs/requeue-folder" in bloco
    # a gravacao vem ANTES do requeue, senao o render sai com o estilo velho
    assert bloco.index("/api/save") < bloco.index("/api/jobs/requeue-folder")


def test_o_despachante_liga_as_duas_acoes():
    assert 'act === "copystyle"' in JS and 'act === "pastestyle"' in JS
    assert "copiarEstiloDoCard(" in JS and "colarEstiloNoCard(" in JS


def test_a_assinatura_do_card_muda_quando_ha_estilo_copiado():
    """Sem isto o card nao repinta depois do copiar e o 'Colar' nao aparece."""
    i = JS.index("function cardSig")
    bloco = JS[i:JS.index("\nfunction ", i + 10)]
    assert "estiloCopiado" in bloco
