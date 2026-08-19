# -*- coding: utf-8 -*-
"""FASE 2 — quantos ffprobe/ffmpeg o CORTE dispara de verdade.

O corte roda como subprocesso (render.py), entao o contador do phase5 nao
enxerga o que acontece dentro dele. Aqui o proprio render.py e importado e
executado NESTE processo (mesmo codigo, sem alteracao), com o subprocess
instrumentado — assim cada ffprobe aparece.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, save  # noqa: E402
from phase5_current import SubprocSpy  # noqa: E402

CLONE = BENCH / "clone_root" / "20260816-002530_IMG_3912_9d41f4134e" / "edit"


def main() -> None:
    edl = CLONE / "edl.json"
    if not edl.exists():
        print("clone ausente — rode phase5_current.py antes")
        return
    ranges = json.loads(edl.read_text(encoding="utf-8-sig")).get("ranges") or []
    out = CLONE / "cut_probecount.mp4"

    import render  # helpers/render.py, sem modificacao

    argv = ["render.py", str(edl), "-o", str(out), "--no-subtitles", "--voice-master"]
    spy = SubprocSpy()
    t0 = time.perf_counter()
    with spy:
        old = sys.argv
        sys.argv = argv
        try:
            render.main()
        except SystemExit:
            pass
        finally:
            sys.argv = old
    el = time.perf_counter() - t0
    t = spy.tally()
    n_probe = sum(v for k, v in t["contagem"].items() if "ffprobe" in k)
    n_ff = sum(v for k, v in t["contagem"].items() if k.startswith("ffmpeg"))
    print(f"corte de {len(ranges)} segmentos em {el:.1f}s")
    print(f"  ffprobe : {n_probe}   ({n_probe / max(1, len(ranges)):.1f} por segmento)")
    print(f"  ffmpeg  : {n_ff}      ({n_ff / max(1, len(ranges)):.1f} por segmento)")
    print(f"  outros  : { {k: v for k, v in t['contagem'].items() if 'ffprobe' not in k and not k.startswith('ffmpeg')} }")
    print(f"  segundos por binario: {t['segundos']}")

    save([{
        "teste": "corte: contagem de subprocessos", "ok": out.exists(),
        "tempo_s": round(el, 2), "segmentos": len(ranges),
        "n_ffprobe": n_probe, "n_ffmpeg": n_ff,
        "ffprobe_por_segmento": round(n_probe / max(1, len(ranges)), 2),
        "n_subproc_total": t["total"],
        "nota": json.dumps(t["segundos"], ensure_ascii=False)[:200],
    }], "phase2_probes.csv")
    (Path(__file__).resolve().parent / "results" / "phase2_cut_calls.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in spy.calls), encoding="utf-8")


if __name__ == "__main__":
    main()
