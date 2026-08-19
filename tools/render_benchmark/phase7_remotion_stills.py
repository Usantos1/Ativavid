# -*- coding: utf-8 -*-
"""EXPERIMENTO 2 — Remotion por ESTADOS em vez de por frame.

Hoje o Remotion desenha 851 frames (239,3 s). A legenda deste projeto muda
21 vezes. Este teste mede quanto custa pedir ao Remotion apenas UMA imagem
por estado — mesmo visual, sem pagar Chromium por frame.

Nao altera nada: usa o Remotion do CLONE, com o comando `still`.
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

CLONE = BENCH / "clone_root" / "20260816-002530_IMG_3912_9d41f4134e" / "edit"
REMO = CLONE / "remotion"
OUT = BENCH / "stills"
FPS = 30
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def cue_frames() -> list[int]:
    """Um frame representativo por bloco de legenda (+ o gancho)."""
    p = REMO / "public" / "caption-cues.json"
    cues = json.loads(p.read_text(encoding="utf-8-sig"))
    cues = cues if isinstance(cues, list) else (cues.get("cues") or [])
    frames = [int(c.get("startMs", 0) / 1000 * FPS) + 1 for c in cues]
    return sorted(set([0] + frames))


def main() -> None:
    if not (REMO / "node_modules").exists():
        print("clone sem node_modules — rode phase5_current.py antes")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    frames = cue_frames()
    cli = REMO / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    print(f"estados a desenhar: {len(frames)}  (o render completo faz 851 frames)\n")

    per: list[float] = []
    fails = 0
    samp = Sampler("stills")
    with samp:
        t0 = time.perf_counter()
        for i, fr in enumerate(frames):
            out = OUT / f"state_{i:03d}.png"
            s = time.perf_counter()
            r = subprocess.run(
                ["node", str(cli), "still", "Overlay", str(out), f"--frame={fr}",
                 "--image-format=png", "--log=error"],
                capture_output=True, text=True, cwd=str(REMO), **_NOWIN,
            )
            el = time.perf_counter() - s
            if r.returncode != 0 or not out.exists():
                fails += 1
                if fails == 1:
                    print("  falha:", (r.stderr or r.stdout or "")[-200:].replace("\n", " "))
            else:
                per.append(el)
            if i == 0:
                print(f"  1o estado (inclui subir o Chromium): {el:.1f}s")
        total = time.perf_counter() - t0

    if not per:
        print("nenhum estado gerado — abortando")
        save([{"teste": "E2 Remotion por estados", "ok": False, "nota": "still falhou"}],
             "phase7_stills.csv")
        return

    med = statistics.median(per)
    frio = per[0] if per else 0
    quente = statistics.median(per[1:]) if len(per) > 1 else med
    print(f"\n  {len(per)} estados em {total:.1f}s")
    print(f"  1o (frio): {frio:.1f}s | mediana dos seguintes: {quente:.1f}s")
    print(f"  render completo hoje: 239,3s por 851 frames")
    print(f"  -> por estado o custo total seria ~{total:.0f}s ({239.3/max(total,0.1):.1f}x melhor)")

    save([{
        "teste": "E2 Remotion por estados (stills)", "ok": True,
        "tempo_s": round(total, 2), "estados": len(per), "falhas": fails,
        "primeiro_s": round(frio, 2), "mediana_seguintes_s": round(quente, 2),
        "vs_render_completo_239s": round(239.3 / max(total, 0.1), 2),
        **samp.stats(),
        "nota": "cada still sobe um Chromium novo; um renderer reaproveitado seria mais rapido",
    }], "phase7_stills.csv")


if __name__ == "__main__":
    main()
