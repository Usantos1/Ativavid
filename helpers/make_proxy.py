"""Gera proxy leve do cut para preview fluido."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
try:
    from app.win_process import hide_console_kwargs
except Exception:  # noqa: BLE001
    def hide_console_kwargs() -> dict:  # type: ignore[misc]
        return {}


def make_cut_proxy(
    cut: Path,
    dest: Path,
    *,
    height: int = 540,
    encoder: str = "libx264",
) -> Path | None:
    """Escreve dest (ex.: edit/cut_proxy.mp4). Retorna path ou None."""
    if not cut.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    h = max(360, min(int(height or 540), 720))
    # even dimensions
    vf = f"scale=-2:{h}"
    cmd = [
        ffmpeg, "-y", "-i", str(cut),
        "-vf", vf,
        "-c:v", encoder if encoder in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf") else "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-an",
        "-movflags", "+faststart",
        str(dest),
    ]
    # GPU encoders need different flags; fall back to libx264 on failure
    hide = hide_console_kwargs()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, **hide)
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
            if encoder != "libx264":
                cmd[cmd.index("-c:v") + 1] = "libx264"
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, **hide)
            if r.returncode != 0 or not dest.exists():
                return None
        return dest
    except (OSError, subprocess.TimeoutExpired):
        return None
