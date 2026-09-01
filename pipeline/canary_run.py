"""Seleciona e roda uma rodada canary OVERLAY — um de cada vez.

Reusa o edit já aprovado (cut + remotion + edit-data) num diretório isolado.
Não grava no projeto do cliente. Não altera o motor.

    uv run python pipeline/canary_run.py --inventory --limit 20
    uv run python pipeline/canary_run.py --run --limit 20
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "helpers"), str(REPO / "pipeline")]

from app.overlay_canary import load_state  # noqa: E402
from app.render_path import classify_render_path  # noqa: E402
from app.settings_store import load_settings, resolve_projects_root, save_settings  # noqa: E402
from app.timeline import timeline_from_edit_data  # noqa: E402

WORK = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_canary20"


def _projects_root() -> Path:
    hinted = Path(r"E:\ATIVAVID\Projetos")
    if hinted.exists():
        return hinted
    return resolve_projects_root(Path.home() / "ATIVAVID" / "Projetos")


def _hide() -> dict:
    try:
        from app.win_process import hide_console_kwargs
        return hide_console_kwargs()
    except Exception:
        return {}


def _ffprobe_json(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        **_hide(),
    )
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def _source_flags(path: Path) -> dict:
    data = _ffprobe_json(path)
    st = next((s for s in (data.get("streams") or []) if s.get("codec_type") == "video"), {})
    w = int(st.get("width") or 0)
    h = int(st.get("height") or 0)
    trc = str(st.get("color_transfer") or "").lower()
    hdr = trc in ("arib-std-b67", "smpte2084") or "hlg" in trc or "pq" in trc
    return {
        "width": w,
        "height": h,
        "is4k": max(w, h) >= 2160,
        "hdr": hdr,
        "codec": st.get("codec_name"),
    }


def _full_render_baseline_sec(timing: dict) -> float | None:
    """Baseline FULL real da fase de render — não inventa estimativa."""
    if str(timing.get("renderPath") or "") != "FULL":
        return None
    stages = timing.get("stages") or {}
    rend = (stages.get("REMOTION_RENDER") or {}).get("sec")
    enc = (stages.get("FINAL_ENCODE") or {}).get("sec")
    if rend is None or enc is None:
        return None
    try:
        return float(rend) + float(enc)
    except (TypeError, ValueError):
        return None


def inventory() -> list[dict]:
    root = _projects_root()
    rows: list[dict] = []
    for proj in sorted(root.iterdir() if root.exists() else []):
        edit = proj / "edit"
        ed_path = edit / "remotion" / "public" / "edit-data.json"
        cut = edit / "cut.mp4"
        if not cut.exists():
            cut = edit / "remotion" / "public" / "cut.mp4"
        if not ed_path.exists() or not cut.exists():
            continue
        try:
            ed = json.loads(ed_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        public = ed_path.parent
        cls = classify_render_path(ed, public=public, ffmpeg_zoom=True)
        if cls["path"] == "FULL" and cls.get("fullReasons"):
            continue
        tl = timeline_from_edit_data(ed)
        edl = {}
        edl_path = edit / "edl.json"
        if edl_path.exists():
            try:
                edl = json.loads(edl_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                edl = {}
        ranges = edl.get("ranges") or []
        sources = edl.get("sources") or {}
        src = None
        if isinstance(sources, dict):
            for v in sources.values():
                p = Path(str(v))
                if p.exists():
                    src = p
                    break
        if src is None:
            vids = [
                p for p in proj.iterdir()
                if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".m4v", ".mxf")
            ]
            src = vids[0] if vids else None
        preset = edit / "preset-used.json"
        flags = _source_flags(src) if src else {
            "width": 0, "height": 0, "is4k": False, "hdr": False, "codec": None,
        }
        timing = {}
        tpath = edit / "timing.json"
        if tpath.exists():
            try:
                timing = json.loads(tpath.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                timing = {}
        rows.append({
            "project": proj.name,
            "edit": str(edit),
            "source": str(src) if src else None,
            "preset": str(preset) if preset.exists() else None,
            "durationSec": tl["durationSec"],
            "frames": tl["durationInFrames"],
            "cuts": len(ranges),
            "path": cls["path"],
            "reasons": cls.get("overlayReasons") or cls.get("reasons"),
            "zoomBaked": bool((edl.get("ffmpegZoom") or {}).get("enabled"))
            or str((ed.get("camera") or {}).get("engine") or "") == "ffmpeg",
            **flags,
            "fullRenderBaselineSec": _full_render_baseline_sec(timing),
        })
    return rows


def _src_name(row: dict) -> str:
    src = row.get("source") or ""
    return Path(src).name.lower() if src else row.get("project") or ""


def pick_n(rows: list[dict], n: int) -> list[dict]:
    """Cobre 1080 / 4K / HDR / curto / 40–60 / 60–90 / poucos / muitos cortes."""
    unused = list(rows)
    picked: list[dict] = []

    def take(pred, prefer=None) -> dict | None:
        used_src = {_src_name(p) for p in picked}
        cands = [r for r in unused if pred(r) and _src_name(r) not in used_src]
        if not cands:
            cands = [r for r in unused if pred(r)]
        if not cands:
            return None
        if prefer:
            cands = sorted(cands, key=prefer, reverse=True)
        choice = cands[0]
        unused.remove(choice)
        return choice

    buckets = [
        ("p1080", lambda r: not r["is4k"] and not r["hdr"], None),
        ("p4k", lambda r: r["is4k"], lambda r: r["durationSec"]),
        ("phdr", lambda r: r["hdr"], lambda r: r["durationSec"]),
        ("short", lambda r: r["durationSec"] < 35, None),
        ("mid_40_60", lambda r: 38 <= r["durationSec"] <= 62, None),
        ("long_60_90", lambda r: r["durationSec"] >= 58, lambda r: r["durationSec"]),
        ("few_cuts", lambda r: r["cuts"] < 8, None),
        ("many_cuts", lambda r: r["cuts"] >= 12, lambda r: (r["cuts"], r["durationSec"])),
    ]
    for name, pred, extra in buckets:
        hit = take(pred, extra)
        if hit:
            hit["slot"] = name
            picked.append(hit)
    while len(picked) < n and unused:
        used_src = {_src_name(p) for p in picked}
        used_durs = [p["durationSec"] for p in picked] or [0.0]

        def score(r: dict) -> tuple:
            novel = 1 if _src_name(r) not in used_src else 0
            dist = min(abs(r["durationSec"] - d) for d in used_durs)
            return (novel, dist, r["cuts"])

        unused.sort(key=score, reverse=True)
        nxt = unused.pop(0)
        nxt["slot"] = nxt.get("slot") or "fill"
        picked.append(nxt)
    return picked[:n]


def pick_baselines(picked: list[dict], n: int = 5) -> list[str]:
    """5 perfis diferentes para FULL real — não estima nos outros."""
    unused = list(picked)
    chosen: list[dict] = []

    def take(pred) -> dict | None:
        for r in unused:
            if pred(r):
                unused.remove(r)
                return r
        return None

    for pred in (
        lambda r: r["durationSec"] < 35 and not r["is4k"],
        lambda r: 38 <= r["durationSec"] <= 62 and (r["is4k"] or r["hdr"]),
        lambda r: r["durationSec"] >= 58,
        lambda r: r["cuts"] >= 12,
    ):
        hit = take(pred)
        if hit:
            chosen.append(hit)
    while len(chosen) < n and unused:
        used_durs = [c["durationSec"] for c in chosen] or [0.0]
        unused.sort(
            key=lambda r: min(abs(r["durationSec"] - d) for d in used_durs),
            reverse=True,
        )
        chosen.append(unused.pop(0))
    names = {c["project"] for c in chosen[:n]}
    for r in picked:
        r["wantFullBaseline"] = r["project"] in names
    return sorted(names)


def activate_canary(limit: int) -> None:
    from app.overlay_canary import STATE_PATH, save_state

    save_state({
        "canaryAttempt": 0,
        "canaryLimit": int(limit),
        "paused": False,
        "pausedReason": None,
        "jobs": [],
        "round": f"canary{limit}",
    })
    save_settings({
        "overlayRollout": "canary",
        "canaryAttempt": 0,
        "canaryLimit": int(limit),
        "experimentalOverlay": False,
        "experimentalFfmpegZoom": False,
    })
    print(f"overlayRollout=canary canaryAttempt=0 canaryLimit={limit}", flush=True)
    print("STATE", STATE_PATH, flush=True)


def _link_modules(src_remotion: Path, dest: Path) -> None:
    nm = dest / "node_modules"
    src = src_remotion / "node_modules"
    if not src.exists():
        src = REPO / "assets" / "shortform" / "node_modules"
    if src.exists() and not nm.exists():
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(nm), str(src.resolve())],
            **_hide(),
        )


def isolate_edit(row: dict) -> Path:
    src_edit = Path(row["edit"])
    dest = WORK / row["project"] / "edit"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in ("cut.mp4", "edl.json", "preset-used.json"):
        p = src_edit / name
        if p.exists():
            shutil.copy2(p, dest / name)
    src_rem = src_edit / "remotion"
    dest_rem = dest / "remotion"
    dest_rem.mkdir(parents=True)
    for name in ("src", "public", "package.json", "remotion.config.ts", "tsconfig.json"):
        p = src_rem / name
        if p.is_dir():
            shutil.copytree(p, dest_rem / name)
        elif p.exists():
            shutil.copy2(p, dest_rem / name)
    _link_modules(src_rem, dest_rem)
    pub_cut = dest_rem / "public" / "cut.mp4"
    cut = dest / "cut.mp4"
    if cut.exists():
        pub_cut.parent.mkdir(parents=True, exist_ok=True)
        if not pub_cut.exists():
            try:
                os.link(cut, pub_cut)
            except OSError:
                shutil.copy2(cut, pub_cut)
    return dest


def _maybe_bake_zoom(edit_dir: Path, row: dict) -> None:
    if row.get("zoomBaked"):
        return
    ed_path = edit_dir / "remotion" / "public" / "edit-data.json"
    edl_path = edit_dir / "edl.json"
    if not ed_path.exists() or not edl_path.exists():
        return
    ed = json.loads(ed_path.read_text(encoding="utf-8-sig"))
    edl = json.loads(edl_path.read_text(encoding="utf-8-sig"))
    cam = ed.get("camera") if isinstance(ed.get("camera"), dict) else {}
    from app.ffmpeg_zoom import attach_to_edl, flatten_remotion_camera

    w = int(ed.get("width") or 1080)
    h = int(ed.get("height") or 1920)
    if not attach_to_edl(edl, cam, width=w, height=h):
        return
    src = row.get("source")
    if not src or not Path(src).exists():
        print("CANARY_ZOOM skip — fonte ausente, segue sem re-cut", flush=True)
        return
    edl_path.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")
    print("CANARY_ZOOM recut extract=on", flush=True)
    helper = REPO / "helpers" / "render.py"
    r = subprocess.run(
        [sys.executable, str(helper), str(edl_path), "-o", str(edit_dir / "cut.mp4"),
         "--no-subtitles", "--voice-master"],
        cwd=str(REPO),
        **_hide(),
    )
    if r.returncode != 0:
        print("CANARY_ZOOM recut failed — abort job", flush=True)
        raise RuntimeError("FFMPEG_ZOOM_RECUT_FAILED")
    flatten_remotion_camera(ed)
    ed_path.write_text(json.dumps(ed, indent=2, ensure_ascii=False), encoding="utf-8")
    pub_cut = edit_dir / "remotion" / "public" / "cut.mp4"
    cut = edit_dir / "cut.mp4"
    # O proprio harness cria pub_cut como HARDLINK do cut (linha ~309);
    # depois do recut in-place os dois nomes ainda sao o MESMO inode e o
    # copy2 levanta SameFileError, derrubando o job do canario.
    try:
        mesmo = pub_cut.exists() and os.path.samefile(cut, pub_cut)
    except OSError:
        mesmo = False
    if not mesmo:
        shutil.copy2(cut, pub_cut)


def _fallback_full(edit_dir: Path, remotion: Path, edit_data: dict) -> None:
    import run_fast as rf
    from remotion_gate import offthread_cache_bytes, remotion_concurrency, remotion_slot

    (remotion / "out").mkdir(exist_ok=True)
    conc = remotion_concurrency()
    cache_b = offthread_cache_bytes()
    extra_flags: list[str] = []
    try:
        from app.render_engine import remotion_flags
        extra_flags = remotion_flags()
        conc_flag = next((f for f in extra_flags if f.startswith("--concurrency=")), None)
        if conc_flag:
            extra_flags = [f for f in extra_flags if not f.startswith("--concurrency=")]
            conc = int(conc_flag.split("=", 1)[1])
    except Exception:
        extra_flags = []
    t0 = time.perf_counter()
    with remotion_slot():
        rend = rf._run_tool(
            rf._remotion_cmd(
                remotion, "render", "Reels", "out/render.mp4",
                f"--concurrency={conc}",
                f"--offthreadvideo-cache-size-in-bytes={cache_b}",
                *extra_flags,
            ),
            cwd=remotion,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            shell=False,
        )
    rf._timing_mark("REMOTION_RENDER", t0)
    if rend.returncode != 0:
        raise RuntimeError(
            f"remotion render failed:\n{(rend.stderr or '')[-2000:]}"
        )
    tl = timeline_from_edit_data(edit_data)
    t1 = time.perf_counter()
    rf.encode_final(
        edit_dir, True, tl["durationSec"],
        duration_in_frames=tl["durationInFrames"],
    )
    rf._timing_mark("FINAL_ENCODE", t1)


def run_full_baseline(edit_dir: Path, remotion: Path, edit_data: dict) -> dict:
    """FULL real, mesma fonte/cut, sem concorrer com OVERLAY. Não consome cota."""
    import run_fast as rf

    print("FULL_BASELINE_START", flush=True)
    saved_timing = dict(rf._TIMING)
    saved_meta = dict(rf._RENDER_META)
    rf._TIMING.clear()
    t0 = time.perf_counter()
    _fallback_full(edit_dir, remotion, edit_data)
    whole = round(time.perf_counter() - t0, 3)
    render_sec = rf._TIMING.get("REMOTION_RENDER")
    encode_sec = rf._TIMING.get("FINAL_ENCODE")
    final = edit_dir / "final.mp4"
    dest = edit_dir / "final_full.mp4"
    if final.exists():
        if dest.exists():
            dest.unlink()
        final.rename(dest)
    rf._TIMING.clear()
    rf._TIMING.update(saved_timing)
    rf._RENDER_META.clear()
    rf._RENDER_META.update(saved_meta)
    print(
        f"FULL_BASELINE_DONE whole={whole:.1f}s render={render_sec} encode={encode_sec}",
        flush=True,
    )
    return {
        "wholeJobSec": whole,
        "renderSec": render_sec,
        "encodeSec": encode_sec,
        "final": str(dest) if dest.exists() else None,
    }


def run_existing_job(row: dict) -> dict:
    import run_fast as rf
    from app.overlay_canary import (
        begin_overlay_attempt,
        close_canary_if_done,
        pause_canary,
        release_overlay_slot,
        try_acquire_overlay_slot,
    )
    from app.overlay_path import overlay_on, overlay_rollout, try_overlay_final

    dest = isolate_edit(row)
    t_cut = time.perf_counter()
    _maybe_bake_zoom(dest, row)
    cut_sec = round(time.perf_counter() - t_cut, 3)
    remotion = dest / "remotion"
    public = remotion / "public"
    ed = json.loads((public / "edit-data.json").read_text(encoding="utf-8-sig"))
    cut = dest / "cut.mp4"
    tl = timeline_from_edit_data(ed)
    duration = float(tl["durationSec"])
    fps = float(tl["fps"])

    cls = classify_render_path(ed, public=public, ffmpeg_zoom=True)
    if cls["path"] == "FULL" and cls.get("fullReasons"):
        print(f"OVERLAY_SKIP ineligible reasons={cls.get('fullReasons')}", flush=True)
        raise RuntimeError(f"CANARY_INELIGIBLE {cls.get('fullReasons')}")

    if not overlay_on():
        raise RuntimeError("CANARY_OFF overlay_on=false")

    full_base = None
    if row.get("wantFullBaseline"):
        try:
            full_base = run_full_baseline(dest, remotion, ed)
        except Exception as e:  # noqa: BLE001
            print(f"FULL_BASELINE_FAILED {e}", flush=True)
            full_base = None

    rf._TIMING.clear()
    rf._RENDER_META.clear()
    t_job = time.perf_counter()

    slot = try_acquire_overlay_slot()
    if slot is None:
        print("OVERLAY_SKIP slot busy — FULL", flush=True)
        raise RuntimeError("OVERLAY_SLOT_BUSY")

    print("OVERLAY_SLOT acquired", flush=True)
    if overlay_rollout() == "canary":
        begin_overlay_attempt()
    overlay_ok = False
    try:
        print(f"OVERLAY_PATH reasons={cls.get('overlayReasons')}", flush=True)
        t_ov = time.perf_counter()
        ov_result = try_overlay_final(
            edit_dir=dest,
            remotion=remotion,
            cut=cut,
            edit_data=ed,
            duration=duration,
            dest=dest / "final.mp4",
        )
        rf._timing_mark("REMOTION_RENDER", t_ov)
        bad = rf._canary_validate_overlay(dest / "final.mp4", ed, ov_result)
        if bad:
            raise RuntimeError(bad)
        rf._RENDER_META["renderPath"] = "OVERLAY"
        rf._RENDER_META["overlaySec"] = (ov_result or {}).get("remotionSec")
        rf._RENDER_META["composeSec"] = (ov_result or {}).get("composeSec")
        rf._RENDER_META["timeline"] = (ov_result or {}).get("timeline")
        rf._RENDER_META["tempPeakBytes"] = (ov_result or {}).get("tempPeakBytes")
        rf._RENDER_META["cutFrames"] = (ov_result or {}).get("cutFrames")
        rf._RENDER_META["overlayFrames"] = (ov_result or {}).get("overlayFrames")
        rf._RENDER_META["tempCleanupDone"] = (ov_result or {}).get("tempCleanupDone")
        overlay_ok = True
    except Exception as e:  # noqa: BLE001
        print(f"OVERLAY_FAILED {e}", flush=True)
        rf._RENDER_META["fallbackReasons"] = ["OVERLAY_FAILED", "FALLBACK_FULL_REMOTION"]
        print("FALLBACK_FULL_REMOTION", flush=True)
        pause_canary(str(e))
        _fallback_full(dest, remotion, ed)
    finally:
        release_overlay_slot(slot)
        print("OVERLAY_SLOT released", flush=True)
        close_canary_if_done()

    other = time.perf_counter() - t_job - sum(rf._TIMING.values())
    if other > 0.05:
        rf._TIMING["OTHER"] = round(other, 3)
    rf.write_timing(dest)

    os.environ.pop("ATIVAVID_CANARY_FULL_BASELINE_SEC", None)
    report = rf._canary_job_report(
        dest, duration=duration, fps=fps, final=dest / "final.mp4",
    )
    report["cutSec"] = cut_sec
    report["alphaValid"] = bool(overlay_ok and not report.get("fallbackUsed"))
    report["tempCleanupDone"] = report.get("TEMP_CLEANUP_DONE")
    report["overlayGainVsEstimatedFull"] = None
    if full_base and overlay_ok and full_base.get("wholeJobSec"):
        ov_parts = float(report.get("overlaySec") or 0) + float(report.get("composeSec") or 0)
        ov_whole = ov_parts if ov_parts > 0 else float(report.get("wholeJobSec") or 0)
        full_whole = float(full_base["wholeJobSec"])
        gain = round(full_whole - ov_whole, 3)
        pct = round(100.0 * gain / full_whole, 1) if full_whole else None
        report["fullBaseline"] = {
            "FULL_wholeJobSec": full_whole,
            "OVERLAY_wholeJobSec": ov_whole,
            "gainSec": gain,
            "gainPercent": pct,
        }
        print(
            f"BASELINE_GAIN full={full_whole:.1f}s overlay={ov_whole:.1f}s "
            f"gain={gain:.1f}s ({pct}%)",
            flush=True,
        )
    (dest / "canary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return report


def run_one(row: dict) -> dict:
    print(
        f"CANARY_RUN {row['slot']} {row['project']} dur={row['durationSec']:.1f}s "
        f"cuts={row['cuts']} 4k={row['is4k']} hdr={row['hdr']}"
        f"{' FULL_BASELINE' if row.get('wantFullBaseline') else ''}",
        flush=True,
    )
    # Garante que o filho/este processo lê settings, não o override de gate.
    os.environ.pop("ATIVAVID_OVERLAY", None)
    os.environ.pop("ATIVAVID_OVERLAY_ROLLOUT", None)
    os.environ.pop("ATIVAVID_FFMPEG_ZOOM", None)
    try:
        report = run_existing_job(row)
        report["exitCode"] = 0
    except Exception as e:  # noqa: BLE001
        print(f"CANARY_JOB_ERROR {e}", flush=True)
        report = {"error": str(e), "exitCode": 1}
    report["project"] = row["project"]
    report["slot"] = row["slot"]
    report["outDir"] = str(WORK / row["project"] / "edit")
    st = load_state()
    report["paused"] = bool(st.get("paused"))
    report["pausedReason"] = st.get("pausedReason")
    return report


def summarize(jobs: list[dict], limit: int) -> dict:
    overlay_jobs = [j for j in jobs if j.get("wholeJobSec") is not None]
    wholes = [float(j["wholeJobSec"]) for j in overlay_jobs]
    fallbacks = [j for j in jobs if j.get("fallbackUsed") or j.get("error")]
    errors = [j for j in jobs if j.get("error") or j.get("pausedReason")]
    frame_bad = [
        j for j in jobs
        if j.get("expectedFrames") and j.get("finalFrames")
        and j["expectedFrames"] != j["finalFrames"]
    ]
    audio_bad = [
        j for j in jobs
        if j.get("truePeak") is not None and float(j["truePeak"]) > -0.99
    ]
    alpha_bad = [
        j for j in jobs
        if j.get("alphaValid") is False
        or "ALPHA" in str(j.get("pausedReason") or "")
        or "ALPHA" in str(j.get("error") or "")
    ]
    temps = [int(j["tempPeakBytes"]) for j in jobs if j.get("tempPeakBytes")]
    encoders = sorted({str(j.get("encoder") or "") for j in jobs if j.get("encoder")})
    n4k = sum(1 for j in jobs if j.get("is4k"))
    nhdr = sum(1 for j in jobs if j.get("hdr"))
    durs = [float(j["durationSec"]) for j in jobs if j.get("durationSec") is not None]
    cuts = [int(j["cuts"]) for j in jobs if j.get("cuts") is not None]
    baselines = [j["fullBaseline"] for j in jobs if j.get("fullBaseline")]
    gains = [float(b["gainSec"]) for b in baselines if b.get("gainSec") is not None]
    return {
        "completed": f"{len(jobs)}/{limit}",
        "fallbacks": len(fallbacks),
        "errors": len(errors),
        "meanWholeJobSec": round(statistics.mean(wholes), 3) if wholes else None,
        "medianWholeJobSec": round(statistics.median(wholes), 3) if wholes else None,
        "minWholeJobSec": round(min(wholes), 3) if wholes else None,
        "maxWholeJobSec": round(max(wholes), 3) if wholes else None,
        "wrongFrames": len(frame_bad),
        "audioProblems": len(audio_bad),
        "alphaProblems": len(alpha_bad),
        "tempPeakBytes": max(temps) if temps else None,
        "count4k": n4k,
        "countHdr": nhdr,
        "durationSec": {
            "min": round(min(durs), 1) if durs else None,
            "max": round(max(durs), 1) if durs else None,
            "median": round(statistics.median(durs), 1) if durs else None,
        },
        "cuts": {
            "min": min(cuts) if cuts else None,
            "max": max(cuts) if cuts else None,
            "median": statistics.median(cuts) if cuts else None,
        },
        "encoder": encoders,
        "paused": any(j.get("paused") for j in jobs),
        "baselines": {
            "n": len(baselines),
            "jobs": baselines,
            "meanGainSec": round(statistics.mean(gains), 3) if gains else None,
            "medianGainSec": round(statistics.median(gains), 3) if gains else None,
            "totalSavedSec": round(sum(gains), 3) if gains else None,
        },
        "jobs": jobs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    limit = max(1, int(args.limit))
    rows = inventory()
    picked = pick_n(rows, limit)
    baseline_names = pick_baselines(picked, 5)
    print(json.dumps({
        "projectsRoot": str(_projects_root()),
        "eligible": len(rows),
        "limit": limit,
        "fullBaselines": baseline_names,
        "picked": [
            {
                "slot": r.get("slot"),
                "project": r["project"],
                "durationSec": r["durationSec"],
                "cuts": r["cuts"],
                "is4k": r["is4k"],
                "hdr": r["hdr"],
                "path": r["path"],
                "wantFullBaseline": r.get("wantFullBaseline"),
            }
            for r in picked
        ],
    }, indent=2, ensure_ascii=False), flush=True)
    if args.inventory or not args.run:
        return 0
    if len(picked) < 5:
        print(f"CANARY_ABORT só {len(picked)} elegíveis (mínimo 5)", flush=True)
        return 2
    if len(picked) < limit:
        print(
            f"CANARY_NOTE só {len(picked)} elegíveis no acervo "
            f"(pedido {limit}) — roda todos e o teto persiste {limit}",
            flush=True,
        )
    activate_canary(limit)
    jobs: list[dict] = []
    try:
        for row in picked:
            st = load_state()
            if st.get("paused") or load_settings().get("overlayRollout") != "canary":
                print("CANARY_STOP paused or off — não segue", flush=True)
                break
            report = run_one(row)
            report["is4k"] = row.get("is4k")
            report["hdr"] = row.get("hdr")
            report["durationSec"] = row.get("durationSec")
            report["cuts"] = row.get("cuts")
            jobs.append(report)
            if load_state().get("paused"):
                print("CANARY_STOP após pause", flush=True)
                break
        if jobs and not load_state().get("paused"):
            save_settings({"overlayRollout": "off"})
            print(
                f"CANARY_CLOSED attempts={load_state().get('canaryAttempt')} "
                f"ran={len(jobs)} limit={limit} overlayRollout=off",
                flush=True,
            )
        summary = summarize(jobs, limit)
        WORK.mkdir(parents=True, exist_ok=True)
        dest = WORK / "canary_summary.json"
        dest.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print("WROTE", dest, flush=True)
        print(json.dumps({k: v for k, v in summary.items() if k != "jobs"}, indent=2), flush=True)
        return 0
    finally:
        if load_settings().get("overlayRollout") == "canary":
            save_settings({"overlayRollout": "off"})
            print("CANARY_SAFETY overlayRollout=off", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
