# -*- coding: utf-8 -*-
"""Fidelidade do motor proprio nos quadros de ENTRADA da palavra.

O `cmp_rast.py` ao lado compara so os quadros ASSENTADOS ("todas as palavras
ja entraram") — de proposito, porque ali a comparacao e estavel. O preco foi
um ponto cego: a curva de entrada do motor esteve ERRADA em toda legenda de
todo video e nenhuma validacao pegou, porque a entrada e uma fracao da cue.

Este script cobre esse buraco: renderiza os mesmos quadros de entrada pelo
Remotion (`remotion still`, um quadro por vez — nao um render inteiro) e pelo
motor proprio, e compara a tinta.

Medido em 21/08/2026, projeto 20260820-215832_IMG_4120, cue i=13
(STACK_MIXED, exit abrupt), quadros 377 a 380 = entrada da ultima palavra:

    quadro   curva `1-(1-t)^3`   curva do template
       377              0,835              **0,986**
       378              0,852              **0,982**
       379              0,893              **0,976**
       380              0,928              **0,973**

A cubica ficava 7 a 17% aquem do Remotion; a bezier do template
(`Easing.bezier(0.16, 1, 0.3, 1)`) fica dentro de 3%.

DUAS ARMADILHAS deste harness, as duas ja custaram uma conclusao errada:

1. Passar um total de quadros ARTIFICIAL ao `Renderizador`. O cartao final e
   ancorado no FIM da composicao — com um total menor que o real ele aparece
   no meio do video e a comparacao mede duas camadas onde o Remotion desenha
   uma (deu razao 2,0 e parecia defeito grave do motor). Use sempre
   `timeline_from_edit_data(ed)["durationInFrames"]`.
2. Escolher um projeto ANTIGO. O `remotion/src` dele pode nao ter os .tsx de
   hoje (falta `ImpactCaptions.tsx`) e o bundle quebra. Pegue o mais recente
   que tenha `node_modules`.

DIFERENCAS CONHECIDAS E ACEITAS (nao sao defeito):

- SOLO_OUTLINE, PRIMEIRO quadro da cue: o Chrome desenha um fragmento verde do
  traco a lapis mesmo com `outlineProg` = 0 — artefato de `strokeDasharray`
  com `pathLength=1` e `strokeDashoffset=1`. O motor nao desenha nada ali, o
  que e ate mais fiel a intencao. E 1 quadro de 5, num preset que e 4% das
  cues.
- Quadros de ENTRADA em geral: o motor rasteriza a escala em estagios de um
  quadro; o Remotion escala continuamente. Da 1,05 a 1,18 de tinta nos dois
  primeiros quadros e converge para ~1,01 no terceiro.

Uso:  python tools/render_benchmark/cmp_entrada.py
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
RAIZ = Path(os.path.expanduser("~/ATIVAVID/Projetos"))
TRAB = Path(os.environ.get("TEMP", r"E:\Temp")) / "ativavid_cmp_entrada"


def escolher(indice: int = 0) -> tuple[Path, list]:
    """O projeto RECENTE com node_modules e scaffold atual.

    `indice` escolhe o n-esimo mais recente. Serve para conferir a fidelidade em
    MAIS DE UM projeto: passar num so nao distingue "o motor esta certo" de "o
    conteudo daquele video nao exercitou o defeito".
    """
    cands = []
    for edit in RAIZ.glob("*/edit"):
        cues_p = edit / "remotion" / "public" / "caption-cues.json"
        src = edit / "remotion" / "src"
        if not (cues_p.is_file() and (edit / "remotion" / "node_modules").exists()):
            continue
        if not (src / "ImpactCaptions.tsx").is_file():
            continue
        try:
            cues = json.loads(cues_p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        cues = cues if isinstance(cues, list) else (cues.get("cues") or [])
        if cues:
            cands.append((edit.parent.stat().st_mtime, edit, cues))
    if not cands:
        raise SystemExit("nenhum projeto com scaffold atual + node_modules")
    cands.sort(reverse=True)
    i = max(0, min(int(indice), len(cands) - 1))
    return cands[i][1], cands[i][2]


def main() -> None:
    from app.overlay_path import prepare_overlay_remotion
    from app.render_proprio import Renderizador
    from app.timeline import timeline_from_edit_data
    from app.win_process import resolve_remotion_argv

    edit, cues = escolher()
    print(f"projeto: {edit.parent.name}")
    shutil.rmtree(TRAB, ignore_errors=True)
    TRAB.mkdir(parents=True)

    cue = max(cues, key=lambda c: sum(len(l) for l in c.get("lines") or []))
    # o MESMO arredondamento do template/motor, senao o harness mira um
    # quadro ao lado e a comparacao vira ruido
    ini_f = Renderizador._arredonda_js(cue["startMs"] / 1000 * 30)
    locais = sorted((w["fromMs"] - cue["startMs"]) / 1000 * 30
                    for ln in cue["lines"] for w in ln)
    quadros = [ini_f + int(locais[-1]) + k for k in (1, 2, 3, 4)]
    print(f"cue i={cue.get('i')} preset={cue.get('preset')} exit={cue.get('exit')}")
    print(f"  entrada da ultima palavra: quadros {quadros}\n")

    ov = prepare_overlay_remotion(edit / "remotion", TRAB / "remotion")
    for f in quadros:
        png = TRAB / f"rem_{f:05d}.png"
        r = subprocess.run(
            resolve_remotion_argv(ov, "still", "Overlay", str(png), f"--frame={f}"),
            cwd=str(ov), capture_output=True, text=True, **NOWIN)
        if r.returncode != 0 or not png.exists():
            raise SystemExit(f"still {f} falhou: {(r.stderr or '')[-400:]}")
    print("  stills do Remotion prontos")

    pub = edit / "remotion" / "public"
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8-sig"))
    total = int(timeline_from_edit_data(ed)["durationInFrames"])   # ver armadilha 1
    r = Renderizador(pub, ed, frames=total, fps=30.0)
    proprio = {}
    for f in quadros:
        buf = np.zeros((r.h, r.w, 4), dtype=np.uint8)
        sujo, primeira = [0, 0, 0, 0], True
        for leg in r.camadas:
            if leg.inicio_f <= f <= leg.fim_f:
                r.desenhar(leg, f - leg.inicio_f, buf, sujo, not primeira)
                primeira = False
        proprio[f] = float(buf[..., 3].sum())
    print(f"  motor proprio pronto ({total} quadros de composicao)\n")

    print(f"  {'quadro':>7} {'Remotion':>13} {'proprio':>13} {'razao':>7}")
    piores = []
    for f in quadros:
        a = float(np.asarray(Image.open(TRAB / f"rem_{f:05d}.png")
                             .convert("RGBA"))[..., 3].sum())
        razao = proprio[f] / a if a else 0.0
        piores.append(razao)
        print(f"  {f:>7} {a:>13.0f} {proprio[f]:>13.0f} {razao:>7.3f}")
    fora = [x for x in piores if abs(x - 1.0) > 0.05]
    print(f"\n{'FORA da margem de 5%: ' + str(len(fora)) if fora else 'todos dentro de 5%'}")


if __name__ == "__main__":
    main()
