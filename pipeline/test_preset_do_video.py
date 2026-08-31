# -*- coding: utf-8 -*-
"""A tela do vídeo mostra de qual PRESET ele é — e deixa trocar.

Caso real (29/08): um vídeo saiu com o verde e o "Segue @Ativacrm" porque
a identidade ativa NO MOMENTO DA IMPORTAÇÃO era outra; o usuário trocou
oito minutos depois. O app não errou — mas a tela do vídeo não dizia qual
identidade estava usando, então só dava para descobrir depois de
renderizar, e a única saída era reimportar.

Até a 4.28 esta linha listava MARCAS, conceito que saiu do app na 4.19:
"não aparece os presets reais ali, no lugar de marca, que a gente não usa
mais" (30/08). A mecânica é a mesma; a unidade é que mudou.
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


def test_o_preset_vem_com_o_estilo_dele():
    """Sem o estilo, dava para ver o nome e nada mais — o vídeo continuaria
    com as cores e o CTA anteriores."""
    from app.brand_presets import STYLE_KEYS

    assert "endCardCopy" in STYLE_KEYS, (
        "sem o CTA no retrato, trocar o preset deixaria o cartao antigo")


def test_a_tela_tem_a_linha_do_preset():
    assert 'id="presetDoVideo"' in HTML and 'id="presetVideoSelect"' in HTML
    assert "Preset deste vídeo" in HTML
    assert 'id="marcaSelect"' not in HTML, "a lista de marcas voltou"


def test_o_editor_nao_tem_mais_o_menu_de_marca():
    """O hub perdeu a tela de Marca na 4.19; o menu do editor e outro
    arquivo e ficou com o item por mais nove versoes."""
    assert 'data-hub-view="marca"' not in HTML


def test_trocar_o_preset_leva_estilo_e_cta():
    i = JS.index("function trocarPresetDoVideo")
    trecho = JS[i:i + 1400]
    assert "applyPresetToUi(p)" in trecho, trecho[:300]
    assert "S.endCardCopy" in trecho, "o CTA ficaria o de antes"
    assert "S.presetUsed.brandPresetId = p.id" in trecho


def test_o_preset_viaja_no_salvar():
    """Sem isto o editor mudava e o render continuava no preset antigo."""
    assert "brandId: (S.presetUsed && S.presetUsed.brandId) || null," in JS
    assert ("brandPresetId: (S.presetUsed && S.presetUsed.brandPresetId) "
            "|| null,") in JS


def test_o_servidor_grava_o_preset_no_job():
    i = PREVIEW.index('marca = str(body.get("brandId")')
    trecho = PREVIEW[i:i + 1400]
    assert 'atual["brandId"] = marca' in trecho, trecho[:300]
    assert 'atual["brandPresetId"] = preset_id' in trecho
    assert "style-setup" in trecho


def test_preview_solto_nao_mostra_a_linha():
    """Na skill (sem servidor de presets) a linha some em vez de dar erro."""
    i = JS.index("async function carregarPresetDoVideo")
    trecho = JS[i:i + 900]
    assert "caixa.hidden = true" in trecho, trecho[:400]
