"""Classifica o caminho de render pelo efeito REAL, não pela flag.

camera.enabled=true com zoom 1.0 e sem tracking/split/matte NÃO é FULL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

ZOOM_EPS = 0.012
PUSH_EPS = 0.005

FULL = "FULL"
OVERLAY = "OVERLAY"
FAST = "FAST"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _zoom_cuts(camera: dict[str, Any] | None) -> bool:
    if not isinstance(camera, dict):
        return False
    return any(abs(_f(z, 1.0) - 1.0) > ZOOM_EPS for z in (camera.get("zooms") or []))


def _push_in(camera: dict[str, Any] | None) -> bool:
    if not isinstance(camera, dict):
        return False
    return abs(_f(camera.get("pushIn"), 0.0)) > PUSH_EPS


def _has_real_zoom(camera: dict[str, Any] | None) -> bool:
    return _zoom_cuts(camera) or _push_in(camera)


def _has_tracking(edit_data: dict[str, Any], public: Path | None) -> bool:
    cam = edit_data.get("camera") if isinstance(edit_data.get("camera"), dict) else {}
    if cam.get("tracking") is True:
        return True
    track_file = public / "track.json" if public else None
    if track_file and track_file.exists():
        try:
            import json

            raw = json.loads(track_file.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, TypeError):
            raw = None
        points = []
        if isinstance(raw, dict):
            points = raw.get("points") or raw.get("track") or []
        elif isinstance(raw, list):
            points = raw
        if len(points) >= 8:
            xs = [_f(p[0] if isinstance(p, (list, tuple)) else (p or {}).get("x"), 0.5) for p in points[:80]]
            ys = [_f(p[1] if isinstance(p, (list, tuple)) else (p or {}).get("y"), 0.4) for p in points[:80]]
            if xs and ys and (max(xs) - min(xs) > 0.04 or max(ys) - min(ys) > 0.04):
                return True
    return False


def ffmpeg_zoom_active(edit_data: dict[str, Any] | None = None, edl: dict[str, Any] | None = None) -> bool:
    """Só olha artefatos do job — a flag de settings NÃO muda auditoria antiga."""
    if isinstance(edl, dict) and isinstance(edl.get("ffmpegZoom"), dict):
        if edl["ffmpegZoom"].get("enabled"):
            return True
    cam = (edit_data or {}).get("camera") if isinstance(edit_data, dict) else None
    return isinstance(cam, dict) and str(cam.get("engine") or "") == "ffmpeg"


def classify_render_path(
    edit_data: dict[str, Any] | None,
    *,
    public: Path | None = None,
    edl: dict[str, Any] | None = None,
    ffmpeg_zoom: bool | None = None,
) -> dict[str, Any]:
    """Devolve {path, reasons, fullReasons, overlayReasons}."""
    data = edit_data if isinstance(edit_data, dict) else {}
    full: list[str] = []
    overlay: list[str] = []
    zoom_in_ffmpeg = ffmpeg_zoom if ffmpeg_zoom is not None else ffmpeg_zoom_active(data, edl)

    if _has_tracking(data, public):
        full.append("tracking")
    if data.get("splitInserts"):
        full.append("split")
    # Layouts que TRANSFORMAM o vídeo (moldura/barra/desfocado) precisam do
    # Remotion compondo o próprio vídeo — não dá para colar por cima no
    # FFmpeg. "degrade" é só um scrim gráfico e continua overlay-elegível.
    from app.video_layouts import transforma_o_video
    if transforma_o_video(data.get("videoLayout")):
        full.append("video_layout")
    behind = data.get("behind") or []
    if behind:
        full.append("matte_behind")
    cam = data.get("camera") if isinstance(data.get("camera"), dict) else None
    if not zoom_in_ffmpeg:
        if _zoom_cuts(cam):
            full.append("zoom_cuts")
        if _push_in(cam):
            full.append("push_in")

    caps = data.get("captions") if isinstance(data.get("captions"), dict) else {}
    hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    end = data.get("endCard") if isinstance(data.get("endCard"), dict) else {}
    if caps.get("enabled"):
        overlay.append("captions")
    if hook.get("enabled"):
        overlay.append("hook")
    if end.get("enabled"):
        overlay.append("end_card")
    if data.get("inserts"):
        overlay.append("inserts")
    if data.get("transitions"):
        overlay.append("flash")
    logo = hook.get("logo") or end.get("logo")
    if logo:
        overlay.append("logo")

    if full:
        path = FULL
        reasons = list(full)
    elif overlay:
        path = OVERLAY
        reasons = list(overlay)
    else:
        path = FAST
        reasons = ["none"]

    only_simple_zoom = path == FULL and set(full) <= {"zoom_cuts"}
    zoom_only = path == FULL and set(full) <= {"zoom_cuts", "push_in"}
    zoom_engine = "ffmpeg" if zoom_in_ffmpeg else "remotion"
    return {
        "path": path,
        "reasons": reasons,
        "fullReasons": full,
        "overlayReasons": overlay,
        "onlySimpleZoomCuts": only_simple_zoom,
        "onlyZoomFamily": zoom_only,
        "zoomEngine": zoom_engine,
        "cameraEnabled": bool((data.get("camera") or {}).get("enabled"))
        if isinstance(data.get("camera"), dict)
        else False,
    }


def analyze_zoom(edit_data: dict[str, Any] | None) -> dict[str, Any]:
    """Classifica o zoom atual vs o que o FFmpeg conseguiria (não implementa)."""
    data = edit_data if isinstance(edit_data, dict) else {}
    cam = data.get("camera") if isinstance(data.get("camera"), dict) else {}
    zooms = [_f(z, 1.0) for z in (cam.get("zooms") or [])]
    push = _f(cam.get("pushIn"), 0.0)
    target = (_f(cam.get("targetX"), 0.5), _f(cam.get("targetY"), 0.4))
    tracking = bool(cam.get("tracking"))
    kinds: list[dict[str, Any]] = []
    if _zoom_cuts(cam):
        kinds.append({
            "name": "zoomCuts",
            "scaleStart": zooms,
            "scaleEnd": zooms,
            "duration": "por segmento (hard cut)",
            "easing": "nenhum — degrau no corte (Remotion: VIDEO_LAG=1; FFmpeg: no frame do corte)",
            "cropCenter": f"fixo {target} se tracking off; senão track.json",
            "followsFace": tracking,
            "staticPerSegment": True,
            "continuousAnimation": False,
            "ffmpegClass": "REMOTION_REQUIRED" if tracking else "FFMPEG_SAFE",
            "note": (
                "CSS scale+translate no OffthreadVideo. Sem tracking: zoom "
                "em direção a (targetX, targetY), clamp nas bordas. "
                "FFmpeg: crop/scale por segmento no extract."
            ),
        })
    if _push_in(cam):
        kinds.append({
            "name": "pushIn",
            "scaleStart": [z for z in zooms] or [1.0],
            "scaleEnd": [z + push for z in (zooms or [1.0])],
            "duration": "duração do segmento (linear 0→1)",
            "easing": "linear (clamp01, sem cubic)",
            "cropCenter": f"fixo {target} se tracking off",
            "followsFace": tracking,
            "staticPerSegment": False,
            "continuousAnimation": True,
            "ffmpegClass": "REMOTION_REQUIRED" if tracking else "FFMPEG_SAFE",
            "note": (
                "S = base + pushIn * n/(N-1) no extract (crop/scale, sem zoompan). "
                "Remotion usa (frame-segFrom)/segLen + VIDEO_LAG; FFmpeg troca no corte."
            ),
        })
    if tracking:
        kinds.append({
            "name": "faceTracking",
            "ffmpegClass": "REMOTION_REQUIRED",
            "followsFace": True,
            "note": "cx,cy por frame em track.json — não migrar.",
        })
    if not kinds:
        return {"ffmpegClass": "NONE", "kinds": []}
    order = {"REMOTION_REQUIRED": 2, "FFMPEG_APPROXIMATE": 1, "FFMPEG_SAFE": 0, "NONE": -1}
    worst = max((k.get("ffmpegClass") or "NONE" for k in kinds), key=lambda x: order.get(x, 0))
    return {"ffmpegClass": worst, "kinds": kinds}
