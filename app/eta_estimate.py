"""ETA local a partir de timing.json histórico. Sem cronômetro falso."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def features(timing: dict | None, *, duration_s: float | None = None, cuts: int | None = None) -> dict:
    t = dict(timing or {})
    dur = duration_s if duration_s is not None else t.get("finalDuration") or t.get("sourceDuration")
    ncuts = cuts if cuts is not None else t.get("cuts") or t.get("rangeCount")
    path = str(t.get("renderPath") or t.get("zoomEngine") or "").lower()
    hdr = bool(t.get("hdr") or t.get("isHdr"))
    if not hdr:
        hdr = "hdr" in path or "hlg" in str(t.get("color") or "").lower()
    return {
        "duration": _f(dur),
        "cuts": int(_f(ncuts)),
        "hdr": hdr,
        "path": path,
        "total": _f(t.get("wholeJobSec") or t.get("totalSec")),
    }


def _weight(feat: dict) -> float:
    w = 8.0 + feat["duration"] * 1.15
    if feat["cuts"] > 12:
        w += (feat["cuts"] - 12) * 0.8
    if feat["hdr"]:
        w *= 1.35
    if "overlay" in feat["path"]:
        w *= 0.72
    if feat["duration"] >= 70:
        w *= 1.1
    return max(8.0, w)


def estimate_seconds(job: dict | None, history: list[dict] | None) -> float | None:
    """Devolve segundos previstos, ou None se não houver histórico suficiente."""
    hist = [h for h in (history or []) if _f((h or {}).get("wholeJobSec") or (h or {}).get("totalSec")) > 3]
    if len(hist) < 2:
        return None
    ratios: list[float] = []
    for h in hist:
        feat = features(h)
        if feat["duration"] < 3 or feat["total"] < 3:
            continue
        ratios.append(feat["total"] / _weight(feat))
    if len(ratios) < 2:
        return None
    ratios.sort()
    mid = ratios[len(ratios) // 2]
    want = features(job or {})
    if want["duration"] < 1:
        return None
    return round(max(12.0, _weight(want) * mid), 1)


def format_eta(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 45:
        return "~40s restantes"
    if s < 90:
        return "~1 min restante"
    mins = s // 60
    rem = s % 60
    if rem < 15:
        return f"~{mins} min restantes"
    return f"~{mins}min{rem:02d}s restantes"


def label_for_job(job: dict | None, history: list[dict] | None) -> str | None:
    return format_eta(estimate_seconds(job, history))


def enrich_from_edit(timing: dict | None, edit_dir: Path | None) -> dict:
    """Completa duration/cuts a partir de intent/EDL já gravados — sem probe."""
    t = dict(timing or {})
    if edit_dir is None:
        return t
    edit = Path(edit_dir)
    intent_p = edit / "job_intent.json"
    if intent_p.exists() and not t.get("sourceDuration") and not t.get("finalDuration"):
        try:
            intent = json.loads(intent_p.read_text(encoding="utf-8-sig"))
            if intent.get("sourceDurationSec"):
                t["sourceDuration"] = float(intent["sourceDurationSec"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    edl_p = edit / "edl.json"
    if edl_p.exists():
        try:
            edl = json.loads(edl_p.read_text(encoding="utf-8-sig"))
            ranges = [r for r in (edl.get("ranges") or []) if isinstance(r, dict)]
            if ranges and not t.get("cuts") and not t.get("rangeCount"):
                t["cuts"] = len(ranges)
            if ranges and not t.get("sourceDuration") and not t.get("finalDuration"):
                t["sourceDuration"] = max(float(r.get("end") or 0) for r in ranges)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return t


def collect_history(projects_root: Path | None, *, limit: int = 30) -> list[dict]:
    root = Path(projects_root) if projects_root else None
    if root is None or not root.is_dir():
        return []
    files = sorted(
        root.glob("*/edit/timing.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out: list[dict] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        out.append(enrich_from_edit(data, path.parent))
    return out


def attach_eta(job: dict, history: list[dict] | None, edit_dir: Path | None = None) -> dict:
    """Anexa etaLabel só se houver histórico. Não inventa cronômetro."""
    status = str(job.get("status") or "")
    if status not in ("processing", "queued", "importing"):
        return job
    feat = enrich_from_edit({}, edit_dir)
    if job.get("durationSec"):
        feat["sourceDuration"] = job["durationSec"]
    label = label_for_job(feat, history)
    if label:
        job["etaLabel"] = label
    return job
