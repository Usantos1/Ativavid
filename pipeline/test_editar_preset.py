# -*- coding: utf-8 -*-
""""onde edita o estilo de um preset?" (30/08). Nao editava.

Estilos editava o ESTILO BASE e, ao salvar, copiava por cima do preset
marcado como padrao — fosse qual fosse o preset carregado na tela. Dos
tres presets dele, so o padrao mudava, e de raspao. O "Uander" mostrava
"nao define o visual" e nao havia como definir.

Agora cada preset tem **Editar estilo**: o editor abre com `?presetId=`
e, nesse modo, grava SO naquele preset. Medido com os presets reais
dele: depois de salvar o Uander, o `default-style.json` ficou byte a
byte igual e os outros dois presets tambem.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

HUB = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
ED = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_o_cartao_do_preset_tem_por_onde_editar():
    i = HUB.index('data-preset-act="default"')
    cartao = HUB[max(0, i - 600):i + 600]
    assert 'data-preset-act="edit"' in cartao
    assert "Editar estilo" in cartao


def test_editar_aponta_o_editor_para_aquele_preset():
    i = HUB.index('act === "edit"')
    bloco = HUB[i:i + 400]
    assert "state.editPresetId = id" in bloco
    assert 'setView("estilo")' in bloco
    # e o endereco do iframe leva o preset
    j = HUB.index("function estiloFrameSrc(")
    assert 'q.set("presetId", state.editPresetId)' in HUB[j:j + 700]


def test_entrar_por_estilos_volta_ao_estilo_base():
    """Menu lateral e atalhos de identidade editam a base. So o botao do
    cartao — que nao tem `data-view` — aponta para um preset."""
    i = HUB.index('const nav = e.target.closest("[data-view]");')
    bloco = HUB[i:i + 700]
    assert 'nav.dataset.view === "estilo"' in bloco
    assert "state.editPresetId = \"\"" in bloco


def test_a_barra_diz_qual_dos_dois_esta_editando():
    """Sao dois destinos diferentes; sem dizer qual, salvar e aposta."""
    i = HUB.index("function barraDoEstilo(")
    bloco = HUB[i:i + 900]
    assert "Editando o preset" in bloco and "Editando o estilo base" in bloco
    assert "muda só este preset" in bloco
    assert 'id="estiloBrandTitulo"' in HTML
    assert 'id="btnEstiloBase"' in HTML


def test_o_editor_reconhece_o_preset_pedido():
    assert "const EDIT_PRESET_ID = new URLSearchParams(location.search)" in ED
    i = ED.index("if (EDIT_PRESET_ID) {\n      const alvo = presets.find(")
    assert "applyPresetToUi(alvo)" in ED[i:i + 400]


def test_salvar_no_modo_preset_nao_toca_no_estilo_base():
    """A parte que importa. O Salvar antigo gravava `/api/default-style`
    e depois copiava por cima do preset PADRAO — editar o Uander mudaria
    o Prime Camp [Centro]."""
    i = ED.index("if (EDIT_PRESET_ID) {", ED.index("const house = {"))
    bloco = ED[i:ED.index("const res = await fetch('/api/default-style'", i)]
    assert "action: 'update'" in bloco
    assert "id: EDIT_PRESET_ID" in bloco
    assert "/api/default-style" not in bloco, (
        "o modo preset nao pode gravar o estilo base"
    )
    assert "return;" in bloco, "sem o return, cai no salvamento do base"


def test_o_botao_diz_para_onde_vai():
    i = ED.index("$('setupGo').textContent")
    bloco = ED[i:i + 300]
    assert "'Salvar preset e voltar'" in bloco
    assert "'Salvar padrão e voltar'" in bloco
