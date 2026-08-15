"""Gates de aceitação OVERLAY — não liga flags, não grava no projeto.

    uv run python pipeline/overlay_gates.py --gate 1
    uv run python pipeline/overlay_gates.py --gate 2
    uv run python pipeline/overlay_gates.py --gate 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "helpers")]

from app.ffmpeg_zoom import attach_to_edl, flatten_remotion_camera  # noqa: E402
from app.overlay_compose import (  # noqa: E402
    compose_overlay, count_frames, validate_overlay_alpha, video_info,
)
from app.overlay_path import (  # noqa: E402
    cleanup_overlay_temps, estimate_overlay_temp_bytes, free_space_bytes,
    prepare_overlay_remotion, render_overlay,
)
from app.render_path import classify_render_path  # noqa: E402
from app.timeline import js_round, timeline_from_edit_data  # noqa: E402
from pipeline.overlay_proto import Sampler, _duration, _ffmpeg, _hide, _remotion_cmd, _run  # noqa: E402

SHORT = Path(r"E:\ATIVAVID\Projetos\20260814-170256_Parte_1_x2_6d5628b3a3\edit")
LONG = Path(r"E:\ATIVAVID\Projetos\20260814-211649_cta_mais_feliz_x2_094e53317f\edit")
ROOT = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_overlay_gates"


def _ffprobe() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin
        return ffprobe_bin()
    except Exception:
        return "ffprobe"


def _dir_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file() and "node_modules" not in p.parts:
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _link_modules(src_remotion: Path, dest: Path) -> None:
    nm = dest / "node_modules"
    src = src_remotion / "node_modules"
    if src.exists() and not nm.exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nm), str(src.resolve())], **_hide(),
        )


def _copy_remotion(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in ("src", "public", "package.json", "remotion.config.ts", "tsconfig.json"):
        p = src / name
        if p.is_dir():
            shutil.copytree(p, dest / name)
        elif p.exists():
            shutil.copy2(p, dest / name)
    _link_modules(src, dest)
    return dest


def _render_py(edl: dict, dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    edl_path = dest.with_suffix(".json")
    edl_path.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")
    t0 = time.perf_counter()
    r = subprocess.run(
        [sys.executable, str(REPO / "helpers" / "render.py"),
         str(edl_path), "-o", str(dest), "--no-subtitles", "--voice-master"],
        cwd=str(REPO), **_hide(),
    )
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"render.py exit={r.returncode}")
    return dt


def _render_reels(remotion: Path, out: Path) -> float:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = _remotion_cmd(remotion, "render", "Reels", str(out), "--concurrency=4")
    print("RENDER Reels", flush=True)
    t0 = time.perf_counter()
    r = _run(cmd, cwd=remotion)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"Reels exit {r.returncode}")
    return dt


def _encode_full(
    src: Path, dest: Path, duration: float, duration_in_frames: int | None = None,
) -> float:
    t0 = time.perf_counter()
    r = subprocess.run(
        [
            _ffmpeg(), "-y", "-hide_banner", "-nostats",
            "-i", str(src),
            "-filter_complex",
            "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
            "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid];"
            "[0:a]loudnorm=I=-14:TP=-1:LRA=11[out]",
            "-map", "[vid]", "-map", "[out]",
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            *(["-frames:v", str(int(duration_in_frames))] if duration_in_frames else []),
            "-t", f"{duration:.6f}", "-movflags", "+faststart", str(dest),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **_hide(),
    )
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"encode failed:\n{(r.stderr or '')[-1200:]}")
    return dt


def audio_report(path: Path) -> dict:
    r = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", str(path),
         "-filter_complex", "ebur128=peak=true,volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **_hide(),
    )
    log = r.stderr or ""
    summary = log
    idx = log.rfind("Summary:")
    if idx >= 0:
        summary = log[idx:]

    def _f(pat: str, src: str = summary):
        m = re.search(pat, src, flags=re.S)
        return float(m.group(1)) if m else None
    pr = subprocess.run(
        [_ffprobe(), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels,duration:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **_hide(),
    )
    try:
        raw = json.loads(pr.stdout or "{}")
    except json.JSONDecodeError:
        raw = {}
    st = (raw.get("streams") or [{}])[0]
    fmt = raw.get("format") or {}
    return {
        "integratedLufs": _f(r"I:\s+([-\d.]+)\s+LUFS"),
        "truePeakDb": _f(r"True peak:\s+Peak:\s+([-\d.]+)\s+dB(?:TP|FS)")
        or _f(r"Peak:\s+([-\d.]+)\s+dBTP"),
        "lra": _f(r"LRA:\s+([-\d.]+)\s+LU"),
        "maxDb": _f(r"max_volume:\s+([-\d.]+)\s+dB"),
        "meanDb": _f(r"mean_volume:\s+([-\d.]+)\s+dB"),
        "duration": float(st.get("duration") or fmt.get("duration") or 0),
        "sampleRate": int(st.get("sample_rate") or 0),
        "channels": int(st.get("channels") or 0),
    }


def _window_peak(path: Path, start: float, dur: float = 0.25) -> float | None:
    r = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **_hide(),
    )
    m = re.search(r"max_volume:\s+([-\d.]+)\s+dB", r.stderr or "")
    return float(m.group(1)) if m else None


def sfx_spots(path: Path, ed: dict, duration: float) -> dict:
    flashes = [float(t.get("at") or 0) for t in (ed.get("transitions") or [])]
    hook_end = float((ed.get("hook") or {}).get("endSec") or 0)
    end_last = float((ed.get("endCard") or {}).get("lastSec") or 2.5)
    spots = {
        "fadeIn": _window_peak(path, 0.0, 0.45),
        "hookEnd": _window_peak(path, max(0.0, hook_end - 0.05), 0.3) if hook_end else None,
        "fadeOut": _window_peak(path, max(0.0, duration - 1.5), 1.5),
        "endCard": _window_peak(path, max(0.0, duration - end_last), 0.4),
    }
    for i, t in enumerate(flashes[:6]):
        spots[f"flash_{i}_{t:.2f}"] = _window_peak(path, max(0.0, t - 0.04), 0.2)
    return spots


def _frames(video: Path, dest: Path, times: list[tuple[str, float]]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, t in times:
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
            str(dest / f"{name}.png"),
        ])


def _extract_exact_frames(video: Path, dest: Path, indices: list[int]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for n in indices:
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video),
            "-vf", f"select=eq(n\\,{n})",
            "-frames:v", "1",
            str(dest / f"frame_{n:04d}.png"),
        ])


def _word_visible(opacity: float) -> bool:
    return opacity > 0.05


def caption_frame_table(
    cues: list[dict],
    *,
    fps: float,
    duration_in_frames: int,
    frames: list[int],
) -> list[dict]:
    """Espelha StackedCaptions: Sequence usa Math.round(ms); palavra usa float local."""
    rows = []
    for n in frames:
        t = n / fps
        t_ms = t * 1000.0
        expected: list[dict] = []
        for cue in cues:
            start_ms = float(cue.get("startMs") or 0)
            end_ms = float(cue.get("endMs") or 0)
            frm = js_round((start_ms / 1000.0) * fps)
            end = js_round((end_ms / 1000.0) * fps)
            dur = max(2, min(end, duration_in_frames) - frm)
            if dur <= 0 or n < frm or n >= frm + dur:
                continue
            local = n - frm
            for line in cue.get("lines") or []:
                for w in line:
                    from_ms = float(w.get("fromMs") or start_ms)
                    to_ms = float(w.get("toMs") or end_ms)
                    local_start = ((from_ms - start_ms) / 1000.0) * fps
                    # interpolate clamp: p=0 antes de localStart
                    p = 0.0 if local < local_start else 1.0
                    if local >= local_start:
                        p = 1.0
                    expected.append({
                        "text": w.get("text"),
                        "fromMs": from_ms,
                        "toMs": to_ms,
                        "cueStartMs": start_ms,
                        "cueEndMs": end_ms,
                        "sequenceFrom": frm,
                        "sequenceEnd": frm + dur,
                        "localStart": round(local_start, 4),
                        "visible": local >= local_start,
                        "rounding": (
                            "cue Sequence: Math.round((ms/1000)*fps); "
                            "word localStart: ((fromMs-startMs)/1000)*fps sem round"
                        ),
                    })
        rows.append({
            "frame": n,
            "timeSec": round(t, 6),
            "timeMs": round(t_ms, 3),
            "expectedWords": [w["text"] for w in expected if w["visible"]],
            "words": expected,
        })
    return rows


def clean_ab(edit_dir: Path, work: Path, tag: str) -> dict:
    """A e B desde a fonte. Sem reutilizar cut/render/overlay do job."""
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    src_rem = edit_dir / "remotion"
    ed = json.loads((src_rem / "public" / "edit-data.json").read_text(encoding="utf-8-sig"))
    edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8-sig"))
    edl.pop("ffmpegZoom", None)
    tl = timeline_from_edit_data(ed)
    duration = float(tl["durationSec"])
    fps = float(tl["fps"])
    expected_frames = int(tl["durationInFrames"])
    print(
        f"GATE {tag} CANONICAL frames={expected_frames} sec={duration:.6f} "
        f"editData={tl['sourceDurationSec']:.6f}",
        flush=True,
    )
    cls_a = classify_render_path(ed, public=src_rem / "public")
    cls_b = classify_render_path(ed, public=src_rem / "public", ffmpeg_zoom=True)
    print(f"GATE {tag} classify A={cls_a['path']} B={cls_b['path']}", flush=True)

    # --- A: CUT normal (sem zoom FFmpeg) + FULL ---
    print(f"GATE {tag} PATH A CUT", flush=True)
    samp = Sampler()
    samp.start()
    t_job = time.perf_counter()
    a_dir = work / "A"
    a_dir.mkdir()
    cut_a = a_dir / "cut.mp4"
    cut_a_sec = _render_py(json.loads(json.dumps(edl)), cut_a)
    print(f"  A CUT {cut_a_sec:.1f}s", flush=True)
    a_rem = _copy_remotion(src_rem, a_dir / "remotion")
    t_ar = _render_reels(a_rem, a_dir / "render.mp4")
    print(f"  A Remotion {t_ar:.1f}s", flush=True)
    t_ae = _encode_full(
        a_dir / "render.mp4", a_dir / "final.mp4",
        duration, duration_in_frames=expected_frames,
    )
    a_wall = time.perf_counter() - t_job
    res_a = samp.stop()
    a_final = a_dir / "final.mp4"
    print(f"  A WHOLE {a_wall:.1f}s", flush=True)

    # --- B: CUT + zoom + OVERLAY ---
    print(f"GATE {tag} PATH B CUT+ZOOM", flush=True)
    samp = Sampler()
    samp.start()
    t_job = time.perf_counter()
    b_dir = work / "B"
    b_dir.mkdir()
    edl_b = json.loads(json.dumps(edl))
    attach_to_edl(
        edl_b, ed.get("camera") or {},
        width=int(ed.get("width") or 1080),
        height=int(ed.get("height") or 1920),
    )
    cut_b = b_dir / "cut.mp4"
    cut_b_sec = _render_py(edl_b, cut_b)
    print(f"  B CUT {cut_b_sec:.1f}s", flush=True)
    ed_b = json.loads(json.dumps(ed))
    flatten_remotion_camera(ed_b)
    b_rem = prepare_overlay_remotion(src_rem, b_dir / "remotion")
    (b_rem / "public" / "edit-data.json").write_text(
        json.dumps(ed_b, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    width = int(ed.get("width") or 1080)
    height = int(ed.get("height") or 1920)
    required = estimate_overlay_temp_bytes(width, height, expected_frames)
    free = free_space_bytes(b_dir)
    print(f"TEMP_REQUIRED_ESTIMATE {required}", flush=True)
    print(f"TEMP_FREE_SPACE {free}", flush=True)
    if free and free < required:
        raise RuntimeError(f"OVERLAY_TEMP_INSUFFICIENT required={required} free={free}")
    t_ov0 = time.perf_counter()
    overlay = render_overlay(b_rem, b_dir / "overlay")
    ov_sec = time.perf_counter() - t_ov0
    print(f"  B Overlay {ov_sec:.1f}s size={overlay.stat().st_size}", flush=True)
    alpha = validate_overlay_alpha(
        overlay,
        width=width,
        height=height,
        duration_in_frames=expected_frames,
        fps=fps,
    )
    st = ed.get("soundtrack") or {}
    trilha = src_rem / "public" / str(st.get("file") or "trilha.mp3")
    if not (st.get("enabled") and trilha.exists()):
        trilha = None
    t_c0 = time.perf_counter()
    mix = compose_overlay(
        cut_b, overlay, b_dir / "final.mp4",
        duration_in_frames=expected_frames,
        fps=fps,
        trilha=trilha,
        trilha_volume=float(st.get("volume") or 0.12),
    )
    compose_sec = time.perf_counter() - t_c0
    b_wall = time.perf_counter() - t_job
    res_b = samp.stop()
    b_final = b_dir / "final.mp4"
    print(f"  B WHOLE {b_wall:.1f}s", flush=True)
    overlay_bytes = overlay.stat().st_size if overlay.exists() else 0
    overlay_frames = count_frames(overlay) if overlay.exists() else 0
    cut_a_frames = count_frames(cut_a)
    cut_b_frames = count_frames(cut_b)

    pa, pb = video_info(a_final), video_info(b_final)
    aa, ab = audio_report(a_final), audio_report(b_final)
    gain = a_wall - b_wall
    pct = 100.0 * gain / a_wall if a_wall else 0.0
    spots = [
        ("start", 0.4),
        ("p25", duration * 0.25),
        ("p50", duration * 0.50),
        ("p75", duration * 0.75),
        ("end", max(0.2, duration - 0.6)),
    ]
    _frames(a_final, work / "frames" / "A", spots)
    _frames(b_final, work / "frames" / "B", spots)
    cap_frames = list(range(9, 16))
    _extract_exact_frames(a_final, work / "frames" / "A_exact", cap_frames)
    _extract_exact_frames(b_final, work / "frames" / "B_exact", cap_frames)
    cues_path = src_rem / "public" / "caption-cues.json"
    try:
        cues = json.loads(cues_path.read_text(encoding="utf-8-sig"))
    except Exception:
        cues = []
    caption_expected = caption_frame_table(
        cues, fps=fps, duration_in_frames=expected_frames, frames=cap_frames,
    )
    cleanup_overlay_temps(
        [
            overlay,
            overlay.with_suffix(".mov"),
            overlay.with_suffix(".webm"),
            b_dir / "_alpha_sample.png",
            b_dir / "final._prenorm.mp4",
        ],
        keep=[b_final, cut_b],
    )

    report = {
        "gate": tag,
        "project": edit_dir.parent.name,
        "timeline": tl,
        "expectedFrames": expected_frames,
        "expectedDuration": duration,
        "cutFramesA": cut_a_frames,
        "cutFramesB": cut_b_frames,
        "overlayFrames": overlay_frames,
        "finalFramesA": pa.get("frames"),
        "finalFramesB": pb.get("frames"),
        "classifyA": cls_a,
        "classifyB": cls_b,
        "captionFrames": caption_expected,
        "A": {
            "wholeJobSec": round(a_wall, 3),
            "cutSec": round(cut_a_sec, 3),
            "remotionSec": round(t_ar, 3),
            "composeEncodeSec": round(t_ae, 3),
            "cutFrames": cut_a_frames,
            "finalFrames": pa.get("frames"),
            "finalDuration": pa.get("duration"),
            "probe": pa,
            "audio": aa,
            "sfxWindows": sfx_spots(a_final, ed, pa["duration"] or duration),
            "resources": res_a,
            "out": str(a_final),
        },
        "B": {
            "wholeJobSec": round(b_wall, 3),
            "cutSec": round(cut_b_sec, 3),
            "remotionSec": round(ov_sec, 3),
            "composeEncodeSec": round(compose_sec, 3),
            "cutFrames": cut_b_frames,
            "overlayFrames": overlay_frames,
            "finalFrames": pb.get("frames"),
            "finalDuration": pb.get("duration"),
            "probe": pb,
            "audio": ab,
            "sfxWindows": sfx_spots(b_final, ed, pb["duration"] or duration),
            "resources": res_b,
            "alpha": alpha,
            "mix": {k: v for k, v in mix.items() if k != "probe"},
            "overlayBytes": overlay_bytes,
            "tempBytesExclModules": _dir_bytes(work),
            "tempRequired": required,
            "tempFree": free,
            "out": str(b_final),
        },
        "WHOLE_JOB_GAIN_SEC": round(gain, 3),
        "WHOLE_JOB_GAIN_PERCENT": round(pct, 2),
        "delta": {
            "frames": (pa.get("frames") or 0) - (pb.get("frames") or 0),
            "duration": round((pa.get("duration") or 0) - (pb.get("duration") or 0), 4),
            "lufs": (
                None if aa["integratedLufs"] is None or ab["integratedLufs"] is None
                else round(aa["integratedLufs"] - ab["integratedLufs"], 2)
            ),
            "truePeak": (
                None if aa["truePeakDb"] is None or ab["truePeakDb"] is None
                else round(aa["truePeakDb"] - ab["truePeakDb"], 2)
            ),
            "samplePeak": (
                None if aa["maxDb"] is None or ab["maxDb"] is None
                else round(aa["maxDb"] - ab["maxDb"], 2)
            ),
        },
        "fps": fps,
    }
    dest = work / f"gate_{tag}_report.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("WROTE", dest, flush=True)
    print(json.dumps({
        "expectedFrames": expected_frames,
        "cutFramesA": cut_a_frames,
        "cutFramesB": cut_b_frames,
        "overlayFrames": overlay_frames,
        "finalFramesA": pa.get("frames"),
        "finalFramesB": pb.get("frames"),
        "expectedDuration": duration,
        "finalDurationA": pa.get("duration"),
        "finalDurationB": pb.get("duration"),
        "WHOLE_JOB_A": report["A"]["wholeJobSec"],
        "WHOLE_JOB_B": report["B"]["wholeJobSec"],
        "WHOLE_JOB_GAIN_SEC": report["WHOLE_JOB_GAIN_SEC"],
        "WHOLE_JOB_GAIN_PERCENT": report["WHOLE_JOB_GAIN_PERCENT"],
        "lufsA": aa.get("integratedLufs"),
        "lufsB": ab.get("integratedLufs"),
        "truePeakA": aa.get("truePeakDb"),
        "truePeakB": ab.get("truePeakDb"),
        "samplePeakA": aa.get("maxDb"),
        "samplePeakB": ab.get("maxDb"),
        "lraA": aa.get("lra"),
        "lraB": ab.get("lra"),
        "framesDelta": report["delta"]["frames"],
        "durationDelta": report["delta"]["duration"],
    }, indent=2), flush=True)
    return report


def gate3(edit_dir: Path, work: Path) -> dict:
    """Falha controlada no Overlay → FALLBACK_FULL → final válido. Sem hook permanente."""
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    src_rem = edit_dir / "remotion"
    ed = json.loads((src_rem / "public" / "edit-data.json").read_text(encoding="utf-8-sig"))
    edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8-sig"))
    edl.pop("ffmpegZoom", None)
    cut = work / "cut.mp4"
    print("GATE 3 CUT (necessário para o fallback ter fonte)", flush=True)
    _render_py(edl, cut)
    rem = _copy_remotion(src_rem, work / "remotion")
    dest_cut = rem / "public" / "cut.mp4"
    dest_cut.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cut, dest_cut)

    import app.overlay_path as ovmod

    def _boom(*_a, **_k):
        raise RuntimeError("OVERLAY_ALPHA_INVALID forced-gate3")

    orig = ovmod.render_overlay
    ovmod.render_overlay = _boom  # type: ignore[assignment]
    overlay_failed = False
    fallback = False
    err = ""
    try:
        from app.overlay_path import try_overlay_final
        try:
            try_overlay_final(
                edit_dir=edit_dir, remotion=rem, cut=cut, edit_data=ed,
                dest=work / "overlay_final.mp4",
            )
        except Exception as e:  # noqa: BLE001
            err = str(e)
            overlay_failed = True
            print(f"OVERLAY_FAILED {e}", flush=True)
            print("FALLBACK_FULL_REMOTION", flush=True)
            fallback = True
            tl3 = timeline_from_edit_data(ed)
            t_r = _render_reels(rem, work / "render.mp4")
            t_e = _encode_full(
                work / "render.mp4", work / "final.mp4",
                tl3["durationSec"], duration_in_frames=tl3["durationInFrames"],
            )
            print(f"  fallback remotion={t_r:.1f}s encode={t_e:.1f}s", flush=True)
    finally:
        ovmod.render_overlay = orig

    final = work / "final.mp4"
    ok = final.exists() and final.stat().st_size > 10_000
    info = video_info(final) if ok else {}
    report = {
        "overlayFailed": overlay_failed,
        "fallbackPrinted": fallback,
        "error": err,
        "finalExists": ok,
        "final": info,
        "hookRemoved": True,
    }
    (work / "gate_3_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print(json.dumps(report, indent=2), flush=True)
    if not (overlay_failed and fallback and ok):
        raise RuntimeError("GATE 3 falhou: fallback não produziu final válido")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", choices=["1", "2", "3", "all"], default="all")
    args = ap.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    if args.gate in ("1", "all"):
        summary["gate1"] = clean_ab(SHORT, ROOT / "gate1", "1")
    if args.gate in ("2", "all"):
        summary["gate2"] = clean_ab(LONG, ROOT / "gate2", "2")
    if args.gate in ("3", "all"):
        summary["gate3"] = gate3(SHORT, ROOT / "gate3")
    (ROOT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
