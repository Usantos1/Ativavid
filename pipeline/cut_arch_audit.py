"""Benchmark de arquitetura do CUT — referência apenas.

Decisão (2026-08-15): SEEK_EXTRACT / CURRENT CPU é o baseline.
Não implementar Working Master, Single-pass nem NVDEC no CURRENT.
Não altera produção.
"""

    python pipeline/cut_arch_audit.py

Um único processo. Lock em E:\\Temp\\ativavid_cut_arch\\audit.lock.
JSON incremental em cut_arch_report.json após cada etapa.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "helpers")]

from app.ffmpeg_zoom import zoom_vf  # noqa: E402
from grade import get_preset  # noqa: E402
from render import (  # noqa: E402
    TONEMAP_CHAIN,
    extract_segment,
    jcut_settings,
    plan_jcut,
    pick_video_encoder,
    shortform_target_fps,
)

EDIT = Path(r"E:\ATIVAVID\Projetos\20260814-211649_cta_mais_feliz_x2_094e53317f\edit")
WORK = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_cut_arch"
LOCK = WORK / "audit.lock"
REPORT_PATH = WORK / "cut_arch_report.json"
HEAVY = "parte_1"
WORK_H = 2400  # 1350×2400 após autorotate 9:16
PUSH = 0.04
ZOOM_CYCLE = [1.14, 1.2, 1.12, 1.22, 1.16, 1.1, 1.18]


def prod_jobs() -> int:
    """Mesmo teto do render.py (J-cut)."""
    return max(1, min(4, (os.cpu_count() or 4) // 3))


def acquire_lock() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        raw = LOCK.read_text(encoding="utf-8").strip()
        try:
            pid = int(raw.split()[0])
        except ValueError:
            pid = -1
        alive = False
        if pid > 0:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        if alive:
            raise SystemExit(f"outro cut_arch_audit rodando pid={pid} — abortando")
    LOCK.write_text(f"{os.getpid()}\n", encoding="utf-8")


def release_lock() -> None:
    try:
        if LOCK.exists() and LOCK.read_text(encoding="utf-8").strip().startswith(str(os.getpid())):
            LOCK.unlink()
    except OSError:
        pass


def fresh_dir(tag: str) -> Path:
    d = WORK / tag
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def save_report(report: dict) -> None:
    payload = json.loads(json.dumps(report, default=str))
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  saved", REPORT_PATH, flush=True)


class Sampler:
    def __init__(self) -> None:
        self.dec: list[float] = []
        self.enc: list[float] = []
        self.gpu: list[float] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(0.8):
                try:
                    r = subprocess.run(
                        ["nvidia-smi",
                         "--query-gpu=utilization.gpu,utilization.decoder,utilization.encoder",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=3,
                    )
                    p = [x.strip() for x in (r.stdout or "").split(",")]
                    if len(p) >= 3:
                        self.gpu.append(float(p[0]))
                        self.dec.append(float(p[1]))
                        self.enc.append(float(p[2]))
                except Exception:
                    pass
        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()

    def stop(self) -> dict:
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)

        def agg(xs: list[float]) -> dict:
            if not xs:
                return {"avg": None, "peak": None}
            return {"avg": round(sum(xs) / len(xs), 1), "peak": round(max(xs), 1)}

        return {"gpu": agg(self.gpu), "nvdec": agg(self.dec), "nvenc": agg(self.enc)}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _probe(path: Path) -> dict:
    r = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,r_frame_rate,width,height:format=duration,size",
        "-of", "json", str(path),
    ])
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    st = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    fps_s = str(st.get("r_frame_rate") or "0/1")
    n, _, d = fps_s.partition("/")
    try:
        frames = int(st["nb_frames"]) if st.get("nb_frames") not in (None, "N/A") else None
    except (TypeError, ValueError):
        frames = None
    return {
        "duration": float(fmt.get("duration") or 0),
        "frames": frames,
        "width": int(st.get("width") or 0),
        "height": int(st.get("height") or 0),
        "fps": round(float(n) / float(d or 1), 3),
        "bytes": int(fmt.get("size") or (path.stat().st_size if path.exists() else 0)),
    }


