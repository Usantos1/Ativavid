"""Acrescenta um vídeo no fim da timeline (CTA), sem reimportar o projeto."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}


def source_key_from_stem(stem: str, used: set[str] | None = None) -> str:
    """Mesma regra do run_fast: stem sanitizado, único no mapa de fontes."""
    base = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:28] or "CTA"
    key = base
    n = 2
    used = used or set()
    while key in used:
        key = f"{base}_{n}"
        n += 1
    return key


def dest_cta_path(project_dir: Path, filename: str) -> Path:
    ext = Path(filename).suffix.lower()
    if ext not in VIDEO_EXT:
        raise ValueError("Escolha um MP4 ou MOV")
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", Path(filename).stem).strip("_") or "video"
    stem = stem[:36]
    base = f"cta_{stem}"
    dest = project_dir / f"{base}{ext}"
    n = 2
    while dest.exists():
        dest = project_dir / f"{base}_{n}{ext}"
        n += 1
    return dest


def write_cta_file(project_dir: Path, filename: str, data: bytes) -> Path:
    if not data:
        raise ValueError("arquivo vazio")
    dest = dest_cta_path(project_dir, filename)
    dest.write_bytes(data)
    return dest


def copy_cta_file(project_dir: Path, src: Path) -> Path:
    if not src.is_file():
        raise ValueError("arquivo não encontrado")
    dest = dest_cta_path(project_dir, src.name)
    shutil.copy2(src, dest)
    return dest


def merge_source_paths(
    existing: list[str],
    extras: list[str],
    project_dir: Path,
) -> list[str]:
    """Junta caminhos, só se estiverem dentro da pasta do projeto."""
    root = project_dir.resolve()
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(existing or []) + list(extras or []):
        if not raw:
            continue
        try:
            resolved = Path(str(raw)).resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        if not resolved.is_file():
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(str(resolved))
    return out


def _ffprobe() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return "ffprobe"


def _hide() -> dict:
    try:
        from app.win_process import hide_console_kwargs

        return hide_console_kwargs()
    except Exception:
        return {}


def probe_clip(path: Path) -> dict:
    """Duração e tamanho. Nunca levanta — sem ffprobe devolve duration 0."""
    exe = _ffprobe()
    hide = _hide()
    duration = 0.0
    width, height = 0, 0
    try:
        dur_out = subprocess.run(
            [
                exe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1", str(path),
            ],
            capture_output=True, text=True, check=False, timeout=30, **hide,
        )
        duration = float((dur_out.stdout or "").strip() or 0.0)
    except (OSError, ValueError, subprocess.SubprocessError):
        duration = 0.0
    try:
        wh_out = subprocess.run(
            [
                exe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_tags=rotate",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, check=False, timeout=30, **hide,
        )
        import json

        data = json.loads(wh_out.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        rot = 0
        try:
            rot = int(float((stream.get("tags") or {}).get("rotate") or 0))
        except (TypeError, ValueError):
            rot = 0
        if abs(rot) % 180 == 90:
            width, height = height, width
    except (OSError, ValueError, subprocess.SubprocessError):
        width, height = 0, 0
    return {"duration": duration, "width": width, "height": height}


def validate_cta_clip(info: dict, *, portrait: bool = True) -> str | None:
    dur = float(info.get("duration") or 0.0)
    if dur < 0.4:
        return "Não deu para ler a duração desse vídeo"
    if dur > 600:
        return "Esse vídeo é longo demais para ir no fim"
    return None


def append_cta(
    project_dir: Path,
    *,
    filename: str = "",
    data: bytes | None = None,
    src_path: str | Path | None = None,
    duration_hint: float | None = None,
) -> dict:
    """Copia o arquivo para a pasta do projeto e devolve a chave do take."""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    dest: Path | None = None
    if src_path:
        dest = copy_cta_file(project_dir, Path(src_path))
    elif data and filename:
        dest = write_cta_file(project_dir, filename, data)
    else:
        raise ValueError("nenhum arquivo")
    info = probe_clip(dest)
    dur = float(info.get("duration") or 0.0)
    if dur < 0.4:
        try:
            dur = float(duration_hint or 0.0)
        except (TypeError, ValueError):
            dur = 0.0
    if dur < 0.4:
        try:
            dest.unlink()
        except OSError:
            pass
        raise ValueError("Não deu para ler esse vídeo. Tente de novo com um MP4 ou MOV.")
    if dur > 600:
        try:
            dest.unlink()
        except OSError:
            pass
        raise ValueError("Esse vídeo é longo demais para ir no fim")
    key = source_key_from_stem(dest.stem)
    return {
        "ok": True,
        "source": key,
        "duration": round(dur, 3),
        "path": str(dest),
        "name": dest.name,
    }
