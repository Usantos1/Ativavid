# -*- coding: utf-8 -*-
"""Medicao isolada de render/export. NAO toca no pipeline de producao.

Roda cada teste N vezes e reporta mediana. Amostra GPU (nvidia-smi dmon)
e CPU (typeperf) durante a execucao, sem instalar nada.
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import subprocess
import threading
import time
from pathlib import Path

BENCH = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad\bench")
RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
CUT = BENCH / "cut.mp4"
DUR = 28.366667
FRAMES = 851

_NOWIN = {}
if hasattr(subprocess, "CREATE_NO_WINDOW"):
    _NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}


class Sampler:
    """GPU (sm/enc/dec/fb) + CPU total, 1 amostra/s, custo desprezivel."""

    def __init__(self, tag: str):
        self.tag = tag
        self.gpu: list[tuple[int, int, int, int]] = []
        self.cpu: list[float] = []
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def _loop(self) -> None:
        p = subprocess.Popen(
            ["nvidia-smi", "dmon", "-s", "um", "-d", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, **_NOWIN,
        )
        try:
            for line in p.stdout:  # type: ignore[union-attr]
                if self._stop.is_set():
                    break
                if line.lstrip().startswith("#"):
                    continue
                f = line.split()
                if len(f) >= 8 and f[1].lstrip("-").isdigit():
                    try:
                        self.gpu.append((int(f[1]), int(f[3]), int(f[4]), int(f[7])))
                    except ValueError:
                        pass
        finally:
            try:
                p.kill()
            except Exception:
                pass

    @staticmethod
    def _cpu_times():
        """GetSystemTimes: instantaneo e exato. O caminho via WMI custava
        mais de 1s por amostra e devolvia vazio durante os testes."""
        import ctypes
        from ctypes import wintypes

        idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
        j = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
        return j(idle), j(kern) + j(user)

    def _cpu_loop(self) -> None:
        prev_i, prev_t = self._cpu_times()
        while not self._stop.is_set():
            self._stop.wait(1.0)
            try:
                i, t = self._cpu_times()
                di, dt = i - prev_i, t - prev_t
                prev_i, prev_t = i, t
                if dt > 0:
                    self.cpu.append(round(100.0 * (1.0 - di / dt), 1))
            except Exception:
                pass

    def __enter__(self):
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        self._c = threading.Thread(target=self._cpu_loop, daemon=True)
        self._c.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        return False

    def stats(self) -> dict:
        def agg(vals, f):
            return round(f(vals), 1) if vals else 0.0
        sm = [g[0] for g in self.gpu]
        enc = [g[1] for g in self.gpu]
        dec = [g[2] for g in self.gpu]
        fb = [g[3] for g in self.gpu]
        return {
            "gpu_sm_avg": agg(sm, statistics.mean), "gpu_sm_max": agg(sm, max),
            "gpu_enc_avg": agg(enc, statistics.mean), "gpu_enc_max": agg(enc, max),
            "gpu_dec_avg": agg(dec, statistics.mean), "gpu_dec_max": agg(dec, max),
            "vram_max_mb": agg(fb, max),
            "cpu_avg": agg(self.cpu, statistics.mean), "cpu_max": agg(self.cpu, max),
            "samples": len(self.gpu),
        }


def probe(path: Path) -> dict:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,bit_rate",
             "-show_entries", "format=duration,size,bit_rate",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, **_NOWIN,
        )
        d = json.loads(r.stdout or "{}")
        fmt = d.get("format") or {}
        st = (d.get("streams") or [{}])[0]
        return {
            "codec": st.get("codec_name", ""),
            "size_mb": round(int(fmt.get("size") or 0) / 1048576, 1),
            "bitrate_mbps": round(int(fmt.get("bit_rate") or 0) / 1e6, 2),
        }
    except Exception:
        return {"codec": "", "size_mb": 0, "bitrate_mbps": 0}


def run_test(name: str, args: list[str], out: str | None, *, runs: int = 3,
             note: str = "", dur: float = DUR, frames: int = FRAMES) -> dict:
    """Executa `runs` vezes, guarda mediana. args = argv completo do ffmpeg."""
    times: list[float] = []
    err = ""
    outp = (BENCH / "out" / out) if out else None
    samp = Sampler(name)
    with samp:
        for i in range(runs):
            if outp and outp.exists():
                outp.unlink()
            t0 = time.perf_counter()
            r = subprocess.run(args, capture_output=True, text=True, **_NOWIN)
            el = time.perf_counter() - t0
            if r.returncode != 0:
                err = (r.stderr or "")[-220:].replace("\n", " ")
                break
            times.append(el)
    if not times:
        row = {"teste": name, "ok": False, "erro": err, "nota": note}
        print(f"  {name:34s} FALHOU  {err[:90]}")
        return row
    med = statistics.median(times)
    info = probe(outp) if (outp and outp.exists()) else {"codec": "", "size_mb": 0, "bitrate_mbps": 0}
    row = {
        "teste": name, "ok": True, "runs": len(times),
        "tempo_s": round(med, 2),
        "spread_s": round(max(times) - min(times), 2),
        "fps": round(frames / med, 1),
        "x_realtime": round(dur / med, 2),
        **info, **samp.stats(), "nota": note,
    }
    print(f"  {name:34s} {med:6.2f}s  {frames/med:6.1f} fps  {dur/med:5.2f}x  "
          f"enc{samp.stats()['gpu_enc_avg']:5.1f}% dec{samp.stats()['gpu_dec_avg']:5.1f}% "
          f"sm{samp.stats()['gpu_sm_avg']:5.1f}% cpu{samp.stats()['cpu_avg']:5.1f}%")
    return row


def save(rows: list[dict], fname: str) -> Path:
    p = RESULTS / fname
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {p}")
    return p
