"""Tarefas visíveis de Apply (quick_apply) — só orquestração/UX.

Não executa corte, Remotion, FFmpeg nem o plano. Só persiste status,
expõe a tarefa na Fila e detecta Apply interrompido após crash.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

TASK_FILE = "apply_task.json"
INDEX_NAME = "apply_tasks.json"
TYPE_QUICK_APPLY = "quick_apply"

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

STAGE_PREPARING = "preparing"
STAGE_REBUILD_CUT = "rebuild_cut"
STAGE_RENDER_VISUAL = "render_visual"
STAGE_FINALIZING = "finalizing"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"

# Estágios internos do apply_status.json → etapa amigável persistida.
# Nunca vazar REUSE_CUT / REBUILD_CUT / FFmpeg / Remotion / OVERLAY / NVENC.
_INTERNAL_STAGE = {
    "queued": (STATUS_QUEUED, STAGE_PREPARING, "Na fila..."),
    "start": (STATUS_RUNNING, STAGE_PREPARING, "Aplicando edição..."),
    "prepare": (STATUS_RUNNING, STAGE_PREPARING, "Preparando alterações..."),
    "cutting": (STATUS_RUNNING, STAGE_REBUILD_CUT, "Atualizando cortes..."),
    "visual": (STATUS_RUNNING, STAGE_RENDER_VISUAL, "Aplicando edição..."),
    "export": (STATUS_RUNNING, STAGE_FINALIZING, "Finalizando vídeo..."),
    "done": (STATUS_COMPLETED, STAGE_COMPLETED, "Vídeo atualizado"),
    "error": (STATUS_FAILED, STAGE_FAILED, "Não foi possível atualizar o vídeo."),
}

_STAGE_LABEL = {
    STAGE_PREPARING: "Aplicando edição...",
    STAGE_REBUILD_CUT: "Atualizando cortes...",
    STAGE_RENDER_VISUAL: "Aplicando edição...",
    STAGE_FINALIZING: "Finalizando vídeo...",
    STAGE_COMPLETED: "Vídeo atualizado",
    STAGE_FAILED: "Não foi possível atualizar o vídeo.",
}

FAIL_TOAST = "Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido."
INTERRUPTED_MSG = "A atualização foi interrompida."
FAIL_GENERIC = "Não foi possível atualizar o vídeo."
_FAIL_DETAIL = {
    "Este projeto antigo precisa ser atualizado antes de aplicar cortes manuais.",
    "Não foi possível preparar este corte. O vídeo anterior foi mantido.",
    INTERRUPTED_MSG,
}
ETA_MIN_SAMPLES = 2
ETA_MIN_DURATION = 20.0
_STALE_NO_PID_SEC = 30.0
INDEX_KEEP_COMPLETED = 8
COMPLETED_INDEX_TTL_SEC = 3600
_index_lock = threading.RLock()


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    last: OSError | None = None
    for attempt in range(8):
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.04 * (attempt + 1))
    if last:
        raise last


def _norm(path: Path | str | None) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve()).replace("\\", "/").lower()
    except (OSError, TypeError):
        return str(path).replace("\\", "/").lower()


def project_id_for(edit_dir: Path) -> str:
    edit = Path(edit_dir)
    if edit.name.lower() == "edit":
        return edit.parent.name
    return edit.name


def projects_root_for(edit_dir: Path) -> Path:
    edit = Path(edit_dir).resolve()
    if edit.name.lower() == "edit":
        return edit.parent.parent
    return edit.parent


def task_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / TASK_FILE


def index_path(projects_root: Path) -> Path:
    return Path(projects_root) / ".ativavid" / INDEX_NAME


def friendly_stage_label(stage: str, message: str | None = None) -> str:
    msg = str(message or "").strip()
    if str(stage or "") == STAGE_FAILED:
        return _fail_queue_label(msg)
    label = _STAGE_LABEL.get(str(stage or ""), "")
    if label:
        return label
    return msg or "Aplicando edição..."


def _fail_queue_label(message: str | None) -> str:
    """Fila mostra detalhe amigável; erros internos viram o genérico."""
    msg = str(message or "").strip()
    if msg in _FAIL_DETAIL:
        return msg
    return FAIL_GENERIC


def map_internal_stage(status_row: dict[str, Any]) -> tuple[str, str, str]:
    """Converte apply_status.json → (status, stage, label) amigáveis."""
    running = bool(status_row.get("running"))
    ok = status_row.get("ok")
    msg = str(status_row.get("message") or "").strip()
    if not running and ok is True:
        return STATUS_COMPLETED, STAGE_COMPLETED, "Vídeo atualizado"
    if not running and ok is False:
        return STATUS_FAILED, STAGE_FAILED, _fail_queue_label(msg)
    raw = str(status_row.get("stage") or "").strip().lower()
    mapped = _INTERNAL_STAGE.get(raw)
    if mapped:
        status, stage, label = mapped
        if msg and status == STATUS_RUNNING:
            label = msg
        elif status == STATUS_FAILED:
            label = _fail_queue_label(msg)
        return status, stage, label
    if running:
        return STATUS_RUNNING, STAGE_PREPARING, msg or "Aplicando edição..."
    return STATUS_QUEUED, STAGE_PREPARING, "Na fila..."


def format_elapsed(seconds: float | int | None) -> str:
    sec = max(0, int(seconds or 0))
    if sec < 60:
        return f"{sec}s"
    minutes, rem = divmod(sec, 60)
    if minutes < 60:
        return f"{minutes}min {rem}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}min"


def format_eta(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    rem = float(seconds)
    if rem < 20:
        return None
    minutes = max(1, int(round(rem / 60.0)))
    if minutes == 1:
        return "~1 min restante"
    return f"~{minutes} min restantes"


def estimate_remaining(edit_dir: Path, started_at: str | None) -> float | None:
    """ETA só com histórico suficiente. Sem chute."""
    hist = _read_json(Path(edit_dir) / "apply_history.json", [])
    if not isinstance(hist, list):
        return None
    durs: list[float] = []
    for row in hist:
        if not isinstance(row, dict) or not row.get("success"):
            continue
        try:
            dur = float(row.get("applyDuration") or 0)
        except (TypeError, ValueError):
            continue
        if dur >= ETA_MIN_DURATION:
            durs.append(dur)
    if len(durs) < ETA_MIN_SAMPLES:
        return None
    durs.sort()
    median = durs[len(durs) // 2]
    started = _parse_ts(started_at)
    if started is None:
        return None
    elapsed = max(0.0, time.time() - started)
    return median - elapsed


def _parse_ts(value: str | None) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return time.mktime(time.strptime(raw[:19], fmt))
        except (ValueError, OverflowError):
            continue
    return None


def read_task(edit_dir: Path) -> dict[str, Any] | None:
    data = _read_json(task_path(edit_dir), None)
    return data if isinstance(data, dict) else None


def public_view(task: dict[str, Any] | None, edit_dir: Path | None = None) -> dict[str, Any] | None:
    if not isinstance(task, dict):
        return None
    status = str(task.get("status") or "")
    stage = str(task.get("stage") or "")
    started = str(task.get("startedAt") or "")
    elapsed_sec = 0.0
    started_ts = _parse_ts(started)
    if started_ts is not None:
        end_ts = _parse_ts(str(task.get("finishedAt") or "")) or time.time()
        elapsed_sec = max(0.0, end_ts - started_ts)
    eta_sec = None
    if status in (STATUS_QUEUED, STATUS_RUNNING) and edit_dir is not None:
        eta_sec = estimate_remaining(edit_dir, started)
    view = {
        "taskId": task.get("taskId") or "",
        "projectId": task.get("projectId") or "",
        "jobId": task.get("jobId") or "",
        "type": TYPE_QUICK_APPLY,
        "acknowledgedAt": task.get("acknowledgedAt"),
        "status": status,
        "stage": stage,
        "stageLabel": friendly_stage_label(stage, str(task.get("stageLabel") or task.get("message") or "")),
        "startedAt": started or None,
        "finishedAt": task.get("finishedAt"),
        "success": task.get("success"),
        "elapsedSec": int(elapsed_sec),
        "elapsedLabel": format_elapsed(elapsed_sec) if started else "",
        "etaLabel": format_eta(eta_sec),
        "title": task.get("title") or "",
        "message": friendly_stage_label(stage, str(task.get("message") or "")),
        "detail": str(task.get("detail") or "") if status == STATUS_FAILED else "",
    }
    return view


def job_in_fila(job: dict[str, Any]) -> bool:
    """Mesma regra da Fila: jobs de IA + Apply ativo/falho."""
    if str(job.get("status") or "") in ("importing", "queued", "processing", "needs_review", "error"):
        return True
    qa = job.get("quickApply") or {}
    return str(qa.get("status") or "") in (STATUS_QUEUED, STATUS_RUNNING, STATUS_FAILED)


def _load_index(projects_root: Path) -> dict[str, dict[str, Any]]:
    raw = _read_json(index_path(projects_root), {})
    if isinstance(raw, dict) and isinstance(raw.get("tasks"), dict):
        out: dict[str, dict[str, Any]] = {}
        for key, val in raw["tasks"].items():
            if isinstance(val, dict):
                out[str(key)] = val
        return out
    return {}


def _save_index(projects_root: Path, tasks: dict[str, dict[str, Any]]) -> None:
    _write_json(index_path(projects_root), {"tasks": tasks})


def _index_key(task: dict[str, Any]) -> str:
    return str(task.get("taskId") or task.get("projectId") or "")


def prune_index(projects_root: Path) -> int:
    """Índice global só guarda ativos + completed recente. Histórico definitivo é apply_history."""
    root = Path(projects_root)
    now = time.time()
    removed = 0
    with _index_lock:
        tasks = _load_index(root)
        completed: list[tuple[float, str]] = []
        for key, task in list(tasks.items()):
            status = str(task.get("status") or "")
            if status not in (STATUS_COMPLETED, STATUS_FAILED):
                continue
            if task.get("acknowledgedAt") and status == STATUS_COMPLETED:
                tasks.pop(key, None)
                removed += 1
                continue
            finished = _parse_ts(str(task.get("finishedAt") or task.get("updatedAt") or ""))
            if status == STATUS_COMPLETED and finished is not None and (now - finished) > COMPLETED_INDEX_TTL_SEC:
                tasks.pop(key, None)
                removed += 1
                continue
            if status == STATUS_COMPLETED:
                completed.append((finished or 0.0, key))
        completed.sort(reverse=True)
        for _ts, key in completed[INDEX_KEEP_COMPLETED:]:
            tasks.pop(key, None)
            removed += 1
        if removed:
            _save_index(root, tasks)
    return removed


def acknowledge_task(
    projects_root: Path,
    *,
    task_id: str = "",
    project_id: str = "",
) -> dict[str, Any] | None:
    """Marca a conclusão como vista e tira completed do índice ativo."""
    root = Path(projects_root)
    want_task = str(task_id or "").strip()
    want_proj = str(project_id or "").strip()
    found: dict[str, Any] | None = None
    with _index_lock:
        tasks = _load_index(root)
        for key, task in list(tasks.items()):
            if want_task and str(task.get("taskId") or "") == want_task:
                found = task
                break
            if want_proj and str(task.get("projectId") or key) == want_proj:
                found = task
                break
    if found is None and want_proj:
        # fallback: arquivo do projeto
        for child in root.iterdir() if root.exists() else []:
            if child.name == want_proj and (child / "edit").is_dir():
                found = read_task(child / "edit")
                break
    if not isinstance(found, dict):
        return None
    found = dict(found)
    found["acknowledgedAt"] = _utc()
    edit = Path(found.get("editDir") or "")
    if edit:
        _persist(edit, found)
    prune_index(root)
    return public_view(found, edit if edit else None)


def _lookup_job(edit_dir: Path, projects_root: Path) -> tuple[str, str]:
    """(jobId, title) a partir de jobs.json, sem criar job novo."""
    jobs_raw = _read_json(Path(projects_root) / ".ativavid" / "jobs.json", {})
    jobs = jobs_raw.get("jobs") if isinstance(jobs_raw, dict) else None
    if not isinstance(jobs, list):
        return "", ""
    want = _norm(edit_dir)
    parent = _norm(Path(edit_dir).parent)
    for job in jobs:
        if not isinstance(job, dict):
            continue
        edit = _norm(job.get("editDir"))
        proj = _norm(job.get("projectDir"))
        if edit == want or proj == parent or edit == parent:
            return str(job.get("id") or ""), str(job.get("title") or job.get("name") or "")
    return "", ""


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return int(code.value) == 259
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _apply_thread_alive() -> bool:
    return any(t.name == "quick-apply" and t.is_alive() for t in threading.enumerate())


def is_stale(task: dict[str, Any], *, boot: bool = False) -> bool:
    if str(task.get("status") or "") not in (STATUS_QUEUED, STATUS_RUNNING):
        return False
    edit = Path(str(task.get("editDir") or ""))
    if edit:
        row = _read_json(edit / "apply_status.json", {})
        if isinstance(row, dict) and row.get("running") is False and row.get("ok") is not None:
            return True
    if _apply_thread_alive():
        return False
    try:
        pid = int(task.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid and pid == os.getpid():
        # PID do app aberto não prova que o Apply ainda está rodando.
        pid = 0
    if pid and _pid_alive(pid):
        return False
    if pid and not _pid_alive(pid):
        return True
    if boot:
        return True
    started = _parse_ts(str(task.get("startedAt") or ""))
    if started is not None and (time.time() - started) > _STALE_NO_PID_SEC:
        return True
    return False


def mark_interrupted(edit_dir: Path, task: dict[str, Any] | None = None) -> dict[str, Any]:
    row = dict(task or read_task(edit_dir) or {})
    row.update({
        "status": STATUS_FAILED,
        "stage": STAGE_FAILED,
        "stageLabel": INTERRUPTED_MSG,
        "message": INTERRUPTED_MSG,
        "finishedAt": _utc(),
        "success": False,
        "interrupted": True,
    })
    return _persist(Path(edit_dir), row)


def sweep_stale_applies(projects_root: Path, *, boot: bool = False) -> list[str]:
    """Não deixa Apply eternamente 'running' depois de crash/restart."""
    root = Path(projects_root)
    marked: list[str] = []
    with _index_lock:
        tasks = _load_index(root)
        for key, task in list(tasks.items()):
            if not is_stale(task, boot=boot):
                continue
            edit = Path(task.get("editDir") or "")
            if edit:
                row = _read_json(edit / "apply_status.json", {})
                if isinstance(row, dict) and row.get("ok") is not None:
                    sync_from_status(edit, row)
                else:
                    mark_interrupted(edit, task)
            else:
                task.update({
                    "status": STATUS_FAILED,
                    "stage": STAGE_FAILED,
                    "finishedAt": _utc(),
                    "success": False,
                    "interrupted": True,
                    "message": INTERRUPTED_MSG,
                })
                tasks[key] = task
                _save_index(root, tasks)
            marked.append(str(task.get("projectId") or key))
    return marked


def _persist(edit_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    edit = Path(edit_dir)
    task.setdefault("type", TYPE_QUICK_APPLY)
    task.setdefault("projectId", project_id_for(edit))
    task["editDir"] = str(edit)
    task["updatedAt"] = _utc()
    _write_json(task_path(edit), task)
    try:
        from app.event_bus import bump

        bump()  # progresso do Apply aparece na Fila sem esperar o poll
    except Exception:
        pass
    root = projects_root_for(edit)
    with _index_lock:
        tasks = _load_index(root)
        tasks[str(task["projectId"])] = dict(task)
        _save_index(root, tasks)
    return task


def register_task(
    edit_dir: Path,
    *,
    status: str = STATUS_QUEUED,
    stage: str = STAGE_PREPARING,
    title: str = "",
    job_id: str = "",
) -> dict[str, Any]:
    edit = Path(edit_dir)
    root = projects_root_for(edit)
    found_id, found_title = _lookup_job(edit, root)
    prev = read_task(edit) or {}
    task = {
        "taskId": str(uuid.uuid4()),
        "projectId": project_id_for(edit),
        "jobId": job_id or found_id or prev.get("jobId") or "",
        "type": TYPE_QUICK_APPLY,
        "acknowledgedAt": None,
        "status": status,
        "stage": stage,
        "stageLabel": friendly_stage_label(stage),
        "message": friendly_stage_label(stage),
        "startedAt": _utc() if status in (STATUS_QUEUED, STATUS_RUNNING) else prev.get("startedAt"),
        "finishedAt": None,
        "success": None,
        "pid": os.getpid(),
        "title": title or found_title or prev.get("title") or project_id_for(edit),
        "interrupted": False,
    }
    return _persist(edit, task)


def sync_from_status(edit_dir: Path, status_row: dict[str, Any]) -> dict[str, Any]:
    """Espelha apply_status.json na tarefa da Fila. Sem tocar no render."""
    edit = Path(edit_dir)
    status, stage, label = map_internal_stage(status_row)
    prev = read_task(edit) or {}
    now = _utc()
    started = prev.get("startedAt") or now
    finished = prev.get("finishedAt")
    success = prev.get("success")
    if status in (STATUS_QUEUED, STATUS_RUNNING):
        finished = None
        success = None
        if not prev.get("startedAt"):
            started = now
    elif status == STATUS_COMPLETED:
        finished = str(status_row.get("at") or now)
        success = True
    elif status == STATUS_FAILED:
        finished = str(status_row.get("at") or now)
        success = False
    root = projects_root_for(edit)
    job_id, title = _lookup_job(edit, root)
    try:
        pid = int(status_row.get("pid") or prev.get("pid") or os.getpid())
    except (TypeError, ValueError):
        pid = os.getpid()
    task = {
        "taskId": prev.get("taskId") or str(uuid.uuid4()),
        "projectId": project_id_for(edit),
        "jobId": job_id or prev.get("jobId") or "",
        "type": TYPE_QUICK_APPLY,
        "acknowledgedAt": prev.get("acknowledgedAt") if status == prev.get("status") else None,
        "status": status,
        "stage": stage,
        "stageLabel": label,
        "message": label,
        "startedAt": started,
        "finishedAt": finished,
        "success": success,
        "pid": pid,
        "title": title or prev.get("title") or project_id_for(edit),
        "interrupted": False,
        "detail": str(status_row.get("error") or status_row.get("detail") or prev.get("detail") or "")
        if status == STATUS_FAILED else "",
    }
    saved = _persist(edit, task)
    if status in (STATUS_COMPLETED, STATUS_FAILED):
        try:
            prune_index(root)
        except Exception:
            pass
    if status == STATUS_COMPLETED and prev.get("status") != STATUS_COMPLETED:
        maybe_desktop_notify(saved.get("title") or "Vídeo", success=True)
    elif status == STATUS_FAILED and prev.get("status") != STATUS_FAILED:
        maybe_desktop_notify(saved.get("title") or "Vídeo", success=False)
    return saved


def attach_apply_to_jobs(jobs: list[dict[str, Any]], projects_root: Path | None = None) -> list[dict[str, Any]]:
    """Cobre o job existente com quickApply. Não cria projeto/job novo."""
    by_edit: dict[str, dict[str, Any]] = {}
    by_job: dict[str, dict[str, Any]] = {}
    if projects_root:
        for task in _load_index(Path(projects_root)).values():
            if task.get("editDir"):
                by_edit[_norm(task["editDir"])] = task
            if task.get("jobId"):
                by_job[str(task["jobId"])] = task
    for job in jobs:
        edit = Path(job.get("editDir") or "")
        task = by_job.get(str(job.get("id") or "")) or by_edit.get(_norm(edit))
        if task is None and edit:
            task = read_task(edit)
        view = public_view(task, edit if edit else None)
        if view:
            job["quickApply"] = view
    return jobs


def enrich_jobs_list(jobs: list[dict[str, Any]], projects_root: Path | None = None) -> list[dict[str, Any]]:
    if projects_root:
        try:
            sweep_stale_applies(Path(projects_root), boot=False)
            prune_index(Path(projects_root))
        except Exception:
            pass
    return attach_apply_to_jobs(jobs, projects_root)


def maybe_desktop_notify(title: str, *, success: bool) -> None:
    """Toast do Windows se for barato. Falha silenciosa — o toast da UI é o obrigatório."""
    if os.environ.get("ATIVAVID_NO_NOTIFY") or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    argv = " ".join(sys.argv).lower()
    if "pytest" in argv or "test_" in Path(sys.argv[0] if sys.argv else "").name.lower():
        return
    if sys.platform != "win32":
        return
    safe = "".join(ch for ch in str(title or "Vídeo") if ch not in "<>&\"'")[:80] or "Vídeo"
    if success:
        heading = "Vídeo atualizado"
        body = f"{safe} está pronto para revisão."
    else:
        heading = "Não foi possível atualizar"
        body = FAIL_TOAST
    xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{heading}</text><text>{body}</text>"
        "</binding></visual></toast>"
    )
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        f"$xml.LoadXml(@'\n{xml}\n'@)\n"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)\n"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('ATIVAVID').Show($toast)\n"
    )
    try:
        import subprocess

        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except Exception:
        return
