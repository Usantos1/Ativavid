# -*- coding: utf-8 -*-
"""EXPERIMENTO 1 — uma faixa de overlay vs. 22 filtros encadeados.

A cadeia de 22 `overlay` deu 2,8x tempo real; o transcode puro faz 9,4x.
Este teste separa: quanto e a CADEIA e quanto e a composicao em si.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, CUT, run_test, save  # noqa: E402
from phase4_compose import prep  # noqa: E402

OUT = BENCH / "out"
LST = BENCH / "track.txt"
TRACK = OUT / "track_prores.mov"
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def build_list(items) -> None:
    """Lista concat: cada grafico segurado ate o proximo comecar.

    Buracos entre blocos viram um PNG totalmente transparente, senao o
    grafico anterior ficaria congelado na tela.
    """
    blank = BENCH / "pngs" / "_blank.png"
    if not blank.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "color=c=black@0.0:s=1080x1920:d=1,format=rgba",
                        "-frames:v", "1", str(blank)], capture_output=True, **_NOWIN)
    # headline (0-4s) sobrepoe legendas; para a faixa unica usamos so as
    # legendas + a headline no inicio, na ordem do tempo
    seq = sorted(items, key=lambda x: x[1])
    lines: list[str] = []
    t = 0.0
    for p, a, b in seq:
        if a > t + 0.02:
            lines.append(f"file '{blank.as_posix()}'\nduration {a - t:.3f}")
        lines.append(f"file '{Path(p).as_posix()}'\nduration {max(0.05, b - a):.3f}")
        t = max(t, b)
    lines.append(f"file '{blank.as_posix()}'\nduration 0.2")
    lines.append(f"file '{blank.as_posix()}'")
    LST.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    items, prep_s = prep()
    build_list(items)
    BASE = ["ffmpeg", "-v", "error", "-y"]
    CONCAT = ["-f", "concat", "-safe", "0", "-i", str(LST)]
    rows: list[dict] = []

    # D1 — faixa direto do concat, UM overlay na CPU
    rows.append(run_test(
        "D1 1 overlay CPU (faixa direta)",
        BASE + ["-i", str(CUT)] + CONCAT + [
            "-filter_complex", "[1:v]format=rgba,fps=30[ov];[0:v][ov]overlay=0:0:shortest=1[v]",
            "-map", "[v]", "-map", "0:a?", "-c:v", "h264_nvenc", "-preset", "p4",
            "-cq", "23", "-c:a", "copy", str(OUT / "d1.mp4")], "d1.mp4",
        note="1 filtro em vez de 22"))

    # D2 — faixa direto do concat, UM overlay_cuda (zero-copy)
    rows.append(run_test(
        "D2 1 overlay_cuda (faixa direta)",
        BASE + ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(CUT)] + CONCAT + [
            "-filter_complex",
            "[0:v]scale_cuda=format=yuv420p[base];"
            "[1:v]format=yuva420p,fps=30,hwupload_cuda[ov];"
            "[base][ov]overlay_cuda=0:0:shortest=1[v]",
            "-map", "[v]", "-map", "0:a?", "-c:v", "h264_nvenc", "-preset", "p4",
            "-cq", "23", "-c:a", "copy", str(OUT / "d2.mp4")], "d2.mp4",
        note="1 filtro, tudo na GPU"))

    # D3 — materializar a faixa em ProRes 4444 (o que o Remotion produz hoje)
    rows.append(run_test(
        "D3 gerar faixa ProRes 4444",
        BASE + CONCAT + ["-r", "30", "-c:v", "prores_ks", "-profile:v", "4444",
                         "-pix_fmt", "yuva444p10le", str(TRACK)], "track_prores.mov",
        note="equivalente ao overlay que o Remotion escreve"))

    # D4 — compor a faixa ProRes ja pronta
    if TRACK.exists():
        rows.append(run_test(
            "D4 compor faixa ProRes + nvenc",
            BASE + ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(CUT),
                    "-i", str(TRACK)] + [
                "-filter_complex",
                "[0:v]scale_cuda=format=yuv420p[base];"
                "[1:v]format=yuva420p,hwupload_cuda[ov];"
                "[base][ov]overlay_cuda=0:0:shortest=1[v]",
                "-map", "[v]", "-map", "0:a?", "-c:v", "h264_nvenc", "-preset", "p4",
                "-cq", "23", "-c:a", "copy", str(OUT / "d4.mp4")], "d4.mp4",
            note="mesma etapa que o compose de producao faz hoje"))

    rows.append({"teste": "prep rasterizacao PNG", "ok": True,
                 "tempo_s": round(prep_s, 2), "nota": f"{len(items)} PNGs, custo unico"})
    save(rows, "phase6_single_track.csv")
