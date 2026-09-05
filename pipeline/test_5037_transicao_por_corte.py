# -*- coding: utf-8 -*-
"""5.0.37: transição escolhida POR CORTE, na régua do editor.

Pedido dele de 01-02/09 ("um profissional pode fazer inserções, cortes,
efeitos… adicionar esse recurso também ali no editor"). Até aqui a
transição era uma só por vídeo, vinda do estilo; o editor nem sabia que
transições existiam.

Como funciona:
  - a régua desenha um losango em cada emenda entre trechos mantidos;
  - clicar nele abre um menu com os mesmos tipos do estilo, mais "Nenhuma
    neste corte" e "Como o estilo manda";
  - a escolha vai para `edit-data.json` (`transicoesPorCorte[i]`) pela op
    `set_transicao_corte`, que marca o estilo como sujo (é desenho);
  - o pipeline refaz as transições a cada render e aplica as escolhas do
    edit-data ANTERIOR por cima — como faz com os inserts manuais.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transicoes import CHAVE_POR_CORTE, aplicar_por_corte  # noqa: E402

FAST = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")

BASE = [{"at": 3.0, "type": "flash"}, {"at": 7.5, "type": "flash"}, {"at": 12.0, "type": "flash"}]


def test_sem_escolhas_nada_muda():
    assert aplicar_por_corte(BASE, None) == BASE
    assert aplicar_por_corte(BASE, {}) == BASE


def test_escolha_troca_so_a_emenda_marcada():
    out = aplicar_por_corte(BASE, {"1": "faixa"})
    assert [t["type"] for t in out] == ["flash", "faixa", "flash"]
    assert out[1]["at"] == 7.5


def test_nenhuma_tira_a_emenda_e_desconhecido_e_ignorado():
    out = aplicar_por_corte(BASE, {"0": "nenhuma", "2": "explosao", "9": "faixa"})
    assert [t["type"] for t in out] == ["flash", "flash"]
    assert out[0]["at"] == 7.5


def test_a_lista_original_nao_e_alterada():
    copia = [dict(t) for t in BASE]
    aplicar_por_corte(BASE, {"0": "faixa"})
    assert BASE == copia


def _edit(tmp_path):
    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "remotion" / "public" / "edit-data.json").write_text(
        json.dumps({"hook": {"enabled": True}}), encoding="utf-8")
    return edit


def test_a_op_grava_no_edit_data_e_marca_sujo(tmp_path):
    from app.quick_corrections import set_transicao_corte

    edit = _edit(tmp_path)
    r = set_transicao_corte(edit, 1, "faixa")
    assert r["ok"] and r[CHAVE_POR_CORTE] == {"1": "faixa"}
    dado = json.loads((edit / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8-sig"))
    assert dado[CHAVE_POR_CORTE] == {"1": "faixa"}
    assert dado["hook"] == {"enabled": True}, "apagou o resto do edit-data"
    corr = json.loads((edit / "corrections.json").read_text(encoding="utf-8-sig"))
    assert (corr.get("dirty") or {}).get("style"), "sem sujo, o vídeo não é refeito"


def test_tipo_vazio_volta_ao_estilo(tmp_path):
    from app.quick_corrections import set_transicao_corte

    edit = _edit(tmp_path)
    set_transicao_corte(edit, 2, "escurece")
    r = set_transicao_corte(edit, 2, "")
    assert r["ok"] and r[CHAVE_POR_CORTE] == {}


def test_a_op_recusa_lixo(tmp_path):
    from app.quick_corrections import set_transicao_corte

    edit = _edit(tmp_path)
    assert set_transicao_corte(edit, "x", "faixa")["ok"] is False
    assert set_transicao_corte(edit, -1, "faixa")["ok"] is False
    assert set_transicao_corte(edit, 0, "explosao")["ok"] is False


def test_o_pipeline_preserva_as_escolhas_entre_renders():
    i = FAST.index('if elems.get("flashCut"):')
    bloco = FAST[i:i + 2600]
    assert "aplicar_por_corte(transitions, escolhas)" in bloco
    assert 'edit-data.json' in bloco and "_ant" in bloco, (
        "sem ler o edit-data anterior, a escolha dura um render")
    assert "ed[CHAVE_POR_CORTE] = escolhas" in bloco, "a chave não sobrevive ao próximo render"


def test_o_editor_desenha_e_abre_o_menu_antes_de_mover_a_agulha():
    assert "function fronteirasDoRascunho()" in PJS
    assert "fronteirasDoRascunho().forEach((tb, i) =>" in PJS, "a régua não desenha as emendas"
    i = PJS.index("if (!e.target.closest('.ruler-track')) return;")
    corpo = PJS[i:i + 900]
    assert corpo.index("abrirMenuDaEmenda(") < corpo.index("seekDraft(t)"), (
        "o clique no losango moveria a agulha em vez de abrir o menu")
    assert "op: 'set_transicao_corte'" in PJS
    assert ".menu-emenda {" in CSS


def test_o_menu_usa_o_catalogo_do_estilo_e_nao_um_segundo():
    i = PJS.index("function abrirMenuDaEmenda(")
    corpo = PJS[i:i + 900]
    assert "$('autoTransicao')" in corpo, "um segundo catálogo em JS apodrece sozinho"
    assert "'Nenhuma neste corte'" in corpo and "'Como o estilo manda'" in corpo
