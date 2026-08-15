"""Benchmark experimental: FULL+zoom Remotion vs OVERLAY+zoom FFmpeg.

Não grava no projeto do usuário. Não liga OVERLAY em produção.

    python pipeline/ffmpeg_zoom_proto.py --edit-dir <projeto>/edit
    python pipeline/ffmpeg_zoom_proto.py --extra
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "helpers") not in sys.path:
    sys.path.insert(0, str(REPO / "helpers"))

from pipeline.overlay_proto import (  # noqa: E402
    DEFAULT_EDIT,
    PROTO_SRC,
    Sampler,
    _compose,
    _duration,
    _encode_full,
    _export_main_symbols,
    _ffmpeg,
    _ffprobe,
    _flatten_edit_data,
    _hide,
    _probe,
    _remotion_cmd,
    _render,
    _run,
    validate_overlay_alpha,
)

WORK = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_ffmpeg_zoom"


def _info(path: Path) -> dict:
    raw = _probe(
        path,
        "-select_streams", "v:0",
        "-show_entries",
        "stream=nb_frames,r_frame_rate,codec_name,bit_rate,width,height:format=duration,bit_rate",
        "-of", "json",
    )
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        data = {}
    st = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    fps_s = str(st.get("r_frame_rate") or "0/1")
    num, _, den = fps_s.partition("/")
    fps = float(num) / float(den or 1)
    frames = st.get("nb_frames")
    try:
        frames = int(frames) if frames not in (None, "N/A") else None
    except (TypeError, ValueError):
        frames = None
    if frames is None:
        n = _probe(path, "-select_streams", "v:0", "-count_frames",
                   "-show_entries", "stream=nb_read_frames",
                   "-of", "default=nokey=1:noprint_wrappers=1")
        try:
            frames = int(n) if n else None
        except ValueError:
            frames = None
    return {
        "duration": float(fmt.get("duration") or 0),
        "fps": round(fps, 3),
        "frames": frames,
        "width": int(st.get("width") or 0),
        "height": int(st.get("height") or 0),
        "codec": st.get("codec_name"),
        "bitrate": int(fmt.get("bit_rate") or st.get("bit_rate") or 0),
        "sizeBytes": path.stat().st_size if path.exists() else 0,
    }


def _copy_edl(src: Path, dest_dir: Path, *, zoom: dict | None) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    edl = json.loads(src.read_text(encoding="utf-8-sig"))
    if zoom:
        edl["ffmpegZoom"] = zoom
    else:
        edl.pop("ffmpegZoom", None)
    dest = dest_dir / "edl.json"
    dest.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def _extract_cut(edl_path: Path, out: Path) -> float:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(REPO), str(REPO / "helpers"), env.get("PYTHONPATH") or ""])
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, str(REPO / "helpers" / "render.py"),
        str(edl_path), "-o", str(out),
        "--no-subtitles", "--voice-master", "--no-polish",
    ]
    print("CUT", out, flush=True)
    t0 = time.perf_counter()
    r = subprocess.run(cmd, cwd=str(REPO), env=env, **_hide())
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"render.py exit {r.returncode} for {out}")
    return dt


def _prepare_remotion(edit_dir: Path, dest: Path, *, flatten: bool, overlay: bool) -> Path:
    src = edit_dir / "remotion"
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
    if overlay:
        shutil.copy2(PROTO_SRC / "Overlay.tsx", dest / "src" / "Overlay.tsx")
        shutil.copy2(PROTO_SRC / "Root.tsx", dest / "src" / "Root.tsx")
        _export_main_symbols(dest / "src" / "Main.tsx")
    if flatten:
        _flatten_edit_data(src / "public" / "edit-data.json", dest / "public" / "edit-data.json")
    return dest


def _spots(segments: list[dict], fps: float, duration: float) -> list[tuple[str, float]]:
    frame = 1.0 / max(1.0, fps)
    out: list[tuple[str, float]] = []
    for i, s in enumerate(segments):
        start = float(s["start"])
        dur = float(s["dur"])
        end = start + dur
        out.append((f"seg{i}_start", min(duration - frame, start + frame * 0.5)))
        out.append((f"seg{i}_mid", start + dur * 0.5))
        if i + 1 < len(segments):
            out.append((f"seg{i}_last_before_cut", max(0.0, end - frame * 1.5)))
            out.append((f"seg{i + 1}_first_after_cut", min(duration - frame, end + frame * 0.5)))
    out.append(("hook", min(0.4, duration * 0.1)))
    out.append(("endcard", max(frame, duration - 0.8)))
    seen: set[str] = set()
    uniq: list[tuple[str, float]] = []
    for name, t in out:
        key = f"{name}:{t:.4f}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append((name, round(max(0.0, min(duration - frame, t)), 4)))
    return uniq


def _grab(video: Path, dest_dir: Path, spots: list[tuple[str, float]]) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for name, t in spots:
        p = dest_dir / f"{name}_{t:.3f}s.png"
        _run([
            _ffmpeg(), "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.4f}", "-i", str(video),
            "-frames:v", "1", str(p),
        ])
        out.append(p)
    return out


def _hstack(a: Path, b: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(a), "-i", str(b),
        "-filter_complex", "hstack=inputs=2",
        str(dest),
    ])


def _zoom_block(edit_dir: Path) -> dict:
    ed = json.loads((edit_dir / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8-sig"))
    cam = ed.get("camera") or {}
    return {
        "enabled": True,
        "zooms": list(cam.get("zooms") or [1.14, 1.2, 1.12]),
        "pushIn": float(cam.get("pushIn") or 0.04),
        "targetX": float(cam.get("targetX") or 0.5),
        "targetY": float(cam.get("targetY") or 0.4),
        "width": int(ed.get("width") or 1080),
        "height": int(ed.get("height") or 1920),
    }


def run_one(edit_dir: Path, work: Path) -> dict:
    from app.render_path import classify_render_path

    edit_dir = edit_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    segs = json.loads((edit_dir / "remotion" / "public" / "segments.json").read_text(encoding="utf-8"))
    ed = json.loads((edit_dir / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8-sig"))
    cls_now = classify_render_path(ed, public=edit_dir / "remotion" / "public")
    cls_if = classify_render_path(ed, public=edit_dir / "remotion" / "public", ffmpeg_zoom=True)

    zoom = _zoom_block(edit_dir)
    edl_src = edit_dir / "edl.json"
    cut_a = work / "cut_a.mp4"
    cut_b = work / "cut_b.mp4"
    edl_a = _copy_edl(edl_src, work / "edl_a", zoom=None)
    edl_b = _copy_edl(edl_src, work / "edl_b", zoom=zoom)

    t_cut_a = _extract_cut(edl_a, cut_a)
    try:
        t_cut_b = _extract_cut(edl_b, cut_b)
        zoom_failed = False
    except RuntimeError as e:
        print("FFMPEG_ZOOM_FAILED", e, flush=True)
        print("FALLBACK_FULL_REMOTION", flush=True)
        t_cut_b = None
        zoom_failed = True
        cut_b = cut_a

    rem_a = _prepare_remotion(edit_dir, work / "remotion_a", flatten=False, overlay=False)
    shutil.copy2(cut_a, rem_a / "public" / "cut.mp4")
    rem_b = _prepare_remotion(edit_dir, work / "remotion_b", flatten=True, overlay=True)
    shutil.copy2(cut_b, rem_b / "public" / "cut.mp4")

    duration = _duration(cut_a)
    fps = float(ed.get("fps") or 30)
    full_raw = work / "full_raw.mp4"
    full_out = work / "full_final.mp4"
    overlay = work / "overlay.mov"
    ov_out = work / "overlay_final.mp4"

    samp_a = Sampler()
    samp_a.start()
    t_full_r = _render(rem_a, "Reels", full_raw, [])
    res_a = samp_a.stop()
    t_full_e, enc_a = _encode_full(full_raw, full_out, duration)

    samp_b = Sampler()
    samp_b.start()
    try:
        t_ov_r = _render(
            rem_b, "Overlay", overlay,
            ["--codec", "prores", "--prores-profile", "4444",
             "--image-format", "png", "--pixel-format", "yuva444p10le"],
        )
    except RuntimeError:
        overlay = work / "overlay.webm"
        t_ov_r = _render(
            rem_b, "Overlay", overlay,
            ["--codec", "vp8", "--pixel-format", "yuva420p"],
        )
    res_b = samp_b.stop()
    alpha = validate_overlay_alpha(
        overlay,
        width=int(ed.get("width") or 1080),
        height=int(ed.get("height") or 1920),
        duration=duration,
        fps=fps,
    )
    t_ov_c, enc_b = _compose(cut_b, overlay, ov_out, duration)

    info_a = _info(full_out)
    info_b = _info(ov_out)
    info_ca = _info(cut_a)
    info_cb = _info(cut_b) if cut_b.exists() else {}

    spots = _spots(segs.get("segments") or [], fps, duration)
    fa = _grab(full_out, work / "frames_a", spots)
    fb = _grab(ov_out, work / "frames_b", spots)
    pairs = work / "frames_pair"
    for pa, pb, (name, t) in zip(fa, fb, spots):
        if pa.exists() and pb.exists():
            _hstack(pa, pb, pairs / f"{name}_{t:.3f}s.png")

    extra_encode = False  # zoom está no extract, não há zoomed.mp4
    a_total = t_cut_a + t_full_r + t_full_e
    b_total = (t_cut_b or 0) + t_ov_r + t_ov_c
    report = {
        "project": str(edit_dir.parent.name),
        "durationSec": duration,
        "fps": fps,
        "classifyNow": cls_now,
        "classifyIfFfmpegZoom": cls_if,
        "zoom": zoom,
        "zoomFailed": zoom_failed,
        "extraEncode": extra_encode,
        "cutA": {"sec": round(t_cut_a, 3), **info_ca},
        "cutB": {"sec": None if t_cut_b is None else round(t_cut_b, 3), **info_cb},
        "zoomCostInCutSec": None if t_cut_b is None else round(t_cut_b - t_cut_a, 3),
        "A_full": {
            "cutSec": round(t_cut_a, 3),
            "remotionSec": round(t_full_r, 3),
            "encodeSec": round(t_full_e, 3),
            "renderSectionSec": round(t_cut_a + t_full_r + t_full_e, 3),
            "wholeJobSec": round(a_total, 3),
            "realtime": round(duration / max(0.001, a_total), 3),
            "remotionFps": round((duration * fps) / max(0.001, t_full_r), 2),
            "encoder": enc_a,
            "resources": res_a,
            **info_a,
        },
        "B_overlay": {
            "cutSec": None if t_cut_b is None else round(t_cut_b, 3),
            "overlaySec": round(t_ov_r, 3),
            "composeSec": round(t_ov_c, 3),
            "renderSectionSec": round(b_total, 3),
            "wholeJobSec": round(b_total, 3),
            "realtime": round(duration / max(0.001, b_total), 3),
            "overlayFps": round((duration * fps) / max(0.001, t_ov_r), 2),
            "encoder": enc_b,
            "resources": res_b,
            "overlayAlpha": alpha,
            **info_b,
        },
        "savedSec": round(a_total - b_total, 3),
        "savedPct": round(100.0 * (a_total - b_total) / a_total, 1) if a_total else 0,
        "sync": {
            "durationDeltaSec": round((info_b.get("duration") or 0) - (info_a.get("duration") or 0), 4),
            "frameDelta": (info_b.get("frames") or 0) - (info_a.get("frames") or 0),
            "fpsA": info_a.get("fps"),
            "fpsB": info_b.get("fps"),
            "cutDurationDeltaSec": round((info_cb.get("duration") or 0) - (info_ca.get("duration") or 0), 4),
            "cutFrameDelta": (info_cb.get("frames") or 0) - (info_ca.get("frames") or 0),
        },
        "spots": [{"name": n, "t": t} for n, t in spots],
        "framesDir": str(pairs),
        "note": (
            "A = FULL Remotion (OffthreadVideo + zoomCuts + pushIn). "
            "B = extract com zoom FFmpeg + overlay transparente. "
            "Sem etapa cut→zoomed. Flag experimental — produção inalterada."
        ),
    }
    (work / "ffmpeg_zoom_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in (
        "project", "durationSec", "savedSec", "savedPct", "zoomCostInCutSec",
        "sync", "zoomFailed", "extraEncode",
    )}, indent=2), flush=True)
    return report


def _list_projects() -> list[dict]:
    rows = []
    root = Path(r"E:\ATIVAVID\Projetos")
    if not root.is_dir():
        return rows
    skip = "20260814-170256_Parte_1_x2_6d5628b3a3"
    for proj in root.iterdir():
        edp = proj / "edit" / "remotion" / "public" / "edit-data.json"
        edl_p = proj / "edit" / "edl.json"
        if not edp.exists() or not edl_p.exists():
            continue
        if proj.name == skip:
            continue
        try:
            ed = json.loads(edp.read_text(encoding="utf-8-sig"))
            edl = json.loads(edl_p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        n = len(edl.get("ranges") or [])
        rows.append({
            "name": proj.name,
            "edit": proj / "edit",
            "nRanges": n,
            "duration": float(ed.get("durationSec") or 0),
        })
    return rows


def pick_extra() -> list[dict]:
    rows = _list_projects()
    if len(rows) < 3:
        return rows
    many = max(rows, key=lambda r: r["nRanges"])
    few = min(rows, key=lambda r: (r["nRanges"], r["duration"]))
    long = max((r for r in rows if r["name"] not in {many["name"], few["name"]}),
               key=lambda r: r["duration"], default=None)
    picked = [few, many]
    if long:
        picked.append(long)
    # unique
    seen = set()
    out = []
    for r in picked:
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        out.append(r)
    return out[:3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit-dir", type=Path, default=DEFAULT_EDIT)
    ap.add_argument("--extra", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        return _smoke(args.edit_dir.resolve())

    if args.extra:
        extras = pick_extra()
        reports = []
        for row in extras:
            w = WORK / f"extra_{row['name']}"
            print(f"\n=== EXTRA {row['name']} cuts={row['nRanges']} dur={row['duration']}s ===", flush=True)
            reports.append(run_one(row["edit"], w))
        summary = {
            "projects": [
                {k: r[k] for k in ("project", "durationSec", "savedSec", "savedPct",
                                   "zoomCostInCutSec", "sync", "zoomFailed") if k in r}
                for r in reports
            ]
        }
        (WORK / "ffmpeg_zoom_extra.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    work = WORK / "main"
    report = run_one(args.edit_dir.resolve(), work)
    return 1 if report.get("zoomFailed") else 0


def _smoke(edit_dir: Path) -> int:
    """1 segmento curto — valida a sintaxe do crop/scale antes do job inteiro."""
    from app.ffmpeg_zoom import zoom_vf
    from render import extract_segment  # helpers/ no path

    edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8-sig"))
    r0 = edl["ranges"][0]
    src = Path(edl["sources"][r0["source"]])
    dest = WORK / "smoke" / "seg.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    spec = {"base": 1.14, "push": 0.04, "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920}
    print("vf", zoom_vf(spec, n_frames=30), flush=True)
    extract_segment(src, float(r0["start"]), 1.0, "", dest, streams="v", zoom=spec)
    info = _info(dest)
    print(json.dumps(info, indent=2), flush=True)
    ok = info.get("width") == 1080 and info.get("height") == 1920 and (info.get("frames") or 0) >= 24
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
