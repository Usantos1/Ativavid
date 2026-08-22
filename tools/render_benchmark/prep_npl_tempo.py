"""Impacto de npl=150 no prep REAL: tempo, GPU, tamanho e cache.

Chama a funcao de producao (`helpers.render.prepared_source`), nao uma copia
do comando — se o pipeline mudar, esta medicao muda junto. A fonte e copiada
para uma pasta de trabalho porque o prep grava `<fonte>.prep.mp4` ao lado do
original, e medir nao pode sujar os projetos do usuario.

Cada npl roda N vezes; reporta a MEDIANA, porque trabalho de GPU nesta maquina
varia ate 2,3x entre execucoes identicas.

Uso:
    py tools/render_benchmark/prep_npl_tempo.py --rodadas 2
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HELPERS = REPO / "helpers"
for p in (str(REPO), str(HELPERS)):
    if p not in sys.path:
        sys.path.insert(0, p)

for _f in (sys.stdout, sys.stderr):
    if hasattr(_f, "reconfigure"):
        try:
            _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

import render as R  # noqa: E402  (helpers/render.py — o modulo de producao)


def _camada1():
    """Carrega camada1_master.py por CAMINHO.

    `tools/render_benchmark` nao e pacote (sem __init__.py), entao
    `from tools.render_benchmark...` depende de namespace package e do cwd —
    e falhou exatamente assim ao rodar por wrapper de outro diretorio.
    """
    import importlib.util

    alvo = Path(__file__).with_name("camada1_master.py")
    spec = importlib.util.spec_from_file_location("camada1_master", alvo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_C1 = _camada1()

SAIDA = REPO / "tools" / "render_benchmark" / "results"
TRABALHO = SAIDA / "_prep_npl"
FONTE = Path(r"E:\ATIVAVID\Projetos\20260814-221753_IMG_1631_b572dfbd8e\IMG_1631.MOV")

# A cadeia de producao, com npl aberto. Precisa bater LETRA A LETRA com
# helpers/render.py:471 fora o npl — senao a medicao seria de outra coisa.
def cadeia(npl: int) -> str:
    return (
        f"zscale=t=linear:npl={npl},"
        "format=gbrpf32le,"
        "zscale=p=bt709,"
        "tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,"
        "format=yuv420p"
    )


class Amostrador(threading.Thread):
    """Le utilizacao de GPU e VRAM enquanto o prep roda."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.parar = threading.Event()
        self.gpu: list[float] = []
        self.mem: list[float] = []

    def run(self) -> None:
        while not self.parar.is_set():
            try:
                r = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=8)
                linha = (r.stdout or "").strip().splitlines()[0]
                g, m = [x.strip() for x in linha.split(",")]
                self.gpu.append(float(g))
                self.mem.append(float(m))
            except Exception:  # noqa: BLE001
                pass
            self.parar.wait(1.0)


def stats_de_luz(arq: Path) -> dict:
    """Reusa a analise da camada 1 para provar que a cor saiu como previsto."""
    return _C1.estatisticas_de_luz(arq)


