"""Card travado sempre tem saída: retry barrado em fonte quebrada, aviso de
Apply falhado não gruda no card e quickApply nunca é persistido."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_tasks import attach_apply_to_jobs  # noqa: E402
from app.local_server import (  # noqa: E402
    CORRUPT_SOURCE_MSG,
    MISSING_SOURCE_MSG,
    JobStore,
    unreadable_source_message,
)


def test_missing_source_blocks_retry(tmp_path):
    assert unreadable_source_message(
        {"source": str(tmp_path / "sumiu.mp4")}
    ) == MISSING_SOURCE_MSG


def test_unreadable_file_blocks_retry(tmp_path):
    junk = tmp_path / "lixo.mp4"
    junk.write_bytes(b"isto nao e um video" * 100)
    assert unreadable_source_message({"source": str(junk)}) == CORRUPT_SOURCE_MSG


def test_job_without_source_is_not_blocked():
    assert unreadable_source_message({}) is None


def test_quick_apply_is_never_persisted(tmp_path):
    root = tmp_path / ".ativavid"
    root.mkdir()
    store = JobStore(tmp_path)
    store.upsert({"id": "j1", "status": "done", "projectDir": str(tmp_path / "p")})
    # simula o enrich mutando o job vivo (foi assim que vazou em produção)
    store.list()[0]["quickApply"] = {"status": "failed", "taskId": "t"}
    store.update("j1", message="Pronto")
    # store novo = leitura do disco, sem passar pelo estado do primeiro
    assert all("quickApply" not in row for row in JobStore(tmp_path).list())


def test_stale_quick_apply_is_dropped_when_task_is_gone(tmp_path):
    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    jobs = [{
        "id": "j1", "status": "done", "editDir": str(edit),
        "quickApply": {"status": "failed", "taskId": "velho"},
    }]
    out = attach_apply_to_jobs(jobs, tmp_path)
    assert "quickApply" not in out[0], "aviso velho continuaria travando o card"

def test_campos_de_visao_nao_entram_na_fila(tmp_path):
    """Os /api/jobs carimbam campos de visão no que o store entrega.

    Antes da fronteira eles caíam no jobs.json e sobreviviam ao run seguinte:
    `stage` de um run velho, `hasCut` de arquivo apagado, `message` transitório
    por cima do definitivo.
    """
    store = JobStore(tmp_path)
    store.upsert({"id": "j1", "status": "done", "message": "Pronto",
                  "projectDir": str(tmp_path / "p"), "sources": ["a.mp4"]})

    vista = store.list()[0]
    vista["hasCut"] = True
    vista["stage"] = "processing"
    vista["progress"] = 42
    vista["message"] = "Renderizando..."
    vista["thumbUrl"] = "/api/jobs/j1/thumb"
    vista["sources"].append("nao_deveria_entrar.mp4")

    store.update("j1", status="done")
    row = JobStore(tmp_path).list()[0]
    for campo in ("hasCut", "stage", "progress", "thumbUrl"):
        assert campo not in row, f"{campo} vazou para a fila"
    assert row["message"] == "Pronto", "mensagem transitória sobrescreveu a real"
    assert row["sources"] == ["a.mp4"], "lista aninhada foi mutada por quem só listou"


def test_lista_nao_e_alias_do_store(tmp_path):
    store = JobStore(tmp_path)
    store.upsert({"id": "j1", "status": "queued", "projectDir": str(tmp_path / "p")})
    store.list()[0]["status"] = "done"
    assert store.get("j1")["status"] == "queued"
