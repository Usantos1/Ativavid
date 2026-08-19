# -*- coding: utf-8 -*-
"""Protótipo — compose incremental: recompor só a janela alterada.

Hoje o compose reencoda os 851 frames a cada troca de headline, mesmo quando
só ~4 s mudaram: custo fixo de 25,1 s (metade do Apply incremental).

O final sai com keyframe a cada 30 frames (medido), então dá para emendar
por cópia. Este protótipo mede o ganho e VALIDA a emenda antes de qualquer
mudança em produção.

Não toca no pipeline: opera sobre cópias em área temporária.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
S = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
WORK = S / "compose_inc"
FPS = 30
GOP = 30


def sh(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True, **NOWIN)
    return r.returncode, (r.stderr or "")[-300:]


def frames_of(p: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, **NOWIN)
    try:
        return int((r.stdout or "0").strip().rstrip(","))
    except ValueError:
        return -1


def snap(a: int, b: int, total: int) -> tuple[int, int]:
    """Alarga a janela até a fronteira de GOP — é onde a cópia é frame-exata."""
    return max(0, (a // GOP) * GOP), min(total, -(-b // GOP) * GOP)


def compose_janela(cut: Path, overlay: Path, a: int, b: int, out: Path) -> float:
    """Compõe SÓ [a,b) — mesma cadeia de vídeo do compose de produção."""
    ss, dur = a / FPS, (b - a) / FPS
    vid = ("[0:v][1:v]overlay=eof_action=pass:format=auto,format=yuv420p,"
           "scale=in_range=full:out_range=limited,"
           "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]")
    t0 = time.perf_counter()
    rc, err = sh(["ffmpeg", "-v", "error", "-y",
                  "-ss", f"{ss:.6f}", "-i", str(cut),
                  "-ss", f"{ss:.6f}", "-i", str(overlay),
                  "-filter_complex", vid, "-map", "[vid]",
                  "-frames:v", str(b - a),
                  "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                  "-g", str(GOP), "-keyint_min", str(GOP), "-forced-idr", "1",
                  "-colorspace", "bt709", "-color_primaries", "bt709",
                  "-color_trc", "bt709", "-color_range", "tv",
                  "-an", str(out)])
    if rc:
        raise RuntimeError(f"janela falhou: {err}")
    return time.perf_counter() - t0


def emenda(old_final: Path, piece: Path, a: int, b: int, total: int, out: Path) -> float:
    """[antigo 0..a) + peça + [antigo b..fim), vídeo por CÓPIA; áudio do antigo."""
    t0 = time.perf_counter()
    parts, lst = [], WORK / "concat.txt"
    if a > 0:
        head = WORK / "head.mp4"
        rc, e = sh(["ffmpeg", "-v", "error", "-y", "-i", str(old_final),
                    "-map", "0:v", "-frames:v", str(a), "-c", "copy", str(head)])
        if rc:
            raise RuntimeError(f"head: {e}")
        parts.append(head)
    parts.append(piece)
    if b < total:
        tail = WORK / "tail.mp4"
        rc, e = sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{b / FPS:.6f}",
                    "-i", str(old_final), "-map", "0:v", "-c", "copy", str(tail)])
        if rc:
            raise RuntimeError(f"tail: {e}")
        parts.append(tail)
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    rc, e = sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", str(lst), "-i", str(old_final),
                "-map", "0:v", "-map", "1:a?", "-c", "copy", str(out)])
    if rc:
        raise RuntimeError(f"concat: {e}")
    return time.perf_counter() - t0


if __name__ == "__main__":
    proj = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        S / "hl" / "20260816-002530_IMG_3912_9d41f4134e" / "edit")
    cut, old_final = proj / "cut.mp4", proj / "final.mp4"
    ov = next((p for p in (S / "hl").rglob("overlay.mov")), None)
    if not ov:
        for _base in (r"E:\Temp\ativavid_overlay_work", r"E:\Temp\ativavid_overlay_cache"):
            _b = Path(_base)
            ov = next((p for p in _b.rglob("overlay.mov")), None) if _b.exists() else None
            if ov:
                break
    if not (cut.exists() and old_final.exists() and ov and ov.exists()):
        print(f"faltando: cut={cut.exists()} final={old_final.exists()} overlay={bool(ov)}")
        raise SystemExit(0)
    WORK.mkdir(parents=True, exist_ok=True)
    total = frames_of(old_final)
    print(f"final antigo: {total} frames | overlay: {ov}")

    # Janela típica de troca de headline: gancho de 0 a 4 s
    a, b = snap(0, int(4.0 * FPS), total)
    print(f"janela alterada (ajustada ao GOP): {a}..{b}  ({(b - a) / FPS:.1f}s de {total / FPS:.1f}s)\n")

    piece = WORK / "piece.mp4"
    t_win = compose_janela(cut, ov, a, b, piece)
    out = WORK / "final_incremental.mp4"
    t_spl = emenda(old_final, piece, a, b, total, out)
    got = frames_of(out)
    print(f"  compor a janela : {t_win:6.1f}s")
    print(f"  emendar         : {t_spl:6.1f}s")
    print(f"  TOTAL           : {t_win + t_spl:6.1f}s   (compose atual: 25,1s)")
    print(f"\n  frames: {got} (esperado {total}) -> {'OK' if got == total else 'DIVERGENTE'}")
    json.dump({"janela": [a, b], "compor_s": round(t_win, 2), "emendar_s": round(t_spl, 2),
               "frames": got, "esperado": total},
              open(Path(__file__).parent / "results" / "phase18_compose_inc.json", "w"),
              indent=2)