def _nvenc(gop: int = 15) -> list[str]:
    return [
        "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21",
        "-b:v", "0", "-pix_fmt", "yuv420p", "-g", str(gop), "-keyint_min", str(gop),
    ]


def shared_vf(*, height: int) -> str:
    grade = get_preset("marca")
    return f"scale=-2:{height},{TONEMAP_CHAIN},format=yuv420p,{grade}"


def zoom_for(i: int, dur: float) -> str:
    n = max(1, int(round(dur * 30)))
    return zoom_vf(
        {"base": ZOOM_CYCLE[i % len(ZOOM_CYCLE)], "push": PUSH,
         "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920},
        n_frames=n, fps=30.0,
    )


def timed(name: str, fn):
    print("RUN", name, flush=True)
    samp = Sampler()
    samp.start()
    t0 = time.perf_counter()
    try:
        result = fn()
        ok = True
        err = None
    except Exception as e:  # noqa: BLE001
        result = None
        ok = False
        err = str(e)[-800:]
        print("  FAIL", name, err, flush=True)
    dt = time.perf_counter() - t0
    res = samp.stop()
    print(f"  {name} {dt:.1f}s ok={ok}", flush=True)
    row = {"name": name, "sec": round(dt, 3), "ok": ok, "error": err,
           "resources": res}
    if isinstance(result, dict):
        row.update({k: v for k, v in result.items() if k != "cmd"})
    return row


def audio_evidence(plan: list[dict]) -> dict:
    """Um extract de áudio com log verbose + tempo de todos os 29."""
    p0 = next(p for p in plan if p["src"].name.lower().endswith(".mov"))
    out = WORK / "audio_evidence.wav"
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-v", "verbose",
        "-ss", f"{p0['a_in']:.6f}", "-i", str(p0["src"]),
        "-t", f"{p0['a_out'] - p0['a_in']:.6f}",
        "-vn",
        "-af", "afade=t=in:st=0:d=0.03,afade=t=out:st=0.1:d=0.03",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
        str(out),
    ]
    r = _run(cmd)
    log = (r.stderr or "")
    mapping = ""
    m = re.search(r"Stream mapping:[\s\S]*?(?:\n\n|\nOutput |\Z)", log)
    if m:
        mapping = m.group(0)
    hevc_decoder_init = bool(re.search(
        r"(Opening decoder hevc|decoder -> hevc|hevc \(native\)|Matched decoder.+hevc)",
        log, re.I,
    ))
    video_in_mapping = bool(re.search(r"Stream mapping:[\s\S]*?Video", log))
    audio_only_mapping = bool(re.search(r"Stream #0:\d+ -> #0:0 \(.*Audio", mapping))
    dec_lines = [ln for ln in log.splitlines()
                 if re.search(r"decoder|hevc|Stream mapping|Video:|Audio:|Stream #", ln, re.I)]
    adir = fresh_dir("audio")

    def one(p: dict) -> float:
        dest = adir / f"a_{p['i']:02d}.wav"
        t0 = time.perf_counter()
        extract_segment(
            p["src"], p["a_in"], p["a_out"] - p["a_in"], "", dest, streams="a",
        )
        return time.perf_counter() - t0

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=prod_jobs()) as ex:
        secs = list(ex.map(one, plan))
    total = time.perf_counter() - t0
    heavy = [s for p, s in zip(plan, secs) if p["range"]["source"] == HEAVY]
    return {
        "command": cmd,
        "vn": "-vn" in cmd,
        "hevcDecoderInit": hevc_decoder_init,
        "videoStreamMapped": video_in_mapping,
        "audioOnlyMapping": audio_only_mapping,
        "streamMapping": mapping.strip()[:800],
        "decoderLogHits": dec_lines[-50:],
        "exit": r.returncode,
        "nAudioExtracts": len(plan),
        "audioWallSec": round(total, 3),
        "audioSumSec": round(sum(secs), 3),
        "audioHeavySumSec": round(sum(heavy), 3),
        "audioMaxSec": round(max(secs), 3),
        "audioMinSec": round(min(secs), 3),
        "jobs": prod_jobs(),
        "note": (
            "Comando real usa -vn. hevcDecoderInit=true só se o log instanciou "
            "decoder HEVC. videoStreamMapped=false + audioOnlyMapping=true "
            "indica demux/seek de áudio, sem decode do 4K."
        ),
    }


