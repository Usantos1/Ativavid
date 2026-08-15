"""A/B isolado: FULL atual vs CUT+zoom FFmpeg+OVERLAY+compose.

Não grava no projeto. Não liga flags de produção.

    uv run python pipeline/overlay_ab.py
    uv run python pipeline/overlay_ab.py --edit-dir <projeto>/edit
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "helpers")]

from app.ffmpeg_zoom import attach_to_edl, flatten_remotion_camera  # noqa: E402
from app.overlay_compose import compose_overlay, validate_overlay_alpha, video_info  # noqa: E402
from app.overlay_path import prepare_overlay_remotion, render_overlay  # noqa: E402
from app.render_path import classify_render_path  # noqa: E402
from pipeline.overlay_proto import (  # noqa: E402
    Sampler,
    _duration,
    _ffmpeg,
    _hide,
    _remotion_cmd,
    _run,
)

DEFAULT_EDIT = Path(
    r"E:\ATIVAVID\Projetos\20260814-170256_Parte_1_x2_6d5628b3a3\edit"
)
WORK = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_overlay_ab"


def _probe_audio_peak(path: Path) -> dict:
    r = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        **_hide(),
    )
    log = r.stderr or ""
    import re
    mx = re.search(r"max_volume:\s*([-\d.]+)\s*dB", log)
    mn = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", log)
    return {
        "maxDb": float(mx.group(1)) if mx else None,
        "meanDb": float(mn.group(1)) if mn else None,
    }


def _frames(video: Path, dest: Path, times: list[float]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for t in times:
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
            str(dest / f"{t:.2f}s.png"),
        ])


def _render_reels(remotion: Path, out: Path) -> float:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = _remotion_cmd(
        remotion, "render", "Reels", str(out), "--concurrency=4",
    )
    print("RENDER Reels", flush=True)
    t0 = time.perf_counter()
    r = _run(cmd, cwd=remotion)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"Reels render exit {r.returncode}")
    return dt


def _cut_with_zoom(edit_dir: Path, dest: Path) -> dict:
    edl_src = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8-sig"))
    ed = json.loads(
        (edit_dir / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8-sig")
    )
    cam = ed.get("camera") or {}
    attached = attach_to_edl(
        edl_src, cam,
        width=int(ed.get("width") or 1080),
        height=int(ed.get("height") or 1920),
    )
    work_edl = WORK / "edl_zoom.json"
    work_edl.write_text(json.dumps(edl_src, indent=2, ensure_ascii=False), encoding="utf-8")
    t0 = time.perf_counter()
    r = subprocess.run(
        [sys.executable, str(REPO / "helpers" / "render.py"),
         str(work_edl), "-o", str(dest), "--no-subtitles", "--voice-master"],
        cwd=str(REPO),
        **_hide(),
    )
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"CUT zoom failed exit={r.returncode}")
    return {"sec": round(dt, 3), "zoomAttached": attached, "probe": video_info(dest)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-dir", type=Path, default=DEFAULT_EDIT)
    args = ap.parse_args()
    edit_dir = args.edit_dir.resolve()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    src_remotion = edit_dir / "remotion"
    ed = json.loads((src_remotion / "public" / "edit-data.json").read_text(encoding="utf-8-sig"))
    cut_orig = edit_dir / "cut.mp4"
    duration = float(ed.get("durationSec") or _duration(cut_orig))
    fps = float(ed.get("fps") or 30)
    cls_full = classify_render_path(ed, public=src_remotion / "public")
    cls_ov = classify_render_path(ed, public=src_remotion / "public", ffmpeg_zoom=True)
    print(f"CLASSIFY full={cls_full['path']} overlay_if_zoom={cls_ov['path']}", flush=True)

    report: dict = {
        "project": edit_dir.parent.name,
        "classifyFull": cls_full,
        "classifyOverlay": cls_ov,
        "note": (
            "A = FULL Remotion (zoom+SFX+trilha no Remotion) + encode NVENC. "
            "B = CUT CPU com zoom FFmpeg + Overlay Remotion + compose "
            "(voz+SFX overlay+trilha+loudnorm). Flags de produção permanecem off."
        ),
    }

    # --- A FULL ---
    print("PATH A FULL", flush=True)
    a_dir = WORK / "A"
    a_rem = a_dir / "remotion"
    if a_rem.exists():
        shutil.rmtree(a_rem, ignore_errors=True)
    shutil.copytree(src_remotion, a_rem, ignore=shutil.ignore_patterns("out", "node_modules"))
    nm = a_rem / "node_modules"
    if (src_remotion / "node_modules").exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nm), str((src_remotion / "node_modules").resolve())],
            **_hide(),
        )
    samp = Sampler()
    samp.start()
    t_job = time.perf_counter()
    t_a_r = _render_reels(a_rem, a_dir / "render.mp4")
    t_enc0 = time.perf_counter()
    a_final = a_dir / "final.mp4"
    enc_r = _run([
        _ffmpeg(), "-y", "-hide_banner", "-nostats",
        "-i", str(a_dir / "render.mp4"),
        "-filter_complex",
        "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid];"
        "[0:a]loudnorm=I=-14:TP=-1:LRA=11[out]",
        "-map", "[vid]", "-map", "[out]",
        "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{duration:.3f}", "-movflags", "+faststart",
        str(a_final),
    ])
    if enc_r.returncode != 0:
        raise RuntimeError(f"A encode failed:\n{(enc_r.stderr or '')[-1500:]}")
    t_a_e = time.perf_counter() - t_enc0
    a_wall = time.perf_counter() - t_job
    res_a = samp.stop()
    report["A"] = {
        "path": "FULL",
        "remotionSec": round(t_a_r, 3),
        "composeSec": round(t_a_e, 3),
        "wholeJobSec": round(a_wall, 3),
        "cutSec": 0,
        "resources": res_a,
        "probe": video_info(a_final),
        "audio": _probe_audio_peak(a_final),
        "out": str(a_final),
        "encoder": "h264_nvenc",
    }
    print(f"  A done {a_wall:.1f}s", flush=True)

    # --- B OVERLAY ---
    print("PATH B OVERLAY", flush=True)
    b_dir = WORK / "B"
    b_dir.mkdir(parents=True)
    samp = Sampler()
    samp.start()
    t_job = time.perf_counter()
    t_cut0 = time.perf_counter()
    cut_b = _cut_with_zoom(edit_dir, b_dir / "cut.mp4")
    cut_sec = time.perf_counter() - t_cut0
    ed_b = json.loads(json.dumps(ed))
    flatten_remotion_camera(ed_b)
    b_rem = prepare_overlay_remotion(src_remotion, b_dir / "remotion")
    (b_rem / "public" / "edit-data.json").write_text(
        json.dumps(ed_b, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    t_ov0 = time.perf_counter()
    overlay = render_overlay(b_rem, b_dir / "overlay")
    ov_sec = time.perf_counter() - t_ov0
    alpha = validate_overlay_alpha(
        overlay,
        width=int(ed.get("width") or 1080),
        height=int(ed.get("height") or 1920),
        duration=_duration(b_dir / "cut.mp4"),
    )
    st = ed.get("soundtrack") or {}
    trilha = src_remotion / "public" / str(st.get("file") or "trilha.mp3")
    if not (st.get("enabled") and trilha.exists()):
        trilha = None
    t_c0 = time.perf_counter()
    mix = compose_overlay(
        b_dir / "cut.mp4", overlay, b_dir / "final.mp4",
        duration=_duration(b_dir / "cut.mp4"),
        trilha=trilha,
        trilha_volume=float(st.get("volume") or 0.12),
    )
    compose_sec = time.perf_counter() - t_c0
    b_wall = time.perf_counter() - t_job
    res_b = samp.stop()
    b_final = b_dir / "final.mp4"
    report["B"] = {
        "path": "OVERLAY",
        "cutSec": round(cut_sec, 3),
        "cut": cut_b,
        "remotionSec": round(ov_sec, 3),
        "composeSec": round(compose_sec, 3),
        "wholeJobSec": round(b_wall, 3),
        "resources": res_b,
        "alpha": alpha,
        "mix": {k: v for k, v in mix.items() if k != "probe"},
        "probe": video_info(b_final),
        "audio": _probe_audio_peak(b_final),
        "out": str(b_final),
    }
    print(f"  B done {b_wall:.1f}s", flush=True)

    spots = [0.4, duration * 0.35, duration * 0.7, max(0.2, duration - 0.8)]
    _frames(a_final, WORK / "frames" / "A", spots)
    _frames(b_final, WORK / "frames" / "B", spots)

    pa, pb = report["A"]["probe"], report["B"]["probe"]
    report["delta"] = {
        "wholeJobSec": round(report["A"]["wholeJobSec"] - report["B"]["wholeJobSec"], 3),
        "remotionSec": round(report["A"]["remotionSec"] - report["B"]["remotionSec"], 3),
        "frames": (pa.get("frames") or 0) - (pb.get("frames") or 0),
        "duration": round((pa.get("duration") or 0) - (pb.get("duration") or 0), 4),
        "bytes": (pa.get("bytes") or 0) - (pb.get("bytes") or 0),
        "maxDb": (
            None if report["A"]["audio"]["maxDb"] is None or report["B"]["audio"]["maxDb"] is None
            else round(report["A"]["audio"]["maxDb"] - report["B"]["audio"]["maxDb"], 2)
        ),
    }
    dest = WORK / "overlay_ab_report.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("WROTE", dest, flush=True)
    print(json.dumps({
        "A": {k: report["A"][k] for k in ("wholeJobSec", "remotionSec", "composeSec", "probe", "audio")},
        "B": {k: report["B"][k] for k in ("wholeJobSec", "cutSec", "remotionSec", "composeSec", "probe", "audio")},
        "delta": report["delta"],
    }, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
