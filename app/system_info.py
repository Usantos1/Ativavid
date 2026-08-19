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

from app.win_process import hide_console_kwargs, refresh_path_env

# Evita re-disparar processos lentos a cada refresh da UI
_CACHE: dict[str, Any] | None = None
_CACHE_AT = 0.0
_CACHE_TTL_S = 120.0


def _run(cmd: list[str], timeout: float = 4.0) -> str:
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


def _ffmpeg_cmd() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe_cmd() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return shutil.which("ffprobe") or "ffprobe"


def _ffmpeg_encoders() -> set[str]:
    out = _run([_ffmpeg_cmd(), "-hide_banner", "-encoders"], timeout=2.5)
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
        _ffmpeg_cmd(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "color=c=black:s=1280x720:d=0.04", "-frames:v", "1", "-an",
        "-c:v", name, *extras, "-f", "null", "-",
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            **hide_console_kwargs(),
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _ram_gb_ctypes() -> tuple[float | None, float | None]:
    """RAM via WinAPI — sem PowerShell (rápido e estável no pythonw)."""
    if sys.platform != "win32":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return None, None
        total = round(stat.ullTotalPhys / (1024**3), 1)
        free = round(stat.ullAvailPhys / (1024**3), 1)
        return total, free
    except Exception:
        return None, None


def physical_cores() -> int:
    """Núcleos FÍSICOS (não threads).

    ffmpeg e Remotion são limitados por núcleo real: hyper-threading não
    dobra a capacidade. Contar os 8 threads de um CPU de 4 núcleos fazia o
    app abrir 4 pipelines pesados que brigavam entre si e cada vídeo levava
    o triplo do tempo. 0 = não deu para descobrir (o chamador usa o lógico).
    """
    if sys.platform == "win32":
        try:
            out = _run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Processor | "
                    "Measure-Object -Property NumberOfCores -Sum).Sum",
                ],
                timeout=8,
            ).strip()
            if out.isdigit() and int(out) > 0:
                return int(out)
        except Exception:  # noqa: BLE001
            pass
        return 0
    try:
        import multiprocessing

        # Linux/mac: sem contagem física barata; o lógico é o que temos
        return multiprocessing.cpu_count()
    except Exception:  # noqa: BLE001
        return 0


def _ram_gb() -> tuple[float | None, float | None]:
    total, free = _ram_gb_ctypes()
    if total is not None:
        return total, free
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return round(vm.total / (1024**3), 1), round(vm.available / (1024**3), 1)
    except Exception:
        return None, None


def _gpu_windows() -> list[dict[str, Any]]:
    """Lista GPUs. Timeout curto — falha silenciosa não pode derrubar /api/system."""
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name, AdapterRAM, DriverVersion | ConvertTo-Json -Compress"
    )
    raw = _run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            ps,
        ],
        timeout=4,
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


def _minimal_machine(projects_root: Path | None = None, err: str = "") -> dict[str, Any]:
    root = projects_root or Path.home() / "ATIVAVID" / "Projetos"
    disk_free = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        disk_free = round(shutil.disk_usage(str(root)).free / (1024**3), 1)
    except OSError:
        pass
    total, free = _ram_gb()
    return {
        "os": platform.system(),
        "osRelease": platform.release(),
        "osVersion": platform.version(),
        "python": platform.python_version(),
        "cpu": platform.processor() or platform.machine(),
        "cores": os.cpu_count() or 1,
        "physicalCores": physical_cores() or os.cpu_count() or 1,
        "ramGb": total,
        "ramFreeGb": free,
        "gpus": [],
        "diskFreeGb": disk_free,
        "projectsRoot": str(root),
        "ffmpeg": {"installed": False, "version": None, "encoders": []},
        "ffprobe": {"installed": False, "version": None},
        "accel": {
            "nvenc": False,
            "qsv": False,
            "amf": False,
            "preferredEncoder": "libx264",
            "mode": "cpu",
            "nvencListed": False,
            "probed": False,
        },
        "error": err or None,
    }


