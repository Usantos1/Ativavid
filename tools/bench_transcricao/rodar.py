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
from tools.bench_transcricao.motores import Saida             # noqa: E402
from tools.bench_transcricao.discordancia import encontrar    # noqa: E402
from tools.bench_transcricao.motores import MotorIndisponivel  # noqa: E402

CENARIOS = ["scribe", "whisper_local", "gemini_audio", "whisper_gemini",
            "whisper_gemini_texto"]


def _planejar_cortes(prontos: dict, video: Path, destino: Path) -> dict:
    """Roda o planejador de produção sobre CADA transcript.

    Não se espera plano idêntico entre motores — a pergunta é quanto o
    transcript influencia a edição final. `divergencia` responde isso: 0.0
    seria o mesmo vídeo, 1.0 seria nenhum segundo em comum.

    NÃO diz qual edição é melhor. O plano do Whisper é só o ponto de
    comparação, por ser o que o produto usa hoje; julgar qualidade de corte
    exige validação humana separada, fora deste benchmark.
    """
    from tools.bench_transcricao.impacto import divergencia_do_plano, planejar

    planos, saida_json = {}, {}
    for nome, r in prontos.items():
        c = planejar(r, video, destino / "cortes" / nome)
        planos[nome] = c
        saida_json[nome] = {"n": c.n, "duracao_s": c.duracao_s,
                            "trechos": c.trechos, "erro": c.erro}
    base = planos.get("whisper_local")
    if base is not None and not base.erro:
        for nome, c in planos.items():
            if not c.erro:
                saida_json[nome]["divergencia"] = divergencia_do_plano(c, base)
    return saida_json


def _ja_feito(caminho: Path) -> Saida | None:
    """Resultado válido de uma rodada anterior, se houver.

    Uma rodada completa leva horas de GPU e queima cota paga de API. Morrer no
    vídeo 6 e ter de refazer os cinco primeiros é caro o bastante para valer
    esta checagem — e o cache de transcrição está DESLIGADO de propósito
    (medição a frio), então sem isto a repetição seria integral.
    """
    if not caminho.is_file():
        return None
    try:
        r = Saida.de_json(json.loads(caminho.read_text(encoding="utf-8")))
    except (ValueError, KeyError):
        return None
    # Motor sem palavra e sem texto é rodada abortada, não resultado.
    return r if (r.palavras or r.texto.strip()) else None


def _um_video(item: dict, saida: Path, so: list[str] | None,
              modelo: str, cortes: bool = False,
              refazer: bool = False) -> dict:
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
        if not refazer:
            anterior = _ja_feito(destino / f"{nome}.json")
            if anterior is not None:
                prontos[nome] = anterior
                estado[nome] = (f"reaproveitado  {len(anterior.palavras)} "
                                f"palavras (use --refazer para repetir)")
                return anterior
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

    if cortes and prontos:
        try:
            planos = _planejar_cortes(prontos, video, trabalho)
            (destino / "_cortes.json").write_text(
                json.dumps(planos, ensure_ascii=False, indent=2),
                encoding="utf-8")
            estado["_cortes"] = "  ".join(
                f"{n}={p['n']}" for n, p in planos.items() if not p.get("erro")
            ) or "nenhum plano (sem sessão de IA?)"
        except Exception as e:  # noqa: BLE001
            estado["_cortes"] = f"ERRO: {type(e).__name__}: {e}"

    # Pontos de divergência + página de validação humana.
    if "whisper_local" in prontos:
        pontos = encontrar({n: r.palavras for n, r in prontos.items()
                            if r.palavras})
        if pontos:
            from tools.bench_transcricao.gemini_sessao import extrair_audio

            try:
                audio = extrair_audio(video, trabalho / "audio")
            except Exception as e:  # noqa: BLE001
                # Cair para o vídeo original em SILÊNCIO era o pior defeito
                # possível aqui: a página abre normal, o botão "ouvir" não dá
                # som nenhum (o navegador não toca .MOV/HEVC), e a pessoa fica
                # olhando para uma tela que parece funcionar. Sem áudio não há
                # validação, e sem validação não há benchmark.
                audio = video
                estado["_audio"] = (
                    f"AVISO: não deu para extrair o áudio "
                    f"({type(e).__name__}: {e}). A página vai apontar para o "
                    f"vídeo original e o navegador pode não tocar — se o "
                    f"botão ouvir ficar mudo, é isto.")
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
    ap.add_argument("--refazer", action="store_true",
                    help="ignorar resultados de rodadas anteriores")
    ap.add_argument("--cortes", action="store_true",
                    help="planejar cortes a partir de cada transcript "
                         "(exige sessão de IA ativa)")
    a = ap.parse_args()

    corpus_p = Path(a.corpus)
    if not corpus_p.is_file():
        print(f"corpus não encontrado: {corpus_p}\n"
              f"Veja tools/bench_transcricao/README.md — são ≥ 8 vídeos reais.",
              file=sys.stderr)
        return 2

    corpus = json.loads(corpus_p.read_text(encoding="utf-8"))
    saida = Path(a.saida)
    sintetico = bool(corpus.get("sintetico")) or any(
        v.get("sintetico") for v in corpus["videos"])
    if sintetico:
        print("CORPUS SINTÉTICO: serve para validar o harness. O relatório "
              "final vai RECUSAR este material — a matriz que decide produção "
              "usa só vídeo real do ATIVAVID.\n")
    relatorio: dict[str, dict] = {}

    for item in corpus["videos"]:
        print(f"\n== {item['id']}  {item.get('tags', '')}")
        estado = _um_video(item, saida, a.so, a.modelo, a.cortes, a.refazer)
        relatorio[item["id"]] = estado
        for k, v in estado.items():
            print(f"   {k:22s} {v}")

    saida.mkdir(parents=True, exist_ok=True)
    (saida / "estado.json").write_text(json.dumps(
        {"_sintetico": sintetico, "videos": relatorio},
        ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for m in relatorio.values()
             for k, v in m.items()
             if not k.startswith("_")
             and (v.startswith("ok") or v.startswith("reaproveitado")))
    alvo = sum(1 for m in relatorio.values()
               for k in m if not k.startswith("_"))
    print(f"\n{ok} de {alvo} execuções bem-sucedidas.")
    if ok:
        print(f"Abra as páginas em {saida / 'validacao'} para criar a "
              f"referência humana, depois rode relatorio.py.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
