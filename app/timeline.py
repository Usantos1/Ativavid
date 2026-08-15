"""Duração canônica da composição — a mesma regra do Remotion FULL.

Root.tsx (shortform e longform) e o proto Overlay:

    durationInFrames = Math.max(1, Math.round(editData.durationSec * editData.fps))

Python 3 `round` usa banker's rounding em *.5; Math.round arredonda half-up.
Esta função replica o Math.round para FULL e OVERLAY terminarem no mesmo frame.
"""
from __future__ import annotations

import math
from typing import Any


def js_round(value: float) -> int:
    """ECMAScript Math.round: half away from zero (half-up para positivos)."""
    x = float(value)
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


def canonical_duration_in_frames(duration_sec: float, fps: float) -> int:
    """Mesma conta que `durationInFrames` no Root.tsx do FULL."""
    return max(1, js_round(float(duration_sec) * float(fps)))


def canonical_timeline(*, duration_sec: float, fps: float) -> dict[str, Any]:
    fps_f = float(fps) if float(fps) > 0 else 30.0
    src = float(duration_sec)
    frames = canonical_duration_in_frames(src, fps_f)
    return {
        "fps": fps_f,
        "sourceDurationSec": src,
        "durationInFrames": frames,
        "durationSec": frames / fps_f,
    }


def timeline_from_edit_data(edit_data: dict[str, Any]) -> dict[str, Any]:
    return canonical_timeline(
        duration_sec=float(edit_data.get("durationSec") or 0),
        fps=float(edit_data.get("fps") or 30),
    )


def planned_edit_duration_sec(edl: dict[str, Any] | None) -> float | None:
    """Duração da edição (J-cut / EDL), não a do container do cut.mp4."""
    if not edl:
        return None
    planned = edl.get("total_duration_s")
    if planned not in (None, ""):
        try:
            val = float(planned)
        except (TypeError, ValueError):
            val = 0.0
        if val > 0:
            return val
    timeline = edl.get("jcut_timeline") or []
    if timeline:
        total = 0.0
        for item in timeline:
            try:
                total += float(item.get("video_duration") or 0)
            except (TypeError, ValueError):
                pass
        if total > 0:
            return total
    ranges = edl.get("ranges") or []
    if ranges:
        total = 0.0
        for r in ranges:
            try:
                total += float(r.get("end") or 0) - float(r.get("start") or 0)
            except (TypeError, ValueError):
                pass
        if total > 0:
            return total
    return None
