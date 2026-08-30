# -*- coding: utf-8 -*-
"""Varre o catálogo de desenhos contra o Remotion e diz quem saiu da faixa.

O ATIVAVID tem DOIS motores que desenham a mesma coisa: o template Remotion
(a referência, em `assets/shortform/src`) e o motor próprio
(`app/render_proprio.py`), que faz ~79% dos vídeos sem abrir o Chrome.
Nenhum teste de código percebe quando os dois divergem — o vídeo sai, só
sai diferente.

Em 30/08/2026 esta varredura achou NOVE defeitos, todos em desenhos
aprovados meses antes e nunca remedidos:

    bolha sem sombra                 0,743 -> 0,964
    karaokê com duas legendas        2,557 -> 1,010
    sublinhado                       1,152 -> 1,008
    manchete (barra fora da tarja)   0,885 -> 1,031
    vazado (meio borrão)             0,856 -> 1,059
    gradiente (meio borrão)          0,815 -> 1,055
    bolha com a letra 900 em vez de 400
    legenda DESLIGADA era desenhada
    b-roll/card final sumindo com a legenda desligada

COMO LER O NÚMERO
    É a razão da TINTA: quantos pixels o motor próprio pinta, dividido pelo
    que o template pinta, no mesmo quadro. Faixa saudável **0,93 a 1,10**.
    Ela pega falta de área — sombra faltando, camada dobrada, borrão pela
    metade. Ela NÃO pega forma, cor nem posição: para isso, o par de quadros
    que a varredura salva ao lado é que responde. (O neon já saiu PRETO com
    a razão em 1,003.)

    Em desenho de ÁREA CHEIA (camada de layout, escurecimento do card final)
    a razão é cega — os dois lados dão a mesma contagem. Ali vale a
    diferença média de alfa e de cor, que este script também imprime.

O QUE PRECISA
    Um projeto já renderizado, com `edit/remotion` montado e node_modules.
    Passe a pasta em `--projeto`. O script NÃO altera o projeto: ele copia
    o `edit-data.json`, mexe na cópia e devolve o original no fim.

USO
    python tools/varrer_desenho.py --projeto <pasta do edit> legendas
    python tools/varrer_desenho.py --projeto <pasta do edit> headlines
    python tools/varrer_desenho.py --projeto <pasta do edit> layouts
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAIXA = (0.93, 1.10)
JANELA = (120, 260)          # quadros de fala contínua no projeto de teste
NOWIN = ({"creationflags": subprocess.CREATE_NO_WINDOW}
         if hasattr(subprocess, "CREATE_NO_WINDOW") else {})


def _quadros(mov: Path, n: int, larg: int, alt: int):
    import numpy as np

    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(mov), "-f", "rawvideo",
         "-pix_fmt", "rgba", "-"], stdout=subprocess.PIPE, **NOWIN)
    tam = larg * alt * 4
    out = []
    while len(out) < n:
        b = p.stdout.read(tam)
        if len(b) < tam:
            break
        out.append(np.frombuffer(b, dtype=np.uint8).reshape(alt, larg, 4))
    p.stdout.close()
    p.wait()
    return out


def _catalogo(grupo: str) -> list[str]:
    """Os ids que a TELA oferece — a lista que o usuário vê é a que importa."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index(f"  {grupo}: [")
    fim = js.index("\n  ],", i)
    return [x for x in re.findall(r"\{id: '([a-z0-9]+)'", js[i:fim])
            if x != "nenhuma"]


def _monta(rend, f: int, larg: int, alt: int):
    """Um quadro do motor próprio — com o `dim`, que é um passo à parte.

    Sem ele o card final mede 0,087: o template escurece a tela inteira e
    aqui sairia só o texto.
    """
    import numpy as np

    buf = (rend.fundo.copy() if rend.fundo is not None
           else np.zeros((alt, larg, 4), dtype=np.uint8))
    sujo = [0, 0, 0, 0]
    primeira = rend.fundo is None
    for leg in rend.camadas:
        if leg.inicio_f <= f <= leg.fim_f:
            if leg.dim:
                rend._aplicar_dim(buf, sujo, leg.dim, f - leg.inicio_f,
                                  leg.dim_fade)
                primeira = False
            rend.desenhar(leg, f - leg.inicio_f, buf, sujo,
                          mesclar=not primeira)
            primeira = False
    return buf


def varrer(edit: Path, grupo: str) -> int:
    import numpy as np
    from PIL import Image

    from app.render_proprio import Renderizador
    from app.video_layouts import CAMADA
    from app.win_process import resolve_remotion_argv

    ov = edit / "remotion"
    pub = ov / "public"
    if not (pub / "edit-data.json").exists():
        print(f"não achei {pub / 'edit-data.json'}")
        return 2

    backup = (pub / "edit-data.json").read_text(encoding="utf-8-sig")
    base = json.loads(backup)
    larg = int(base.get("width") or 1080)
    alt = int(base.get("height") or 1920)
    fps = float(base.get("fps") or 30.0)
    A, B = JANELA

    itens = {"legendas": lambda: _catalogo("captions"),
             "headlines": lambda: _catalogo("headlines"),
             "layouts": lambda: list(CAMADA)}[grupo]()
    print(f"varrendo {len(itens)} de {grupo}: {' '.join(itens)}\n")
    fora = []
    try:
        for nome in itens:
            ed = json.loads(json.dumps(base))
            ed["transitions"] = []
            ed["hook"] = dict(ed.get("hook") or {}, enabled=grupo == "headlines")
            ed["endCard"] = dict(ed.get("endCard") or {}, enabled=False)
            ed["captions"] = dict(ed.get("captions") or {},
                                  enabled=grupo == "legendas")
            if grupo == "legendas":
                ed["captions"]["style"] = nome
            elif grupo == "headlines":
                ed["hook"]["style"] = nome
                ed["hook"]["endSec"] = 12.0
            else:
                ed["videoLayout"] = nome
            (pub / "edit-data.json").write_text(
                json.dumps(ed, ensure_ascii=False), encoding="utf-8")

            rm = edit / f".varredura_rm_{nome}.mov"
            cmd = resolve_remotion_argv(
                ov, "render", "Overlay", str(rm), f"--frames={A}-{B - 1}",
                "--codec", "prores", "--prores-profile", "4444",
                "--image-format", "png", "--pixel-format", "yuva444p10le")
            t0 = time.perf_counter()
            r = subprocess.run(cmd, cwd=str(ov), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", **NOWIN)
            if r.returncode != 0 or not rm.exists():
                print(f"  {nome:12s} FALHOU o Remotion")
                fora.append(nome)
                continue
            t_rm = time.perf_counter() - t0

            rend = Renderizador(pub, ed, frames=B, fps=fps,
                                width=larg, height=alt)
            ns = edit / f".varredura_ns_{nome}.mov"
            ff = subprocess.Popen(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "rawvideo", "-pix_fmt", "rgba", f"-s", f"{larg}x{alt}",
                 "-r", f"{fps:g}", "-i", "-", "-c:v", "qtrle", str(ns)],
                stdin=subprocess.PIPE, **NOWIN)
            t0 = time.perf_counter()
            for f in range(A, B):
                ff.stdin.write(_monta(rend, f, larg, alt).tobytes())
            ff.stdin.close()
            ff.wait()
            t_ns = time.perf_counter() - t0

            qr = _quadros(rm, B - A, larg, alt)
            qn = _quadros(ns, B - A, larg, alt)
            m = min(len(qr), len(qn))
            if not m:
                print(f"  {nome:12s} sem quadros")
                fora.append(nome)
                continue
            tr = np.array([(qr[i][..., 3] > 8).sum() for i in range(m)],
                          dtype=float)
            tn = np.array([(qn[i][..., 3] > 8).sum() for i in range(m)],
                          dtype=float)
            com = tr > 500
            if not com.any():
                print(f"  {nome:12s} o template não desenhou nada")
                fora.append(nome)
                continue
            razao = float(np.median(tn[com] / np.maximum(tr[com], 1)))
            i = int(np.argmax(tr))
            a, b = qr[i], qn[i]
            aa, ab = a[..., 3].astype(np.int16), b[..., 3].astype(np.int16)
            uniao = (aa > 8) | (ab > 8)
            d_alfa = float(np.abs(aa - ab)[uniao].mean()) if uniao.any() else 0.0
            ok = FAIXA[0] <= razao <= FAIXA[1]
            print(f"  {nome:12s} tinta {razao:.3f}  d_alfa {d_alfa:5.1f}  "
                  f"| Remotion {t_rm:.1f}s vs nosso {t_ns:.1f}s"
                  f"{'' if ok else '   <- FORA'}")
            if not ok:
                fora.append(nome)
            par = Image.new("RGB", (larg, alt // 2), (26, 26, 26))
            for k, q in enumerate((a, b)):
                im = Image.fromarray(q, "RGBA").resize((larg // 2, alt // 2))
                par.paste(im, (k * (larg // 2), 0), im)
            par.save(edit / f".varredura_par_{nome}.png")
            rm.unlink(missing_ok=True)
            ns.unlink(missing_ok=True)
    finally:
        (pub / "edit-data.json").write_text(backup, encoding="utf-8")
        print("\nedit-data devolvido ao original")

    if fora:
        print("FORA DA FAIXA (olhe `.varredura_par_<nome>.png` antes de "
              "concluir — a razão de tinta não vê forma nem cor):")
        for nome in fora:
            print(f"  {nome}")
        return 1
    print(f"todos dentro de {FAIXA[0]}–{FAIXA[1]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("grupo", choices=["legendas", "headlines", "layouts"])
    ap.add_argument("--projeto", required=True, type=Path,
                    help="a pasta `edit` de um projeto já renderizado")
    a = ap.parse_args()
    return varrer(a.projeto, a.grupo)


if __name__ == "__main__":
    raise SystemExit(main())
