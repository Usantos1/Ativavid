# -*- coding: utf-8 -*-
"""Marca e Presets viraram uma tela so (4.19).

Pedido de 30/08: "presets e marcas quero apenas um deles ... nao esta
lincado uma coisa com a outra". Os dados dele dizem o mesmo — as marcas
gravadas e os presets da marca ativa tinham OS MESMOS NOMES:

    marcas   -> Prime Camp, Uander, Prime Camp - Centro, Ativa CRM, Marca
    presets  -> Prime Camp, Uander, Prime Camp [Centro]

A marca continua no disco (e ela que guarda o estilo base, o cartao final
e o formato de saida); o que saiu foi a tela. Este arquivo guarda as duas
coisas que a mudanca poderia estragar: a tela que ficou tem de continuar
tendo o que a outra tinha, e o formato de saida nao pode apagar o resto
da marca ao ser salvo.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _bloco_dos_presets() -> str:
    i = HTML.index('id="view-presets"')
    j = HTML.index('id="view-ia"')
    return HTML[i:j]


def test_a_tela_de_marca_saiu_inteira():
    for marca in ('data-view="marca"', 'id="view-marca"',
                  'id="brandSelect"', 'id="btnBrandActivate"',
                  'id="btnBrandSave"', 'id="brandNewName"'):
        assert marca not in HTML, marca


def test_o_que_ela_tinha_de_proprio_mudou_de_casa():
    """Formato de saida e os atalhos de identidade nao existiam em nenhum
    outro lugar — sair junto com a tela seria perder funcao."""
    bloco = _bloco_dos_presets()
    assert 'id="exportPresetSelect"' in bloco
    assert 'id="identGrid"' in bloco
    # 5.0.1: a cor virou campo (`#empCor`); fontes e cartao continuam quadros
    for alvo in ('id="empCor"', 'data-ident="fontes"',
                 'data-ident="cartao"'):
        assert alvo in bloco, alvo


def test_link_antigo_para_marca_abre_presets():
    """Botao salvo, atalho, qualquer `setView("marca")` que tenha sobrado."""
    i = JS.index('if (name === "keys") name = "ia";')
    assert 'if (name === "marca") name = "presets";' in JS[i:i + 400]


def test_a_tela_nao_fala_mais_em_marca():
    """So o texto VISIVEL. Os comentarios contam por que a tela mudou —
    e sem eles a proxima pessoa refaz a separacao que acabou de sair."""
    import re

    visivel = re.sub(r"<!--.*?-->", "", _bloco_dos_presets(), flags=re.S)
    assert "marca" not in visivel.lower().replace("marcado", ""), (
        "a palavra que ele pediu para sumir voltou ao texto da tela"
    )


def test_quem_lia_o_seletor_passou_a_ler_a_marca_ativa():
    """`#brandSelect` sumiu; dois lugares liam o valor dele — o iframe do
    editor de estilo e o corpo da importacao."""
    assert "$(\"#brandSelect\")" not in JS
    assert "state.brandActive?.id || null" in JS


# ------------------------------------------------------------------ o formato

@pytest.fixture()
def marcas(tmp_path, monkeypatch):
    from app import brand_kits as bk

    monkeypatch.setattr(bk, "BRANDS_DIR", tmp_path / "brands")
    monkeypatch.setattr(bk, "ACTIVE_PATH", tmp_path / "brands" / "active.json")
    (tmp_path / "brands").mkdir()
    return tmp_path / "brands"


def test_trocar_o_formato_nao_apaga_o_resto_da_marca(marcas):
    """`save_brand` grava `dict(body)` — o corpo do pedido VIRA o arquivo.
    Mandar so o formato por ali levaria junto o estilo base, a cor de
    destaque e o texto do cartao final."""
    from app.brand_kits import set_export_preset

    (marcas / "prime-camp.json").write_text(json.dumps({
        "brandId": "prime-camp", "brandName": "Prime Camp",
        "exportPreset": "reels", "accent": "#e30004",
        "endCardCopy": {"line1": "Segue @lojaprimecamp"},
        "captionStyle": "impacto",
    }, ensure_ascii=False), encoding="utf-8")
    (marcas / "active.json").write_text(
        json.dumps({"activeId": "prime-camp"}), encoding="utf-8")

    set_export_preset("youtube")

    d = json.loads((marcas / "prime-camp.json").read_text(encoding="utf-8"))
    assert d["exportPreset"] == "youtube"
    assert d["accent"] == "#e30004"
    assert d["captionStyle"] == "impacto"
    assert d["endCardCopy"]["line1"] == "Segue @lojaprimecamp"
    assert d["brandName"] == "Prime Camp"


def test_formato_desconhecido_nao_grava(marcas):
    from app.brand_kits import set_export_preset

    (marcas / "padrao.json").write_text(
        json.dumps({"brandId": "padrao", "exportPreset": "reels"}),
        encoding="utf-8")
    (marcas / "active.json").write_text(
        json.dumps({"activeId": "padrao"}), encoding="utf-8")
    with pytest.raises(ValueError):
        set_export_preset("tiktok-vertical-9x16")
    d = json.loads((marcas / "padrao.json").read_text(encoding="utf-8"))
    assert d["exportPreset"] == "reels"


def test_a_rota_conhece_a_acao():
    ls = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = ls.index('if path == "/api/brands":', ls.index("def do_POST"))
    assert 'if action == "format":' in ls[i:i + 800]