def current_video(plan: list[dict], *, cuda: bool) -> dict:
    """N extracts de vídeo como hoje (zoom no extract), jobs da produção."""
    vdir = fresh_dir("current_cuda" if cuda else "current_cpu")
    jobs = prod_jobs()

    def one(p: dict) -> Path:
        dest = vdir / f"v_{p['i']:02d}.mp4"
        i = p["i"]
        dur = p["v_out"] - p["v_in"]
        if cuda:
            vf = shared_vf(height=1920) + "," + zoom_for(i, dur)
            cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats"]
            cmd += ["-hwaccel", "cuda"]
            cmd += ["-ss", f"{p['v_in']:.6f}", "-i", str(p["src"]),
                    "-t", f"{dur:.6f}", "-an", "-vf", vf, "-r", "30",
                    *_nvenc(30), str(dest)]
            r = _run(cmd)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-600:])
        else:
            extract_segment(
                p["src"], p["v_in"], dur, get_preset("marca"), dest,
                streams="v",
                zoom={"base": ZOOM_CYCLE[i % len(ZOOM_CYCLE)], "push": PUSH,
                      "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920},
            )
        return dest

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        paths = list(ex.map(one, plan))
    dt = time.perf_counter() - t0
    concat = vdir / "cut.mp4"
    _concat(paths, concat)
    heavy_opens = sum(1 for p in plan if p["range"]["source"] == HEAVY)
    return {
        "cutSec": round(dt, 3),
        "preprocessSec": 0,
        "opens": len(plan),
        "opensHeavySource": heavy_opens,
        "hevcDecodes": heavy_opens,
        "jobs": jobs,
        "cuda": cuda,
        "out": str(concat),
        "probe": _probe(concat),
        "clipBytes": sum(p.stat().st_size for p in paths if p.exists()),
    }


def _concat(paths: list[Path], dest: Path) -> None:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in paths), encoding="utf-8")
    r = _run(["ffmpeg", "-y", "-nostdin", "-hide_banner", "-f", "concat", "-safe", "0",
              "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(dest)])
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])


def working_master(plan: list[dict], src: Path, *, cuda: bool, gop: int) -> dict:
    tag = f"wm_{'cuda' if cuda else 'cpu'}_g{gop}"
    wdir = fresh_dir(tag)
    master = wdir / "working_master.mp4"
    vf = shared_vf(height=WORK_H)
    cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats"]
    if cuda:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", str(src), "-an", "-vf", vf, "-r", "30", *_nvenc(gop),
            "-movflags", "+faststart", str(master)]
    t0 = time.perf_counter()
    r = _run(cmd)
    pre = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    heavy = [p for p in plan if p["range"]["source"] == HEAVY]
    light = [p for p in plan if p["range"]["source"] != HEAVY]

    def cut_from_master(p: dict) -> Path:
        dest = wdir / f"v_{p['i']:02d}.mp4"
        dur = p["v_out"] - p["v_in"]
        z = zoom_for(p["i"], dur)
        c = [
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats",
            "-ss", f"{p['v_in']:.6f}", "-i", str(master),
            "-t", f"{dur:.6f}", "-an", "-vf", z, "-r", "30",
            *_nvenc(30), str(dest),
        ]
        rr = _run(c)
        if rr.returncode != 0:
            raise RuntimeError(rr.stderr[-500:])
        return dest

    def cut_light(p: dict) -> Path:
        dest = wdir / f"v_{p['i']:02d}.mp4"
        dur = p["v_out"] - p["v_in"]
        extract_segment(
            p["src"], p["v_in"], dur, get_preset("marca"), dest, streams="v",
            zoom={"base": ZOOM_CYCLE[p["i"] % 7], "push": PUSH,
                  "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920},
        )
        return dest

    t1 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=prod_jobs()) as ex:
        hpaths = list(ex.map(cut_from_master, heavy))
        lpaths = list(ex.map(cut_light, light))
    cut_sec = time.perf_counter() - t1
    by_i = {p["i"]: path for p, path in list(zip(heavy, hpaths)) + list(zip(light, lpaths))}
    ordered = [by_i[p["i"]] for p in plan]
    concat = wdir / "cut.mp4"
    _concat(ordered, concat)
    return {
        "preprocessSec": round(pre, 3),
        "cutSec": round(cut_sec, 3),
        "master": _probe(master),
        "masterPath": str(master),
        "out": str(concat),
        "probe": _probe(concat),
        "opensHeavySource": 1,
        "hevcDecodes": 1,
        "gop": gop,
        "cuda": cuda,
        "workingRes": [1350, WORK_H],
    }


