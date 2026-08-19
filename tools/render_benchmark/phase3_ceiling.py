# -*- coding: utf-8 -*-
"""FASE 3 — teto da maquina. Transcode puro do mesmo cut.mp4."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, CUT, run_test, save  # noqa: E402

FF = "ffmpeg"
BASE = [FF, "-v", "error", "-y"]
NUL = ["-f", "null", "-"]

TESTS = [
    ("A0 copia de fluxo",
     BASE + ["-i", str(CUT), "-c", "copy", str(BENCH / "out" / "a0.mp4")], "a0.mp4",
     "piso absoluto: so copia"),
    ("A3a decode CPU -> null",
     BASE + ["-i", str(CUT)] + NUL, None, "custo do decode isolado"),
    ("A3b decode NVDEC -> null",
     BASE + ["-hwaccel", "cuda", "-i", str(CUT)] + NUL, None, "NVDEC isolado"),
    ("A1 CPU decode -> h264_nvenc",
     BASE + ["-i", str(CUT), "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
             "-c:a", "copy", str(BENCH / "out" / "a1.mp4")], "a1.mp4", ""),
    ("A2 CPU decode -> hevc_nvenc",
     BASE + ["-i", str(CUT), "-c:v", "hevc_nvenc", "-preset", "p4", "-cq", "26",
             "-c:a", "copy", str(BENCH / "out" / "a2.mp4")], "a2.mp4", ""),
    ("A3c NVDEC->NVENC zero-copy",
     BASE + ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(CUT),
             "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
             "-c:a", "copy", str(BENCH / "out" / "a3c.mp4")], "a3c.mp4",
     "frame nunca sai da GPU"),
    ("A3c2 NVDEC->hevc_nvenc zero-copy",
     BASE + ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(CUT),
             "-c:v", "hevc_nvenc", "-preset", "p4", "-cq", "26",
             "-c:a", "copy", str(BENCH / "out" / "a3c2.mp4")], "a3c2.mp4", ""),
    ("A3d d3d11va -> h264_nvenc",
     BASE + ["-hwaccel", "d3d11va", "-i", str(CUT),
             "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
             "-c:a", "copy", str(BENCH / "out" / "a3d.mp4")], "a3d.mp4", ""),
    ("A4 CPU decode -> libx264 veryfast",
     BASE + ["-i", str(CUT), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "copy", str(BENCH / "out" / "a4.mp4")], "a4.mp4", "regua CPU"),
    ("A5 av1_nvenc (esperado falhar)",
     BASE + ["-i", str(CUT), "-c:v", "av1_nvenc", "-cq", "30",
             "-c:a", "copy", str(BENCH / "out" / "a5.mp4")], "a5.mp4",
     "Ampere nao codifica AV1 — confirmar"),
]

if __name__ == "__main__":
    print(f"FASE 3 — teto da maquina  ({CUT.name}, 28.37s, 851 frames, 1080x1920)\n")
    rows = [run_test(n, a, o, runs=3, note=note) for n, a, o, note in TESTS]
    save(rows, "phase3_ceiling.csv")
