# -*- coding: utf-8 -*-
"""FASE 4 — composicao SEM Remotion.

Mesma carga visual do projeto real (1 headline 0-4s + 21 blocos de legenda),
desenhada por FFmpeg. FFmpeg aqui e REGUA de capacidade da maquina, nao
uma afirmacao sobre o motor do CapCut.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_lib import BENCH, CUT, run_test, save  # noqa: E402

PROJ = Path(r"E:\ATIVAVID\Projetos\20260816-002530_IMG_3912_9d41f4134e\edit")
PNG = BENCH / "pngs"
FONT = r"C\:/Windows/Fonts/arialbd.ttf"
_NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def prep() -> tuple[list[tuple[Path, float, float]], float]:
    """Rasteriza headline + um PNG por bloco de legenda. Mede o custo."""
    PNG.mkdir(parents=True, exist_ok=True)
    cues = json.load(open(PROJ / "remotion/public/caption-cues.json", encoding="utf-8-sig"))
    cues = cues if isinstance(cues, list) else (cues.get("cues") or [])
    ed = json.load(open(PROJ / "remotion/public/edit-data.json", encoding="utf-8-sig"))
    hook = ed.get("hook") or {}

    def draw(path: Path, text: str, y: str, size: int) -> None:
        safe = text.replace("'", "").replace(":", " ").replace("\\", "")[:44]
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
             "-i", "color=c=black@0.0:s=1080x1920:d=1,format=rgba",
             "-vf", (f"drawtext=fontfile='{FONT}':text='{safe}':fontcolor=white:"
                     f"fontsize={size}:borderw=8:bordercolor=black:x=(w-text_w)/2:y={y}"),
             "-frames:v", "1", str(path)], capture_output=True, **_NOWIN)

    t0 = time.perf_counter()
    items: list[tuple[Path, float, float]] = []
    hl = PNG / "headline.png"
    draw(hl, " ".join(hook.get("lines") or ["Quase perdi essa venda"]), "h*0.16", 84)
    items.append((hl, 0.0, float(hook.get("endSec") or 4.0)))
    for i, c in enumerate(cues):
        p = PNG / f"cue_{i:03d}.png"
        txt = " ".join(w.get("text", "") for ln in c.get("lines", []) for w in ln)
        draw(p, txt, "h*0.72", 64)
        items.append((p, c.get("startMs", 0) / 1000, c.get("endMs", 0) / 1000))
    el = time.perf_counter() - t0
    made = [i for i in items if i[0].exists()]
    print(f"  rasterizacao: {len(made)} PNGs em {el:.1f}s ({el/max(1,len(made)):.2f}s cada)\n")
    return made, el


def chain_cpu(items) -> tuple[list[str], str]:
    """Cadeia de overlay na CPU, um filtro por grafico."""
    ins: list[str] = []
    parts: list[str] = []
    prev = "[0:v]"
    for i, (p, a, b) in enumerate(items):
        ins += ["-i", str(p)]
        lbl = f"[v{i}]"
        parts.append(f"{prev}[{i+1}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'{lbl}")
        prev = lbl
    return ins, ";".join(parts) + f";{prev}null[vout]"


def chain_cuda(items) -> tuple[list[str], str]:
    """Mesma cadeia, mas na GPU. Cada PNG sobe uma vez (hwupload_cuda)."""
    ins: list[str] = []
    # overlay_cuda recusa alpha sobre nv12 ("Can't overlay yuva420p on nv12").
    # Converter a BASE para yuv420p ainda na GPU destrava o caminho.
    parts: list[str] = ["[0:v]scale_cuda=format=yuv420p[base]"]
    prev = "[base]"
    for i, (p, a, b) in enumerate(items):
        ins += ["-i", str(p)]
        parts.append(f"[{i+1}:v]format=yuva420p,hwupload_cuda[o{i}]")
        lbl = f"[v{i}]"
        parts.append(f"{prev}[o{i}]overlay_cuda=0:0:enable='between(t,{a:.2f},{b:.2f})'{lbl}")
        prev = lbl
    return ins, ";".join(parts) + f";{prev}null[vout]"


if __name__ == "__main__":
    items, prep_s = prep()
    BASE = ["ffmpeg", "-v", "error", "-y"]
    rows: list[dict] = []

    ins, fc = chain_cpu(items)
    rows.append(run_test(
        "B1 CPU decode + overlay CPU + nvenc",
        BASE + ["-i", str(CUT)] + ins + ["-filter_complex", fc, "-map", "[vout]", "-map", "0:a?",
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-c:a", "copy",
                str(BENCH / "out" / "b1.mp4")], "b1.mp4",
        note=f"{len(items)} graficos, blend na CPU"))

    ins, fc = chain_cuda(items)
    rows.append(run_test(
        "B2 NVDEC + overlay_cuda + nvenc",
        BASE + ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(CUT)] + ins
        + ["-filter_complex", fc, "-map", "[vout]", "-map", "0:a?",
           "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-c:a", "copy",
           str(BENCH / "out" / "b2.mp4")], "b2.mp4", note="zero-copy pretendido"))

    rows.append(run_test(
        "B3 NVDEC + overlay_cuda + hevc",
        BASE + ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", str(CUT)] + ins
        + ["-filter_complex", fc, "-map", "[vout]", "-map", "0:a?",
           "-c:v", "hevc_nvenc", "-preset", "p4", "-cq", "26", "-c:a", "copy",
           str(BENCH / "out" / "b3.mp4")], "b3.mp4", note="zero-copy pretendido"))

    # B4: texto rasterizado a cada frame (o oposto de pre-rasterizar)
    dt = []
    for i, (_p, a, b) in enumerate(items[:8]):
        dt.append(f"drawtext=fontfile='{FONT}':text='bloco {i}':fontcolor=white:fontsize=64:"
                  f"borderw=8:bordercolor=black:x=(w-text_w)/2:y=h*0.72:"
                  f"enable='between(t,{a:.2f},{b:.2f})'")
    rows.append(run_test(
        "B4 drawtext por frame + nvenc",
        BASE + ["-i", str(CUT), "-vf", ",".join(dt),
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-c:a", "copy",
                str(BENCH / "out" / "b4.mp4")], "b4.mp4",
        note="8 drawtext; forca frame na CPU"))

    rows.append({"teste": "prep rasterizacao PNG", "ok": True, "tempo_s": round(prep_s, 2),
                 "nota": f"{len(items)} PNGs, custo unico"})
    save(rows, "phase4_compose.csv")
