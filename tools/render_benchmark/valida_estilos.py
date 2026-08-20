# -*- coding: utf-8 -*-
"""Validacao lado a lado dos estilos novos contra o Remotion.

Para cada estilo: escreve o edit-data do scaffold com aquele style, renderiza
uma faixa curta no Remotion E no renderizador proprio, e compara a TINTA
(pixels com alpha) quadro a quadro na faixa das legendas. Salva o par de
quadros para inspecao visual.

Nao toca em producao: trabalha no scaffold de teste ja montado.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, r"E:\Code\ativa-vid")
from app.render_proprio import Renderizador  # noqa: E402
from app.win_process import resolve_remotion_argv  # noqa: E402

S = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
OV = S / "prova_real" / "remotion"
PUB = OV / "public"
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}
A, B = 120, 260          # faixa com fala continua
FPS = 30.0


def _quadros(mov: Path, n: int) -> np.ndarray:
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(mov), "-f", "rawvideo",
         "-pix_fmt", "rgba", "-"], stdout=subprocess.PIPE, **NOWIN)
    tam = 1080 * 1920 * 4
    out = []
    while len(out) < n:
        b = p.stdout.read(tam)
        if len(b) < tam:
            break
        out.append(np.frombuffer(b, dtype=np.uint8).reshape(1920, 1080, 4))
    p.stdout.close()
    p.wait()
    return np.array(out)


def valida(estilo: str, ed_base: dict) -> dict:
    ed = json.loads(json.dumps(ed_base))
    ed["captions"] = dict(ed.get("captions") or {}, style=estilo)
    ed["hook"] = dict(ed.get("hook") or {}, enabled=False)
    ed["endCard"] = dict(ed.get("endCard") or {}, enabled=False)
    ed["transitions"] = []
    (PUB / "edit-data.json").write_text(json.dumps(ed, ensure_ascii=False),
                                        encoding="utf-8")

    rm = S / f"val_rm_{estilo}.mov"
    cmd = resolve_remotion_argv(
        OV, "render", "Overlay", str(rm), f"--frames={A}-{B - 1}",
        "--codec", "prores", "--prores-profile", "4444",
        "--image-format", "png", "--pixel-format", "yuva444p10le")
    t0 = time.perf_counter()
    r = subprocess.run(cmd, cwd=str(OV), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **NOWIN)
    t_rm = time.perf_counter() - t0
    if r.returncode != 0 or not rm.exists():
        return {"estilo": estilo, "erro": ((r.stderr or "") + (r.stdout or ""))[-200:]}

    ns = S / f"val_ns_{estilo}.mov"
    t0 = time.perf_counter()
    rend = Renderizador(PUB, ed, frames=B, fps=FPS, width=1080, height=1920)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
         "-pix_fmt", "rgba", "-s", "1080x1920", "-r", "30", "-i", "-",
         "-c:v", "qtrle", str(ns)], stdin=subprocess.PIPE, **NOWIN)
    buf = np.zeros((1920, 1080, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]
    for f in range(A, B):
        if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
            buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
        sujo[:] = [0, 0, 0, 0]
        primeira = True
        for leg in rend.camadas:
            if leg.inicio_f <= f <= leg.fim_f:
                rend.desenhar(leg, f - leg.inicio_f, buf, sujo,
                              mesclar=not primeira)
                primeira = False
        ff.stdin.write(buf.tobytes())
    ff.stdin.close()
    ff.wait()
    t_ns = time.perf_counter() - t0

    n = B - A
    qr, qn = _quadros(rm, n), _quadros(ns, n)
    m = min(len(qr), len(qn))
    tr = np.array([(qr[i][..., 3] > 8).sum() for i in range(m)], dtype=float)
    tn = np.array([(qn[i][..., 3] > 8).sum() for i in range(m)], dtype=float)
    com = tr > 500
    razao = tn[com] / np.maximum(tr[com], 1) if com.any() else np.array([0.0])

    # par de quadros para inspecao
    meio = m // 2
    par = Image.new("RGB", (1080, 700), (28, 28, 28))
    for k, q in enumerate((qr[meio], qn[meio])):
        im = Image.fromarray(q, "RGBA").crop((0, 1150, 1080, 1700)).resize((540, 280))
        par.paste(im, (k * 540, 210), im)
    par.save(S / f"val_{estilo}.png")
    return {"estilo": estilo, "quadros": int(m), "com_tinta": int(com.sum()),
            "mediana": float(np.median(razao)), "p5": float(np.percentile(razao, 5)),
            "p95": float(np.percentile(razao, 95)),
            "t_remotion": round(t_rm, 1), "t_nosso": round(t_ns, 1)}


if __name__ == "__main__":
    backup = (PUB / "edit-data.json").read_text(encoding="utf-8-sig")
    base = json.loads(backup)
    try:
        for estilo in sys.argv[1:] or ["impacto", "scatter", "simples"]:
            r = valida(estilo, base)
            if "erro" in r:
                print(f"  {estilo:10s} FALHOU: {r['erro'][:120]}")
            else:
                print(f"  {r['estilo']:10s} tinta mediana {r['mediana']:.3f} "
                      f"(p5 {r['p5']:.2f} p95 {r['p95']:.2f}) | "
                      f"{r['com_tinta']}/{r['quadros']} quadros | "
                      f"Remotion {r['t_remotion']}s vs nosso {r['t_nosso']}s")
    finally:
        (PUB / "edit-data.json").write_text(backup, encoding="utf-8")
        print("  edit-data restaurado")
