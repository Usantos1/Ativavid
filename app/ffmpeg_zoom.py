"""Zoom por segmento no extract do corte — crop/scale, sem zoompan.

S = base + push * n / (N-1)
Âncora (cx, cy) = (0.5, 0.4) quando não há tracking.
Sem VIDEO_LAG. Sem etapa extra depois do cut.mp4.
"""
from __future__ import annotations

import os
from typing import Any


def experimental_on() -> bool:
    env = (os.environ.get("ATIVAVID_FFMPEG_ZOOM") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        from app.settings_store import load_settings

        return bool(load_settings().get("experimentalFfmpegZoom"))
    except Exception:
        return False


def zoom_enabled(edl: dict[str, Any] | None) -> bool:
    z = (edl or {}).get("ffmpegZoom")
    return isinstance(z, dict) and bool(z.get("enabled"))


# 5.0.66: zoom escolhido POR TAKE no editor. O que o planejador escreve
# continua sendo o padrao ("automatico"); estas quatro opcoes so mandam
# quando o usuario pediu alguma coisa naquele trecho.
#
# Os numeros saem do que os projetos reais ja usam: 313 de 317 tem
# `pushIn` 0,04 e as bases alternam entre 1,10 e 1,22. "Suave" fica abaixo
# dessa faixa e "forte" acima, para as duas serem visiveis ao lado do
# automatico.
ZOOMS_DO_TAKE: dict[str, dict[str, float] | None] = {
    "nenhum": None,
    "suave": {"base": 1.06, "push": 0.03},
    "forte": {"base": 1.20, "push": 0.12},
}


def zoom_do_range(r: Any) -> str:
    """O pedido de zoom deste trecho: "" (automatico) ou uma chave."""
    if not isinstance(r, dict):
        return ""
    v = str(r.get("zoom") or "").strip().lower()
    return v if v in ZOOMS_DO_TAKE else ""


def zoom_for_index(edl: dict[str, Any], index: int) -> dict[str, Any] | None:
    z = edl.get("ffmpegZoom")
    if not isinstance(z, dict) or not z.get("enabled"):
        return None
    ranges = edl.get("ranges") or []
    pedido = zoom_do_range(ranges[index] if 0 <= index < len(ranges) else None)
    if pedido:
        escolha = ZOOMS_DO_TAKE[pedido]
        if escolha is None:
            return None          # este take fica parado
        return {
            "base": escolha["base"],
            "push": escolha["push"],
            "cx": float(z.get("targetX") or 0.5),
            "cy": float(z.get("targetY") or 0.4),
            "outW": int(z.get("width") or 1080),
            "outH": int(z.get("height") or 1920),
        }
    zooms = list(z.get("zooms") or [1.0])
    if not zooms:
        zooms = [1.0]
    return {
        "base": float(zooms[index % len(zooms)]),
        "push": float(z.get("pushIn") or 0.0),
        "cx": float(z.get("targetX") or 0.5),
        "cy": float(z.get("targetY") or 0.4),
        "outW": int(z.get("width") or 1080),
        "outH": int(z.get("height") or 1920),
    }


def zoom_vf(spec: dict[str, Any], *, n_frames: int, fps: float | None = None) -> str:
    """Push-in frame-determinístico sem zoompan e sem resample extra.

    crop+`n` no FFmpeg 9 avalia S só no init. scale eval=frame reavalia:

      S = base + push * min(1, t * fps / (N-1))
      scale UP por S → crop outW×outH na âncora (cx, cy)

    Usa `t` (não `n`) para não depender do FPS da fonte. Equivale ao CSS
    do Remotion (âncora 0.5/0.4, S>1), sem VIDEO_LAG.
    """
    base = max(1.0, float(spec.get("base") or 1.0))
    push = max(0.0, float(spec.get("push") or 0.0))
    cx = float(spec.get("cx") or 0.5)
    cy = float(spec.get("cy") or 0.4)
    out_w = int(spec.get("outW") or 1080)
    out_h = int(spec.get("outH") or 1920)
    n_frames = max(1, int(n_frames))
    denom = max(1, n_frames - 1)
    if fps and fps > 0:
        s = f"({base:.6f}+{push:.6f}*min(1\\,t*{float(fps):.6f}/{denom}))"
    else:
        s = f"({base:.6f}+{push:.6f}*n/{denom})"
    return (
        f"scale=w='trunc(iw*({s})/2)*2':h='trunc(ih*({s})/2)*2':"
        f"eval=frame:flags=lanczos,"
        f"crop={out_w}:{out_h}:"
        f"x='trunc((iw-{out_w})*{cx:.6f}/2)*2+0*t':"
        f"y='trunc((ih-{out_h})*{cy:.6f}/2)*2+0*t',"
        f"setsar=1"
    )


def attach_to_edl(
    edl: dict[str, Any],
    camera: dict[str, Any],
    *,
    width: int = 1080,
    height: int = 1920,
) -> bool:
    """Grava ffmpegZoom no EDL. False se o zoom for identidade."""
    zooms = [float(z) for z in (camera.get("zooms") or [1.0])]
    if not zooms:
        zooms = [1.0]
    push = float(camera.get("pushIn") or 0.0)
    if all(abs(z - 1.0) < 0.012 for z in zooms) and abs(push) < 0.005:
        return False
    edl["ffmpegZoom"] = {
        "enabled": True,
        "zooms": zooms,
        "pushIn": push,
        "targetX": float(camera.get("targetX") or 0.5),
        "targetY": float(camera.get("targetY") or 0.4),
        "width": int(width),
        "height": int(height),
    }
    return True


def flatten_remotion_camera(edit_data: dict[str, Any]) -> dict[str, Any]:
    """Desliga o zoom no Remotion depois de bake no cut — evita zoom duplo."""
    cam = dict(edit_data.get("camera") or {})
    zooms = [float(z) for z in (cam.get("zooms") or [1.0])]
    n = max(1, len(zooms))
    cam["baked"] = {
        "zooms": zooms,
        "pushIn": float(cam.get("pushIn") or 0.0),
        "targetX": float(cam.get("targetX") or 0.5),
        "targetY": float(cam.get("targetY") or 0.4),
    }
    cam["zooms"] = [1.0] * n
    cam["pushIn"] = 0.0
    cam["engine"] = "ffmpeg"
    cam["enabled"] = True
    edit_data["camera"] = cam
    return edit_data
