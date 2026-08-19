"""Caminho experimental OVERLAY — Remotion só gráfica, compose no FFmpeg.

O template shipped (Main/Root) não é editado. Copia o remotion para uma
pasta de trabalho, injeta Overlay.tsx + Root com a composition Overlay.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from app.ffmpeg_tools import first_record
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PROTO_SRC = REPO / "assets" / "overlay-proto"

# ---------- render incremental do overlay -----------------------------------
# Guarda o ÚLTIMO overlay ProRes por projeto (movido, não copiado) + um
# snapshot dos insumos. No próximo render, se só a headline mudou e/ou só o
# TEXTO das legendas (timings idênticos), renderiza apenas os frames afetados
# e emenda com -c copy no restante do overlay antigo — ProRes 4444 é
# all-intra, a emenda é frame-exata. O validate_overlay_alpha continua sendo
# o gate final; qualquer dúvida cai no render completo.
def _ffmpeg() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return shutil.which("ffprobe") or "ffprobe"


_OV_CACHE_ROOT = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_overlay_cache"
_OV_CACHE_CAP = 3 * 1024**3  # LRU: no máximo ~3 GB de overlays guardados
# Acima disto de cobertura, o parcial não compensa o risco/overhead da emenda.
_OV_MAX_COVERAGE = 0.85


def _template_fingerprint(ov_remotion: Path) -> str:
    """Identidade do template: estilos novos shipados invalidam o cache."""
    parts = []
    try:
        parts.append((REPO / "VERSION").read_text(encoding="utf-8").strip())
    except OSError:
        parts.append("?")
    src = ov_remotion / "src"
    if src.is_dir():
        for f in sorted(src.glob("*.tsx")):
            try:
                parts.append(f"{f.name}:{f.stat().st_size}")
            except OSError:
                pass
    return "|".join(parts)


def _overlay_snapshot(public: Path, ov_remotion: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"_template": _template_fingerprint(ov_remotion)}
    for name in ("edit-data.json", "captions.json", "caption-cues.json"):
        p = public / name
        try:
            out[name] = json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None
        except (OSError, json.JSONDecodeError):
            out[name] = None
    return out


def _texts_only_first_change_ms(old: Any, new: Any) -> float | None:
    """Se old→new muda SÓ campos 'text' (mesmos timings), devolve o startMs da
    primeira mudança. Qualquer outra diferença devolve None (= render completo).
    O regrupamento de linhas propaga para frente, então o parcial vai do
    primeiro ponto de mudança até o FIM."""
    if old == new:
        return None
    if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new):
        return None
    first: float | None = None

    def _walk(a: Any, b: Any, t_hint: float | None) -> bool:
        nonlocal first
        if isinstance(a, dict) and isinstance(b, dict):
            if set(a.keys()) != set(b.keys()):
                return False
            t = a.get("startMs") if isinstance(a.get("startMs"), (int, float)) else (
                a.get("fromMs") if isinstance(a.get("fromMs"), (int, float)) else t_hint)
            for k in a:
                av, bv = a[k], b[k]
                if av == bv:
                    continue
                if k in ("text", "word") and isinstance(av, str) and isinstance(bv, str):
                    if t is not None and (first is None or t < first):
                        first = float(t)
                    continue
                if not _walk(av, bv, t):
                    return False
            return True
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return False
            return all(_walk(x, y, t_hint) for x, y in zip(a, b))
        return a == b

    if not _walk(old, new, None):
        return None
    return first


def _incremental_ranges(
    old: dict[str, Any], new: dict[str, Any], fps: float, frames: int,
) -> list[tuple[int, int]] | None:
    """None = render completo. [] = insumos idênticos (ainda assim rendere-
    mos completo — compose precisa do arquivo — mas via cache). Senão, lista
    de (start, end) exclusivo de frames a re-renderizar."""
    if old.get("_template") != new.get("_template"):
        return None
    old_ed = old.get("edit-data.json") or {}
    new_ed = new.get("edit-data.json") or {}

    def _strip_hook(ed: dict) -> dict:
        d = json.loads(json.dumps(ed))
        d.pop("hook", None)
        return d

    if _strip_hook(old_ed) != _strip_hook(new_ed):
        return None
    ranges: list[tuple[int, int]] = []
    if (old_ed.get("hook") or {}) != (new_ed.get("hook") or {}):
        end_sec = float((new_ed.get("hook") or {}).get("endSec") or 4.0)
        old_end = float((old_ed.get("hook") or {}).get("endSec") or 4.0)
        # cobre a maior das duas janelas + folga para o fade de saída
        ranges.append((0, min(frames, int(max(end_sec, old_end) * fps) + 12)))

    caps_first = _texts_only_first_change_ms(
        old.get("captions.json"), new.get("captions.json"))
    cues_changed = old.get("caption-cues.json") != new.get("caption-cues.json")
    if caps_first is None and (old.get("captions.json") != new.get("captions.json")):
        return None  # mudança de timing/estrutura nas legendas
    if cues_changed:
        cues_first = _texts_only_first_change_ms(
            old.get("caption-cues.json"), new.get("caption-cues.json"))
        if cues_first is None:
            return None
        caps_first = cues_first if caps_first is None else min(caps_first, cues_first)
    if caps_first is not None:
        # 30 frames antes: a palavra mudada pode regrupar a linha/cue em curso
        start_f = max(0, int(caps_first / 1000.0 * fps) - 30)
        ranges.append((start_f, frames))

    if not ranges:
        return []
    # merge de sobreposições
    ranges.sort()
    merged = [ranges[0]]
    for a, b in ranges[1:]:
        la, lb = merged[-1]
        if a <= lb:
            merged[-1] = (la, max(lb, b))
        else:
            merged.append((a, b))
    return merged


def _cache_dir_for(edit_dir: Path) -> Path:
    """Slot por PROJETO. `edit_dir.name` é sempre "edit" — usar só isso fazia
    todos os projetos colidirem no mesmo slot (um sobrescrevia o cache do
    outro e nenhum reusava). O hash do caminho absoluto separa de verdade.
    """
    import hashlib

    p = Path(edit_dir).resolve()
    tag = hashlib.sha1(str(p).lower().encode("utf-8")).hexdigest()[:12]
    parent = p.parent.name or "proj"
    safe = "".join(c for c in parent if c.isalnum() or c in "-_")[:40]
    return _OV_CACHE_ROOT / f"{safe}_{tag}"


def load_overlay_cache(edit_dir: Path) -> tuple[Path, dict[str, Any]] | None:
    d = _cache_dir_for(edit_dir)
    mov = d / "overlay.mov"
    meta = d / "inputs.json"
    if not (mov.is_file() and meta.is_file()):
        return None
    try:
        snap = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return mov, snap


def store_overlay_cache(edit_dir: Path, overlay: Path, snapshot: dict[str, Any]) -> None:
    """Move (não copia) o overlay para o cache e poda o LRU acima do teto."""
    if overlay.suffix.lower() != ".mov":
        return  # só ProRes é emendável
    d = _cache_dir_for(edit_dir)
    try:
        d.mkdir(parents=True, exist_ok=True)
        dest = d / "overlay.mov"
        dest.unlink(missing_ok=True)
        os.replace(overlay, dest)
        (d / "inputs.json").write_text(
            json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        os.utime(d, None)
    except OSError as e:
        print(f"[warn] overlay cache store: {e}", flush=True)
        return
    try:
        dirs = [p for p in _OV_CACHE_ROOT.iterdir() if p.is_dir()]
        sized = []
        for p in dirs:
            sz = sum(f.stat().st_size for f in p.glob("*") if f.is_file())
            sized.append((p.stat().st_mtime, sz, p))
        total = sum(s for _, s, _ in sized)
        for _, sz, p in sorted(sized):
            if total <= _OV_CACHE_CAP:
                break
            if p == d:
                continue
            shutil.rmtree(p, ignore_errors=True)
            total -= sz
    except OSError:
        pass


def _mov_frames(path: Path) -> int:
    try:
        r = subprocess.run(
            [_ffprobe(), "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=nb_frames", "-of", "default=nw=1:nk=1",
             str(path)],
            capture_output=True, text=True, timeout=30, **_hide(),
        )
        return int(first_record(r.stdout) or 0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0


def render_overlay_incremental(
    ov_remotion: Path,
    cached_mov: Path,
    ranges: list[tuple[int, int]],
    *,
    frames: int,
    fps: float,
    work: Path,
) -> Path:
    """Renderiza só `ranges` e emenda com o overlay anterior (-c copy).

    O áudio (SFX) vem INTEIRO do overlay antigo — o parcial só é permitido
    quando os timings não mudaram, então os cliques/whoosh caem nos mesmos
    lugares. Levanta em qualquer inconsistência; o caller cai no completo.
    """
    covered = sum(b - a for a, b in ranges)
    if not ranges or covered / max(1, frames) > _OV_MAX_COVERAGE:
        raise RuntimeError(f"OVERLAY_INCR_COVERAGE {covered}/{frames}")
    if _mov_frames(cached_mov) != frames:
        raise RuntimeError("OVERLAY_INCR_CACHE_FRAMES mismatch")

    from app.win_process import resolve_remotion_argv

    work.mkdir(parents=True, exist_ok=True)
    pieces: list[Path] = []
    cursor = 0
    idx = 0

    def _cut_old(a: int, b: int) -> Path:
        nonlocal idx
        piece = work / f"_incr_old_{idx:02d}.mov"
        idx += 1
        r = subprocess.run(
            [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
             "-ss", f"{a / fps:.6f}", "-i", str(cached_mov),
             "-map", "0:v", "-c:v", "copy", "-frames:v", str(b - a), "-an",
             str(piece)],
            capture_output=True, **_hide(),
        )
        if r.returncode != 0 or not piece.is_file():
            raise RuntimeError(f"OVERLAY_INCR_CUT {a}-{b}")
        return piece

    def _render_new(a: int, b: int) -> Path:
        nonlocal idx
        piece = work / f"_incr_new_{idx:02d}.mov"
        idx += 1
        cmd = resolve_remotion_argv(
            ov_remotion, "render", "Overlay", str(piece),
            f"--frames={a}-{b - 1}",
            "--codec", "prores", "--prores-profile", "4444",
            "--image-format", "png", "--pixel-format", "yuva444p10le",
        )
        r = subprocess.run(
            cmd, cwd=str(ov_remotion),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            **_hide(),
        )
        if r.returncode != 0 or not piece.is_file():
            tail = (r.stderr or r.stdout or "")[-400:]
            raise RuntimeError(f"OVERLAY_INCR_RENDER {a}-{b}: {tail}")
        return piece

    for a, b in ranges:
        a, b = max(0, a), min(frames, b)
        if a > cursor:
            pieces.append(_cut_old(cursor, a))
        pieces.append(_render_new(a, b))
        cursor = b
    if cursor < frames:
        pieces.append(_cut_old(cursor, frames))

    lst = work / "_incr_concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces), encoding="utf-8")
    spliced = work / "_incr_spliced.mov"
    r = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(spliced)],
        capture_output=True, **_hide(),
    )
    if r.returncode != 0 or not spliced.is_file():
        raise RuntimeError("OVERLAY_INCR_CONCAT")
    out = work / "overlay.mov"
    r = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(spliced), "-i", str(cached_mov),
         "-map", "0:v", "-map", "1:a?", "-c", "copy", str(out)],
        capture_output=True, **_hide(),
    )
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError("OVERLAY_INCR_MUX")
    got = _mov_frames(out)
    if got != frames:
        raise RuntimeError(f"OVERLAY_INCR_FRAMES {got}!={frames}")
    for p in pieces + [lst, spliced]:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    rendered = sum(b - a for a, b in ranges)
    print(f"OVERLAY_INCREMENTAL rendered={rendered}/{frames} frames", flush=True)
    return out

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
        snapshot = _overlay_snapshot(public, ov_remotion)
        cached = load_overlay_cache(edit_dir)
        if cached is not None:
            c_mov, c_snap = cached
            plan = _incremental_ranges(c_snap, snapshot, fps, frames)
            if plan is None:
                pass  # mudou demais — render completo abaixo
            elif plan == []:
                # gráficos idênticos ao último render — reusa o cache inteiro
                try:
                    reuse = work / "overlay.mov"
                    reuse.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(c_mov, reuse)
                    overlay = reuse
                    print("OVERLAY_INCREMENTAL rendered=0/%d (cache integral)" % frames,
                          flush=True)
                except OSError:
                    overlay = None
            else:
                try:
                    overlay = render_overlay_incremental(
                        ov_remotion, c_mov, plan,
                        frames=frames, fps=fps, work=work,
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] overlay incremental: {e} — render completo", flush=True)
                    overlay = None
        if overlay is None:
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
        # Guarda o overlay validado para o próximo render incremental —
        # move (custo zero), o cleanup abaixo só encontra o que sobrou.
        store_overlay_cache(edit_dir, overlay, snapshot)
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
