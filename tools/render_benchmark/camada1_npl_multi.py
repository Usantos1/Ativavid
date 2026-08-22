"""Valida npl (100/150/203) em varias fontes HLG, cenas diferentes.

Continua a camada 1. Scaler e ordem ja foram decididos e nao se repetem aqui:
bicubic e escalar-antes ficaram, com diferenca de 0,056 e 0,093 VMAF para as
alternativas — ruido perto do limiar de 1 ponto do perceptivel.

O que resta e npl, que nao e questao de fidelidade e sim de aparencia: nenhuma
metrica elege vencedor. O que se mede aqui e o custo de cada escolha —
highlight que estoura de vez (>=235) e o quanto a imagem inteira escurece — em
cenas com desafios diferentes. A decisao continua sendo de quem olha.

Uso:
    py tools/render_benchmark/camada1_npl_multi.py
    py tools/render_benchmark/camada1_npl_multi.py --dur 8
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.render_benchmark.camada1_master import (  # noqa: E402
    CROP,
    acha_regioes,
    estatisticas_de_luz,
    gera,
    maquina_ocupada,
    quadro,
    vf_tonemap_depois,
)

for _f in (sys.stdout, sys.stderr):
    if hasattr(_f, "reconfigure"):
        try:
            _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

SAIDA = REPO / "tools" / "render_benchmark" / "results"
NPLS = (100, 150, 203)

# As cenas foram escolhidas por triagem do material real, nao por sorteio.
# Nenhuma tem ceu aberto: o corpus inteiro do usuario e interior de loja.
FONTES = [
    {"nome": "janela_luz_forte",
     "arq": r"E:\ATIVAVID\Projetos\20260814-205037_Nao_usar_celular_5cb37951f7\Nao_usar_celular.MOV",
     "cena": "loja com porta aberta para a rua (luz de dia contra interior)",
     "inicio": 20.0},
    {"nome": "pele_luz_normal",
     "arq": r"E:\ATIVAVID\Projetos\20260814-221753_IMG_1631_b572dfbd8e\IMG_1631.MOV",
     "cena": "rosto em primeiro plano, iluminacao normal de loja",
     "inicio": 30.0},
    {"nome": "contraste_sombra",
     "arq": r"E:\ATIVAVID\Projetos\20260814-211400_tem_capinha_fb4a44eff8\tem_capinha.MOV",
     "cena": "vitrine iluminada contra interior escuro",
     "inicio": 18.0},
]


def mosaico(dest_dir: Path, prefixo: str, sufixo: str, saida: Path) -> bool:
    from PIL import Image, ImageDraw

    rot = {100: "npl=100 (ATUAL)", 150: "npl=150", 203: "npl=203 (BT.2408)"}
    imgs = []
    for n in NPLS:
        nome = f"{prefixo}_{n}__{sufixo}.png" if sufixo else f"{prefixo}_{n}.png"
        p = dest_dir / nome
        if not p.exists():
            return False
        im = Image.open(p).convert("RGB")
        if not sufixo:                      # quadro inteiro: reduz para caber
            r = 380 / im.width
            im = im.resize((380, int(im.height * r)), Image.LANCZOS)
        imgs.append((n, im))
    w, h = imgs[0][1].size
    cv = Image.new("RGB", (w * len(imgs), h + 34), (18, 18, 20))
    d = ImageDraw.Draw(cv)
    for i, (n, im) in enumerate(imgs):
        cv.paste(im, (i * w, 34))
        d.text((i * w + 8, 10), rot[n], fill=(255, 255, 255))
        if i:
            d.line([(i * w, 0), (i * w, h + 34)], fill=(90, 90, 95), width=2)
    cv.save(saida)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dur", type=float, default=8.0)
    ap.add_argument("--forcar", action="store_true")
    args = ap.parse_args()

    ocupada = maquina_ocupada()
    if ocupada and not args.forcar:
        print("MAQUINA OCUPADA - medir agora da numero inflado. Rodando:")
        for p in ocupada[:6]:
            print("  ", p)
        return 2

    tmp = SAIDA / "_npl_multi"
    tmp.mkdir(parents=True, exist_ok=True)
    quadros_dir = SAIDA / "quadros_npl_multi"
    quadros_dir.mkdir(parents=True, exist_ok=True)

    tudo = []
    for f in FONTES:
        fonte = Path(f["arq"])
        if not fonte.exists():
            print(f"[pulando] nao achei {fonte}")
            continue
        print(f"\n=== {f['nome']} — {f['cena']}")
        print(f"    {fonte.name} @ {f['inicio']}s + {args.dur}s")
        meio = args.dur / 2
        arquivos: dict[int, Path] = {}
        linhas = []
        for npl in NPLS:
            arq = tmp / f"{f['nome']}_{npl}.mp4"
            t = gera(fonte, f["inicio"], args.dur,
                     vf_tonemap_depois(npl, "lanczos"), arq, sem_perda=False)
            arquivos[npl] = arq
            luz = estatisticas_de_luz(arq)
            p = luz["percentis"]
            linhas.append({"npl": npl, "segundos": round(t, 1), **luz})
            print(f"  npl={npl:<4} luma {luz['luma_media']:>6} | p95 {p['p95']:>5} | p99 {p['p99']:>5}"
                  f" | >=235 {luz['frac_clip_teto_235']:.4f} | >=230 {luz['frac_clip_alto_230']:.4f}"
                  f" | <=16 {luz['frac_esmagado_16']:.4f}")

        regioes = acha_regioes(arquivos[150], meio)
        for npl, arq in arquivos.items():
            quadro(arq, meio, quadros_dir / f"{f['nome']}_{npl}.png", regioes)
        feitos = []
        for suf in ("", "luz_forte", "area_clara", "pele"):
            nome = f"mosaico_{f['nome']}" + (f"_{suf}" if suf else "_quadro") + ".png"
            if mosaico(quadros_dir, f["nome"], suf, quadros_dir / nome):
                feitos.append(nome)
        print(f"  regioes: {', '.join(regioes)} | mosaicos: {len(feitos)}")
        tudo.append({"fonte": f["nome"], "cena": f["cena"], "arquivo": str(fonte),
                     "inicio": f["inicio"], "dur": args.dur,
                     "regioes": {k: list(v) for k, v in regioes.items()},
                     "npl": linhas})

    rel = SAIDA / "camada1_npl_multi.json"
    rel.write_text(json.dumps({"crop": CROP, "fontes": tudo}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\nrelatorio: {rel}")
    print(f"quadros  : {quadros_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
