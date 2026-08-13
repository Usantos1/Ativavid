"""Probe rápido de mídia para a tela Início (ffprobe local)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def probe_video(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "error": "arquivo não encontrado"}
    if not shutil.which("ffprobe"):
        return {"ok": False, "error": "ffprobe ausente"}
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        from app.win_process import hide_console_kwargs

        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            **hide_console_kwargs(),
        )
        data = json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)[:120]}

    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        return {"ok": False, "error": "sem vídeo"}

    w = int(v.get("width") or 0)
    h = int(v.get("height") or 0)
    # rotation
    rot = 0
    try:
        rot = int(float((v.get("tags") or {}).get("rotate") or 0))
    except (TypeError, ValueError):
        pass
    if abs(rot) % 180 == 90:
        w, h = h, w
    dur = float(fmt.get("duration") or v.get("duration") or 0)
    fps = 30.0
    rate = v.get("r_frame_rate") or "30/1"
    try:
        if "/" in rate:
            n, d = rate.split("/", 1)
            fps = float(n) / max(float(d), 1e-6)
        else:
            fps = float(rate)
    except (TypeError, ValueError):
        pass
    size_mb = round(int(fmt.get("size") or 0) / (1024 * 1024), 1)
    orientation = "vertical" if h > w else ("horizontal" if w > h else "quadrado")
    return {
        "ok": True,
        "durationSec": round(dur, 2),
        "width": w,
        "height": h,
        "fps": round(fps, 2),
        "videoCodec": v.get("codec_name"),
        "audio": bool(a),
        "audioCodec": (a or {}).get("codec_name"),
        "sizeMb": size_mb,
        "orientation": orientation,
        "label": (
            f"{_fmt_dur(dur)} · {w}×{h} · "
            f"{'Vertical' if orientation == 'vertical' else orientation.title()} · "
            f"{'Áudio OK' if a else 'Sem áudio'}"
        ),
    }


def _fmt_dur(s: float) -> str:
    s = max(0, int(round(s)))
    m, sec = divmod(s, 60)
    return f"{m:02d}:{sec:02d}"
