# -*- coding: utf-8 -*-
"""5.0.4: copiar presets de uma empresa para outra.

Ele (04/09): "Quero copiar os presets de uma empresa pra outra sabe".
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import brand_presets as bp  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    bp.create("prime", "Prime Camp [Topo]", style={"edit": "limpa", "accent": "#ff0004"}, content_type="viral", root=tmp_path)
    bp.create("prime", "Prime Camp [YouTube]", style={"edit": "split"}, content_type="informational", root=tmp_path)
    bp.create("crm", "CRM Reels", style={"edit": "limpa"}, root=tmp_path)
    bp.set_default("crm", "crm-reels", root=tmp_path)
    return tmp_path


def test_copia_um_preset_sem_virar_padrao_no_destino(root):
    r = bp.copy_to_brand("prime", "crm", "prime-camp-topo", root=root)
    assert r["copiados"] == [{"id": "prime-camp-topo", "name": "Prime Camp [Topo]"}]
    dest = bp.load("crm", root=root)
    assert dest["activeId"] == "crm-reels", "o padrao do destino nao muda"
    novo = next(p for p in dest["presets"] if p["id"] == "prime-camp-topo")
    assert novo["style"]["accent"] == "#ff0004" and novo["contentType"] == "viral" and not novo["isDefault"]
    assert len(bp.load("prime", root=root)["presets"]) == 3, "a origem fica como estava (padrao + 2)"


def test_copia_todos_e_nao_atropela_nome_igual(root):
    bp.copy_to_brand("prime", "crm", "prime-camp-topo", root=root)
    r = bp.copy_to_brand("prime", "crm", None, root=root)
    nomes = [c["name"] for c in r["copiados"]]
    assert "Prime Camp [Topo] (cópia)" in nomes and "Prime Camp [YouTube]" in nomes
    ids = [p["id"] for p in bp.load("crm", root=root)["presets"]]
    assert len(ids) == len(set(ids)), "ids unicos no destino"


def test_recusa_mesma_empresa_e_preset_inexistente(root):
    with pytest.raises(ValueError, match="mesma empresa"):
        bp.copy_to_brand("prime", "prime", None, root=root)
    with pytest.raises(ValueError, match="não encontrado"):
        bp.copy_to_brand("prime", "crm", "nao-existe", root=root)


def test_a_rota_e_a_tela_oferecem_copiar():
    i = SERVER.index('elif action == "copy":')
    bloco = SERVER[i:i + 900]
    assert "copy_to_brand(brand_id, destino, str(body.get(\"id\") or \"\") or None," in bloco
    assert '"destinoNome": nome' in bloco
    assert 'data-preset-act="copy"' in SJS and 'id="btnPresetsCopiarTodos"' in SHTML
    assert "async function copiarPresetsPara(id, rotulo)" in SJS and "function pedirEmpresa(titulo, empresas)" in SJS
    assert 'await presetAction("copy", { id: id || "", to: destino });' in SJS
    assert 'btnTodos.onclick = () => copiarPresetsPara("", "");' in SJS
