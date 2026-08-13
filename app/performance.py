"""Perfis de desempenho + concorrência da fila."""
from __future__ import annotations

from typing import Any

from app.system_info import detect_machine

PROFILES = ("auto", "eco", "balanced", "performance")


def resolve_profile(name: str | None, machine: dict[str, Any] | None = None) -> str:
    n = (name or "auto").strip().lower()
    if n in PROFILES and n != "auto":
        return n
    m = machine or detect_machine()
    ram = float(m.get("ramGb") or 8)
    cores = int(m.get("cores") or 2)
    gpu = (m.get("accel") or {}).get("mode") == "gpu"
    if ram < 8 or cores <= 2:
        return "eco"
    if gpu and ram >= 16 and cores >= 8:
        return "performance"
    return "balanced"


def profile_settings(name: str | None = None, machine: dict[str, Any] | None = None) -> dict[str, Any]:
    m = machine or detect_machine()
    profile = resolve_profile(name, m)
    enc = (m.get("accel") or {}).get("preferredEncoder") or "libx264"

    if profile == "eco":
        return {
            "profile": profile,
            "label": "Econômico",
            "parallelJobs": 1,
            "extractJobs": 1,
            "proxyHeight": 540,
            "proxyEnabled": True,
            "thumbEager": False,
            "encoder": "libx264",  # eco: always CPU for stability
            "renderTier": "preview",
            "previewFps": 24,
        }
    if profile == "performance":
        ram = float(m.get("ramGb") or 0)
        cores = int(m.get("cores") or 4)
        parallel = 1
        if ram >= 16 and cores >= 6:
            parallel = 2
        if ram >= 32 and cores >= 10:
            parallel = 3
        return {
            "profile": profile,
            "label": "Desempenho",
            "parallelJobs": parallel,
            "extractJobs": min(4, max(2, cores // 2)),
            "proxyHeight": 720,
            "proxyEnabled": ram < 32,
            "thumbEager": True,
            "encoder": enc,
            "renderTier": "final",
            "previewFps": 30,
        }
    # balanced
    ram = float(m.get("ramGb") or 0)
    cores = int(m.get("cores") or 4)
    return {
        "profile": profile,
        "label": "Balanceado",
        "parallelJobs": 2 if ram >= 16 and cores >= 6 else 1,
        "extractJobs": min(3, max(1, cores // 3)),
        "proxyHeight": 540,
        "proxyEnabled": True,
        "thumbEager": True,
        "encoder": enc,
        "renderTier": "final",
        "previewFps": 30,
    }