def detect_machine(
    projects_root: Path | None = None,
    *,
    force: bool = False,
    probe_encoders: bool = False,
    quick: bool = False,
) -> dict[str, Any]:
    """Detecta OS/RAM/GPU. Nunca levanta — /api/system precisa sempre responder.

    quick=True: sem PowerShell/GPU e sem ffmpeg -encoders (UI Sistema <1s).
    Doutor usa quick=False (detalhe completo).
    """
    global _CACHE, _CACHE_AT
    now = time.time()
    root_key = ""
    if projects_root is not None:
        try:
            root_key = str(Path(projects_root).expanduser().resolve())
        except OSError:
            root_key = str(projects_root)
    if (
        not force
        and _CACHE is not None
        and (now - _CACHE_AT) < _CACHE_TTL_S
        and (
            not root_key
            or str(_CACHE.get("projectsRoot") or "") == root_key
            or str(_CACHE.get("projectsRoot") or "") == str(projects_root or "")
        )
        # cache full serve quick; cache quick does NOT serve full
        and (quick or not _CACHE.get("quick"))
    ):
        return dict(_CACHE)

    try:
        refresh_path_env()
    except Exception:
        pass
    try:
        from app.ffmpeg_tools import ensure_ffmpeg_on_path

        ensure_ffmpeg_on_path()
    except Exception:
        pass

    try:
        result = _detect_machine_inner(
            projects_root,
            probe_encoders=probe_encoders,
            quick=quick,
        )
    except Exception as e:
        result = _minimal_machine(projects_root, err=str(e)[:240])

    if root_key:
        result["projectsRoot"] = root_key
    result["quick"] = bool(quick)
    # Só sobrescreve cache full com full; quick só se ainda não há cache
    if not quick or _CACHE is None or _CACHE.get("quick"):
        _CACHE = result
        _CACHE_AT = time.time()
    return dict(result)


def _detect_machine_inner(
    projects_root: Path | None,
    *,
    probe_encoders: bool,
    quick: bool = False,
) -> dict[str, Any]:
    total_ram, free_ram = _ram_gb()
    cpu = platform.processor() or platform.machine()
    cores = os.cpu_count() or 1
    physical = physical_cores() or cores

    ff_bin = _ffmpeg_cmd()
    fp_bin = _ffprobe_cmd()
    ff_ok = Path(ff_bin).exists() if os.path.isabs(ff_bin) else bool(shutil.which(ff_bin) or shutil.which("ffmpeg"))
    fp_ok = Path(fp_bin).exists() if os.path.isabs(fp_bin) else bool(shutil.which(fp_bin) or shutil.which("ffprobe"))

    encoders: set[str] = set()
    gpus: list[dict[str, Any]] = []
    if quick:
        # UI Sistema: RAM/cores/disco + encoders ffmpeg (rápido). Sem PowerShell GPU.
        encoders = _ffmpeg_encoders() if ff_ok else set()
    else:
        encoders = _ffmpeg_encoders() if ff_ok else set()
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
        root = Path(root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        disk_free = round(shutil.disk_usage(str(root)).free / (1024**3), 1)
    except OSError:
        pass

    ff: list[str] = []
    fp: list[str] = []
    if not quick:
        ff = _run([ff_bin, "-version"], timeout=3).splitlines() if ff_ok else []
        fp = _run([fp_bin, "-version"], timeout=3).splitlines() if fp_ok else []

    return {
        "os": platform.system(),
        "osRelease": platform.release(),
        "osVersion": platform.version(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cores": cores,
        "physicalCores": physical,
        "ramGb": total_ram,
        "ramFreeGb": free_ram,
        "gpus": gpus,
        "diskFreeGb": disk_free,
        "projectsRoot": str(root),
        "ffmpeg": {
            "installed": bool(ff_ok),
            "version": ff[0][:80] if ff else None,
            "encoders": sorted(encoders),
        },
        "ffprobe": {
            "installed": bool(fp_ok),
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


def system_payload(projects_root: Path | None = None) -> dict[str, Any]:
    """Resposta do /api/system — usada pelos dois servidores.

    Estava copiada nos dois e já tinha divergido (um cortava a mensagem de erro
    em 200 caracteres, o outro em 240). A detecção roda em thread separada com
    prazo: numa máquina lenta ela travava a tela de Configurações.
    """
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FutTimeout

    from app.performance import profile_settings
    from app.settings_store import load_settings, public_settings

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(detect_machine, projects_root, quick=True)
            try:
                machine = fut.result(timeout=5.0)
            except FutTimeout:
                machine = _minimal_machine(
                    projects_root, err="detecção demorou — veja Diagnóstico abaixo")
    except Exception as e:  # noqa: BLE001
        machine = _minimal_machine(projects_root, err=str(e)[:240])

    try:
        settings = load_settings()
        publicas = public_settings()
    except Exception:  # noqa: BLE001
        settings, publicas = {}, {}

    try:
        perf = profile_settings(settings.get("performanceProfile") if settings else None,
                                machine)
    except Exception:  # noqa: BLE001
        perf = {"profile": "auto", "label": "Automático", "parallelJobs": 1,
                "proxyEnabled": True, "proxyHeight": 540}

    return {"machine": machine, "settings": publicas, "performance": perf}
