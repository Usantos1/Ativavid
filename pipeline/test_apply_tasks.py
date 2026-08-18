"""Orquestração UX do Apply — mocks, sem FFmpeg/Remotion/render."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["ATIVAVID_NO_NOTIFY"] = "1"

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import write_apply_status
from app.apply_tasks import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STAGE_FINALIZING,
    STAGE_PREPARING,
    STAGE_RENDER_VISUAL,
    acknowledge_task,
    attach_apply_to_jobs,
    estimate_remaining,
    format_elapsed,
    job_in_fila,
    mark_interrupted,
    prune_index,
    public_view,
    read_task,
    register_task,
    sweep_stale_applies,
    sync_from_status,
)


def _project(root: Path, title: str = "Celular caiu") -> tuple[Path, dict]:
    proj = root / "20260816_celular_caiu"
    edit = proj / "edit"
    edit.mkdir(parents=True)
    (edit / "final.mp4").write_bytes(b"OLD")
    meta = root / ".ativavid"
    meta.mkdir(exist_ok=True)
    job = {
        "id": "job-celular",
        "name": "IMG_1645.mp4",
        "title": title,
        "status": "done",
        "editDir": str(edit),
        "projectDir": str(proj),
    }
    (meta / "jobs.json").write_text(
        json.dumps({"jobs": [job]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return edit, job


def test_fila_badge_and_lifecycle(tmp_path: Path):
    edit, job = _project(tmp_path)
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    assert not job_in_fila(jobs[0])
    assert "quickApply" not in jobs[0] or jobs[0].get("quickApply") is None

    register_task(edit, status=STATUS_QUEUED, stage=STAGE_PREPARING, title="Celular caiu")
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    qa = jobs[0]["quickApply"]
    assert qa["type"] == "quick_apply"
    assert qa["status"] == "queued"
    assert job_in_fila(jobs[0])
    assert qa["stageLabel"] == "Aplicando edição..."

    sync_from_status(edit, {"running": True, "ok": None, "stage": "visual", "message": "Aplicando edição..."})
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    qa = jobs[0]["quickApply"]
    assert qa["status"] == "running"
    assert qa["stage"] == STAGE_RENDER_VISUAL
    assert qa["stageLabel"] == "Aplicando edição..."
    assert job_in_fila(jobs[0])
    assert jobs[0]["status"] == "done"

    sync_from_status(edit, {"running": True, "ok": None, "stage": "export", "message": "Finalizando vídeo..."})
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    assert jobs[0]["quickApply"]["stage"] == STAGE_FINALIZING
    assert jobs[0]["quickApply"]["stageLabel"] == "Finalizando vídeo..."

    sync_from_status(edit, {"running": False, "ok": True, "stage": "done", "message": "Vídeo atualizado", "at": "2026-08-17T20:00:00"})
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    qa = jobs[0]["quickApply"]
    assert qa["status"] == STATUS_COMPLETED
    assert qa["success"] is True
    assert not job_in_fila(jobs[0])
    assert jobs[0]["status"] == "done"
    assert (edit / "final.mp4").read_bytes() == b"OLD"


def test_failure_keeps_previous_final(tmp_path: Path):
    edit, job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING, stage=STAGE_RENDER_VISUAL)
    sync_from_status(edit, {
        "running": False,
        "ok": False,
        "stage": "error",
        "message": "Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido.",
    })
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    qa = jobs[0]["quickApply"]
    assert qa["status"] == STATUS_FAILED
    assert qa["success"] is False
    assert qa["stageLabel"] == "Não foi possível atualizar o vídeo."
    assert job_in_fila(jobs[0])
    assert jobs[0]["status"] == "done"
    assert (edit / "final.mp4").read_bytes() == b"OLD"


def test_failure_shows_friendly_prepare_message(tmp_path: Path):
    edit, job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING, stage=STAGE_RENDER_VISUAL)
    sync_from_status(edit, {
        "running": False,
        "ok": False,
        "stage": "error",
        "message": "Este projeto antigo precisa ser atualizado antes de aplicar cortes manuais.",
        "error": "overlap sem provenance reconstruível",
    })
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    qa = jobs[0]["quickApply"]
    assert qa["status"] == STATUS_FAILED
    assert qa["stageLabel"] == "Este projeto antigo precisa ser atualizado antes de aplicar cortes manuais."
    leaked = json.dumps({k: qa[k] for k in ("stageLabel", "message", "status") if k in qa})
    assert "overlap" not in leaked
    assert "provenance" not in leaked
    assert qa.get("detail")


def test_failed_start_stage_does_not_stay_running(tmp_path: Path):
    """Falha no começo não deixa a Fila em ATUALIZANDO para sempre."""
    edit, job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING, stage=STAGE_PREPARING)
    (edit / "apply_status.json").write_text(json.dumps({
        "running": False,
        "ok": False,
        "stage": "start",
        "message": "Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido.",
        "pid": os.getpid(),
    }), encoding="utf-8")
    task = read_task(edit)
    task["pid"] = os.getpid()
    (edit / "apply_task.json").write_text(json.dumps(task), encoding="utf-8")
    index = tmp_path / ".ativavid" / "apply_tasks.json"
    index.write_text(
        json.dumps({"tasks": {task["projectId"]: {**task, "editDir": str(edit)}}}),
        encoding="utf-8",
    )
    marked = sweep_stale_applies(tmp_path)
    assert marked
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    qa = jobs[0]["quickApply"]
    assert qa["status"] == STATUS_FAILED
    assert qa["success"] is False


def test_leave_editor_keeps_task(tmp_path: Path):
    edit, job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING, stage=STAGE_RENDER_VISUAL)
    persisted = read_task(edit)
    assert persisted["status"] == "running"
    view = public_view(persisted, edit)
    assert view["stageLabel"] == "Aplicando edição..."
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    assert jobs[0]["quickApply"]["status"] == "running"
    assert job_in_fila(jobs[0])


def test_write_apply_status_mirrors_task(tmp_path: Path):
    edit, _job = _project(tmp_path)
    write_apply_status(edit, running=True, ok=None, message="Atualizando cortes...", stage="cutting")
    task = read_task(edit)
    assert task["status"] == "running"
    assert task["stage"] == "rebuild_cut"
    assert task["stageLabel"] == "Atualizando cortes..."
    leaked = json.dumps(task)
    for forbidden in ("REUSE_CUT", "REBUILD_CUT", "FFmpeg", "Remotion", "OVERLAY", "NVENC"):
        assert forbidden not in leaked


def test_stale_running_is_marked_failed(tmp_path: Path):
    edit, job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING, stage=STAGE_RENDER_VISUAL)
    task = read_task(edit)
    task["pid"] = 1
    (edit / "apply_task.json").write_text(json.dumps(task), encoding="utf-8")
    index = tmp_path / ".ativavid" / "apply_tasks.json"
    index.write_text(json.dumps({"tasks": {task["projectId"]: {**task, "editDir": str(edit)}}}), encoding="utf-8")
    marked = sweep_stale_applies(tmp_path, boot=True)
    assert marked
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    assert jobs[0]["quickApply"]["status"] == "failed"
    assert job_in_fila(jobs[0])


def test_eta_only_with_enough_history(tmp_path: Path):
    edit, _job = _project(tmp_path)
    assert estimate_remaining(edit, "2026-08-17T20:00:00") is None
    (edit / "apply_history.json").write_text(
        json.dumps([
            {"type": "REUSE_CUT", "applyDuration": 80, "success": True},
        ]),
        encoding="utf-8",
    )
    assert estimate_remaining(edit, "2026-08-17T20:00:00") is None
    (edit / "apply_history.json").write_text(
        json.dumps([
            {"type": "REUSE_CUT", "applyDuration": 80, "success": True},
            {"type": "REUSE_CUT", "applyDuration": 90, "success": True},
        ]),
        encoding="utf-8",
    )
    rem = estimate_remaining(edit, "2026-08-17T20:00:00")
    assert rem is not None
    view = public_view({
        "status": "running",
        "stage": "render_visual",
        "startedAt": "2099-01-01T00:00:00",
        "projectId": "x",
    }, edit)
    assert view["etaLabel"] is None or "~" in view["etaLabel"]


def test_queued_apply_counts_as_busy(tmp_path: Path):
    from app.apply_execute import is_apply_running, write_apply_status

    edit, _job = _project(tmp_path)
    write_apply_status(edit, running=False, ok=None, message="Na fila...", stage="queued")
    register_task(edit, status=STATUS_QUEUED, stage=STAGE_PREPARING)
    assert is_apply_running(edit) is True


def test_elapsed_label():
    assert format_elapsed(14) == "14s"
    assert format_elapsed(134) == "2min 14s"


def test_interrupted_helper(tmp_path: Path):
    edit, _job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING)
    mark_interrupted(edit)
    task = read_task(edit)
    assert task["status"] == "failed"
    assert task["interrupted"] is True


def test_task_id_and_ack_prunes_index(tmp_path: Path):
    edit, job = _project(tmp_path)
    first = register_task(edit, status=STATUS_RUNNING)
    assert first.get("taskId")
    sync_from_status(edit, {"running": False, "ok": True, "stage": "done"})
    task = read_task(edit)
    assert task["status"] == "completed"
    assert task["taskId"] == first["taskId"]
    view = acknowledge_task(tmp_path, task_id=task["taskId"])
    assert view and view.get("acknowledgedAt")
    index = json.loads((tmp_path / ".ativavid" / "apply_tasks.json").read_text(encoding="utf-8"))
    assert task["projectId"] not in (index.get("tasks") or {})
    assert read_task(edit)["status"] == "completed"
    jobs = [dict(job)]
    attach_apply_to_jobs(jobs, tmp_path)
    assert not job_in_fila(jobs[0])


def test_prune_old_completed(tmp_path: Path):
    edit, _job = _project(tmp_path)
    register_task(edit, status=STATUS_RUNNING)
    sync_from_status(edit, {"running": False, "ok": True, "stage": "done", "at": "2020-01-01T00:00:00"})
    task = read_task(edit)
    task["finishedAt"] = "2020-01-01T00:00:00"
    (edit / "apply_task.json").write_text(json.dumps(task), encoding="utf-8")
    index_p = tmp_path / ".ativavid" / "apply_tasks.json"
    index_p.write_text(json.dumps({"tasks": {task["projectId"]: task}}), encoding="utf-8")
    assert prune_index(tmp_path) >= 1
    index = json.loads(index_p.read_text(encoding="utf-8"))
    assert task["projectId"] not in (index.get("tasks") or {})
    assert read_task(edit)["status"] == "completed"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        test_fila_badge_and_lifecycle(root / "life")
        test_failure_keeps_previous_final(root / "fail")
        test_failure_shows_friendly_prepare_message(root / "prov")
        test_failed_start_stage_does_not_stay_running(root / "stuck")
        test_leave_editor_keeps_task(root / "leave")
        test_write_apply_status_mirrors_task(root / "mirror")
        test_stale_running_is_marked_failed(root / "stale")
        test_eta_only_with_enough_history(root / "eta")
        test_elapsed_label()
        test_interrupted_helper(root / "int")
        test_task_id_and_ack_prunes_index(root / "ack")
        test_prune_old_completed(root / "prune")
    print("ok")
