# -*- coding: utf-8 -*-
""""cade a fonte Integral que pedi pra voce instalar?" (30/08).

Estava instalada desde 29/08 — `Fontspring-DEMO-integralcf-bold.otf`, na
pasta certa, funcionando. A LISTA e que nao dizia: a unica opcao se
chamava "Sua fonte (pasta Fontes)", e nenhuma tela mostrava qual fonte
era essa. Atras disso havia um limite calado: o pipeline pegava o
primeiro arquivo em ordem alfabetica, entao a segunda fonte da pasta
nunca tocava.

Agora cada fonte tem sua linha, com o nome que ela mesma declara
(`Fontspring-DEMO-integralcf-bold.otf` -> "FONTSPRING DEMO - Integral CF
Bold"), e o id pode nomear qual usar.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import fontes  # noqa: E402

ED = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _pasta(tmp_path, monkeypatch) -> Path:
    p = tmp_path / "Fontes"
    p.mkdir()
    monkeypatch.setattr(fontes, "pasta", lambda: p)
    return p


def test_a_primeira_continua_respondendo_pelo_id_antigo(tmp_path, monkeypatch):
    """Estilo salvo antes desta versao guarda `arquivo` puro. Ele tem de
    cair exatamente na mesma fonte de sempre — a primeira da pasta."""
    p = _pasta(tmp_path, monkeypatch)
    (p / "b-segunda.ttf").write_bytes(b"\x00")
    (p / "a-primeira.otf").write_bytes(b"\x00")
    assert fontes.escolher("arquivo").name == "a-primeira.otf"


def test_o_id_pode_nomear_a_fonte(tmp_path, monkeypatch):
    p = _pasta(tmp_path, monkeypatch)
    (p / "b-segunda.ttf").write_bytes(b"\x00")
    (p / "a-primeira.otf").write_bytes(b"\x00")
    assert fontes.escolher("arquivo:b-segunda.ttf").name == "b-segunda.ttf"


def test_fonte_apagada_nao_derruba_o_render(tmp_path, monkeypatch):
    """Render nao para por causa de fonte: cai na primeira."""
    p = _pasta(tmp_path, monkeypatch)
    (p / "a-primeira.otf").write_bytes(b"\x00")
    assert fontes.escolher("arquivo:sumiu.ttf").name == "a-primeira.otf"


def test_pasta_vazia_devolve_nada(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    assert fontes.escolher("arquivo") is None
    assert fontes.listar() == []


def test_id_de_outra_familia_nao_e_da_pasta(tmp_path, monkeypatch):
    _pasta(tmp_path, monkeypatch)
    assert fontes.escolher("poppins") is None


def test_arquivo_quebrado_entra_na_lista_pelo_nome_do_arquivo(tmp_path, monkeypatch):
    """Sumir da lista seria pior: ele nao entenderia por que a fonte que
    acabou de copiar nao aparece."""
    p = _pasta(tmp_path, monkeypatch)
    (p / "nao-e-fonte.ttf").write_bytes(b"isto nao e uma fonte")
    lista = fontes.listar()
    assert [f["arquivo"] for f in lista] == ["nao-e-fonte.ttf"]
    assert lista[0]["nome"] == "nao-e-fonte"


def test_o_nome_sai_de_dentro_do_arquivo():
    """Na maquina dele: e ai que a palavra "Integral" aparece."""
    real = Path.home() / "ATIVAVID" / "Fontes"
    achados = [f for f in (real.iterdir() if real.is_dir() else [])
               if f.suffix.lower() in fontes.EXTS]
    if not achados:
        return
    nomes = [f["nome"] for f in fontes.listar()]
    assert any(n and n != Path(a.name).stem
               for n, a in zip(nomes, achados)), nomes


def test_o_pipeline_aceita_o_id_com_nome():
    i = RF.index("def _apply_brand_fonts(")
    bloco = RF[i:RF.index("\ndef ", i + 10)]
    assert 'startswith("arquivo:")' in bloco
    i = RF.index("def _attach_brand_font_file(")
    bloco = RF[i:RF.index("\ndef ", i + 10)]
    assert "escolher_fonte(ids[uses[0]])" in bloco
    assert 'v.lower().startswith("arquivo")' in bloco


def test_os_dois_motores_leem_o_mesmo_id():
    rp = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert 'ident.startswith("arquivo")' in rp
    ts = (REPO / "assets" / "shortform" / "src" / "fonts.ts").read_text(encoding="utf-8")
    assert "id.startsWith('arquivo:')" in ts


def test_a_tela_lista_as_fontes_pelo_nome():
    assert "async function carregarFontesDoUsuario()" in ED
    i = ED.index("async function carregarFontesDoUsuario()")
    bloco = ED[i:i + 1400]
    assert "'/api/fontes'" in bloco
    assert "'autoCapFont', 'autoHlFont'" in bloco
    # a primeira mantem o id antigo
    assert "i === 0 ? 'arquivo'" in bloco
    assert "carregarFontesDoUsuario().catch" in ED


def test_a_rota_existe_no_servidor_e_no_app():
    srv = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert '"/api/fontes"' in srv
    app = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/fontes"' in app, "rota nova nasce gateada se nao entrar aqui"
