# -*- coding: utf-8 -*-
"""5.0.1: tela de Empresas (era Presets): criar, editar, apagar, logo.

Ele (04/09): "onde eu vou criar ou editar as empresas?" — nao tinha onde.
"tornar o presets como se fosse... uma empresa; cada empresa ter os seus
presets, estilo, hashtag; esta bem confuso como vou trocar de empresa".
"""
import base64
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import brand_kits as bk  # noqa: E402

SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


@pytest.fixture
def casa(monkeypatch, tmp_path):
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "padrao.json").write_text(json.dumps({"brandId": "padrao", "brandName": "Padrão", "exportPreset": "reels"}), encoding="utf-8")
    (brands / "active.json").write_text(json.dumps({"activeId": "padrao"}), encoding="utf-8")
    monkeypatch.setattr(bk, "USER_DIR", tmp_path)
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    monkeypatch.setattr(bk, "ACTIVE_PATH", brands / "active.json")
    monkeypatch.setattr(bk, "LOGOS_DIR", brands / "logos")
    monkeypatch.setattr(bk, "USER_PRESET", tmp_path / "default-style.json")
    monkeypatch.setattr(bk, "PREVIEW", tmp_path / "preview-inexistente")
    monkeypatch.setattr(bk, "ensure_brands_dir", lambda: None)
    from app import brand_presets as bp
    monkeypatch.setattr(bp, "PRESETS_DIR", tmp_path / "brand-presets")
    return brands


# ------------------------------------------------------------- criar
def test_criar_empresa_nasce_do_estilo_padrao_e_nao_atropela(casa):
    r = bk.create_brand("Prime Camp", "#e30004")
    assert r["id"] == "prime-camp" and r["name"] == "Prime Camp"
    d = json.loads((casa / "prime-camp.json").read_text(encoding="utf-8"))
    assert d["accent"] == "#e30004" and d["exportPreset"] == "reels"
    assert "perfil" not in d and "empresa" not in d, "empresa nova nao herda o perfil de outra"
    with pytest.raises(ValueError, match="Já existe"):
        bk.create_brand("Prime Camp")
    with pytest.raises(ValueError, match="nome"):
        bk.create_brand("   ")
    assert any(b["id"] == "prime-camp" for b in bk.list_brands())


def test_a_listagem_traz_logo_presets_e_perfil(casa):
    bk.create_brand("Loja")
    (casa / "loja.json").write_text(json.dumps({"brandId": "loja", "brandName": "Loja", "perfil": {"vende": "capas"}}), encoding="utf-8")
    b = next(x for x in bk.list_brands() if x["id"] == "loja")
    assert b["perfilOk"] is True and b["presetCount"] >= 1 and b["logoUrl"] == ""
    p = next(x for x in bk.list_brands() if x["id"] == "padrao")
    assert p["perfilOk"] is False


# ------------------------------------------------------------ editar
def test_editar_troca_nome_e_cor_sem_apagar_o_resto(casa):
    (casa / "padrao.json").write_text(json.dumps({
        "brandId": "padrao", "brandName": "Padrão", "exportPreset": "youtube",
        "endCardCopy": {"line1": "Segue"}, "perfil": {"vende": "x"}, "accent": "#111111"}), encoding="utf-8")
    r = bk.update_brand("padrao", {"name": "Uander", "accent": "#00ff00"})
    d = json.loads((casa / "padrao.json").read_text(encoding="utf-8"))
    assert r["name"] == "Uander" and d["accent"] == "#00ff00"
    assert d["exportPreset"] == "youtube" and d["endCardCopy"]["line1"] == "Segue" and d["perfil"] == {"vende": "x"}
    bk.update_brand("padrao", {"accent": "roxo"})
    assert "accent" not in json.loads((casa / "padrao.json").read_text(encoding="utf-8")), "cor invalida = sem cor"
    with pytest.raises(ValueError):
        bk.update_brand("nao-existe", {"name": "x"})


