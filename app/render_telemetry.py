"""Telemetria LOCAL do Motor de Render Automático — não envia nada."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_DIR = Path.home() / "ATIVAVID"
STATS_PATH = USER_DIR / "render-stats.json"

_EMPTY = {
    "totalJobs": 0,
    "overlayJobs": 0,
    "fullJobs": 0,
    "fallbacks": 0,
    "validationErrors": 0,
    "overlayWholeSecSum": 0.0,
    "fullWholeSecSum": 0.0,
    "meanOverlaySec": None,
    "meanFullSec": None,
    "lastFallback": None,
    "updatedAt": None,
}

_VALIDATION_MARKERS = (
    "FRAMES", "DURATION", "TRUE_PEAK", "ALPHA", "TEMP_CLEANUP",
    "FINAL_INVALID", "OVERLAY_FRAMES", "OVERLAY_ALPHA", "OVERLAY_SIZE",
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_stats() -> dict[str, Any]:
    try:
        raw = json.loads(STATS_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            out = dict(_EMPTY)
            out.update(raw)
            return out
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return dict(_EMPTY)


def save_stats(data: dict[str, Any]) -> dict[str, Any]:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    out = dict(_EMPTY)
    out.update(data)
    ov_n = int(out.get("overlayJobs") or 0)
    fu_n = int(out.get("fullJobs") or 0)
    ov_sum = float(out.get("overlayWholeSecSum") or 0)
    fu_sum = float(out.get("fullWholeSecSum") or 0)
    out["meanOverlaySec"] = round(ov_sum / ov_n, 3) if ov_n else None
    out["meanFullSec"] = round(fu_sum / fu_n, 3) if fu_n else None
    out["updatedAt"] = _now()
    STATS_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _is_validation_error(reason: str | None) -> bool:
    text = str(reason or "")
    return any(m in text for m in _VALIDATION_MARKERS)


def record_job(report: dict[str, Any]) -> dict[str, Any]:
    """Acumula estatísticas locais. Sem rede."""
    st = load_stats()
    engine = str(report.get("renderEngine") or report.get("renderPath") or "FULL")
    whole = report.get("wholeJobSec")
    try:
        whole_f = float(whole) if whole is not None else None
    except (TypeError, ValueError):
        whole_f = None
    st["totalJobs"] = int(st.get("totalJobs") or 0) + 1
    if engine == "OVERLAY":
        st["overlayJobs"] = int(st.get("overlayJobs") or 0) + 1
        if whole_f is not None:
            st["overlayWholeSecSum"] = float(st.get("overlayWholeSecSum") or 0) + whole_f
    else:
        st["fullJobs"] = int(st.get("fullJobs") or 0) + 1
        if whole_f is not None:
            st["fullWholeSecSum"] = float(st.get("fullWholeSecSum") or 0) + whole_f
    if report.get("fallbackUsed"):
        st["fallbacks"] = int(st.get("fallbacks") or 0) + 1
        reason = report.get("fallbackReason")
        st["lastFallback"] = {"reason": reason, "at": _now()}
        if _is_validation_error(str(reason or "")):
            st["validationErrors"] = int(st.get("validationErrors") or 0) + 1
    return save_stats(st)


def print_render_result(report: dict[str, Any]) -> None:
    engine = report.get("renderEngine") or report.get("renderPath") or "FULL"
    fallback = "true" if report.get("fallbackUsed") else "false"
    exp = report.get("expectedFrames")
    got = report.get("finalFrames")
    dur = report.get("finalDuration")
    if dur is None:
        dur = report.get("expectedDuration")
    parts = [
        f"engine={engine}",
        f"fallback={fallback}",
    ]
    if report.get("fallbackUsed") and report.get("fallbackReason"):
        reason = str(report["fallbackReason"]).replace(" ", "_")[:80]
        parts.append(f"reason={reason}")
    if dur is not None:
        try:
            parts.append(f"duration={float(dur):.1f}s")
        except (TypeError, ValueError):
            parts.append(f"duration={dur}")
    if exp is not None or got is not None:
        parts.append(f"frames={got}/{exp}")
    if report.get("wholeJobSec") is not None:
        parts.append(f"whole={report['wholeJobSec']}")
    if report.get("encoder"):
        parts.append(f"encoder={report['encoder']}")
    if report.get("truePeak") is not None:
        parts.append(f"tp={report['truePeak']}")
    print("RENDER_RESULT " + " ".join(parts), flush=True)


def merge_into_timing(edit_dir: Path, report: dict[str, Any]) -> None:
    path = edit_dir / "timing.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            data = {}
    keys = (
        "renderEngine", "fallbackUsed", "fallbackReason", "wholeJobSec",
        "cutSec", "remotionSec", "composeSec", "expectedFrames", "cutFrames",
        "overlayFrames", "finalFrames", "expectedDuration", "finalDuration",
        "integratedLUFS", "truePeak", "tempPeakBytes", "encoder", "gpu",
        "tempCleanupDone",
    )
    for k in keys:
        if report.get(k) is not None:
            data[k] = report[k]
    if report.get("renderEngine"):
        data["renderPath"] = report["renderEngine"]
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def emit(edit_dir: Path, report: dict[str, Any]) -> None:
    print_render_result(report)
    merge_into_timing(edit_dir, report)
    try:
        record_job(report)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] render-stats: {e}", flush=True)
