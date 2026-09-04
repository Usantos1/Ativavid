# -*- coding: utf-8 -*-
"""5.0.0: workspace por empresa (passo 1) e numeracao nova.

Ele (03/09): "to pensando em criar workspace por empresas ai vai ficar
mais organizado os roteiros, os videos, presets e trabalhos feitos por
empresas" e "nao quero versao assim 4.101, o ideal seria 4.1.1".
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import jobs_view  # noqa: E402
from app.update_check import _versao_tupla  # noqa: E402

SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


# ------------------------------------------------------- numeracao nova
def test_a_versao_nova_e_5_0_0_e_o_atualizador_a_ve_como_mais_nova():
    v = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    assert v.count(".") == 2, "maior.menor.correcao"
    assert _versao_tupla(v) > _versao_tupla("4.101")
    assert _versao_tupla("5.0.1") > _versao_tupla("5.0.0")
    assert _versao_tupla("5.1.0") > _versao_tupla("5.0.9")
    # a razao de nao ser 4.1.1: o atualizador leria como MAIS ANTIGA
    assert _versao_tupla("4.1.1") < _versao_tupla("4.101")
    iss = (REPO / "installer" / "ativa-vid.iss").read_text(encoding="utf-8")
    assert f'#define MyAppVersion "{v}"' in iss


# ------------------------------------------------ o job sabe de quem e
def test_a_marca_vem_do_preset_usado_ou_da_importacao(tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    assert jobs_view._marca_do_projeto({}, edit) == "", "sem nada = sem empresa"
    (edit / "job_intent.json").write_text(json.dumps({"brandId": "loja"}), encoding="utf-8")
    assert jobs_view._marca_do_projeto({}, edit) == "loja", "antes do render vale a importacao"
    (edit / "preset-used.json").write_text(json.dumps({"brandId": "camp", "presetId": "x"}), encoding="utf-8")
    assert jobs_view._marca_do_projeto({}, edit) == "camp", "o preset usado no render manda"
    assert jobs_view._marca_do_projeto({"brandId": "job"}, edit) == "job", "o que ja esta no job vence"
    (edit / "preset-used.json").write_text("{quebrado", encoding="utf-8")
    assert jobs_view._marca_do_projeto({}, edit) == "loja", "json quebrado nao derruba o card"


def test_o_card_recebe_o_brand_id():
    src = (REPO / "app" / "jobs_view.py").read_text(encoding="utf-8")
    i = src.index("def _montar_card(")
    assert 'j["brandId"] = _marca_do_projeto(j, edit)' in src[i:i + 600]


# ------------------------------------------------------- a tela filtra
def test_fila_concluidos_projetos_e_inicio_respeitam_o_workspace():
    i = SJS.index("function filterJobs(kind)")
    bloco = SJS[i:SJS.index("function renderJobs()", i)]
    assert bloco.count("jobsDoWorkspace()") >= 4, "fila, concluidos, projetos e os recentes do inicio"
    assert "return state.jobs.filter(jobInFila)" not in bloco
    j = SJS.index("function jobNaMarca(j)")
    fn = SJS[j:SJS.index("function nomeDaMarca", j)]
    assert 'if (state.wsMarca === "all") return true;' in fn
    assert "return !j.brandId || j.brandId === ativa;" in fn, "video sem empresa aparece em todos"
    assert 'setCount("#countProjetos", jobsDoWorkspace().length);' in SJS


def test_o_menu_do_workspace_lista_as_empresas_e_troca_a_marca():
    assert 'id="wsMarcas"' in SHTML
    assert "function renderWsMarcas()" in SJS
    assert 'item("__all__", "Todas as empresas"' in SJS
    k = SJS.index('const marca = e.target.closest("[data-ws-marca]");')
    bloco = SJS[k:k + 1400]
    assert "await ativarEmpresa(id);" in bloco, "trocar empresa = ativar a marca"
    f = SJS.index("async function ativarEmpresa(id)")
    fn = SJS[f:SJS.index("function renderWsMarcas", f)]
    assert 'JSON.stringify({ action: "activate", id })' in fn and "await loadBrandsUi();" in fn
    assert 'setWsMarca("all");' in bloco
    assert "if (abrir) renderWsMarcas();" in SJS, "contagens frescas ao abrir"


def test_em_todas_as_empresas_o_card_diz_de_quem_e():
    assert 'if (state.wsMarca === "all" && j.brandId) metaBits.unshift(nomeDaMarca(j.brandId));' in SJS
    i = SJS.index("function cardSig(j, opts)")
    assert "_ws," in SJS[i:i + 700], "o chip entra na assinatura do card, senao nao repinta ao trocar"
    assert 'const nome = state.wsMarca === "all" ? "Todas as empresas"' in SJS


def test_vazio_por_empresa_diz_isso_e_oferece_ver_todas():
    """5.0.12: com "Uander" ativa e 291 videos na Prime Camp, o Inicio dizia
    "seus videos aparecem aqui assim que o primeiro ficar pronto"."""
    assert "function escondidosPorEmpresa(view)" in SJS
    i = SJS.index("function renderInto(boxId, emptyId, jobs, opts)")
    bloco = SJS[i:i + 3000]
    assert "} else if (escondidos) {" in bloco and "data-ver-todas" in bloco
    assert 'if (view === "fila") return outros.filter(jobInFila).length;' in SJS
    k = SJS.index('const todas = e.target.closest("[data-ver-todas]");')
    assert 'setWsMarca("all");' in SJS[k:k + 200]
