# -*- coding: utf-8 -*-
"""FASE 2 + 5 — o caminho ATUAL do ATIVAVID, medido.

Roda sobre um CLONE do projeto. Nao toca na fila, no projeto original nem
no codigo de producao: as funcoes sao chamadas como estao, e a contagem de
subprocessos vem de um wrapper aplicado ao subprocess DESTE processo.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, Sampler, save  # noqa: E402

SRC_PROJ = Path(r"E:\ATIVAVID\Projetos\20260816-002530_IMG_3912_9d41f4134e")
CLONE_ROOT = BENCH / "clone_root"
DUR, FRAMES = 28.366667, 851


class SubprocSpy:
    """Conta e cronometra todo subprocesso deste processo.

    Patch aplicado em memoria, no processo do benchmark — nenhum arquivo de
    producao e alterado. Nao enxerga netos (ex.: ffmpeg do Chromium); isso
    e complementado pelo amostrador de processos.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._run = subprocess.run
        self._popen = subprocess.Popen

    def _name(self, args) -> str:
        try:
            a0 = args[0] if isinstance(args, (list, tuple)) else str(args).split()[0]
        except Exception:
            return "?"
        return Path(str(a0)).name.lower()

    def __enter__(self):
        spy = self

        def run(*a, **kw):
            t0 = time.perf_counter()
            try:
                return spy._run(*a, **kw)
            finally:
                spy.calls.append({"bin": spy._name(a[0] if a else kw.get("args")),
                                  "sec": round(time.perf_counter() - t0, 3),
                                  "args": " ".join(map(str, a[0]))[:400] if a and isinstance(a[0], (list, tuple)) else ""})

        class Popen(spy._popen):  # type: ignore[misc,valid-type]
            def __init__(self, *a, **kw):
                spy.calls.append({"bin": spy._name(a[0] if a else kw.get("args")),
                                  "sec": None,
                                  "args": " ".join(map(str, a[0]))[:400] if a and isinstance(a[0], (list, tuple)) else ""})
                super().__init__(*a, **kw)

        subprocess.run = run
        subprocess.Popen = Popen
        return self

    def __exit__(self, *a):
        subprocess.run = self._run
        subprocess.Popen = self._popen
        return False

    def tally(self) -> dict:
        out: dict[str, int] = {}
        secs: dict[str, float] = {}
        for c in self.calls:
            b = c["bin"] or "?"
            out[b] = out.get(b, 0) + 1
            if c["sec"]:
                secs[b] = round(secs.get(b, 0.0) + c["sec"], 2)
        return {"contagem": out, "segundos": secs, "total": len(self.calls)}


def clone() -> Path:
    if CLONE_ROOT.exists():
        shutil.rmtree(CLONE_ROOT, ignore_errors=True)
    dest = CLONE_ROOT / SRC_PROJ.name
    dest.mkdir(parents=True)
    # robocopy preserva junction (node_modules do cache do Remotion) e e rapido
    subprocess.run(["robocopy", str(SRC_PROJ), str(dest), "/E", "/NFL", "/NDL",
                    "/NJH", "/NJS", "/NP", "/R:1", "/W:1"], capture_output=True)
    return dest


def main() -> None:
    rows: list[dict] = []
    print("clonando projeto (isolado, original intocado)...")
    proj = clone()
    edit = proj / "edit"
    print(f"  clone: {proj}")

    os.environ["ATIVAVID_PROJECTS"] = str(CLONE_ROOT)
    os.environ["ATIVAVID_REMOTION_LOCK"] = str(CLONE_ROOT / ".ativavid" / "remotion.lock")
    (CLONE_ROOT / ".ativavid").mkdir(exist_ok=True)

    # ---------- C0: refazer o cut (render.py sobre o EDL) ----------
    from app.win_process import resolve_python_cmd

    py = resolve_python_cmd(REPO)
    out_cut = edit / "cut_bench.mp4"
    samp = Sampler("C0")
    with samp:
        t0 = time.perf_counter()
        r = subprocess.run(
            [*py, str(REPO / "helpers" / "render.py"), str(edit / "edl.json"),
             "-o", str(out_cut), "--no-subtitles", "--voice-master"],
            capture_output=True, text=True, cwd=str(REPO),
            env={**os.environ, "PYTHONPATH": str(REPO)},
        )
        c0 = time.perf_counter() - t0
    ok = r.returncode == 0 and out_cut.exists()
    print(f"\nC0 refazer o corte              {c0:7.2f}s  ok={ok}")
    if not ok:
        print("   stderr:", (r.stderr or "")[-300:])
    nseg = len(json.loads((edit / "edl.json").read_text(encoding="utf-8-sig")).get("ranges") or [])
    rows.append({"teste": "C0 refazer o corte (render.py)", "ok": ok,
                 "tempo_s": round(c0, 2), "fps": round(FRAMES / c0, 1),
                 "x_realtime": round(DUR / c0, 2), **samp.stats(),
                 "nota": f"{nseg} segmentos no EDL"})

    # ---------- C1: Apply visual (Remotion/overlay + compose + encode) ----------
    from app.apply_execute import execute_apply_plan
    from app.apply_plan import plan_apply_changes
    from app.quick_corrections import load as load_corr
    from app.quick_corrections import save as save_corr

    corr = load_corr(edit)
    corr["dirty"] = {"headline": True, "captions": False, "edl": False, "style": False}
    corr["pending"] = {"headline": 1, "captions": 0, "edl": 0, "style": 0}
    save_corr(edit, corr)
    plan = plan_apply_changes(load_corr(edit))
    print(f"C1 plano: mode={plan.get('mode')} renderMode={plan.get('renderMode')} "
          f"rebuildCut={plan.get('rebuildCut')}")

    spy = SubprocSpy()
    samp2 = Sampler("C1")
    logbuf: list[str] = []
    with samp2, spy:
        t0 = time.perf_counter()
        try:
            res = execute_apply_plan(edit, plan)
            okc1 = bool(res.get("ok"))
        except Exception as e:  # noqa: BLE001
            okc1 = False
            logbuf.append(f"EXC {e}")
        c1 = time.perf_counter() - t0
    t = spy.tally()
    print(f"C1 Apply visual                 {c1:7.2f}s  ok={okc1}")
    print(f"   subprocessos: {t['contagem']}")
    print(f"   segundos por binario: {t['segundos']}")
    rows.append({"teste": "C1 Apply visual (caminho atual)", "ok": okc1,
                 "tempo_s": round(c1, 2), "fps": round(FRAMES / c1, 1),
                 "x_realtime": round(DUR / c1, 2), **samp2.stats(),
                 "n_ffmpeg": t["contagem"].get("ffmpeg.exe", 0) + t["contagem"].get("ffmpeg", 0),
                 "n_ffprobe": t["contagem"].get("ffprobe.exe", 0) + t["contagem"].get("ffprobe", 0),
                 "n_node": t["contagem"].get("node.exe", 0) + t["contagem"].get("npx.cmd", 0),
                 "n_subproc_total": t["total"],
                 "nota": json.dumps(t["segundos"], ensure_ascii=False)[:200]})

    (Path(__file__).resolve().parent / "results" / "phase5_subprocs.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in spy.calls), encoding="utf-8")
    save(rows, "phase5_current.csv")


if __name__ == "__main__":
    main()
