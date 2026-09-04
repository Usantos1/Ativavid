# -*- coding: utf-8 -*-
"""5.0.22: a cor da empresa tem de chegar ao vídeo (e não voltar ao vermelho).

Ele (04/09, com print de "Santos e Souza Advogados", cor #aa855a, e o
vídeo saindo com faixa VERMELHA): "esse foi mudando a cor do estilo e
refeito e voltou vermelho, a cor que o cliente escolheu era outra".

Medido: `assets/brands/padrao.json` (o modelo empacotado) traz
`emphasisAccent: #FF0000`, e `create_brand`/`update_brand` só escreviam
`accent`. Como a cadeia é app → empresa → preset → projeto, e o preset de
uma empresa nova nasce com estilo VAZIO, o vermelho da empresa chegava ao
render.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import brand_kits as bk  # noqa: E402
from app import preset_chain  # noqa: E402

PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


@pytest.fixture
def casa(monkeypatch, tmp_path):
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "padrao.json").write_text(json.dumps({
        "brandId": "padrao", "brandName": "Padrão"}), encoding="utf-8")
    (brands / "active.json").write_text(json.dumps({"activeId": "padrao"}), encoding="utf-8")
    monkeypatch.setattr(bk, "USER_DIR", tmp_path)
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    monkeypatch.setattr(bk, "ACTIVE_PATH", brands / "active.json")
    monkeypatch.setattr(bk, "LOGOS_DIR", brands / "logos")
    monkeypatch.setattr(bk, "USER_PRESET", tmp_path / "default-style.json")
    monkeypatch.setattr(bk, "ensure_brands_dir", lambda: None)
    from app import brand_presets as bp
    monkeypatch.setattr(bp, "PRESETS_DIR", tmp_path / "brand-presets")
    return brands


def _lido(casa, bid):
    return json.loads((casa / f"{bid}.json").read_text(encoding="utf-8-sig"))


def test_o_modelo_empacotado_realmente_traz_o_vermelho():
    """Se esta premissa mudar, o resto deste arquivo perde o sentido."""
    semente = json.loads((REPO / "assets" / "brands" / "padrao.json")
                         .read_text(encoding="utf-8-sig"))
    assert semente.get("emphasisAccent", "").upper() == "#FF0000"


def test_empresa_nova_com_cor_nao_herda_o_realce_vermelho(casa, monkeypatch):
    monkeypatch.setattr(bk, "_estilo_semente", lambda: {
        "accent": "#e30004", "captionAccent": "#FFFFFF",
        "emphasisAccent": "#FF0000", "captions": "stacked"})
    r = bk.create_brand("Santos e Souza Advogados", "#aa855a")
    d = _lido(casa, r["id"])
    assert d["accent"] == "#aa855a"
    assert d["emphasisAccent"] == "#aa855a", "o realce ficou vermelho no video"
    assert d["captionAccent"] == "#FFFFFF", "a cor do TEXTO da legenda continua branca"


def test_salvar_a_identidade_repinta_o_realce(casa, monkeypatch):
    """O conserto para quem ja criou a empresa: salvar a cor de novo."""
    monkeypatch.setattr(bk, "_estilo_semente", lambda: {
        "accent": "#e30004", "emphasisAccent": "#FF0000", "circleAccent": "#FF0000"})
    bk.create_brand("Cliente")
    d = _lido(casa, "cliente")
    assert d["emphasisAccent"] == "#FF0000"        # nasceu vermelha (sem cor)
    bk.update_brand("cliente", {"accent": "#aa855a"})
    d = _lido(casa, "cliente")
    assert d["accent"] == "#aa855a" and d["emphasisAccent"] == "#aa855a"
    assert d["circleAccent"] == "#aa855a", "o circulo do empilhado acompanha"


def test_a_cor_da_empresa_chega_ao_render_quando_o_preset_nao_manda(casa, monkeypatch):
    """A prova do caminho inteiro: app → empresa → preset (vazio) → projeto."""
    monkeypatch.setattr(bk, "_estilo_semente", lambda: {
        "accent": "#e30004", "emphasisAccent": "#FF0000"})
    bk.create_brand("Santos e Souza", "#aa855a")
    marca = _lido(casa, "santos-e-souza")
    resolvido = preset_chain.resolve(
        app_default={"accent": "#e30004", "emphasisAccent": "#FF0000"},
        brand=marca, brand_preset=None, project=None)
    assert resolvido["emphasisAccent"] == "#aa855a", (
        "o realce do video sai vermelho mesmo com a cor escolhida")
    # e um preset com cor propria continua mandando (nada muda para quem ja
    # ajustou o preset)
    com_preset = preset_chain.resolve(
        app_default={"accent": "#e30004", "emphasisAccent": "#FF0000"},
        brand=marca, brand_preset={"emphasisAccent": "#1a842f"}, project=None)
    assert com_preset["emphasisAccent"] == "#1a842f"


def test_a_barra_de_presets_comeca_no_preset_do_video():
    i = PJS.index("const wantId = (!HOUSE_STYLE && !HUB_EMBED)")
    bloco = PJS[i - 700:i + 260]
    assert "S.presetUsed.brandPresetId || S.presetUsed.presetId" in bloco
    assert "presets.some((p) => p.id === doVideo) ? doVideo" in bloco, (
        "a barra continua mostrando o primeiro preset da lista")
