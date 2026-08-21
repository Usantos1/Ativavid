# -*- coding: utf-8 -*-
"""Varredura ampla do motor proprio contra o Remotion, num projeto real.

O `cmp_entrada.py` ao lado prova um ponto (a entrada de uma palavra). Isto
VARRE: amostra legendas de todos os presets, a manchete e o cartao final, e
compara tinta e posicao vertical em cada quadro escolhido.

Foi esta varredura que achou, em 21/08/2026, dois defeitos que ninguem tinha
ido procurar:

  - o relogio da cue usava `int()` onde o template usa `Math.round` — 57 das
    112 cues do projeto caiam num quadro diferente. Num quadro o motor
    desenhava 3,3x a tinta; noutro, NADA.
  - a curva de entrada da bezier tinha sido aplicada no motor INTEIRO, e a
    manchete usa `Easing.out(Easing.cubic)` — razao 1,537 e centro vertical
    11,8px fora.

Depois dos dois: de 33 pontos, os fora de 10% cairam de 11 para 4.

TRES ARMADILHAS deste harness — as tres ja me deram conclusao errada:

1. Total de quadros ARTIFICIAL. O cartao final e ancorado no FIM da
   composicao; com um total menor ele aparece no meio do video e a comparacao
   mede duas camadas onde o Remotion desenha uma (razao 2,0, cara de defeito
   grave). Use `timeline_from_edit_data(ed)["durationInFrames"]`.
2. Projeto ANTIGO. O `remotion/src` dele pode nao ter os .tsx de hoje e o
   bundle quebra.
3. Esquecer o ESCURECIMENTO do cartao final. Ele e aplicado no BUFFER
   (`_aplicar_dim`), nao como camada — sem ele o quadro sai quase vazio e da
   razao 0,02, como se o motor nao desenhasse o cartao.

DIFERENCAS ACEITAS. Medido em 21/08/2026, 35 pontos: 30 dentro de 10%, e os
5 de fora sao estes dois casos, nenhum defeito:

  - os dois PRIMEIROS quadros de uma entrada ficam 1,18 a 1,27 (o motor
    rasteriza a escala e a opacidade em estagios de um quadro; o Remotion
    interpola continuamente) e convergem para ~1,01 no terceiro;
  - alguns quadros de entrada saem 10 a 14% mais LEVES (0,86 a 0,90), pelo
    mesmo motivo, do outro lado do arredondamento do estagio.

O centro vertical, que e o que denuncia posicao errada, fica dentro de poucos
pixels em TODOS os 35 pontos — inclusive nesses cinco.

Uso:  python tools/render_benchmark/cmp_varredura.py [indice]
      indice 0 = projeto mais recente, 1 = o anterior, e assim por diante.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
TRAB = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_cmp_varredura"
MAX_CUES = 8


def main() -> None:
    from app.overlay_path import prepare_overlay_remotion
    from app.render_proprio import Renderizador
    from app.timeline import timeline_from_edit_data
    from app.win_process import resolve_remotion_argv
    from tools.render_benchmark.cmp_entrada import escolher

    indice = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    edit, cues = escolher(indice)
    pub = edit / "remotion" / "public"
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8-sig"))
    total = int(timeline_from_edit_data(ed)["durationInFrames"])   # armadilha 1
    hook, ec = ed.get("hook") or {}, ed.get("endCard") or {}
    print(f"projeto: {edit.parent.name}")
    print(f"  {total} quadros  headline={hook.get('style')}  "
          f"legenda={(ed.get('captions') or {}).get('style')}\n")

    alvos: list[tuple[str, int]] = []
    if hook.get("enabled"):
        fim = Renderizador._arredonda_js(float(hook.get("endSec") or 4.0) * 30)
        alvos += [("manchete", f) for f in (1, 2, 4, 8, 14, fim - 4, fim + 1)]
    if ec.get("enabled"):
        ini = total - Renderizador._arredonda_js(float(ec.get("lastSec") or 2.5) * 30)
        alvos += [("cartao", f) for f in (ini + 1, ini + 3, ini + 12, total - 3)]

    por_preset: dict[str, list] = {}
    for c in cues:
        por_preset.setdefault(c.get("preset") or "STACK_MIXED", []).append(c)
    amostra = []
    for lista in por_preset.values():
        amostra += lista[::max(1, len(lista) // 3)][:3]
    for c in amostra[:MAX_CUES]:
        ini = Renderizador._arredonda_js(c["startMs"] / 1000 * 30)
        dur = Renderizador._arredonda_js(c["endMs"] / 1000 * 30) - ini
        locais = sorted((w["fromMs"] - c["startMs"]) / 1000 * 30
                        for ln in c["lines"] for w in ln)
        pontos = {ini + 2, ini + max(1, dur // 2), ini + max(1, dur - 4)}
        if locais and locais[-1] > 2:
            pontos.add(ini + int(locais[-1]) + 2)
        alvos += [(f"cue {c.get('i')}", f) for f in sorted(pontos)]
    alvos = [(k, f) for k, f in alvos if 0 <= f < total]

    shutil.rmtree(TRAB, ignore_errors=True)
    TRAB.mkdir(parents=True)
    ov = prepare_overlay_remotion(edit / "remotion", TRAB / "remotion")
    print(f"renderizando {len(alvos)} stills...", flush=True)
    for _, f in alvos:
        png = TRAB / f"r{f:05d}.png"
        if png.exists():
            continue
        r = subprocess.run(
            resolve_remotion_argv(ov, "still", "Overlay", str(png), f"--frame={f}"),
            cwd=str(ov), capture_output=True, text=True, **NOWIN)
        if r.returncode != 0 or not png.exists():
            print(f"  still {f} falhou")

    r = Renderizador(pub, ed, frames=total, fps=30.0)
    linhas = []
    for k, f in alvos:
        png = TRAB / f"r{f:05d}.png"
        if not png.exists():
            continue
        a = np.asarray(Image.open(png).convert("RGBA"))[..., 3].astype(np.float64)
        buf = np.zeros((r.h, r.w, 4), dtype=np.uint8)
        sujo, primeira = [0, 0, 0, 0], True
        for leg in r.camadas:
            if leg.inicio_f <= f <= leg.fim_f:
                if leg.dim:                                    # armadilha 3
                    r._aplicar_dim(buf, sujo, leg.dim, f - leg.inicio_f,
                                   leg.dim_fade)
                    primeira = False
                r.desenhar(leg, f - leg.inicio_f, buf, sujo, not primeira)
                primeira = False
        b = buf[..., 3].astype(np.float64)
        sa, sb = a.sum(), b.sum()
        if sa < 1000 and sb < 1000:
            continue
        razao = sb / sa if sa else float("inf")
        ys = np.arange(a.shape[0])
        ca = float((a.sum(axis=1) * ys).sum() / sa) if sa else 0.0
        cb = float((b.sum(axis=1) * ys).sum() / sb) if sb else 0.0
        linhas.append((abs(razao - 1.0), k, f, razao, ca, cb))

    linhas.sort(reverse=True)
    print(f"\n  {'o que':<10} {'quadro':>7} {'razao':>7} {'cY rem':>8} {'cY pro':>8} {'dY':>6}")
    for _, k, f, razao, ca, cb in linhas:
        print(f"  {k:<10} {f:>7} {razao:>7.3f} {ca:>8.1f} {cb:>8.1f} {cb - ca:>6.1f}")
    fora = [x for x in linhas if x[0] > 0.10]
    print(f"\n{len(linhas)} pontos; {len(fora)} com mais de 10% de diferenca")


if __name__ == "__main__":
    main()
