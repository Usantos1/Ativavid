"""Resolve ffmpeg/ffprobe — prefer pasta do usuário / vendor, depois PATH."""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENDOR = REPO / "vendor" / "ffmpeg"
USER_FFMPEG = Path.home() / "ATIVAVID" / "ffmpeg"


def _bin_dirs() -> list[Path]:
    return [USER_FFMPEG, VENDOR]


def ensure_ffmpeg_on_path() -> Path | None:
    """Coloca a melhor pasta ffmpeg no início do PATH. Retorna a pasta ou None."""
    chosen: Path | None = None
    for d in _bin_dirs():
        if (d / "ffprobe.exe").exists() or (d / "ffprobe").exists() or (d / "ffmpeg.exe").exists():
            chosen = d
            break
    if chosen is None:
        return None
    path = os.environ.get("PATH", "")
    vend = str(chosen.resolve())
    parts = [p for p in path.split(os.pathsep) if p] if path else []
    if not parts or Path(parts[0]).resolve() != chosen.resolve():
        os.environ["PATH"] = vend + os.pathsep + path
    return chosen


@lru_cache(maxsize=1)
def ffprobe_bin() -> str:
    ensure_ffmpeg_on_path()
    for d in _bin_dirs():
        for name in ("ffprobe.exe", "ffprobe"):
            p = d / name
            if p.exists():
                return str(p)
    found = shutil.which("ffprobe")
    if found:
        return found
    return "ffprobe"


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    ensure_ffmpeg_on_path()
    for d in _bin_dirs():
        for name in ("ffmpeg.exe", "ffmpeg"):
            p = d / name
            if p.exists():
                return str(p)
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"
