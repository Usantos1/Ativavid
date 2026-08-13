"""Detecção da máquina — Sistema / Desempenho (local-first)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.win_process import hide_console_kwargs

# Evita re-disparar 8–10 processos (e flash de CMD) a cada refresh da UI
_CACHE: dict[str, Any] | None = None
_CACHE_AT = 0.0
_CACHE_TTL_S = 120.0


def _run(cmd: list[str], timeout: float = 8.0) -> str:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            **hide_console_kwargs(),
        )
        return ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _ffmpeg_encoders() -> set[str]:
    out = _run(["ffmpeg", "-hide_banner", "-encoders"], timeout=10)
    found: set[str] = set()
    for name in ("h264_nvenc", "hevc_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"):
        if name in out:
            found.add(name)
    return found


def _encoder_opens(name: str) -> bool:
    """True if ffmpeg can actually open the encoder (nvenc may be listed but driver-too-old)."""
    extras = {
        "h264_nvenc": ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"],
        "h264_qsv": ["-preset", "medium", "-global_quality", "23", "-pix_fmt", "nv12"],
        "h264_amf": ["-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24", "-pix_fmt", "yuv420p"],
    }.get(name, [])
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "color=c=black:s=64x64:d=0.04", "-frames:v", "1", "-an",
        "-c:v", name, *extras, "-f", "null", "-",
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=6,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            **hide_console_kwargs(),
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _gpu_windows() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name, AdapterRAM, DriverVersion | ConvertTo-Json -Compress"
    )
    raw = _run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
        timeout=8,
    )
    if not raw:
        return []
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    gpus = []
    for g in data or []:
        ram = g.get("AdapterRAM") or 0
        try:
            ram_gb = round(int(ram) / (1024**3), 1) if int(ram) > 0 else None
        except (TypeError, ValueError):
            ram_gb = None
        gpus.append({
            "name": (g.get("Name") or "GPU").strip(),
            "vramGb": ram_gb,
            "driver": g.get("DriverVersion"),
        })
    return gpus


def _ram_gb() -> tuple[float | None, float | None]:
    """(total, available) in GB."""
    if sys.platform == "win32":
        ps = (
            "$o=Get-CimInstance Win32_OperatingSystem; "
            "[pscustomobject]@{total=$o.TotalVisibleMemorySize; free=$o.FreePhysicalMemory} "
            "| ConvertTo-Json -Compress"
        )
        raw = _run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=6,
        )
        if raw:
            import json
            try:
                d = json.loads(raw)
                total = round(int(d["total"]) / (1024**2), 1)
                free = round(int(d["free"]) / (1024**2), 1)
                return total, free
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return round(vm.total / (1024**3), 1), round(vm.available / (1024**3), 1)
    except Exception:
        return None, None


def detect_machine(
    projects_root: Path | None = None,
    *,
    force: bool = False,
    probe_encoders: bool = False,
) -> dict[str, Any]:
    """Detecta OS/RAM/GPU. Por padrão NÃO abre cada encoder (isso trava a UI do Sistema)."""
    global _CACHE, _CACHE_AT
    now = time.time()
    if (
        not force
        and _CACHE is not None
        and (now - _CACHE_AT) < _CACHE_TTL_S
        and (
            projects_root is None
            or str(_CACHE.get("projectsRoot") or "") == str(projects_root)
        )
    ):
        return dict(_CACHE)

    total_ram, free_ram = _ram_gb()
    cpu = platform.processor() or platform.machine()
    cores = os.cpu_count() or 1
    encoders = _ffmpeg_encoders() if shutil.which("ffmpeg") else set()
    gpus = _gpu_windows()
    nvidia = any("nvidia" in (g.get("name") or "").lower() for g in gpus) or ("h264_nvenc" in encoders)
    qsv = "h264_qsv" in encoders or any("intel" in (g.get("name") or "").lower() for g in gpus)
    amf = "h264_amf" in encoders or any(
        x in (g.get("name") or "").lower() for g in gpus for x in ("amd", "radeon")
    )

    prefer = "libx264"
    if nvidia and "h264_nvenc" in encoders:
        prefer = "h264_nvenc"
        if probe_encoders and not _encoder_opens("h264_nvenc"):
            prefer = "libx264"
    if prefer == "libx264" and qsv and "h264_qsv" in encoders:
        prefer = "h264_qsv"
        if probe_encoders and not _encoder_opens("h264_qsv"):
            prefer = "libx264"
    if prefer == "libx264" and amf and "h264_amf" in encoders:
        prefer = "h264_amf"
        if probe_encoders and not _encoder_opens("h264_amf"):
            prefer = "libx264"

    disk_free = None
    root = projects_root or Path.home() / "ATIVAVID" / "Projetos"
    try:
        root.mkdir(parents=True, exist_ok=True)
        disk_free = round(shutil.disk_usage(str(root)).free / (1024**3), 1)
    except OSError:
        pass

    ff = _run(["ffmpeg", "-version"], timeout=5).splitlines()
    fp = _run(["ffprobe", "-version"], timeout=5).splitlines()

    result = {
        "os": platform.system(),
        "osRelease": platform.release(),
        "osVersion": platform.version(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cores": cores,
        "ramGb": total_ram,
        "ramFreeGb": free_ram,
        "gpus": gpus,
        "diskFreeGb": disk_free,
        "projectsRoot": str(root),
        "ffmpeg": {
            "installed": bool(shutil.which("ffmpeg")),
            "version": ff[0][:80] if ff else None,
            "encoders": sorted(encoders),
        },
        "ffprobe": {
            "installed": bool(shutil.which("ffprobe")),
            "version": fp[0][:80] if fp else None,
        },
        "accel": {
            "nvenc": prefer == "h264_nvenc",
            "qsv": prefer == "h264_qsv",
            "amf": prefer == "h264_amf",
            "preferredEncoder": prefer,
            "mode": "gpu" if prefer != "libx264" else "cpu",
            "nvencListed": "h264_nvenc" in encoders,
            "probed": bool(probe_encoders),
        },
    }
    _CACHE = result
    _CACHE_AT = now
    return dict(result)
