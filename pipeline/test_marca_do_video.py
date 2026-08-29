# -*- coding: utf-8 -*-
"""A tela do vídeo mostra de qual marca ele é — e deixa trocar.

Caso real (29/08): um vídeo saiu com o verde e o "Segue @Ativacrm" porque
a marca ativa NO MOMENTO DA IMPORTAÇÃO era a Ativa CRM; o usuário trocou
para Prime Camp oito minutos depois. O app não errou — mas a tela do vídeo
não dizia qual marca estava usando, então só dava para descobrir depois de
renderizar, e a única saída era reimportar.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
PREVIEW = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")


def test_a_marca_vem_com_o_estilo_dela():
    """Sem o estilo, dava para ver o nome e nada mais — o vídeo continuaria
    com as cores e o CTA da marca antiga."""
    from app.brand_kits import list_brands
    marcas = list_brands()
    assert marcas, "nenhuma marca"
    assert all("style" in m for m in marcas), marcas[0].keys()
    assert all("name" in m and "id" in m for m in marcas)


def test_a_tela_tem_a_linha_da_marca():
    assert 'id="marcaDoVideo"' in HTML and 'id="marcaSelect"' in HTML
    assert "MARCA DESTE VÍDEO" in HTML or "Marca deste vídeo" in HTML


def test_trocar_a_marca_leva_estilo_e_cta():
    i = JS.index("function trocarMarcaDoVideo")
    trecho = JS[i:i + 1200]
    assert "applyPresetToUi({ style: m.style })" in trecho, trecho[:300]
    assert "S.endCardCopy" in trecho, "o CTA ficaria o da marca antiga"
    assert "S.presetUsed.brandId = m.id" in trecho


def test_o_brandid_viaja_no_salvar():
    """Sem isto o editor mudava e o render continuava na marca antiga."""
    assert "brandId: (S.presetUsed && S.presetUsed.brandId) || null," in JS


def test_o_servidor_grava_a_marca_no_job():
    i = PREVIEW.index('marca = str(body.get("brandId")')
    trecho = PREVIEW[i:i + 700]
    assert 'atual["brandId"] = marca' in trecho, trecho[:300]
    assert "style-setup" in trecho


def test_preview_solto_nao_mostra_a_linha():
    """Na skill (sem servidor de marcas) a linha some em vez de dar erro."""
    i = JS.index("async function carregarMarcaDoVideo")
    trecho = JS[i:i + 900]
    assert "caixa.hidden = true" in trecho, trecho[:400]
