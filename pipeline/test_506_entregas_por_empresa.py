# -*- coding: utf-8 -*-
"""5.0.6: pasta de entrega por empresa (Entregas/<Empresa>/<video>/).

Passo 3 do workspace por empresa que ele pediu (03/09): "os trabalhos
feitos por empresa" reunidos num lugar so, para entregar ao cliente.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import delivery_pack as dp  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


def _projeto(tmp_path, brand):
    proj = tmp_path / "Projetos" / "p1"
    edit = proj / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "final.mp4").write_bytes(b"mp4")
    (edit / "cover.jpg").write_bytes(b"j" * 500)
    (edit / "legenda.txt").write_text("legenda", encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"fase": 3}), encoding="utf-8")
    if brand:
        (edit / "preset-used.json").write_text(json.dumps({"brandId": brand}), encoding="utf-8")
    return proj, edit


def _casa(monkeypatch, tmp_path):
    from app import brand_kits as bk
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "prime.json").write_text(json.dumps({"brandId": "prime", "brandName": "Prime Camp: Centro"}), encoding="utf-8")
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    monkeypatch.setattr(dp, "entregas_root", lambda projects_root=None: (tmp_path / "Entregas"))


def test_o_pack_e_espelhado_em_entregas_da_empresa(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    proj, edit = _projeto(tmp_path, "prime")
    pack = dp.ensure_delivery_pack(edit, stem_override="Troca de tela")
    esp = tmp_path / "Entregas" / "Prime Camp Centro" / "Troca de tela"
    assert pack is not None and esp.is_dir(), "nome da empresa sem os caracteres proibidos do Windows"
    assert sorted(p.name for p in esp.iterdir()) == ["Troca de tela.mp4", "capa.jpg", "legenda.txt"]


def test_renomear_a_manchete_renomeia_o_espelho(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    proj, edit = _projeto(tmp_path, "prime")
    dp.ensure_delivery_pack(edit, stem_override="Nome antigo")
    dp.ensure_delivery_pack(edit, stem_override="Nome novo")
    base = tmp_path / "Entregas" / "Prime Camp Centro"
    assert (base / "Nome novo").is_dir() and not (base / "Nome antigo").exists(), "sem pasta para tras"
    assert (base / "Nome novo" / "Nome novo.mp4").exists()


def test_video_sem_empresa_vai_para_sem_empresa(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    proj, edit = _projeto(tmp_path, "")
    dp.ensure_delivery_pack(edit, stem_override="Solto")
    assert (tmp_path / "Entregas" / "Sem empresa" / "Solto" / "Solto.mp4").exists()


def test_a_pasta_da_empresa_e_pelo_nome_e_a_raiz_fica_ao_lado_dos_projetos(monkeypatch, tmp_path):
    from app import brand_kits as bk
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "crm.json").write_text(json.dumps({"brandId": "crm", "brandName": "Ativa CRM"}), encoding="utf-8")
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    from app import settings_store as ss
    monkeypatch.setattr(ss, "load_settings", lambda: {"entregasRoot": None})
    projetos = tmp_path / "ATIVAVID" / "Projetos"
    projetos.mkdir(parents=True)
    assert dp.entregas_root(projetos) == tmp_path / "ATIVAVID" / "Entregas"
    assert dp.pasta_de_entrega_da_empresa("crm", projetos) == tmp_path / "ATIVAVID" / "Entregas" / "Ativa CRM"
    monkeypatch.setattr(ss, "load_settings", lambda: {"entregasRoot": str(tmp_path / "Drive")})
    assert dp.entregas_root(projetos) == tmp_path / "Drive", "quem quer manda direto para a pasta do Drive"


def test_rotas_e_tela():
    assert 'if path == "/api/entregas/abrir" or path == "/api/entregas/reunir":' in SERVER
    d = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/entregas/abrir",' in d and '"/api/entregas/reunir",' in d
    assert 'id="empEntregas"' in SHTML and 'id="empEntregasReunir"' in SHTML
    assert 'await api("/api/entregas/abrir"' in SJS and 'await api("/api/entregas/reunir"' in SJS
    assert '"entregasRoot": None' in (REPO / "app" / "settings_store.py").read_text(encoding="utf-8")


def test_a_pasta_do_projeto_como_entrada_tambem_acha_a_empresa(monkeypatch, tmp_path):
    """5.0.10: o pack rebuildado com a pasta do PROJETO caia em 'Sem empresa'."""
    _casa(monkeypatch, tmp_path)
    proj, edit = _projeto(tmp_path, "prime")
    pack = dp.ensure_delivery_pack(edit, stem_override="Troca de tela")
    esp = dp.espelhar_na_entrega(proj, pack)
    assert esp == tmp_path / "Entregas" / "Prime Camp Centro" / "Troca de tela"
    assert not (tmp_path / "Entregas" / "Sem empresa").exists()


def test_espelho_perdido_em_sem_empresa_e_adotado(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    proj, edit = _projeto(tmp_path, "prime")
    pack = dp.ensure_delivery_pack(edit, stem_override="Troca de tela")
    perdido = tmp_path / "Entregas" / "Sem empresa" / "Troca de tela"
    perdido.mkdir(parents=True)
    (perdido / "antigo.txt").write_text("x", encoding="utf-8")
    # o espelho certo ainda nao existe: o perdido e MOVIDO, nao duplicado
    import shutil
    shutil.rmtree(tmp_path / "Entregas" / "Prime Camp Centro")
    esp = dp.espelhar_na_entrega(edit, pack)
    assert (esp / "antigo.txt").exists() and (esp / "Troca de tela.mp4").exists()
    assert not perdido.exists()


def test_a_copia_automatica_pode_ser_desligada(monkeypatch, tmp_path):
    """5.0.13: com entregasAuto=false o pack nasce sem espelho; Reunir continua."""
    _casa(monkeypatch, tmp_path)
    from app import settings_store as ss
    monkeypatch.setattr(ss, "load_settings", lambda: {"entregasAuto": False})
    proj, edit = _projeto(tmp_path, "prime")
    pack = dp.ensure_delivery_pack(edit, stem_override="Sem espelho")
    assert pack is not None and not (tmp_path / "Entregas").exists()
    assert dp.espelhar_na_entrega(edit, pack) == tmp_path / "Entregas" / "Prime Camp Centro" / "Sem espelho"
    assert dp.tamanho_do_pack(pack) > 0


def test_reunir_conta_antes_de_copiar():
    i = SERVER.index('so_contar = bool(body.get("dryRun"))')
    bloco = SERVER[i:i + 1800]
    assert "bytes_total += tamanho_do_pack(pack)" in bloco and '"bytes": bytes_total' in bloco
    assert 'body: JSON.stringify({ brandId: b.id, dryRun: true })' in SJS
    assert "Vai copiar cerca de ${peso}" in SJS
    assert 'id="entregasAutoChk"' in SHTML and 'JSON.stringify({ entregasAuto: !!chkAuto.checked })' in SJS
