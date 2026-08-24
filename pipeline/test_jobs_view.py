# -*- coding: utf-8 -*-
"""A vista da Fila é montada num lugar só (app/jobs_view.py).

O /api/jobs existia duas vezes, quase igual, e o defeito dos campos de visão
grudando no card teve de ser caçado nos dois. Estes testes prendem o contrato.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.job_store import SqliteJobStore  # noqa: E402
from app.jobs_view import build  # noqa: E402


def _projeto(root: Path, jid: str, **campos) -> dict:
    proj = root / f"p_{jid}"
    edit = proj / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    job = {"id": jid, "title": f"Vídeo {jid}", "status": "done", "message": "Pronto",
           "projectDir": str(proj), "editDir": str(edit),
           "createdAt": "2026-08-19T10:00:00Z"}
    job.update(campos)
    return job


def test_campos_derivados_saem_na_vista(tmp_path):
    store = SqliteJobStore(tmp_path)
    job = _projeto(tmp_path, "j1")
    (Path(job["editDir"]) / "cut.mp4").write_bytes(b"x")
    (Path(job["editDir"]) / "thumb.jpg").write_bytes(b"x")
    store.upsert(job)

    vista = build(store, tmp_path)[0]
    assert vista["hasCut"] is True
    assert vista["hasThumb"] is True
    assert vista["thumbUrl"] == "/api/jobs/j1/thumb"
    assert vista["stage"] == "done"


def test_a_vista_nao_volta_para_a_fila(tmp_path):
    """O motivo de tudo isto: derivado é derivado, não vira estado gravado."""
    store = SqliteJobStore(tmp_path)
    store.upsert(_projeto(tmp_path, "j1"))
    build(store, tmp_path)
    gravado = store.get("j1")
    for campo in ("hasCut", "hasFinal", "hasThumb", "thumbUrl", "stage", "stageLabel"):
        assert campo not in gravado, f"{campo} entrou na fila"


def test_progresso_vem_do_pipeline_status(tmp_path):
    store = SqliteJobStore(tmp_path)
    job = _projeto(tmp_path, "j1", status="processing")
    (Path(job["editDir"]) / "pipeline_status.json").write_text(
        json.dumps({"stage": "render", "progress": 42, "message": "Renderizando"}),
        encoding="utf-8")
    store.upsert(job)

    vista = build(store, tmp_path)[0]
    assert (vista["stage"], vista["progress"]) == ("render", 42)
    assert vista["message"] == "Renderizando"
    assert store.get("j1")["message"] == "Pronto", "mensagem passageira gravou por cima"


def test_status_corrompido_nao_derruba_a_fila(tmp_path):
    store = SqliteJobStore(tmp_path)
    job = _projeto(tmp_path, "j1", status="processing")
    (Path(job["editDir"]) / "pipeline_status.json").write_text("{lixo", encoding="utf-8")
    store.upsert(job)
    assert build(store, tmp_path)[0]["stage"] == "processing"


def test_links_do_editor_so_com_com_links(tmp_path):
    """A única diferença real entre os dois servidores."""
    store = SqliteJobStore(tmp_path)
    store.upsert(_projeto(tmp_path, "j1"))

    assert "editorUrl" not in build(store, tmp_path)[0]
    com = build(store, tmp_path, com_links=True)[0]
    assert com["editorUrl"].endswith("/fase1")
    assert com["estiloUrl"].endswith("/estilo")
    assert com["finalUrl"].endswith("/fase2")


def test_pasta_com_espaco_e_acento_vira_link_valido(tmp_path):
    store = SqliteJobStore(tmp_path)
    proj = tmp_path / "Promoção de Março"
    (proj / "edit").mkdir(parents=True)
    store.upsert({"id": "j1", "status": "done", "projectDir": str(proj),
                  "editDir": str(proj / "edit")})
    url = build(store, tmp_path, com_links=True)[0]["editorUrl"]
    assert " " not in url and "ç" not in url, url


def test_projeto_com_pasta_sumida_nao_quebra(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "status": "done",
                  "projectDir": str(tmp_path / "sumiu"),
                  "editDir": str(tmp_path / "sumiu" / "edit")})
    vista = build(store, tmp_path)[0]
    assert vista["hasCut"] is False and vista["hasFinal"] is False


def test_fila_vazia(tmp_path):
    assert build(SqliteJobStore(tmp_path), tmp_path) == []


# --- o card avisa quando o vídeo saiu sem IA -------------------------------
#
# Em 20 e 21/08 a extensão parou de entregar a sessão do Gemini, o corte caiu
# para a heurística e o título passou a ser as primeiras palavras da fala. O
# pipeline registrava isso, mas só no log. 50 vídeos saíram assim e a Fila não
# dizia nada. O que estes testes travam é os dois lados: o aviso aparece na
# falha de verdade, e NÃO aparece nos cortes que dispensam IA de propósito.


def _com_resultado(root: Path, jid: str, llm: dict, **campos) -> dict:
    job = _projeto(root, jid, **campos)
    (Path(job["editDir"]) / "result.json").write_text(
        json.dumps({"status": "done", "llm": llm}), encoding="utf-8")
    return job


def test_aviso_aparece_quando_a_ia_falhou(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert(_com_resultado(tmp_path, "j1",
                                {"ok": False, "error": "sessão expirada"}))
    aviso = build(store, tmp_path)[0].get("iaAviso") or ""
    assert aviso, "vídeo sem IA e o card não avisou"
    assert "Reconecte" in aviso, "foi a sessão: mandar reconectar está certo"
    # Sem jargão: nada de Gemini, sessão, backend ou cookie na tela.
    for termo in ("gemini", "chatgpt", "backend", "cookie", "sessão expirada"):
        assert termo not in aviso.lower(), f"jargão vazando no card: {termo}"


@pytest.mark.parametrize("backend", [
    "gemini-web", "chatgpt-web",     # a IA respondeu
    "preview_edits", "manual_edl",   # o corte é do próprio usuário
    "heuristic_light",               # modo leve dispensa IA de propósito
    "multi_take_concat",
])
def test_sem_aviso_quando_nao_houve_falha(tmp_path, backend):
    store = SqliteJobStore(tmp_path)
    store.upsert(_com_resultado(tmp_path, "j1", {"ok": True, "backend": backend}))
    assert "iaAviso" not in build(store, tmp_path)[0]


def test_video_ainda_processando_nao_recebe_aviso(tmp_path):
    """O result.json de um render anterior não pode marcar o job em andamento."""
    store = SqliteJobStore(tmp_path)
    store.upsert(_com_resultado(tmp_path, "j1", {"ok": False}, status="processing"))
    assert "iaAviso" not in build(store, tmp_path)[0]


def test_result_corrompido_nao_derruba_a_fila(tmp_path):
    store = SqliteJobStore(tmp_path)
    job = _projeto(tmp_path, "j1")
    (Path(job["editDir"]) / "result.json").write_text("{ nao é json", encoding="utf-8")
    store.upsert(job)
    assert build(store, tmp_path)[0]["id"] == "j1"


def test_defeito_de_codigo_nao_manda_mexer_na_conexao(tmp_path):
    """65 dos 67 avisos nos projetos reais seriam por `KeyError: 'viral'` — um
    defeito de código, já corrigido. Mandar reconectar ali é conselho errado:
    a sessão estava boa e o que resolve é gerar de novo."""
    store = SqliteJobStore(tmp_path)
    store.upsert(_com_resultado(tmp_path, "j1", {"ok": False, "error": "'viral'"}))
    aviso = build(store, tmp_path)[0].get("iaAviso") or ""
    assert "Reconecte" not in aviso, aviso
    assert "de novo" in aviso


@pytest.mark.parametrize("erro", [
    "Nenhuma sessão pronta. Em Chaves & IA: abra Gemini",
    "Sessão Gemini incompleta",
    "Capture a sessão com a extensão",
])
def test_falha_de_sessao_ainda_manda_reconectar(tmp_path, erro):
    store = SqliteJobStore(tmp_path)
    store.upsert(_com_resultado(tmp_path, "j1", {"ok": False, "error": erro}))
    assert "Reconecte" in (build(store, tmp_path)[0].get("iaAviso") or "")


# --- o modo de edicao aparece no card ---------------------------------------
#
# O modo muda o CORTE (leve = heuristico, sem IA) e era invisivel: em 24/08 o
# usuario importou o mesmo video 3x trocando o TIPO e herdando o modo leve em
# silencio — o corte saiu identico (70,4s) e nada na tela explicava.


def test_modo_leve_aparece_na_ficha(tmp_path):
    store = SqliteJobStore(tmp_path)
    job = _projeto(tmp_path, "j1")
    (Path(job["editDir"]) / "job_intent.json").write_text(
        json.dumps({"editingIntent": "light"}), encoding="utf-8")
    store.upsert(job)
    assert build(store, tmp_path)[0].get("modoLabel") == "Edição leve"


def test_modo_padrao_fica_implicito(tmp_path):
    store = SqliteJobStore(tmp_path)
    job = _projeto(tmp_path, "j1")
    (Path(job["editDir"]) / "job_intent.json").write_text(
        json.dumps({"editingIntent": "dynamic"}), encoding="utf-8")
    store.upsert(job)
    assert "modoLabel" not in build(store, tmp_path)[0]
