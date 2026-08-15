"""Protótipo isolado OVERLAY_PATH — não entra no job normal.

Uso:
    python pipeline/overlay_proto.py --edit-dir <projeto>/edit

Copia o Remotion para pasta temp, desliga zoom/tracking, renderiza FULL (Reels)
e OVERLAY (sem cut.mp4), compõe com FFmpeg+NVENC e grava o relatório.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PROTO_SRC = REPO / "assets" / "overlay-proto"
DEFAULT_EDIT = Path(
    r"E:\ATIVAVID\Projetos\20260814-170256_Parte_1_x2_6d5628b3a3\edit"
)


def _hide() -> dict:
    try:
        from app.win_process import hide_console_kwargs

        return hide_console_kwargs()
    except Exception:
        return {}


def _ffmpeg() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _ffprobe() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return "ffprobe"


class Sampler:
    def __init__(self) -> None:
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self) -> None:
        try:
            import psutil  # type: ignore
        except Exception:
            return
        proc = psutil.Process()

        def loop() -> None:
            while not self._stop.wait(2.0):
                try:
                    cpu = psutil.cpu_percent(interval=None)
                    ram = proc.memory_info().rss / (1024 * 1024)
                    self.samples.append((cpu, ram))
                except Exception:
                    return

        psutil.cpu_percent(interval=None)
        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()

    def stop(self) -> dict[str, float]:
        self._stop.set()
        if self._t:
            self._t.join(timeout=3)
        if not self.samples:
            return {}
        cpus = [s[0] for s in self.samples]
        rams = [s[1] for s in self.samples]
        return {
            "cpuAvg": round(sum(cpus) / len(cpus), 1),
            "cpuPeak": round(max(cpus), 1),
            "ramAvgMb": round(sum(rams) / len(rams), 1),
            "ramPeakMb": round(max(rams), 1),
        }


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, **_hide())


def _probe(path: Path, *args: str) -> str:
    r = subprocess.run(
        [_ffprobe(), "-v", "error", *args, str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        **_hide(),
    )
    return (r.stdout or "").strip()


def _duration(path: Path) -> float:
    return float(_probe(path, "-show_entries", "format=duration",
                        "-of", "default=nokey=1:noprint_wrappers=1") or 0)


def validate_overlay_alpha(path: Path, *, width: int, height: int, duration: float, fps: float) -> dict:
    """Recusa overlay sem alpha real. VP8 yuv420p opaco já quebrou o proto."""
    info = _probe(
        path,
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_frames,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json",
    )
    try:
        raw = json.loads(info or "{}")
    except json.JSONDecodeError:
        raw = {}
    st = (raw.get("streams") or [{}])[0]
    fmt = raw.get("format") or {}
    pix = str(st.get("pix_fmt") or "")
    codec = str(st.get("codec_name") or "")
    w, h = int(st.get("width") or 0), int(st.get("height") or 0)
    dur = float(fmt.get("duration") or 0)
    has_alpha = any(tok in pix for tok in ("a", "argb", "rgba", "yuva", "gbra"))
    report = {
        "ok": False,
        "codec": codec,
        "pix_fmt": pix,
        "width": w,
        "height": h,
        "duration": dur,
        "hasAlpha": has_alpha,
        "opaque": None,
    }
    if not has_alpha:
        raise RuntimeError(
            f"OVERLAY_ALPHA_INVALID pix_fmt={pix} codec={codec} — sem canal alpha. "
            "Recusado (evita compose preto)."
        )
    if w != width or h != height:
        raise RuntimeError(f"OVERLAY_SIZE_INVALID {w}x{h} != {width}x{height}")
    if duration and abs(dur - duration) > 0.15:
        raise RuntimeError(f"OVERLAY_DURATION_INVALID {dur} != {duration}")
    # Amostra: se o alpha for 255 em todos os pixels de 3 frames, a camada é inútil.
    sample = path.parent / "_alpha_sample.png"
    opaque_hits = 0
    for t in (0.2, max(0.2, duration * 0.5), max(0.2, duration - 0.4)):
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", str(path),
            "-frames:v", "1", "-pix_fmt", "rgba", str(sample),
        ])
        if sample.exists() and _png_fully_opaque(sample):
            opaque_hits += 1
    report["opaque"] = opaque_hits == 3
    if report["opaque"]:
        raise RuntimeError("OVERLAY_ALPHA_OPAQUE — alpha 100% opaco no vídeo inteiro.")
    report["ok"] = True
    print(f"OVERLAY_ALPHA_OK codec={codec} pix_fmt={pix} {w}x{h}", flush=True)
    return report


def _png_fully_opaque(path: Path) -> bool:
    try:
        from PIL import Image  # type: ignore

        im = Image.open(path)
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        extrema = im.getextrema()
        return len(extrema) == 4 and extrema[3][0] >= 255
    except Exception:
        return False


def _export_main_symbols(main_tsx: Path) -> None:
    text = main_tsx.read_text(encoding="utf-8")
    for name in ("Karaoke", "Inserts", "EndCard", "HookIntro"):
        text = text.replace(f"const {name}:", f"export const {name}:", 1)
    main_tsx.write_text(text, encoding="utf-8")


def _flatten_edit_data(src: Path, dest: Path) -> dict:
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    cam = dict(data.get("camera") or {})
    zooms = cam.get("zooms") or [1.0]
    cam["zooms"] = [1.0] * max(1, len(zooms))
    cam["pushIn"] = 0.0
    cam["enabled"] = True
    data["camera"] = cam
    data["behind"] = []
    data.pop("splitInserts", None)
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def _prepare_work(edit_dir: Path, work: Path) -> Path:
    src = edit_dir / "remotion"
    dest = work / "remotion"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in ("src", "public", "package.json", "remotion.config.ts", "tsconfig.json"):
        p = src / name
        if p.is_dir():
            shutil.copytree(p, dest / name)
        elif p.exists():
            shutil.copy2(p, dest / name)
    nm = dest / "node_modules"
    if (src / "node_modules").exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nm), str((src / "node_modules").resolve())],
            **_hide(),
        )
        if not nm.exists():
            os.symlink(str(src / "node_modules"), str(nm), target_is_directory=True)
    shutil.copy2(PROTO_SRC / "Overlay.tsx", dest / "src" / "Overlay.tsx")
    shutil.copy2(PROTO_SRC / "Root.tsx", dest / "src" / "Root.tsx")
    _export_main_symbols(dest / "src" / "Main.tsx")
    _flatten_edit_data(src / "public" / "edit-data.json", dest / "public" / "edit-data.json")
    return dest


def _remotion_cmd(remotion: Path, *args: str) -> list[str]:
    from app.win_process import resolve_remotion_argv

    return resolve_remotion_argv(remotion, *args)


def _render(remotion: Path, comp: str, out: Path, extra: list[str]) -> float:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = _remotion_cmd(
        remotion, "render", comp, str(out),
        "--concurrency=4",
        *extra,
    )
    print("RENDER", comp, flush=True)
    t0 = time.perf_counter()
    r = _run(cmd, cwd=remotion)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"remotion {comp} exit {r.returncode}")
    return dt


def _compose(cut: Path, overlay: Path, dest: Path, duration: float) -> tuple[float, str]:
    from app.render_engine import encode_with_fallback, encoder_args

    enc, _ = encoder_args()

    dec: list[str] = ["-c:v", "libvpx"] if overlay.suffix.lower() == ".webm" else []

    def _cmd(name: str, extra: list[str]) -> list[str]:
        return [
            _ffmpeg(), "-y", "-hide_banner", "-nostats",
            "-i", str(cut),
            *dec,
            "-i", str(overlay),
            "-filter_complex",
            "[0:v][1:v]overlay=eof_action=pass:format=auto,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:v", name, *extra,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", f"{duration:.3f}",
            "-movflags", "+faststart",
            str(dest),
        ]

    t0 = time.perf_counter()
    proc = encode_with_fallback(_cmd, label="overlay_compose")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"compose failed:\n{(proc.stderr or '')[-2000:]}")
    return dt, enc


def _encode_full(src: Path, dest: Path, duration: float) -> tuple[float, str]:
    from app.render_engine import encode_with_fallback, encoder_args

    enc, _ = encoder_args()
    fc = (
        "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid];"
        "[0:a]anull[out]"
    )

    def _cmd(name: str, extra: list[str]) -> list[str]:
        return [
            _ffmpeg(), "-y", "-hide_banner", "-nostats",
            "-i", str(src),
            "-filter_complex", fc,
            "-map", "[vid]", "-map", "[out]",
            "-c:v", name, *extra,
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{duration:.3f}",
            "-movflags", "+faststart",
            str(dest),
        ]

    t0 = time.perf_counter()
    proc = encode_with_fallback(_cmd, label="full_encode")
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"full encode failed:\n{(proc.stderr or '')[-2000:]}")
    return dt, enc


def _frames(video: Path, dest_dir: Path, times: list[float]) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i, t in enumerate(times):
        p = dest_dir / f"{video.stem}_{i}_{t:.2f}s.png"
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", str(video),
            "-frames:v", "1", str(p),
        ])
        out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-dir", type=Path, default=DEFAULT_EDIT)
    args = ap.parse_args()
    edit_dir = args.edit_dir.resolve()
    work = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_overlay_proto"
    work.mkdir(parents=True, exist_ok=True)

    from app.render_path import classify_render_path

    remotion = _prepare_work(edit_dir, work)
    ed = json.loads((remotion / "public" / "edit-data.json").read_text(encoding="utf-8"))
    cls = classify_render_path(ed, public=remotion / "public")
    print(f"RENDER_PATH {cls['path']} reasons={cls['reasons']}", flush=True)

    cut = edit_dir / "cut.mp4"
    duration = _duration(cut)
    fps = float(ed.get("fps") or 30)
    spots = [0.4, duration * 0.5, max(0.2, duration - 0.8)]

    full_raw = work / "full_raw.mp4"
    overlay = work / "overlay.webm"
    full_out = work / "full_final.mp4"
    ov_out = work / "overlay_final.mp4"

    samp_full = Sampler()
    samp_full.start()
    t_full_r = _render(remotion, "Reels", full_raw, [])
    res_full_r = samp_full.stop()

    samp_ov = Sampler()
    samp_ov.start()
    overlay = work / "overlay.mov"
    try:
        t_ov_r = _render(
            remotion, "Overlay", overlay,
            ["--codec", "prores", "--prores-profile", "4444",
             "--image-format", "png", "--pixel-format", "yuva444p10le"],
        )
    except RuntimeError:
        overlay = work / "overlay.webm"
        t_ov_r = _render(
            remotion, "Overlay", overlay,
            ["--codec", "vp8", "--pixel-format", "yuva420p"],
        )
    res_ov_r = samp_ov.stop()

    t_full_e, enc = _encode_full(full_raw, full_out, duration)
    alpha = validate_overlay_alpha(
        overlay,
        width=int(ed.get("width") or 1080),
        height=int(ed.get("height") or 1920),
        duration=duration,
        fps=fps,
    )
    t_ov_c, enc2 = _compose(cut, overlay, ov_out, duration)

    _frames(full_out, work / "frames", spots)
    _frames(ov_out, work / "frames", spots)

    report = {
        "renderPath": cls,
        "durationSec": duration,
        "fps": fps,
        "encoder": enc or enc2,
        "overlayAlpha": alpha,
        "full": {
            "remotionSec": round(t_full_r, 3),
            "ffmpegSec": round(t_full_e, 3),
            "totalSec": round(t_full_r + t_full_e, 3),
            "realtime": round(duration / max(0.001, t_full_r + t_full_e), 3),
            "remotionFps": round((duration * fps) / max(0.001, t_full_r), 2),
            "resources": res_full_r,
            "sizeBytes": full_out.stat().st_size if full_out.exists() else 0,
        },
        "overlay": {
            "remotionSec": round(t_ov_r, 3),
            "ffmpegSec": round(t_ov_c, 3),
            "totalSec": round(t_ov_r + t_ov_c, 3),
            "realtime": round(duration / max(0.001, t_ov_r + t_ov_c), 3),
            "remotionFps": round((duration * fps) / max(0.001, t_ov_r), 2),
            "resources": res_ov_r,
            "sizeBytes": ov_out.stat().st_size if ov_out.exists() else 0,
        },
        "savedSec": None,
        "savedPct": None,
        "note": (
            "Zoom/tracking/split/matte desligados nos dois caminhos. "
            "FULL ainda carrega OffthreadVideo(cut.mp4). "
            "OVERLAY não carrega vídeo. Áudio do compose vem de cut.mp4. "
            "Flag experimental — pipeline de produção inalterado."
        ),
    }
    ft = report["full"]["totalSec"]
    ot = report["overlay"]["totalSec"]
    report["savedSec"] = round(ft - ot, 3)
    report["savedPct"] = round(100.0 * (ft - ot) / ft, 1) if ft else 0
    (work / "overlay_proto_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
