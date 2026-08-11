#!/usr/bin/env python3
"""Render several projects' Phase 2 at once.

Editing one video at a time is the real ceiling, not frames per second. On the
box this was tuned on, one Remotion render at full concurrency took 104s for a
288-frame reel — but Remotion refuses a concurrency above the core count, so a
single render can never use more than the machine has. Throughput therefore
comes from running SEVERAL projects side by side, each on a slice of the cores.

Latency vs throughput, concretely: one project at --concurrency=8 finishes that
one video soonest; four projects at 2 each finish four videos sooner. For a
queue, the second is what matters.

Usage:
    python helpers/render_queue.py <edit-dir> [<edit-dir> ...] [--parallel 2]
    python helpers/render_queue.py --root "E:/1 AAAAA/1 novos" --all
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def phase2_ready(edit: Path) -> tuple[bool, str]:
    """Cheap preflight. A queue that dies 40 minutes in because job 6 was
    missing a file is worse than one that refuses that job up front."""
    rem = edit / "remotion"
    if not rem.is_dir():
        return False, "sem pasta remotion/"
    if not (rem / "node_modules").is_dir():
        return False, "node_modules ausente (rode npm install)"
    for f in ("edit-data.json", "captions.json", "segments.json", "cut.mp4"):
        if not (rem / "public" / f).exists():
            return False, f"public/{f} ausente"
    return True, ""


def render_one(edit: Path, concurrency: int) -> dict:
    ok, why = phase2_ready(edit)
    if not ok:
        return {"edit": str(edit), "ok": False, "sec": 0.0, "error": why}
    out = edit / "remotion" / "out" / "render.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    p = subprocess.run(
        ["npx", "remotion", "render", "Reels", str(out), f"--concurrency={concurrency}"],
        cwd=str(edit / "remotion"), capture_output=True, text=True, shell=(os.name == "nt"),
    )
    dt = time.time() - t0
    if p.returncode != 0 or not out.exists():
        tail = (p.stderr or p.stdout or "").strip().splitlines()
        return {"edit": str(edit), "ok": False, "sec": dt,
                "error": (tail[-1] if tail else "render falhou")[:200]}
    return {"edit": str(edit), "ok": True, "sec": dt, "out": str(out)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Renderiza a Fase 2 de varios projetos em paralelo")
    ap.add_argument("edits", nargs="*", type=Path, help="pastas <edit> a renderizar")
    ap.add_argument("--root", type=Path, action="append",
                    help="pasta com projetos irmaos (<root>/<projeto>/edit). Repetivel.")
    ap.add_argument("--all", action="store_true",
                    help="com --root: enfileira todo projeto pronto para a Fase 2")
    ap.add_argument("--parallel", type=int, default=2,
                    help="quantos projetos ao mesmo tempo (padrao 2)")
    ap.add_argument("--dry-run", action="store_true",
                    help="so lista o que seria renderizado e o preflight de cada um; "
                         "nao escreve nada em projeto nenhum")
    args = ap.parse_args()

    edits = [p.resolve() for p in args.edits]
    if args.root and args.all:
        for r in args.root:
            edits += [p.resolve() for p in sorted(r.glob("*/edit")) if p.is_dir()]
    edits = list(dict.fromkeys(edits))
    if not edits:
        raise SystemExit("nada para renderizar — passe pastas <edit> ou --root ... --all")

    cores = os.cpu_count() or 4
    par = max(1, min(args.parallel, len(edits)))
    # Split the cores across the running jobs. Remotion validates concurrency
    # against the core count and errors out above it, so this also keeps every
    # job inside a value it will accept.
    per = max(1, min(cores, cores // par))

    print(f"{len(edits)} projeto(s) | {par} em paralelo | concurrency={per} cada "
          f"({cores} nucleos)", flush=True)

    # Default-safe inspection. Without this the only way to see what the queue
    # WOULD do was to let it render — which is exactly how a "preflight check"
    # ended up overwriting a real project's render.mp4.
    if args.dry_run:
        for e in edits:
            ok, why = phase2_ready(e)
            print(f"  [{'ok  ' if ok else 'PULA'}] {e.parent.name}"
                  + ("" if ok else f" :: {why}"), flush=True)
        pronto = sum(1 for e in edits if phase2_ready(e)[0])
        print(f"\n--dry-run: nada foi escrito. {pronto}/{len(edits)} prontos para renderizar.",
              flush=True)
        return

    skipped = [(e, phase2_ready(e)[1]) for e in edits if not phase2_ready(e)[0]]
    for e, why in skipped:
        print(f"  PULA {e.parent.name}: {why}", flush=True)

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=par) as pool:
        for r in pool.map(lambda e: render_one(e, per), edits):
            tag = "ok " if r["ok"] else "ERRO"
            print(f"  [{tag}] {Path(r['edit']).parent.name} — {r['sec']:.0f}s"
                  + ("" if r["ok"] else f" :: {r['error']}"), flush=True)
            results.append(r)

    total = time.time() - t0
    done = [r for r in results if r["ok"]]
    print(f"\n{len(done)}/{len(results)} renderizados em {total:.0f}s", flush=True)
    if done:
        serial = sum(r["sec"] for r in done)
        print(f"soma dos tempos individuais: {serial:.0f}s "
              f"— ganho do paralelismo: {serial / total:.2f}x", flush=True)
    print(json.dumps(results, ensure_ascii=False), file=sys.stderr)
    sys.exit(0 if len(done) == len(results) else 1)


if __name__ == "__main__":
    main()