# ------------------------------------------------------------ apagar
def test_apagar_leva_logo_e_presets_mas_nunca_a_ultima(casa, tmp_path):
    from app import brand_presets as bp
    bk.create_brand("Loja")
    bp.create("loja", "Loja - Reels", style={})
    assert (tmp_path / "brand-presets" / "loja.json").exists()
    png = base64.b64encode(b"\x89PNG fake").decode()
    bk.set_logo("loja", f"data:image/png;base64,{png}")
    assert (casa / "logos" / "loja.png").exists()
    bk.activate_brand("loja")
    r = bk.delete_brand("loja")
    assert r["removed"] == "loja" and r["activeId"] == "padrao", "apagar a ativa volta para a padrao"
    assert not (casa / "loja.json").exists()
    assert not (casa / "logos" / "loja.png").exists()
    assert not (tmp_path / "brand-presets" / "loja.json").exists()
    with pytest.raises(ValueError, match="única"):
        bk.delete_brand("padrao")


# -------------------------------------------------------------- logo
def test_logo_aceita_png_jpg_webp_e_recusa_o_resto(casa):
    b64 = base64.b64encode(b"x" * 10).decode()
    bk.set_logo("padrao", f"data:image/jpeg;base64,{b64}")
    assert bk.logo_path("padrao").suffix == ".jpg"
    bk.set_logo("padrao", f"data:image/webp;base64,{b64}")
    assert bk.logo_path("padrao").suffix == ".webp", "o logo anterior sai"
    assert not (casa / "logos" / "padrao.jpg").exists()
    assert "/api/brands/logo?id=padrao&v=" in next(x for x in bk.list_brands() if x["id"] == "padrao")["logoUrl"]
    with pytest.raises(ValueError, match="PNG, JPG ou WebP"):
        bk.set_logo("padrao", "data:image/gif;base64,AAAA")
    with pytest.raises(ValueError, match="3 MB"):
        bk.set_logo("padrao", "data:image/png;base64," + base64.b64encode(b"x" * (bk.LOGO_MAX_BYTES + 1)).decode())
    bk.remove_logo("padrao")
    assert bk.logo_path("padrao") is None


# --------------------------------------------------------------- tela
def test_as_acoes_chegam_no_servidor():
    i = SERVER.index('if path == "/api/brands":\n            from app.brand_kits import (\n                activate_brand, create_brand')
    bloco = SERVER[i:i + 2200]
    for a in ("create", "update", "delete", "logo", "logo_remove"):
        assert f'elif action == "{a}":' in bloco, a
    assert 'if path == "/api/brands/logo":' in SERVER
    assert '"/api/brands/logo",' in (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")


def test_a_tela_de_empresas_tem_cards_identidade_perfil_e_presets():
    i = SHTML.index('id="view-presets"')
    bloco = SHTML[i:SHTML.index('id="view-ia"', i)]
    assert 'id="empCards"' in bloco
    for k in ("empNome", "empCor", "empLogoInput", "empSalvar", "empApagar", "exportPresetSelect",
              "rotPerfilGrid", "rotPerfilDosVideos", "rotEmpresaSalvar", "btnPresetNovo", "presetList"):
        assert f'id="{k}"' in bloco, k
    assert '<span class="sb-txt">Empresas</span>' in SHTML and '<span class="sb-txt">Presets</span>' not in SHTML
    assert 'data-ws="empresas"' in SHTML, "o menu do rodape leva para a tela"
    # a caixa saiu do Roteiro; o link so aponta para Empresas
    r = SHTML.index('id="view-roteiro"')
    rot = SHTML[r:SHTML.index('id="view-presets"', r)]
    assert 'id="rotPerfilGrid"' not in rot
    assert 'id="rotEmpresaAbrir" data-view="presets"' in rot


def test_a_tela_cria_ativa_edita_e_apaga_pela_api():
    assert "function renderEmpresaCards()" in SJS and "function wireEmpresas()" in SJS
    assert 'empresaAction({ action: "create", name: nome.trim() })' in SJS
    assert 'empresaAction({ action: "update", id, name: $("#empNome")?.value || "", accent: $("#empCor")?.value || "" })' in SJS
    assert 'empresaAction({ action: "delete", id: b.id })' in SJS
    assert 'empresaAction({ action: "logo", id, dataUrl: String(rd.result || "") })' in SJS
    assert "await ativarEmpresa(card.dataset.emp);" in SJS, "clicar no card ativa a empresa"
    assert 'if (acao === "empresas") return setView("presets");' in SJS
    assert 'presets: ["Empresas",' in SJS
    # o perfil grava na empresa ATIVA, nao na do ultimo pack do roteiro
    assert 'const bid = (state.brandActive && state.brandActive.id) || state.roteiro.brandId;' in SJS
    assert "loadEmpresaUi().catch(() => {});" in SJS
