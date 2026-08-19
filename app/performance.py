"""Perfis de desempenho + concorrência da fila.

Dois conceitos:
  parallelJobs  — quantos vídeos fazem a fase LEVE ao mesmo tempo
                  (transcrever, analisar, cortar, preparar). Remotion espera
                  no lock quando a fase pesada chega.
  renderSlots   — quantos Remotion/npm pesados podem rodar juntos (1–2).
"""
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
    ram = float(m.get("ramGb") or 0)
    cores = int(m.get("cores") or 4)
    # Quantos vídeos rodam juntos se mede em núcleo REAL: ffmpeg e Remotion
    # não ganham com hyper-threading. Contar threads fazia um CPU de 4
    # núcleos abrir 4 pipelines pesados, e cada vídeo levava o triplo do
    # tempo (medido na máquina do usuário: fase de análise de 2min virou 8min).
    real = int(m.get("physicalCores") or 0) or max(1, cores // 2)

    if profile == "eco":
        return {
            "profile": profile,
            "label": "Econômico",
            "parallelJobs": 1,
            "renderSlots": 1,
            "extractJobs": 1,
            "proxyHeight": 540,
            "proxyEnabled": True,
            "thumbEager": False,
            "encoder": "libx264",
            "renderTier": "preview",
            "previewFps": 24,
            "hint": "1 video por vez — leve + Remotion no mesmo ritmo.",
        }
    if profile == "performance":
        # Fase leve em paralelo; Remotion limitado (slot).
        parallel = min(6, max(2, real // 2))
        render_slots = 2 if ram >= 24 and real >= 8 else 1
        return {
            "profile": profile,
            "label": "Desempenho",
            "parallelJobs": parallel,
            "renderSlots": render_slots,
            "extractJobs": min(4, max(2, real // 2)),
            "proxyHeight": 720,
            "proxyEnabled": ram < 32,
            "thumbEager": True,
            "encoder": enc,
            "renderTier": "final",
            "previewFps": 30,
            "hint": (
                f"{parallel} em fase leve / Remotion {render_slots} por vez."
            ),
        }
    # balanced
    parallel = min(4, max(1, real // 2)) if ram >= 12 else 1
    return {
        "profile": profile,
        "label": "Balanceado",
        "parallelJobs": parallel,
        "renderSlots": 1,
        "extractJobs": min(3, max(1, real // 3)),
        "proxyHeight": 540,
        "proxyEnabled": True,
        "thumbEager": True,
        "encoder": enc,
        "renderTier": "final",
        "previewFps": 30,
        "hint": f"{parallel} em fase leve / Remotion 1 por vez.",
    }