def _piecewise_zoom(heavy: list[dict]) -> str:
    """Zoom que reinicia em cada segmento, no tempo de saída (após setpts)."""
    acc = 0.0
    layers: list[tuple[float, str]] = []
    for p in heavy:
        dur = p["v_out"] - p["v_in"]
        n = max(1, int(round(dur * 30)))
        denom = max(1, n - 1)
        base = ZOOM_CYCLE[p["i"] % len(ZOOM_CYCLE)]
        t0 = acc
        local = f"(t-{t0:.6f})"
        s = f"({base:.6f}+{PUSH:.6f}*min(1\\,{local}*30/{denom}))"
        acc += dur
        layers.append((acc, s))
    expr = layers[-1][1]
    for t1, s in reversed(layers[:-1]):
        expr = f"if(lt(t\\,{t1:.6f})\\,{s}\\,{expr})"
    return (
        f"scale=w='trunc(iw*({expr})/2)*2':h='trunc(ih*({expr})/2)*2':"
        f"eval=frame:flags=lanczos,"
        f"crop=1080:1920:"
        f"x='trunc((iw-1080)*0.500000/2)*2+0*t':"
        f"y='trunc((ih-1920)*0.400000/2)*2+0*t',"
        f"setsar=1"
    )


def single_pass(plan: list[dict], src: Path, *, cuda: bool) -> dict:
    """Um decode da fonte pesada. select das faixas + zoom por segmento.

    Evita split=N (27 cópias de cada frame em RAM). Assume que os segmentos
    pesados estão em ordem cronológica da fonte — verdadeiro neste EDL.
    """
    tag = f"sp_{'cuda' if cuda else 'cpu'}"
    wdir = fresh_dir(tag)
    heavy = [p for p in plan if p["range"]["source"] == HEAVY]
    starts = [p["v_in"] for p in heavy]
    if starts != sorted(starts):
        raise RuntimeError("SINGLE_PASS select exige segmentos pesados em ordem de fonte")
    pre = shared_vf(height=WORK_H)
    sel = "+".join(f"between(t,{p['v_in']:.6f},{p['v_out']:.6f})" for p in heavy)
    zoom = _piecewise_zoom(heavy)
    fc = f"[0:v]{pre},select='{sel}',setpts=N/30/TB,{zoom}[vout]"
    heavy_out = wdir / "heavy.mp4"
    cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats"]
    if cuda:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", str(src), "-filter_complex", fc, "-map", "[vout]",
            "-an", "-r", "30", *_nvenc(30), str(heavy_out)]
    t0 = time.perf_counter()
    r = _run(cmd)
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-1200:])
    light = [p for p in plan if p["range"]["source"] != HEAVY]
    lpaths = []
    for p in light:
        dest = wdir / f"v_{p['i']:02d}.mp4"
        extract_segment(
            p["src"], p["v_in"], p["v_out"] - p["v_in"], get_preset("marca"),
            dest, streams="v",
            zoom={"base": ZOOM_CYCLE[p["i"] % 7], "push": PUSH,
                  "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920},
        )
        lpaths.append((p["i"], dest))
    by_i = {i: path for i, path in lpaths}
    ordered_light = [by_i[p["i"]] for p in plan if p["i"] in by_i]
    concat = wdir / "cut.mp4"
    _concat(ordered_light + [heavy_out], concat)
    return {
        "preprocessSec": 0,
        "cutSec": round(dt, 3),
        "out": str(concat),
        "probe": _probe(concat),
        "heavyProbe": _probe(heavy_out),
        "opensHeavySource": 1,
        "hevcDecodes": 1,
        "cuda": cuda,
        "filterComplexChars": len(fc),
        "method": "select+setpts+piecewise_zoom (sem split=N)",
    }


def grab_frames(video: Path, dest: Path, spots: list[tuple[str, float]]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name, t in spots:
        _run([
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
            str(dest / f"{name}.png"),
        ])


def main() -> int:
    acquire_lock()
    try:
        return _main()
    finally:
        release_lock()


def _main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    edl = json.loads((EDIT / "edl.json").read_text(encoding="utf-8-sig"))
    fps = int(shortform_target_fps(Path(edl["sources"][HEAVY])))
    cfg = jcut_settings(edl, fps)
    plan = plan_jcut(edl, EDIT, cfg)
    src_heavy = Path(edl["sources"][HEAVY])
    heavy_n = sum(1 for p in plan if p["range"]["source"] == HEAVY)
    used = sum(p["v_out"] - p["v_in"] for p in plan if p["range"]["source"] == HEAVY)
    src_dur = 93.308
    coverage = used / src_dur
    src_bytes = src_heavy.stat().st_size if src_heavy.exists() else 0

    report: dict = {
        "project": EDIT.parent.name,
        "nRanges": len(plan),
        "heavyRanges": heavy_n,
        "heavyUsedSec": round(used, 3),
        "heavySourceSec": src_dur,
        "coverage": round(coverage, 3),
        "workingRes": [1350, WORK_H],
        "prodJobs": prod_jobs(),
        "encoder": pick_video_encoder()[0],
        "heavySourceBytes": src_bytes,
        "note": (
            "Run isolado com lock. CURRENT usa os mesmos jobs do render.py. "
            "SINGLE_PASS usa select+setpts, não split=N. Produção intocada."
        ),
    }
    if REPORT_PATH.exists():
        try:
            prev = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            for k, v in prev.items():
                if k not in report:
                    report[k] = v
        except (OSError, json.JSONDecodeError):
            pass
    save_report(report)

    if isinstance(report.get("audio"), dict) and report["audio"].get("vn") is not None:
        print("SKIP AUDIO EVIDENCE", flush=True)
    else:
        print("AUDIO EVIDENCE", flush=True)
        report["audio"] = audio_evidence(plan)
        save_report(report)

    stages = (
        ("CURRENT_cpu", lambda: current_video(plan, cuda=False)),
        ("CURRENT_cuda", lambda: current_video(plan, cuda=True)),
        ("WM_cpu_g15", lambda: working_master(plan, src_heavy, cuda=False, gop=15)),
        ("WM_cuda_g15", lambda: working_master(plan, src_heavy, cuda=True, gop=15)),
        ("WM_cuda_g30", lambda: working_master(plan, src_heavy, cuda=True, gop=30)),
        ("SP_cpu", lambda: single_pass(plan, src_heavy, cuda=False)),
        ("SP_cuda", lambda: single_pass(plan, src_heavy, cuda=True)),
    )
    for name, fn in stages:
        prev_row = report.get(name)
        if isinstance(prev_row, dict) and prev_row.get("ok"):
            print(f"SKIP {name} (já ok={prev_row.get('sec')}s)", flush=True)
            continue
        report[name] = timed(name, fn)
        save_report(report)

    spots = [
        ("start", 0.4),
        ("first_heavy_cut", 3.2),
        ("push_mid", 20.0),
        ("hard_cut", 40.0),
        ("hdr_sky", 55.0),
        ("endcard", 76.5),
    ]
    for key in ("CURRENT_cpu", "WM_cuda_g15", "SP_cuda"):
        row = report.get(key) or {}
        out = row.get("out")
        if out and Path(out).exists() and row.get("ok"):
            grab_frames(Path(out), WORK / "frames" / key, spots)
    report["framesDir"] = str(WORK / "frames")
    save_report(report)
    print("WROTE", REPORT_PATH, flush=True)
    summary = {}
    for k, v in report.items():
        if not isinstance(v, dict):
            summary[k] = v
            continue
        summary[k] = {kk: vv for kk, vv in v.items()
                      if kk not in ("decoderLogHits", "error", "command")}
    print(json.dumps(summary, indent=2, default=str)[:5000], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
