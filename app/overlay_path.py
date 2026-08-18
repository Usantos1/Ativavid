"""Caminho experimental OVERLAY — Remotion só gráfica, compose no FFmpeg.

O template shipped (Main/Root) não é editado. Copia o remotion para uma
pasta de trabalho, injeta Overlay.tsx + Root com a composition Overlay.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PROTO_SRC = REPO / "assets" / "overlay-proto"

# ProRes 4444 medido ~0.08 B/px; 0.25 B/px + 512 MB cobre margem operacional.
_TEMP_BYTES_PER_PIXEL = 0.25
_TEMP_SCRATCH = 512 * 1024 * 1024


def overlay_rollout() -> str:
    """off | canary | default. Interno — o cliente não escolhe o caminho."""
    env = (os.environ.get("ATIVAVID_OVERLAY_ROLLOUT") or "").strip().lower()
    if env in ("off", "canary", "default"):
        return env
    try:
        from app.settings_store import load_settings

        raw = str(load_settings().get("overlayRollout") or "default").strip().lower()
    except Exception:
        raw = "default"
    return raw if raw in ("off", "canary", "default") else "default"


def overlay_on() -> bool:
    """True se o motor automático pode tentar OVERLAY neste install."""
    env = (os.environ.get("ATIVAVID_OVERLAY") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    mode = overlay_rollout()
    if mode == "canary":
        from app.overlay_canary import canary_allows_attempt

        return canary_allows_attempt()
    if mode == "default":
        return True
    try:
        from app.settings_store import load_settings

        if load_settings().get("experimentalOverlay"):
            return True
    except Exception:
        pass
    return False


def experimental_on() -> bool:
    """Alias estável — gates e run_fast já importam este nome."""
    return overlay_on()


def overlay_eligible(edit_data: dict[str, Any], public: Path | None = None) -> bool:
    """False se tracking/split/matte/behind — esses ficam no FULL."""
    from app.render_path import classify_render_path

    cls = classify_render_path(edit_data, public=public, ffmpeg_zoom=True)
    return cls["path"] != "FULL" or not cls.get("fullReasons")


def _hide() -> dict:
    try:
        from app.win_process import hide_console_kwargs

        return hide_console_kwargs()
    except Exception:
        return {}


def prepare_overlay_remotion(src_remotion: Path, dest: Path) -> Path:
    """Cópia de trabalho com Overlay.tsx. src/ do projeto permanece intacto."""
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in ("src", "public", "package.json", "remotion.config.ts", "tsconfig.json"):
        p = src_remotion / name
        if p.is_dir():
            # A composição Overlay é só gráfica (sem cut.mp4/OffthreadVideo);
            # copiar os .mp4 do public/ duplicaria o vídeo inteiro à toa.
            ignore = shutil.ignore_patterns("*.mp4") if name == "public" else None
            shutil.copytree(p, dest / name, ignore=ignore)
        elif p.exists():
            shutil.copy2(p, dest / name)
    nm = dest / "node_modules"
    src_nm = src_remotion / "node_modules"
    if src_nm.exists() and not nm.exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nm), str(src_nm.resolve())],
            **_hide(),
        )
        if not nm.exists():
            try:
                os.symlink(str(src_nm), str(nm), target_is_directory=True)
            except OSError:
                pass
    shutil.copy2(PROTO_SRC / "Overlay.tsx", dest / "src" / "Overlay.tsx")
    shutil.copy2(PROTO_SRC / "Root.tsx", dest / "src" / "Root.tsx")
    main_tsx = dest / "src" / "Main.tsx"
    text = main_tsx.read_text(encoding="utf-8")
    for name in ("Karaoke", "Inserts", "EndCard", "HookIntro"):
        text = text.replace(f"const {name}:", f"export const {name}:", 1)
    main_tsx.write_text(text, encoding="utf-8")
    return dest


def estimate_overlay_temp_bytes(width: int, height: int, frames: int) -> int:
    overlay = int(max(1, width) * max(1, height) * max(1, frames) * _TEMP_BYTES_PER_PIXEL)
    return overlay + _TEMP_SCRATCH


def free_space_bytes(path: Path) -> int:
    root = path if path.exists() else path.parent
    try:
        return int(shutil.disk_usage(str(root)).free)
    except OSError:
        return 0


def cleanup_overlay_temps(
    paths: list[Path],
    *,
    keep: list[Path] | None = None,
) -> bool:
    """Apaga só temporários do Overlay. Nunca o original nem um final válido."""
    protected = {p.resolve() for p in (keep or []) if p}
    protected_names = {"cut.mp4", "final.mp4"}
    done = True
    for p in paths:
        if not p:
            continue
        try:
            resolved = p.resolve()
        except OSError:
            resolved = p
        if resolved in protected or p.name in protected_names:
            continue
        try:
            if p.is_file():
                p.unlink()
            elif p.is_dir() and p.name not in ("public", "src"):
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            done = False
    print(f"TEMP_CLEANUP_DONE ok={str(done).lower()}", flush=True)
    return done


def render_overlay(remotion: Path, out: Path) -> Path:
    """ProRes 4444 com alpha; fallback VP8 yuva."""
    from app.win_process import resolve_remotion_argv

    out.parent.mkdir(parents=True, exist_ok=True)

    # Concorrência do perfil, não um 4 fixo — o overlay é o mesmo Chrome do
    # caminho FULL e ignorava o perfil de desempenho inteiro.
    try:
        import sys as _sys

        _helpers = str(Path(__file__).resolve().parent.parent / "helpers")
        if _helpers not in _sys.path:
            _sys.path.insert(0, _helpers)
        from remotion_gate import remotion_concurrency  # type: ignore

        conc = remotion_concurrency()
    except Exception:
        conc = 4

    def _one(path: Path, extra: list[str]) -> subprocess.CompletedProcess:
        cmd = resolve_remotion_argv(
            remotion, "render", "Overlay", str(path),
            f"--concurrency={conc}", *extra,
        )
        print(f"RENDER Overlay {path.name} conc={conc}", flush=True)
        return subprocess.run(cmd, cwd=str(remotion), **_hide())

    mov = out.with_suffix(".mov")
    r = _one(mov, [
        "--codec", "prores", "--prores-profile", "4444",
        "--image-format", "png", "--pixel-format", "yuva444p10le",
    ])
    if r.returncode == 0 and mov.exists():
        return mov
    webm = out.with_suffix(".webm")
    r = _one(webm, ["--codec", "vp8", "--pixel-format", "yuva420p"])
    if r.returncode != 0 or not webm.exists():
        raise RuntimeError(f"OVERLAY_RENDER_FAILED exit={r.returncode}")
    return webm


def try_overlay_final(
    *,
    edit_dir: Path,
    remotion: Path,
    cut: Path,
    edit_data: dict[str, Any],
    duration: float | None = None,
    dest: Path,
) -> dict[str, Any]:
    """Render Overlay + compose. Levanta se não der — o caller faz fallback FULL."""
    from app.overlay_compose import compose_overlay, validate_overlay_alpha
    from app.timeline import timeline_from_edit_data

    public = remotion / "public"
    if not overlay_eligible(edit_data, public):
        raise RuntimeError("OVERLAY_INELIGIBLE tracking/split/matte")

    tl = timeline_from_edit_data(edit_data)
    frames = int(tl["durationInFrames"])
    fps = float(tl["fps"])
    if duration is not None and abs(float(duration) - float(tl["sourceDurationSec"])) > 0.05:
        print(
            f"TIMELINE_IGNORE_CALLER_DURATION caller={float(duration):.6f} "
            f"editData={tl['sourceDurationSec']:.6f} canonical={tl['durationSec']:.6f} "
            f"frames={frames}",
            flush=True,
        )
    print(
        f"CANONICAL_DURATION frames={frames} sec={tl['durationSec']:.6f} "
        f"sourceDurationSec={tl['sourceDurationSec']:.6f} fps={fps:g}",
        flush=True,
    )

    work = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_overlay_work" / edit_dir.name
    width = int(edit_data.get("width") or 1080)
    height = int(edit_data.get("height") or 1920)
    required = estimate_overlay_temp_bytes(width, height, frames)
    free = free_space_bytes(work)
    print(f"TEMP_REQUIRED_ESTIMATE {required}", flush=True)
    print(f"TEMP_FREE_SPACE {free}", flush=True)
    if free and free < required:
        raise RuntimeError(
            f"OVERLAY_TEMP_INSUFFICIENT required={required} free={free}"
        )

    overlay: Path | None = None
    ov_remotion: Path | None = None
    temps: list[Path] = []
    result: dict[str, Any] = {}
    cleanup_ok = False
    try:
        ov_remotion = prepare_overlay_remotion(remotion, work / "remotion")
        t0 = time.perf_counter()
        overlay = render_overlay(ov_remotion, work / "overlay")
        render_sec = time.perf_counter() - t0
        temps.extend([
            overlay,
            overlay.with_suffix(".mov"),
            overlay.with_suffix(".webm"),
            overlay.parent / "_alpha_sample.png",
            dest.with_name(dest.stem + "._prenorm.mp4"),
        ])
        alpha = validate_overlay_alpha(
            overlay,
            width=width,
            height=height,
            duration_in_frames=frames,
            fps=fps,
        )
        st = edit_data.get("soundtrack") or {}
        trilha = public / str(st.get("file") or "trilha.mp3")
        if not (st.get("enabled") and trilha.exists()):
            trilha = None
        t1 = time.perf_counter()
        mix = compose_overlay(
            cut, overlay, dest,
            duration_in_frames=frames,
            fps=fps,
            trilha=trilha,
            trilha_volume=float(st.get("volume") or 0.12),
        )
        compose_sec = time.perf_counter() - t1
        print(
            f"OVERLAY_COMPOSE_DONE render={render_sec:.1f}s compose={compose_sec:.1f}s "
            f"sfx={mix['sfxFromOverlay']} trilha={mix['soundtrack']}",
            flush=True,
        )
        result = {
            "overlay": str(overlay),
            "alpha": alpha,
            "mix": mix,
            "remotionSec": round(render_sec, 3),
            "composeSec": round(compose_sec, 3),
            "timeline": tl,
            "tempPeakBytes": required,
            "overlayFrames": int((alpha or {}).get("overlayFrames") or frames),
            "cutFrames": int((mix or {}).get("cutFrames") or 0),
        }
    finally:
        if ov_remotion is not None:
            temps.append(ov_remotion)
        cleanup_ok = cleanup_overlay_temps(temps, keep=[dest, cut])
    if not result:
        raise RuntimeError("OVERLAY_RENDER_FAILED")
    result["tempCleanupDone"] = bool(cleanup_ok)
    if not cleanup_ok:
        raise RuntimeError("TEMP_CLEANUP_FAILED")
    return result
