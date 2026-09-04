# -*- coding: utf-8 -*-
"""5.0.23: o estilo base da empresa tem de chegar ao vídeo.

Ele (04/09, terceira vez no mesmo assunto): "ele escolhe o preset certo do
cliente, edita o vídeo, quando clica em editar ou refaz o vídeo está com
uma legenda vermelha, não fica salvo as cores do preset que ele definiu.
Ele já refez tudo, já excluiu a empresa, já criou novamente. E sempre
volta com a cor vermelho padrão, e o tipo de legenda ali padrão vermelho
que é aquela empilhada".

Medido no fluxo real: um preset nasce com uma CÓPIA INTEIRA do estilo do
momento (`brand_presets.create` faz `style_snapshot` do estilo base). A
cadeia do render é app -> empresa -> preset -> projeto, então o preset
congelado passava por cima do estilo base — e a tela de Estilos promete
"vale para todos os presets desta empresa".

Duas correções, e este arquivo cobre as duas:
  1. a empresa nova não nasce mais com uma cópia do modelo empacotado;
  2. salvar o estilo base grava NA EMPRESA e leva a mudança aos presets
     que ainda seguiam o valor antigo (quem tem valor próprio continua
     mandando).
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import brand_kits as bk  # noqa: E402
from app import brand_presets as bp  # noqa: E402
from app import preset_chain  # noqa: E402

PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")

# O que vinha do modelo empacotado e reaparecia no vídeo dele
VERMELHO = {"captions": "stacked", "headline": "realce", "edit": "limpa",
            "accent": "#e30004", "captionAccent": "#FFFFFF",
            "emphasisAccent": "#FF0000"}
# O que ele escolheu para o cliente
DELE = {"captions": "marcador", "accent": "#aa855a",
        "captionAccent": "#FFFFFF", "emphasisAccent": "#020080"}


@pytest.fixture
def casa(monkeypatch, tmp_path):
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "padrao.json").write_text(
        json.dumps({"brandId": "padrao", "brandName": "Padrão", **VERMELHO}),
        encoding="utf-8")
    (brands / "active.json").write_text('{"activeId": "padrao"}', encoding="utf-8")
    monkeypatch.setattr(bk, "USER_DIR", tmp_path)
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    monkeypatch.setattr(bk, "ACTIVE_PATH", brands / "active.json")
    monkeypatch.setattr(bk, "LOGOS_DIR", brands / "logos")
    monkeypatch.setattr(bk, "USER_PRESET", tmp_path / "default-style.json")
    monkeypatch.setattr(bk, "PREVIEW", tmp_path / "preview")   # não tocar no pacote
    monkeypatch.setattr(bk, "ensure_brands_dir", lambda: None)
    monkeypatch.setattr(bp, "PRESETS_DIR", tmp_path / "brand-presets")
    return brands


def _marca(casa, bid):
    return json.loads((casa / f"{bid}.json").read_text(encoding="utf-8-sig"))


def _preset(bid, pid):
    p = next(x for x in bp.load(bid)["presets"] if x["id"] == pid)
    return p.get("style") or {}


def test_empresa_nova_nao_nasce_com_o_estilo_do_modelo(casa):
    """A empresa guarda identidade. O visual vem do app e dos presets."""
    r = bk.create_brand("Santos e Souza Advogados")
    d = _marca(casa, r["id"])
    for k in ("captions", "headline", "edit"):
        assert k not in d, f"a empresa nova congelou `{k}` do modelo"
    assert d["exportPreset"] == "reels", "o formato de saída precisa continuar"
    assert d["brandName"] == "Santos e Souza Advogados"


def test_o_estilo_base_alcanca_o_preset_que_seguia_o_valor_antigo(casa):
    bid = bk.create_brand("Santos e Souza", "#aa855a")["id"]
    # o preset nasce com a cópia inteira do estilo do momento — é o que a
    # tela de Presets manda em "Novo preset"
    pid = bp.create(bid, "Cliente", style=dict(VERMELHO))["activeId"]
    r = bk.update_brand_style(bid, dict(DELE))
    assert r["presetsAtualizados"] >= 2

    est = _preset(bid, pid)
    assert est["captions"] == "marcador", "o preset ficou com a legenda empilhada"
    assert est["emphasisAccent"] == "#020080", "o preset ficou com o vermelho"


def test_preset_com_ajuste_proprio_continua_mandando(casa):
    bid = bk.create_brand("Cliente")["id"]
    proprio = {**VERMELHO, "captions": "impacto", "emphasisAccent": "#1a842f"}
    pid = bp.create(bid, "Anúncio", style=proprio)["activeId"]
    bk.update_brand_style(bid, dict(DELE))
    est = _preset(bid, pid)
    assert est["captions"] == "impacto", "atropelou o preset ajustado de propósito"
    assert est["emphasisAccent"] == "#1a842f"
    # o que ele NÃO tinha mexido acompanha a base
    assert est["accent"] == "#aa855a"


def test_a_cor_e_a_legenda_salvas_chegam_ao_render(casa, tmp_path):
    """A prova do caminho inteiro: app -> empresa -> preset -> projeto."""
    bid = bk.create_brand("Santos e Souza", "#aa855a")["id"]
    pid = bp.create(bid, "Cliente", style=dict(VERMELHO))["activeId"]
    bk.update_brand_style(bid, dict(DELE))

    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    (edit / "editing_intent.json").write_text(
        json.dumps({"brandId": bid, "brandPresetId": pid}), encoding="utf-8")
    usado = preset_chain.resolve_for_edit(
        edit, job={"brandId": bid}, app_default=dict(VERMELHO),
        presets_root=tmp_path / "brand-presets", write=False)
    assert usado["captions"] == "marcador", "o vídeo sai empilhado"
    assert usado["emphasisAccent"] == "#020080", "o vídeo sai vermelho"


def test_salvar_o_estilo_preserva_nome_logo_e_perfil(casa):
    """`save_brand` grava o corpo inteiro e apagaria tudo isso."""
    bid = bk.create_brand("Cliente")["id"]
    d0 = _marca(casa, bid)
    d0.update({"empresa": "Advocacia", "perfil": {"tom": "sério"}})
    (casa / f"{bid}.json").write_text(json.dumps(d0), encoding="utf-8")
    bk.update_brand_style(bid, {**DELE, "brandName": "OUTRO NOME"})
    d = _marca(casa, bid)
    assert d["brandName"] == "Cliente", "o Salvar do estilo renomeou a empresa"
    assert d["empresa"] == "Advocacia" and d["perfil"] == {"tom": "sério"}
    assert d["captions"] == "marcador"


def test_a_tela_de_estilo_salva_na_empresa():
    i = PJS.index("// COM EMPRESA, o estilo base e DELA")
    bloco = PJS[i:i + 900]
    assert "action: 'estilo'" in bloco and "'/api/brands'" in bloco
    assert '"/api/brands"' in SRV or "'/api/brands'" in SRV
    assert "update_brand_style(" in SRV, "a rota do estilo da empresa sumiu"


def test_o_preset_vazio_leva_a_cor_da_empresa_para_o_editor(casa):
    """`resolved`: o estilo CHEIO que o vídeo teria com aquele preset.

    Toda empresa nasce com um preset "Padrão" VAZIO. Escolher esse preset
    no editor fazia `Object.assign` de nada — a tela seguia com a cor do
    vídeo anterior e o "Salvar e refazer" congelava essa cor no projeto,
    que é a camada mais forte da cadeia.
    """
    from app import local_server as srv

    bid = bk.create_brand("Santos e Souza", "#aa855a")["id"]
    bk.update_brand_style(bid, dict(DELE))
    pack = bp.load(bid)
    assert pack["presets"][0]["style"] == {}, "o preset que nasce junto não é vazio"

    srv._resolver_presets(pack, bid)
    cheio = pack["presets"][0]["resolved"]
    assert cheio["captions"] == "marcador"
    assert cheio["emphasisAccent"] == "#020080"
    assert cheio["accent"] == "#aa855a"
    for k in ("brandId", "brandName", "note"):
        assert k not in cheio, f"`{k}` não é estilo e ia sujar a tela"


def test_o_editor_usa_o_estilo_cheio_ao_trocar_de_preset():
    i = PJS.index("function trocarPresetDoVideo(")
    corpo = PJS[i:i + 1400]
    assert "p.resolved || p.style" in corpo, (
        "escolher um preset vazio volta a não mudar nada na tela")
    assert "const cta = est.endCardCopy" in corpo, "o CTA ficou para trás"


def test_pintar_presets_poe_a_cor_da_empresa_em_todos(casa):
    """O reparo do que já está gravado.

    Nas empresas reais dele os presets carregam vermelhos que não batem
    nem com a fábrica nem com a base (`#ff0004`, `#FF0000`) — herança de
    versões antigas. Nenhuma regra automática sabe se aquilo foi escolha,
    então quem diz é ele, por botão.
    """
    bid = bk.create_brand("Santos e Souza", "#aa855a")["id"]
    p1 = bp.create(bid, "Cliente", style={**VERMELHO, "accent": "#ff0004"})["activeId"]
    p2 = bp.create(bid, "Anúncio", style={"emphasisAccent": "#FF0000",
                                          "circleAccent": "#FF0000"})["activeId"]
    r = bk.pintar_presets(bid)
    assert r["cor"] == "#aa855a" and r["presets"] >= 2

    a = _preset(bid, p1)
    assert a["accent"] == "#aa855a" and a["emphasisAccent"] == "#aa855a"
    assert a["captions"] == "stacked", "pintar a cor mexeu no resto do preset"
    b = _preset(bid, p2)
    assert b["circleAccent"] == "#aa855a", "o círculo do empilhado ficou vermelho"


def test_pintar_sem_cor_de_destaque_avisa(casa):
    bid = bk.create_brand("Sem cor")["id"]
    with pytest.raises(ValueError):
        bk.pintar_presets(bid)


def test_o_botao_de_pintar_existe_na_tela_de_empresas():
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'id="btnPresetsPintar"' in html
    assert "wirePintarPresets()" in js, "o botão ficaria sem ação"
    assert 'action: "pintar"' in js


def test_o_video_pode_voltar_ao_estilo_do_preset():
    """O estilo ajustado NO VÍDEO é a camada mais forte da cadeia.

    Um vídeo editado antes de acertar a cor da empresa ficava com a cor
    velha congelada em `preview_style.json`, e nem escolher o preset de
    novo o tirava de lá: trocar para o MESMO preset não dispara `change`.
    """
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnUsarPreset"' in html
    i = PJS.index("const voltar = document.getElementById('btnUsarPreset')")
    corpo = PJS[i:i + 1200]
    assert "pedirConfirmacao(" in corpo, "troca o estilo do vídeo sem avisar"
    assert "trocarPresetDoVideo(alvo.id)" in corpo
    assert "Salvar e refazer" in corpo, "não diz que falta salvar"
