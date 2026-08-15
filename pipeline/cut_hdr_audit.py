"""Auditoria quantitativa do CUT HDR/4K — não altera o pipeline.

Uso:
    python pipeline/cut_hdr_audit.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "helpers") not in sys.path:
    sys.path.insert(0, str(REPO / "helpers"))

SRC = Path(r"E:\ATIVAVID\Projetos\20260814-211649_cta_mais_feliz_x2_094e53317f\parte_1.MOV")
SS = 23.53
DUR = 8.0
WORK = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_cut_audit"

TONEMAP = (
    "zscale=t=linear:npl=100,"
    "format=gbrpf32le,"
    "zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,"
    "format=yuv420p"
)
GRADE = (
    "eq=contrast=1.14:saturation=1.18:gamma=0.96:brightness=0.012,"
    "colorbalance=rs=0.025:rm=0.02:rh=0.012:bs=-0.02:bm=-0.012:bh=-0.008,"
    "hue=h=-3"
)
SCALE = "scale=-2:1920"


def _hide() -> dict:
    try:
        from app.win_process import hide_console_kwargs
        return hide_console_kwargs()
    except Exception:
        return {}


def _nvenc() -> list[str]:
    return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23",
            "-b:v", "0", "-pix_fmt", "yuv420p", "-g", "30"]


class Sampler:
    def __init__(self) -> None:
        self.cpu: list[float] = []
        self.ram: list[float] = []
        self.gpu: list[float] = []
        self.dec: list[float] = []
        self.enc: list[float] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self) -> None:
        try:
            import psutil
        except Exception:
            psutil = None  # type: ignore
        if psutil:
            psutil.cpu_percent(interval=None)

        def loop() -> None:
            while not self._stop.wait(0.8):
                if psutil:
                    try:
                        self.cpu.append(psutil.cpu_percent(interval=None))
                        self.ram.append(psutil.virtual_memory().used / (1024 * 1024))
                    except Exception:
                        pass
                try:
                    r = subprocess.run(
                        ["nvidia-smi",
                         "--query-gpu=utilization.gpu,utilization.decoder,utilization.encoder,memory.used",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=3, **_hide(),
                    )
                    parts = [p.strip() for p in (r.stdout or "").split(",")]
                    if len(parts) >= 4:
                        self.gpu.append(float(parts[0]))
                        self.dec.append(float(parts[1]))
                        self.enc.append(float(parts[2]))
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

        return {
            "cpu": agg(self.cpu),
            "ramMb": agg(self.ram),
            "gpuCompute": agg(self.gpu),
            "gpuDecode": agg(self.dec),
            "gpuEncode": agg(self.enc),
        }


def run_cmd(name: str, cmd: list[str], *, out: Path | None = None) -> dict:
    print("RUN", name, flush=True)
    samp = Sampler()
    samp.start()
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", **_hide())
    dt = time.perf_counter() - t0
    res = samp.stop()
    err = (r.stderr or "")[-2500:]
    ok = r.returncode == 0
    frames = DUR * 30.0
    row = {
        "name": name,
        "ok": ok,
        "sec": round(dt, 3),
        "fps": round(frames / dt, 2) if dt else None,
        "realtime": round(DUR / dt, 3) if dt else None,
        "exit": r.returncode,
        "resources": res,
        "errorTail": None if ok else err[-800:],
        "outBytes": out.stat().st_size if out and out.exists() else 0,
    }
    print(f"  {name} {dt:.2f}s  {row['realtime']}x  ok={ok}", flush=True)
    if not ok:
        print(err[-400:], flush=True)
    return row


def ff_base() -> list[str]:
    return ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats",
            "-ss", f"{SS:.3f}", "-i", str(SRC), "-t", f"{DUR:.3f}", "-an"]


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    from app.ffmpeg_zoom import zoom_vf

    zoom_static = zoom_vf(
        {"base": 1.22, "push": 0.0, "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920},
        n_frames=int(DUR * 30), fps=30.0,
    )
    zoom_push = zoom_vf(
        {"base": 1.14, "push": 0.04, "cx": 0.5, "cy": 0.4, "outW": 1080, "outH": 1920},
        n_frames=int(DUR * 30), fps=30.0,
    )
    full = f"{SCALE},{TONEMAP},format=yuv420p,{GRADE},{zoom_push}"

    rows: list[dict] = []

    # --- decode only (null) ---
    rows.append(run_cmd("DEC_CPU_null", [
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats",
        "-ss", f"{SS:.3f}", "-i", str(SRC), "-t", f"{DUR:.3f}",
        "-an", "-f", "null", "-",
    ]))
    for acc, name in (("cuda", "DEC_CUDA_null"), ("d3d11va", "DEC_D3D11_null"),
                      ("qsv", "DEC_QSV_null"), ("dxva2", "DEC_DXVA2_null")):
        rows.append(run_cmd(name, [
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-nostats",
            "-hwaccel", acc,
            "-ss", f"{SS:.3f}", "-i", str(SRC), "-t", f"{DUR:.3f}",
            "-an", "-f", "null", "-",
        ]))

    # --- A–G encode path (NVENC constante) ---
    tests = [
        ("A_cut_encode", None),
        ("B_scale_1080x1920", SCALE),
        ("C_scale_tonemap", f"{SCALE},{TONEMAP}"),
        ("C2_tonemap_at_4K_then_scale", f"{TONEMAP},{SCALE}"),
        ("D_scale_tonemap_grade", f"{SCALE},{TONEMAP},format=yuv420p,{GRADE}"),
        ("E_zoomCuts_static", f"{SCALE},{TONEMAP},format=yuv420p,{GRADE},{zoom_static}"),
        ("F_pushIn", f"{SCALE},{TONEMAP},format=yuv420p,{GRADE},{zoom_push}"),
        ("G_full_current", full),
    ]
    for name, vf in tests:
        out = WORK / f"{name}.mp4"
        cmd = ff_base()
        if vf:
            cmd += ["-vf", vf]
        cmd += ["-r", "30", *_nvenc(), "-movflags", "+faststart", str(out)]
        rows.append(run_cmd(name, cmd, out=out))

    # --- alternativas de tonemap (só timing, não produção) ---
    alts = [
        ("ALT_tonemap_opencl",
         f"{SCALE},format=p010,hwupload,tonemap_opencl=tonemap=hable:desat=0:format=nv12,hwdownload,format=nv12"),
        ("ALT_libplacebo_tonemap",
         f"{SCALE},libplacebo=w=1080:h=1920:tonemapping=hable:colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv,format=yuv420p"),
        ("ALT_zscale_only_no_hable",
         f"{SCALE},zscale=t=bt709:m=bt709:p=bt709:r=tv,format=yuv420p"),
    ]
    for name, vf in alts:
        out = WORK / f"{name}.mp4"
        cmd = ff_base() + ["-vf", vf, "-r", "30", *_nvenc(), str(out)]
        rows.append(run_cmd(name, cmd, out=out))

    # decode+scale null (sem encode) para isolar encode
    rows.append(run_cmd("B2_scale_null", ff_base() + ["-vf", SCALE, "-f", "null", "-"]))
    rows.append(run_cmd("C3_scale_tonemap_null", ff_base() + ["-vf", f"{SCALE},{TONEMAP}", "-f", "null", "-"]))

    src_info = {
        "path": str(SRC),
        "ss": SS,
        "durationSec": DUR,
        "codec": "hevc Main 10",
        "stored": "3840x2160",
        "afterRotate": "2160x3840",
        "afterScale": "1080x1920",
        "pix_fmt": "yuv420p10le",
        "transfer": "arib-std-b67 (HLG)",
        "primaries": "bt2020",
        "dolbyVisionRPU": True,
        "fps": 30,
        "project": "20260814-211649_cta_mais_feliz_x2_094e53317f (CUT ~25 min / 79 s)",
    }
    max_z = 1.22
    work_w = int((1080 * max_z + 1) // 2 * 2)
    work_h = int((1920 * max_z + 1) // 2 * 2)
    analysis = {
        "currentFilterOrder": [
            "decode 4K HEVC 10-bit HLG + Dolby Vision RPU (hoje: CPU software)",
            "autorotate → 2160x3840",
            "scale=-2:1920 → 1080x1920  (já reduz ANTES do tonemap)",
            "TONEMAP_CHAIN zscale linear + gbrpf32le + hable + zscale bt709 (CPU)",
            "format=yuv420p + grade marca",
            "zoom scale eval=frame UP * S + crop 1080x1920",
            "NVENC encode",
        ],
        "pixels": {
            "native4K": 2160 * 3840,
            "output1080": 1080 * 1920,
            "workingForZoom1_22": work_w * work_h,
            "workingWh": [work_w, work_h],
            "note": (
                "Hoje o scale vai a 1080x1920 e o zoom AMPLIA de novo. "
                f"Working segura para zoom {max_z}: {work_w}x{work_h} "
                "(pixels extras para o crop, ~1.5x o 1080p, ~0.37x o 4K)."
            ),
        },
        "tonemapCurrent": TONEMAP,
        "tonemapAlternatives": [
            "tonemap_opencl (GPU) — mesmo hable",
            "libplacebo (Vulkan/GPU) — hable",
            "zscale direto HLG→709 sem hable (mais barato, look diferente)",
            "npl=203 (BT.2408) vs npl=100 atual",
        ],
    }
    report = {"source": src_info, "tests": rows, "analysis": analysis}
    dest = WORK / "cut_hdr_audit.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("WROTE", dest, flush=True)
    for row in rows:
        print(f"{row['name']:28} ok={row['ok']} {row['sec']:8.2f}s  "
              f"{row.get('realtime')}x  cpu={row['resources']['cpu']} "
              f"dec={row['resources']['gpuDecode']} enc={row['resources']['gpuEncode']}",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
