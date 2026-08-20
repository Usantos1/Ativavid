# -*- coding: utf-8 -*-
"""EXPERIMENTO — legenda desenhada DIRETO sobre o video, numa passada so.

Hoje sao duas etapas: o Remotion desenha as legendas num video ProRes 4444 com
transparencia (43 MB para 251 quadros), e depois o ffmpeg compoe esse arquivo
sobre o corte. O intermediario existe porque o Remotion e um navegador: ele nao
tem como receber o video e desenhar por cima.

Sendo nos donos do rasterizador, o intermediario some. Mede-se aqui:

    decodificar o corte -> compor a legenda em memoria -> encodar o final

contra o caminho atual (Remotion + compose), no mesmo trecho.

Nao toca em producao.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase20_render_proprio as R  # noqa: E402

NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def uma_passada(cut: Path, cues: list[dict], a: int, b: int, saida: Path) -> float:
    """Nos desenhamos a legenda; o ffmpeg faz o resto.

    A primeira versao decodificava o video em Python e compunha em numpy: 108
    ms/quadro, quase tudo em converter cor e copiar 6 MB por quadro. Nao ha
    motivo — o ffmpeg compoe em C e ainda roda em paralelo com o nosso
    desenho, cada um no seu processo. O pipe leva SO a legenda.
    """
    legs = [R.montar(c) for c in cues]
    n = b - a
    t0 = time.perf_counter()
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-ss", f"{a / R.FPS:.6f}", "-i", str(cut),
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{R.W}x{R.H}",
         "-r", str(R.FPS), "-i", "-",
         "-filter_complex", "[0:v][1:v]overlay=eof_action=endall:format=auto,"
                            "format=yuv420p[v]",
         "-map", "[v]", "-frames:v", str(n),
         "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", str(saida)],
        stdin=subprocess.PIPE, **NOWIN)

    ov = np.zeros((R.H, R.W, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    for f in range(a, b):
        leg = next((l for l in legs if l.inicio_f <= f <= l.fim_f), None)
        R.desenhar(leg, f - (leg.inicio_f if leg else 0), ov, sujo)
        ff.stdin.write(ov.tobytes())
    ff.stdin.close()
    ff.wait()
    return time.perf_counter() - t0


if __name__ == "__main__":
    proj = Path(sys.argv[1])
    a, b = int(sys.argv[2]), int(sys.argv[3])
    cut = proj / "edit" / "cut.mp4"
    public = proj / "edit" / "remotion" / "public"
    dados = json.loads((public / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = dados if isinstance(dados, list) else (dados.get("cues") or [])
    saida = R.BENCH / "final_uma_passada.mp4"
    el = uma_passada(cut, cues, a, b, saida)
    n = b - a
    print(f"  UMA PASSADA: {n} quadros em {el:.1f}s = {el / n * 1000:.0f} ms/quadro "
          f"({n / R.FPS / el:.1f}x tempo real)")
    if saida.exists():
        print(f"  saida: {saida.stat().st_size / 1024 / 1024:.0f} MB")
