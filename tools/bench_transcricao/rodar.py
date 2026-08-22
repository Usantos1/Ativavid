# -*- coding: utf-8 -*-
"""Roda os cinco cenários sobre o corpus e grava tudo em disco.

    python tools/bench_transcricao/rodar.py --corpus corpus.json --saida bench/

Cada cenário que não estiver configurado FALHA EXPLICITAMENTE e é registrado
como não-executado. Nada é estimado: uma célula vazia na matriz final é
informação, uma célula chutada é ruído com aparência de dado.

Ordem dentro de um vídeo: B primeiro, porque D e E dependem dele.

Depois de rodar os motores, gera os pontos de divergência e a página de
validação — é o que transforma "8 vídeos para transcrever à mão" em "N
trechos de 3 segundos para ouvir".
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.bench_transcricao import motores, validar          # noqa: E402
from tools.bench_transcricao.discordancia import encontrar    # noqa: E402
from tools.bench_transcricao.motores import MotorIndisponivel  # noqa: E402

CENARIOS = ["scribe", "whisper_local", "gemini_audio", "whisper_gemini",
            "whisper_gemini_texto"]


def _um_video(item: dict, saida: Path, so: list[str] | None,
              modelo: str) -> dict:
    vid = item["id"]
    video = Path(item["video"]).expanduser()
    destino = saida / vid
    trabalho = destino / "trabalho"
    estado: dict[str, str] = {}
    prontos: dict[str, motores.Saida] = {}

    if not video.is_file():
        return {c: f"FONTE AUSENTE: {video}" for c in CENARIOS}

    def executar(nome: str, fn):
        if so and nome not in so:
            estado[nome] = "pulado"
            return None
        try:
            r = fn()
            r.salvar(destino / f"{nome}.json")
            prontos[nome] = r
            estado[nome] = (f"ok  {r.tempos.get('total', 0):.1f}s  "
                            f"{len(r.palavras)} palavras  "
                            f"granularidade={r.granularidade}")
            return r
        except MotorIndisponivel as e:
            estado[nome] = f"NÃO CONFIGURADO: {e}"
        except Exception as e:  # noqa: BLE001
            estado[nome] = f"ERRO: {type(e).__name__}: {e}"
            traceback.print_exc()
        return None

    base = executar("whisper_local",
                    lambda: motores.whisper_local(video, trabalho, modelo))
    executar("scribe", lambda: motores.scribe(video, trabalho))
    executar("gemini_audio", lambda: motores.gemini_audio(video, trabalho))

    if base is not None:
        executar("whisper_gemini",
                 lambda: motores.whisper_mais_gemini(base, video, trabalho,
                                                     ouvindo=True))
        executar("whisper_gemini_texto",
                 lambda: motores.whisper_mais_gemini(base, video, trabalho,
                                                     ouvindo=False))
    else:
        for n in ("whisper_gemini", "whisper_gemini_texto"):
            estado[n] = "BLOQUEADO: depende do cenário B"

    # Pontos de divergência + página de validação humana.
    if "whisper_local" in prontos:
        pontos = encontrar({n: r.palavras for n, r in prontos.items()
                            if r.palavras})
        if pontos:
            from tools.bench_transcricao.gemini_api import extrair_audio

            try:
                audio = extrair_audio(video, trabalho / "audio")
            except Exception:  # noqa: BLE001
                audio = video          # o player abre o vídeo direto
            pagina = validar.gerar(vid, audio.resolve(), pontos,
                                   saida / "validacao")
            total = sum(len(p.indices) for p in pontos)
            estado["_validacao"] = (
                f"{len(pontos)} trechos ({total} palavras de "
                f"{len(prontos['whisper_local'].palavras)}) → {pagina.name}")
        else:
            estado["_validacao"] = "nenhuma divergência entre os motores"
    return estado


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark de transcrição ATIVAVID")
    ap.add_argument("--corpus", default="corpus.json")
    ap.add_argument("--saida", default="bench")
    ap.add_argument("--modelo", default="medium", help="modelo do cenário B")
    ap.add_argument("--so", nargs="*", choices=CENARIOS,
                    help="rodar só estes cenários")
    a = ap.parse_args()

    corpus_p = Path(a.corpus)
    if not corpus_p.is_file():
        print(f"corpus não encontrado: {corpus_p}\n"
              f"Veja tools/bench_transcricao/README.md — são ≥ 8 vídeos reais.",
              file=sys.stderr)
        return 2

    corpus = json.loads(corpus_p.read_text(encoding="utf-8"))
    saida = Path(a.saida)
    relatorio: dict[str, dict] = {}

    for item in corpus["videos"]:
        print(f"\n== {item['id']}  {item.get('tags', '')}")
        estado = _um_video(item, saida, a.so, a.modelo)
        relatorio[item["id"]] = estado
        for k, v in estado.items():
            print(f"   {k:22s} {v}")

    saida.mkdir(parents=True, exist_ok=True)
    (saida / "estado.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for m in relatorio.values()
             for k, v in m.items() if not k.startswith("_") and v.startswith("ok"))
    alvo = sum(1 for m in relatorio.values()
               for k in m if not k.startswith("_"))
    print(f"\n{ok} de {alvo} execuções bem-sucedidas.")
    if ok:
        print(f"Abra as páginas em {saida / 'validacao'} para criar a "
              f"referência humana, depois rode relatorio.py.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
