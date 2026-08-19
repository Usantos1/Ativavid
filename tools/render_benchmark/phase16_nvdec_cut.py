# -*- coding: utf-8 -*-
"""EXPERIMENTO 7 — quanto vale ligar NVDEC no CORTE.

O corte a frio custou 336,5 s com CPU a 99,6% e GPU de decode em 0%.
Aqui o mesmo trabalho (mesmos 5 segmentos, mesma grade, mesmo zoom) e
medido em tres caminhos, para dar numero ao ganho recomendado.

Benchmark isolado: escreve so na area temporaria, nao toca o produto.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, Sampler, save  # noqa: E402

PROJ = Path(r"E:\ATIVAVID\Projetos\20260816-002530_IMG_3912_9d41f4134e")
EDL = PROJ / "edit" / "edl.json"
OUT = BENCH / "cutbench"
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

# grade "marca" = warm_cinematic; aproximacao do que o preset aplica
GRADE = "eq=contrast=1.06:saturation=1.08,colorbalance=rs=.02:bs=-.02"
ZOOM = "scale=1188:2112,crop=1080:1920"   # zoom ~1.10 baked, como o ffmpeg_zoom


def segments() -> tuple[Path, list[tuple[float, float]]]:
    e = json.loads(EDL.read_text(encoding="utf-8-sig"))
    src = None
    s = e.get("sources")
    if isinstance(s, dict):
        src = Path(next(iter(s.values()))["path"] if isinstance(next(iter(s.values())), dict)
                   else next(iter(s.values())))
    elif isinstance(s, list) and s:
        src = Path(s[0]["path"] if isinstance(s[0], dict) else s[0])
    if src is None or not src.exists():
        cand = [p for p in PROJ.glob("*.MOV")] + [p for p in PROJ.glob("*.mp4")
                                                 if p.name not in ("base.mp4",)]
        src = cand[0] if cand else None
    return src, [(float(r["start"]), float(r["end"])) for r in (e.get("ranges") or [])]


def run_cut(label: str, *, gpu_decode: bool, encoder: str, runs: int = 2) -> dict:
    src, rngs = segments()
    if src is None:
        print("fonte nao encontrada")
        return {}
    OUT.mkdir(parents=True, exist_ok=True)
    times: list[float] = []
    samp = Sampler(label)
    with samp:
        for _ in range(runs):
            t0 = time.perf_counter()
            partes = []
            for i, (a, b) in enumerate(rngs):
                out = OUT / f"seg_{i}.mp4"
                cmd = ["ffmpeg", "-v", "error", "-y"]
                if gpu_decode:
                    cmd += ["-hwaccel", "cuda"]
                cmd += ["-ss", f"{a:.6f}", "-to", f"{b:.6f}", "-i", str(src),
                        "-vf", f"{GRADE},{ZOOM}", "-c:v", encoder]
                cmd += (["-preset", "p4", "-cq", "20"] if "nvenc" in encoder
                        else ["-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"])
                cmd += ["-g", "30", "-keyint_min", "15", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", str(out)]
                r = subprocess.run(cmd, capture_output=True, text=True, **_NOWIN)
                if r.returncode:
                    print(f"  {label}: falhou no segmento {i}: {(r.stderr or '')[-150:]}")
                    return {}
                partes.append(out)
            lst = OUT / "list.txt"
            lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in partes), encoding="utf-8")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                            "-i", str(lst), "-c", "copy", str(OUT / f"cut_{label[:3]}.mp4")],
                           capture_output=True, **_NOWIN)
            times.append(time.perf_counter() - t0)
    med = statistics.median(times)
    st = samp.stats()
    print(f"  {label:38s} {med:6.1f}s  enc{st['gpu_enc_avg']:5.1f}% dec{st['gpu_dec_avg']:5.1f}% "
          f"cpu{st['cpu_avg']:5.1f}%")
    return {"caminho": label, "tempo_s": round(med, 1), "runs": len(times), **st}


if __name__ == "__main__":
    src, rngs = segments()
    dur = sum(b - a for a, b in rngs)
    print(f"corte de {len(rngs)} segmentos ({dur:.1f}s de video) — fonte: {src.name if src else '?'}\n")
    rows = [
        run_cut("CPU decode + libx264 (como hoje)", gpu_decode=False, encoder="libx264"),
        run_cut("CPU decode + h264_nvenc", gpu_decode=False, encoder="h264_nvenc"),
        run_cut("NVDEC + h264_nvenc", gpu_decode=True, encoder="h264_nvenc"),
    ]
    rows = [r for r in rows if r]
    if len(rows) >= 2:
        base = rows[0]["tempo_s"]
        for r in rows[1:]:
            print(f"  -> {r['caminho']}: {base / r['tempo_s']:.1f}x mais rapido")
            r["ganho_vs_hoje"] = round(base / r["tempo_s"], 2)
    save(rows, "phase16_nvdec_cut.csv")
