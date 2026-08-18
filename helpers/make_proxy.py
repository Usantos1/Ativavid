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
    enc = encoder if encoder in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf") else "libx264"
    # -preset veryfast/-crf são flags de x264: nos encoders de GPU elas
    # falhavam SEMPRE e todo proxy pagava um encode perdido antes do fallback.
    quality = {
        "libx264": ["-preset", "veryfast", "-crf", "28"],
        "h264_nvenc": ["-preset", "p1", "-rc", "vbr", "-cq", "32", "-b:v", "0"],
        "h264_qsv": ["-preset", "veryfast", "-global_quality", "30"],
        "h264_amf": ["-quality", "speed", "-rc", "cqp", "-qp_i", "30", "-qp_p", "32"],
    }

    def _cmd(e: str) -> list[str]:
        return [
            ffmpeg, "-y", "-i", str(cut),
            "-vf", vf,
            "-c:v", e, *quality[e],
            "-an",
            "-movflags", "+faststart",
            str(dest),
        ]

    hide = hide_console_kwargs()
    try:
        r = subprocess.run(_cmd(enc), capture_output=True, text=True, timeout=180, **hide)
        if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
            if enc != "libx264":
                r = subprocess.run(
                    _cmd("libx264"), capture_output=True, text=True, timeout=180, **hide)
            if r.returncode != 0 or not dest.exists():
                return None
        return dest
    except (OSError, subprocess.TimeoutExpired):
        return None
