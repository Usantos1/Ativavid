# -*- coding: utf-8 -*-
"""5.0.2: imagens e videos da Biblioteca por empresa, com o "Comum".

Ele (04/09): "a biblioteca tambem deve ser separada por empresa, nao a de
audio e trilha sonora, isso pode ser padrao pra todas, mas as imagens
devem ser por marca, por empresa".
"""
import json
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import broll_library as bl  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """Biblioteca ao lado de uma raiz de projetos de teste."""
    monkeypatch.setattr(bl, "_sfx_do_usuario_ligado", lambda: False)
    monkeypatch.setattr(bl, "sfx_do_app", lambda: [])
    projetos = tmp_path / "Projetos"
    projetos.mkdir()
    root = bl.library_root(projetos)
    (root / "images" / "bancada-1.jpg").write_bytes(b"x")          # comum (acervo antigo)
    (root / "images" / "prime-camp").mkdir()
    (root / "images" / "prime-camp" / "loja-2.jpg").write_bytes(b"x")
    (root / "images" / "ativa-crm").mkdir()
    (root / "images" / "ativa-crm" / "painel-3.png").write_bytes(b"x")
    (root / "clips" / "prime-camp").mkdir()
    (root / "clips" / "prime-camp" / "humor--patada.mp4").write_bytes(b"x")
    (root / "Trilhas" / "viral--beat.mp3").write_bytes(b"x")
    return projetos, root


def _por_nome(items):
    return {i["name"]: i for i in items}


def test_a_listagem_diz_de_quem_e_cada_arquivo(lib):
    projetos, root = lib
    it = _por_nome(bl.list_assets(projetos)["items"])
    assert it["bancada-1.jpg"]["empresa"] == "" and it["bancada-1.jpg"]["rel"] == "images/bancada-1.jpg"
    assert it["loja-2.jpg"]["empresa"] == "prime-camp" and it["loja-2.jpg"]["rel"] == "images/prime-camp/loja-2.jpg"
    assert it["painel-3.png"]["empresa"] == "ativa-crm"
    assert it["humor--patada.mp4"]["empresa"] == "prime-camp" and it["humor--patada.mp4"]["kind"] == "clip"
    assert it["viral--beat.mp3"]["empresa"] == "" and it["viral--beat.mp3"]["rel"] == "Trilhas/viral--beat.mp3"


def test_da_empresa_e_os_dela_mais_os_comuns(lib):
    projetos, _ = lib
    items = bl.list_assets(projetos)["items"]
    nomes = lambda xs: sorted(i["name"] for i in xs)  # noqa: E731
    assert nomes(bl.da_empresa(items, "prime-camp")) == ["bancada-1.jpg", "humor--patada.mp4", "loja-2.jpg", "viral--beat.mp3"]
    assert nomes(bl.da_empresa(items, "ativa-crm")) == ["bancada-1.jpg", "painel-3.png", "viral--beat.mp3"]
    assert nomes(bl.da_empresa(items, "")) == nomes(items), "sem empresa vale tudo (projeto antigo)"


def test_o_broll_e_o_humor_respeitam_a_empresa(lib):
    projetos, _ = lib
    assert sorted(i["name"] for i in bl.pick_for_query("loja", projetos, brand_id="ativa-crm")) == ["bancada-1.jpg", "painel-3.png"]
    assert "loja-2.jpg" in [i["name"] for i in bl.pick_for_query("loja", projetos, brand_id="prime-camp")]
    assert [i["name"] for i in bl.clipes_de_humor(projetos, brand_id="prime-camp")] == ["humor--patada.mp4"]
    assert bl.clipes_de_humor(projetos, brand_id="ativa-crm") == []


def test_adicionar_guarda_na_pasta_da_empresa_ou_no_comum(lib):
    projetos, root = lib
    r = bl.add_bytes("foto.jpg", b"jpg", projects_root=projetos, empresa="Ativa CRM")
    assert r["empresa"] == "ativa-crm" and r["rel"].startswith("images/ativa-crm/")
    assert (root / r["rel"]).exists()
    r2 = bl.add_bytes("foto.jpg", b"jpg", projects_root=projetos)
    assert r2["empresa"] == "" and r2["rel"].startswith("images/") and "/" not in r2["rel"][7:]
    r3 = bl.add_bytes("beat.mp3", b"mp3", projects_root=projetos, empresa="ativa-crm")
    assert r3["empresa"] == "" and r3["rel"] == "Trilhas/beat.mp3", "som e comum a todas"


def test_mover_muda_o_dono_e_a_categoria_continua_funcionando(lib):
    projetos, root = lib
    r = bl.mover_para_empresa("images/bancada-1.jpg", "prime-camp", projects_root=projetos)
    assert r["rel"] == "images/prime-camp/bancada-1.jpg" and (root / r["rel"]).exists()
    r = bl.mover_para_empresa(r["rel"], "", projects_root=projetos)
    assert r["rel"] == "images/bancada-1.jpg", "de volta para o Comum"
    c = bl.set_categoria("images/prime-camp/loja-2.jpg", "loja", projects_root=projetos)
    assert c["rel"] == "images/prime-camp/loja--loja-2.jpg", "rel relativo a raiz, nao so ao pai"
    with pytest.raises(ValueError):
        bl.mover_para_empresa("Trilhas/viral--beat.mp3", "prime-camp", projects_root=projetos)


def test_a_marca_do_projeto_vem_do_edit(tmp_path):
    edit = tmp_path / "p" / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    assert bl.marca_do_projeto(public) == ""
    (edit / "job_intent.json").write_text(json.dumps({"brandId": "loja"}), encoding="utf-8")
    assert bl.marca_do_projeto(public) == "loja"
    (edit / "preset-used.json").write_text(json.dumps({"brandId": "camp"}), encoding="utf-8")
    assert bl.marca_do_projeto(public) == "camp"


def test_o_pipeline_e_o_servidor_passam_a_empresa():
    assert 'brand_id=str(preset.get("brandId") or ""))' in RUN
    assert 'humor_com_acervo = bool(clipes_de_humor(\n                    raiz_projetos, brand_id=str(preset.get("brandId") or "")))' in RUN
    assert 'if path == "/api/library/mover":' in SERVER
    assert 'empresa=_emp or None)' in SERVER
    assert '"/api/library/mover",' in (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    i = (REPO / "app" / "broll_library.py").read_text(encoding="utf-8").index("if prefer_library:")
    assert "brand_id = marca_do_projeto(public_dir)" in (REPO / "app" / "broll_library.py").read_text(encoding="utf-8")[i:i + 300]


def test_a_tela_tem_o_seletor_de_quem_e_sobe_para_a_empresa_ativa():
    assert 'id="libraryDono"' in SHTML
    assert "function renderLibraryDono(" in SJS and "function libSeletorDono(" in SJS
    assert 'chip("comum", "Só Comum", nComum)' in SJS
    assert 'const emp = visual && state.libDono !== "comum" ? ativa : "";' in SJS
    assert 'emp ? `empresa=${encodeURIComponent(emp)}` : ""' in SJS
    assert 'await api("/api/library/mover", {' in SJS
    assert 'if (dono === "comum") return !i.empresa;' in SJS
    assert 'return !i.empresa || i.empresa === ativa;' in SJS


def test_o_editor_so_ve_o_acervo_da_empresa_do_video():
    assert ".filter((it) => !bidProj || !it.empresa || it.empresa === bidProj);" in PJS
    assert "&empresa=${encodeURIComponent(bidProj)}" in PJS
