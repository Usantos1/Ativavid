"""Limpeza de cache local do ATIVAVID — nunca apaga fontes do usuário."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


CACHE_GLOBS = (
    ".preview_cache",
    "clips_draft",
    "clips_preview",
    "_jcut_video.mp4",
    "_jcut_audio.wav",
    "_concat_jcut.txt",
)


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for child in p.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def measure_cache(projects_root: Path) -> dict[str, Any]:
    bytes_total = 0
    items: list[dict[str, Any]] = []
    if not projects_root.exists():
        return {"bytes": 0, "gb": 0.0, "items": []}
    for proj in projects_root.iterdir():
        if not proj.is_dir() or proj.name.startswith("."):
            continue
        edit = proj / "edit"
        if not edit.is_dir():
            continue
        for name in (".preview_cache", "clips_draft", "clips_preview", "clips_graded"):
            p = edit / name
            if p.exists():
                sz = _dir_size(p)
                bytes_total += sz
                items.append({"path": str(p), "bytes": sz})
        # remotion node_modules never — only public temp renders? skip node_modules
    return {
        "bytes": bytes_total,
        "gb": round(bytes_total / (1024**3), 2),
        "items": items[:200],
    }


def clear_cache(projects_root: Path, *, keep_graded: bool = True) -> dict[str, Any]:
    removed = 0
    freed = 0
    for proj in projects_root.iterdir() if projects_root.exists() else []:
        if not proj.is_dir() or proj.name.startswith("."):
            continue
        edit = proj / "edit"
        targets = [".preview_cache", "clips_draft", "clips_preview"]
        if not keep_graded:
            targets.append("clips_graded")
        for name in targets:
            p = edit / name
            if not p.exists():
                continue
            sz = _dir_size(p)
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)
                removed += 1
                freed += sz
            except OSError:
                pass
    return {"ok": True, "removed": removed, "freedGb": round(freed / (1024**3), 2)}
