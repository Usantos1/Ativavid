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


def uma_passada(cut: Path, cues: list[dict], a: int, b: int, saida: Path,
                caixa: bool = True) -> tuple[float, str]:
    """Nos desenhamos a legenda; o ffmpeg faz o resto.

    Duas versoes anteriores e o que elas ensinaram:
      - decodificar o video em Python e compor em numpy: 108 ms/quadro, quase
        tudo em converter cor e copiar 6 MB por quadro. O ffmpeg compoe em C e
        roda em paralelo, em outro processo — nao ha motivo para fazer isso
        aqui;
      - mandar a TELA INTEIRA em RGBA pelo cano: 76 ms/quadro, dominado por
        8,3 MB por quadro de tubo.

    Legenda mora sempre na mesma faixa da tela. `caixa=True` transmite so essa
    faixa e o ffmpeg posiciona com o overlay.
    """
    legs = [R.montar(c) for c in cues]
    n = b - a
    if caixa:
        bx0, by0, bx1, by1 = R.caixa_de(legs)
    else:
        bx0, by0, bx1, by1 = 0, 0, R.W, R.H
    bw, bh = bx1 - bx0, by1 - by0

    t0 = time.perf_counter()
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-ss", f"{a / R.FPS:.6f}", "-i", str(cut),
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{bw}x{bh}",
         "-r", str(R.FPS), "-i", "-",
         "-filter_complex",
         f"[0:v][1:v]overlay=x={bx0}:y={by0}:eof_action=endall:format=auto,"
         "format=yuv420p[v]",
         "-map", "[v]", "-frames:v", str(n),
         "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", str(saida)],
        stdin=subprocess.PIPE, **NOWIN)

    ov = np.zeros((bh, bw, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    for f in range(a, b):
        leg = next((l for l in legs if l.inicio_f <= f <= l.fim_f), None)
        R.desenhar(leg, f - (leg.inicio_f if leg else 0), ov, sujo, (bx0, by0))
        ff.stdin.write(ov.tobytes())
    ff.stdin.close()
    ff.wait()
    mb = bw * bh * 4 / 1024 / 1024
    return time.perf_counter() - t0, f"{bw}x{bh} ({mb:.1f} MB/quadro no cano)"


if __name__ == "__main__":
    proj = Path(sys.argv[1])
    a, b = int(sys.argv[2]), int(sys.argv[3])
    cut = proj / "edit" / "cut.mp4"
    public = proj / "edit" / "remotion" / "public"
    dados = json.loads((public / "caption-cues.json").read_text(encoding="utf-8-sig"))
    cues = dados if isinstance(dados, list) else (dados.get("cues") or [])
    saida = R.BENCH / "final_uma_passada.mp4"
    ed = public / "edit-data.json"
    if ed.exists():
        R.usar_config(json.loads(ed.read_text(encoding="utf-8-sig")))
    n = b - a
    for usa_caixa in (False, True):
        el, info = uma_passada(cut, cues, a, b, saida, caixa=usa_caixa)
        rotulo = "so a faixa da legenda" if usa_caixa else "tela inteira      "
        print(f"  {rotulo}: {el:5.1f}s = {el / n * 1000:3.0f} ms/quadro "
              f"({n / R.FPS / el:.1f}x tempo real)  {info}")
    if saida.exists():
        print(f"  saida: {saida.stat().st_size / 1024 / 1024:.0f} MB")
