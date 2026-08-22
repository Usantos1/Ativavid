# -*- coding: utf-8 -*-
"""Corpus sintético para VALIDAR O HARNESS — não para julgar motor.

PARA QUE SERVE. Antes de gastar uma noite de GPU e cota de API nos vídeos
reais, é bom saber que o harness roda inteiro: motor → discordância → página
de validação → matriz. Este módulo gera fala com `espeak-ng` em pt-BR e sabe,
por construção, o texto exato de cada clipe — então dá para conferir se o WER,
as categorias e o alinhamento respondem o que deveriam.

PARA QUE **NÃO** SERVE. Voz sintética não tem prosódia natural, hesitação,
sobreposição de locutores nem a acústica de uma gravação de celular. Um WER
medido aqui não diz NADA sobre a qualidade de nenhum motor no material do
usuário. Quem decide o benchmark são os vídeos reais; isto é teste de encanamento.

Os textos cobrem de propósito o que as métricas de produto medem: gírias e
contrações (`cê`, `tá`, `tô`, `né`, `pra`), marcas, números e nomes próprios.

    python tools/bench_transcricao/corpus_sintetico.py --saida bench/sintetico
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# (id, tags, texto). O texto é a referência exata — é isto que foi mandado
# para o sintetizador, então não há dúvida sobre o que "foi falado".
CLIPES: list[tuple[str, list[str], str]] = [
    ("s01", ["uma_pessoa", "coloquial_br", "girias"],
     "Cê tá ligado que eu tô falando sério, né mano. "
     "Pra mim isso aí não faz sentido nenhum."),
    ("s02", ["marcas", "nomes_proprios"],
     "A gente fechou com a PrimeCamp semana passada. "
     "O Rafael da ATIVAVID vai cuidar da parte técnica."),
    ("s03", ["numeros"],
     "Foram quinze mil reais no primeiro mês. "
     "A meta pra dois mil e vinte e seis é três mil e quinhentos por semana."),
    ("s04", ["coloquial_br", "pausas"],
     "Então… deixa eu ver aqui. "
     "Tipo assim, ó, o negócio é o seguinte."),
    ("s05", ["fala_rapida", "girias"],
     "Bora que bora, tamo junto, cê vai gostar demais disso aqui, confia."),
    ("s06", ["nomes_proprios", "numeros", "coloquial_br"],
     "O Anderson mandou de Belo Horizonte umas duzentas unidades. "
     "Chegou tudo certinho, tá?"),
]

# Variações acústicas aplicadas com ffmpeg. Cada uma vira um clipe próprio,
# para o relatório poder dizer ONDE cada motor sofre em vez de dar só média.
VARIACOES: dict[str, list[str]] = {
    "limpo": [],
    "ruido": ["-filter_complex",
              "anoisesrc=color=brown:amplitude=0.06[n];"
              "[0:a][n]amix=inputs=2:duration=first"],
    "musica_fundo": ["-filter_complex",
                     "sine=frequency=220:sample_rate=16000[m];"
                     "[m]volume=0.10[mv];[0:a][mv]amix=inputs=2:duration=first"],
    "fala_baixa": ["-af", "volume=0.22"],
}


def _espeak(texto: str, destino: Path, wpm: int) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["espeak-ng", "-v", "pt-br", "-s", str(wpm),
                    "-w", str(destino), texto], check=True,
                   capture_output=True)


def _ffmpeg(entrada: Path, destino: Path, filtros: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada),
                    *filtros, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                    str(destino)], check=True, capture_output=True)


def gerar(saida: Path, wpm: int = 150) -> Path:
    bruto = saida / "_bruto"
    midia = saida / "media"
    midia.mkdir(parents=True, exist_ok=True)

    videos = []
    for cid, tags, texto in CLIPES:
        wav = bruto / f"{cid}.wav"
        _espeak(texto, wav, wpm if "fala_rapida" not in tags else wpm + 70)

        for var, filtros in VARIACOES.items():
            # Só o clipe limpo vira todas as variações; os outros ficariam
            # redundantes e dobrariam o tempo de máquina sem medir nada novo.
            if var != "limpo" and cid != "s01":
                continue
            vid = cid if var == "limpo" else f"{cid}_{var}"
            destino = midia / f"{vid}.wav"
            _ffmpeg(wav, destino, filtros)
            videos.append({
                "id": vid, "video": str(destino.resolve()),
                "tags": tags + ([] if var == "limpo" else [var]),
                "referencia": texto,
                "notas": f"sintético espeak-ng pt-br, variação '{var}'",
            })

    corpus = saida / "corpus.json"
    corpus.write_text(json.dumps({
        "_leia": "CORPUS SINTÉTICO — valida o harness, NÃO julga motor. "
                 "Voz de espeak-ng não representa o material real do usuário.",
        "videos": videos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # A referência já é conhecida: grava no formato que o relatório espera,
    # para dar para medir WER sem passar pela validação humana.
    ref = saida / "referencia"
    ref.mkdir(parents=True, exist_ok=True)
    for v in videos:
        (ref / f"{v['id']}.json").write_text(json.dumps(
            {"video": v["id"], "texto_conhecido": v["referencia"]},
            ensure_ascii=False, indent=2), encoding="utf-8")
    return corpus


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="bench/sintetico")
    ap.add_argument("--wpm", type=int, default=150)
    a = ap.parse_args()
    for exe in ("espeak-ng", "ffmpeg"):
        if subprocess.run(["which", exe], capture_output=True).returncode:
            print(f"falta {exe}", file=sys.stderr)
            return 2
    c = gerar(Path(a.saida), a.wpm)
    d = json.loads(c.read_text(encoding="utf-8"))
    print(f"{len(d['videos'])} clipes em {c.parent / 'media'}")
    print(f"corpus: {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
