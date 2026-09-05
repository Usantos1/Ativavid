"""Prepara a fonte (escala + tonemap + grade) ANTES do corte — 5.0.74.

E a MESMA funcao, a mesma chave e o mesmo arquivo que o `render.py` usa
dentro do corte (`prepared_source`); o que muda e QUANDO. O pipeline chama
isto ao fim da analise de cada take, e o prep corre em paralelo com o
plano da IA; quando o corte chega, `prepare_sources_parallel` acha o
arquivo pronto (PREPARED_SOURCE HIT) e paga so o que sobrou.

MEDIDO nos jobs reais dele: a fonte preparada e o passo mais caro do corte
numa fonte HDR (o tonemap da fonte inteira), e o corte e 31% do job; o
plano (5,9 s de mediana, 10,8 s nos ultimos 40 jobs) rodava ANTES dele, com
a CPU parada. 63% das fontes dele sao HDR.

Fonte SDR ou grade `auto`: nada a fazer, sai na hora — o corte segue como
sempre. Nunca levanta: um prep que falha aqui e refeito pelo corte.

Uso: prep_source.py <video> --grade-field <marca|filtro|auto> [--sem-nvdec]
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print
import argparse
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--grade-field", default="",
                    help="o campo `grade` que o EDL vai carregar (nome de preset, "
                         "filtro cru ou auto)")
    ap.add_argument("--sem-nvdec", action="store_true",
                    help="varios takes: o NVDEC fica com um so (regra do corte)")
    args = ap.parse_args()

    from render import (  # noqa: E402 — helpers/ esta no PYTHONPATH
        is_hdr_source, is_portrait_source, prepared_source, resolve_grade_filter,
    )

    video = args.video.resolve()
    t0 = time.perf_counter()
    try:
        resolved = resolve_grade_filter(args.grade_field)
        if resolved == "__AUTO__":
            print("PREP_CEDO pulado: grade auto (resolvido por segmento)", flush=True)
            return
        if not is_hdr_source(video):
            print(f"PREP_CEDO pulado: {video.name} nao e HDR", flush=True)
            return
        # EXATAMENTE a regra de `extract_all_segments` — a chave do arquivo
        # preparado embute a escala, e uma escala diferente seria um MISS.
        scale = "scale=-2:1920" if is_portrait_source(video) else "scale=1920:-2"
        pronto = prepared_source(video, scale, resolved,
                                 permitir_nvdec=not args.sem_nvdec)
        print(f"PREP_CEDO {'pronto' if pronto else 'sem fonte preparada'} "
              f"{video.name} em {time.perf_counter() - t0:.1f}s", flush=True)
    except Exception as e:  # noqa: BLE001 — o corte refaz se precisar
        print(f"PREP_CEDO falhou {type(e).__name__}: {str(e)[:160]}", flush=True)


if __name__ == "__main__":
    main()
