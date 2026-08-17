"""Ranges protegidos: a IA não remove. Não mexe em render."""
from __future__ import annotations

from typing import Any


def overlap_sec(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def overlaps(a0: float, a1: float, b0: float, b1: float, *, min_sec: float = 0.08) -> bool:
    return overlap_sec(a0, a1, b0, b1) >= min_sec


def normalize_range(item: dict | None) -> dict | None:
    if not isinstance(item, dict):
        return None
    try:
        start = float(item.get("start"))
        end = float(item.get("end"))
    except (TypeError, ValueError):
        return None
    if end <= start or start < 0:
        return None
    out = {"start": round(start, 3), "end": round(end, 3)}
    for key in ("source", "reason", "label"):
        val = item.get(key)
        if val:
            out[key] = str(val)[:80]
    for key in ("draftStart", "draftEnd"):
        if item.get(key) is None:
            continue
        try:
            out[key] = round(float(item[key]), 3)
        except (TypeError, ValueError):
            pass
    return out


def merge_ranges(ranges: list[dict] | None) -> list[dict]:
    items = [r for r in (normalize_range(x) for x in (ranges or [])) if r]
    items.sort(key=lambda r: (str(r.get("source") or ""), r["start"]))
    out: list[dict] = []
    for r in items:
        if not out:
            out.append(r)
            continue
        last = out[-1]
        same = str(last.get("source") or "") == str(r.get("source") or "")
        if same and r["start"] <= last["end"] + 0.05:
            last["end"] = max(last["end"], r["end"])
            if r.get("draftEnd") is not None:
                last["draftEnd"] = max(float(last.get("draftEnd") or 0), float(r["draftEnd"]))
        else:
            out.append(r)
    return out


def add_range(ranges: list[dict] | None, item: dict) -> list[dict]:
    nxt = list(ranges or [])
    norm = normalize_range(item)
    if norm:
        nxt.append(norm)
    return merge_ranges(nxt)


def remove_overlapping(ranges: list[dict] | None, start: float, end: float) -> list[dict]:
    out: list[dict] = []
    for r in ranges or []:
        a0 = float(r.get("draftStart") if r.get("draftStart") is not None else r.get("start") or 0)
        a1 = float(r.get("draftEnd") if r.get("draftEnd") is not None else r.get("end") or 0)
        if not overlaps(a0, a1, start, end):
            out.append(r)
    return out


def _op_span(op: dict) -> tuple[float, float] | None:
    kind = str(op.get("op") or op.get("action") or "")
    if kind in ("remove_range", "trim_range") and "start" in op and "end" in op:
        try:
            return float(op["start"]), float(op["end"])
        except (TypeError, ValueError):
            return None
    if kind == "set_duration_max" and "maxSec" in op:
        try:
            return float(op["maxSec"]), 1e9
        except (TypeError, ValueError):
            return None
    return None


def filter_ai_ops(
    operations: list[dict[str, Any]] | None,
    protected: list[dict] | None,
) -> dict[str, list[dict]]:
    """Separa ops que cortam range protegido. restore_range passa."""
    kept: list[dict] = []
    blocked: list[dict] = []
    prot = merge_ranges(protected)
    for op in operations or []:
        kind = str(op.get("op") or op.get("action") or "")
        if kind == "restore_range":
            kept.append(op)
            continue
        span = _op_span(op)
        if span is None:
            kept.append(op)
            continue
        a0, a1 = span
        hit = False
        for r in prot:
            b0 = float(r.get("draftStart") if r.get("draftStart") is not None else r["start"])
            b1 = float(r.get("draftEnd") if r.get("draftEnd") is not None else r["end"])
            if overlaps(a0, a1, b0, b1):
                hit = True
                break
        if hit:
            blocked.append({**op, "blocked": True, "reason": "PROTECTED_RANGE_BLOCKED"})
        else:
            kept.append(op)
    return {"kept": kept, "blocked": blocked}


def format_blocked_log(blocked: list[dict] | None) -> list[str]:
    lines: list[str] = []
    for op in blocked or []:
        kind = str(op.get("op") or op.get("action") or "?").upper()
        try:
            a = float(op.get("start") if "start" in op else op.get("maxSec") or 0)
            b = float(op.get("end") if "end" in op else a)
            lines.append(f"PROTECTED_RANGE_BLOCKED {kind} {a:.2f}-{b:.2f}")
        except (TypeError, ValueError):
            lines.append(f"PROTECTED_RANGE_BLOCKED {kind}")
    return lines