def mede(npl: int, rodadas: int, scale: str, grade: str) -> dict:
    original = R.TONEMAP_CHAIN
    R.TONEMAP_CHAIN = cadeia(npl)
    try:
        fonte = TRABALHO / f"npl{npl}_{FONTE.name}"
        if not fonte.exists():
            shutil.copy2(FONTE, fonte)

        chaves, tempos, gpus, mems = [], [], [], []
        prep_path = None
        for i in range(rodadas):
            # limpa o cache para medir a GERACAO, nao o hit
            for lixo in (fonte.with_suffix(fonte.suffix + ".prep.mp4"),
                         fonte.with_suffix(fonte.suffix + ".prepkey")):
                lixo.unlink(missing_ok=True)

            am = Amostrador()
            am.start()
            t0 = time.perf_counter()
            prep_path = R.prepared_source(fonte, scale, grade, quiet=True)
            dt = time.perf_counter() - t0
            am.parar.set()
            am.join(timeout=4)

            if prep_path is None:
                raise RuntimeError("prepared_source devolveu None (fonte nao e HDR?)")
            tempos.append(dt)
            if am.gpu:
                gpus.append(statistics.mean(am.gpu))
                mems.append(max(am.mem))
            chaves.append(fonte.with_suffix(fonte.suffix + ".prepkey").read_text(
                encoding="utf-8").strip())
            print(f"     rodada {i+1}/{rodadas}: {dt:.1f}s", flush=True)

        # e o HIT de cache, para confirmar que a segunda chamada reaproveita
        t0 = time.perf_counter()
        again = R.prepared_source(fonte, scale, grade, quiet=True)
        t_hit = time.perf_counter() - t0

        return {
            "npl": npl,
            "segundos_mediana": round(statistics.median(tempos), 1),
            "segundos_todas": [round(t, 1) for t in tempos],
            "hit_de_cache_s": round(t_hit, 3),
            "hit_reaproveitou": bool(again and Path(again) == Path(prep_path)),
            "gpu_media_pct": round(statistics.mean(gpus), 1) if gpus else None,
            "vram_pico_mb": round(max(mems)) if mems else None,
            "prep_mb": round(Path(prep_path).stat().st_size / 1048576, 1),
            "chave": chaves[0],
            "chave_estavel": len(set(chaves)) == 1,
            "luz": stats_de_luz(Path(prep_path)),
        }
    finally:
        R.TONEMAP_CHAIN = original


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodadas", type=int, default=2)
    ap.add_argument("--forcar", action="store_true")
    args = ap.parse_args()

    ocupada = [p for p in _C1.maquina_ocupada() if "prep_npl" not in p.lower()]
    if ocupada and not args.forcar:
        print("MAQUINA OCUPADA - medir agora da numero inflado. Rodando:")
        for p in ocupada[:6]:
            print("  ", p)
        return 2

    if not FONTE.exists():
        print(f"fonte nao existe: {FONTE}")
        return 1
    TRABALHO.mkdir(parents=True, exist_ok=True)

    # os mesmos argumentos que o pipeline passa no caminho de reels vertical
    scale = "scale=-2:1920"
    grade = ""

    print(f"fonte  : {FONTE.name} ({FONTE.stat().st_size/1048576:.0f} MB)")
    print(f"scale  : {scale} | grade: {grade or '(vazio)'}")
    print(f"rodadas: {args.rodadas} (mediana)\n")

    res = []
    for npl in (100, 150):
        print(f"-- npl={npl}")
        res.append(mede(npl, args.rodadas, scale, grade))
        r = res[-1]
        print(f"   mediana {r['segundos_mediana']}s | GPU {r['gpu_media_pct']}% "
              f"| VRAM {r['vram_pico_mb']} MB | prep {r['prep_mb']} MB")
        print(f"   chave {r['chave']} | hit {r['hit_de_cache_s']}s "
              f"(reaproveitou: {r['hit_reaproveitou']})\n")

    a, b = res[0], res[1]
    delta = b["segundos_mediana"] - a["segundos_mediana"]
    pct = (delta / a["segundos_mediana"] * 100) if a["segundos_mediana"] else 0
    print("=" * 66)
    print(f"tempo    : {a['segundos_mediana']}s -> {b['segundos_mediana']}s "
          f"({delta:+.1f}s, {pct:+.1f}%)")
    print(f"tamanho  : {a['prep_mb']} MB -> {b['prep_mb']} MB")
    print(f"cache    : chave {'MUDOU' if a['chave'] != b['chave'] else 'NAO MUDOU (!)'}")
    print(f"luma     : {a['luz']['luma_media']} -> {b['luz']['luma_media']}")
    print(f"clip>=235: {a['luz']['frac_clip_teto_235']:.4f} -> {b['luz']['frac_clip_teto_235']:.4f}")

    rel = SAIDA / "prep_npl_tempo.json"
    rel.write_text(json.dumps({"fonte": str(FONTE), "scale": scale,
                               "rodadas": args.rodadas, "resultados": res},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nrelatorio: {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
