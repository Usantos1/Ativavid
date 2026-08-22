# -*- coding: utf-8 -*-
"""O que dá para saber assim que a rodada termina, sem referência humana.

A matriz final espera alguém ouvir os trechos divergentes. Isso leva tempo, e
enquanto não acontece a rodada fica parecendo que não produziu nada. Produziu:

  **concordância entre motores** — quem se parece com quem. Não diz quem está
  certo (dois motores podem errar igual), mas já mostra se algum está fora da
  curva, e quanto trabalho de ouvido vem pela frente.

  **quanto o cenário D mexeu** — correções propostas, aplicadas, recusadas por
  âncora ou confiança, e se a linha do tempo do Whisper sobreviveu. Isto NÃO
  precisa de referência humana: é verificável sozinho, e é a condição de
  eliminação do cenário D. Se ele mexeu no tempo, perdeu, com WER nenhum.

  **saúde do karaokê** — quanto a produção teve de reparar em cada transcript.
  Também independe de referência.

  **esforço de validação** — quantos trechos e quantas palavras vão precisar de
  ouvido, por vídeo.

    python tools/bench_transcricao/preliminar.py --saida bench/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.bench_transcricao.alinhar import chave              # noqa: E402
from tools.bench_transcricao.discordancia import encontrar     # noqa: E402
from tools.bench_transcricao.impacto import conferir_karaoke   # noqa: E402
from tools.bench_transcricao.metricas import levenshtein_ops   # noqa: E402
from tools.bench_transcricao.motores import Saida              # noqa: E402


def concordancia(a: Saida, b: Saida) -> float | None:
    """Fração de palavras iguais entre dois motores.

    Simétrica de propósito: nenhum dos dois é referência aqui.
    """
    ta = [chave(p.texto) for p in a.palavras] or \
         [chave(t) for t in a.texto.split()]
    tb = [chave(p.texto) for p in b.palavras] or \
         [chave(t) for t in b.texto.split()]
    if not ta or not tb:
        return None
    c, _ = levenshtein_ops(ta, tb)
    return 2 * c.hits / (len(ta) + len(tb))


def carregar(pasta: Path) -> dict[str, Saida]:
    out = {}
    for f in sorted(pasta.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            out[f.stem] = Saida.de_json(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, KeyError):
            continue
    return out


def _tabela(titulo: str, cab: list[str], linhas: list[list[str]]) -> str:
    larg = [max(len(cab[i]), *(len(l[i]) for l in linhas)) if linhas
            else len(cab[i]) for i in range(len(cab))]
    out = [f"\n## {titulo}\n"]
    out.append("| " + " | ".join(c.ljust(larg[i]) for i, c in enumerate(cab)) + " |")
    out.append("| " + " | ".join("-" * larg[i] for i in range(len(cab))) + " |")
    for l in linhas:
        out.append("| " + " | ".join(l[i].ljust(larg[i]) for i in range(len(cab))) + " |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="bench")
    a = ap.parse_args()
    saida = Path(a.saida)
    if not saida.is_dir():
        print(f"não existe: {saida}", file=sys.stderr)
        return 2

    videos = sorted(p for p in saida.iterdir()
                    if p.is_dir() and p.name != "validacao")
    if not videos:
        print("nenhum vídeo processado ainda.")
        return 2

    print(f"# Preliminar — {len(videos)} vídeo(s), sem referência humana\n")
    print("Nada aqui diz quem está CERTO: dois motores podem errar igual. "
          "Diz quem\nestá fora da curva, quanto ouvido humano falta, e as "
          "duas coisas que se\nverificam sozinhas — se o cenário D respeitou "
          "o tempo do Whisper, e quanto\na produção teve de reparar cada "
          "legenda.")

    # ------------------------------------------------------- concordância
    pares: dict[tuple[str, str], list[float]] = {}
    esforco: list[list[str]] = []
    d_linhas: list[list[str]] = []
    k_linhas: list[list[str]] = []

    for v in videos:
        m = carregar(v)
        if not m:
            continue
        nomes = sorted(m)
        for i, x in enumerate(nomes):
            for y in nomes[i + 1:]:
                c = concordancia(m[x], m[y])
                if c is not None:
                    pares.setdefault((x, y), []).append(c)

        base = m.get("whisper_local")
        if base is not None:
            pontos = encontrar({n: s.palavras for n, s in m.items() if s.palavras})
            palavras = sum(len(p.indices) for p in pontos)
            total = len(base.palavras) or 1
            esforco.append([v.name, str(len(pontos)), str(palavras),
                            f"{100 * palavras / total:.1f}%",
                            "sim" if (saida / "validacao" /
                                      f"validacao_{v.name}.json").is_file()
                            else "não"])

        for nome, s in m.items():
            if nome.startswith("whisper_gemini"):
                meta = s.meta
                d_linhas.append([
                    v.name, nome,
                    str(meta.get("correcoes_propostas", "—")),
                    str(meta.get("correcoes_aplicadas", "—")),
                    str(len(meta.get("correcoes_ignoradas") or [])),
                    str(meta.get("insercoes_recusadas", "—")),
                    "SIM" if meta.get("linha_do_tempo_preservada") else "NÃO",
                ])
            if s.granularidade == "palavra" and s.palavras:
                k = conferir_karaoke(s)
                k_linhas.append([v.name, nome, str(k.palavras_reparadas),
                                 f"{k.deslocamento_maximo_ms:.0f} ms",
                                 "intacto" if k.intacto else "reparado"])

    if pares:
        linhas = [[x, y, f"{100 * sum(v) / len(v):.1f}%", str(len(v))]
                  for (x, y), v in sorted(pares.items(),
                                          key=lambda kv: -sum(kv[1]) / len(kv[1]))]
        print(_tabela("Concordância entre motores",
                      ["motor A", "motor B", "palavras iguais", "vídeos"], linhas))

    if esforco:
        print(_tabela("Esforço de validação humana",
                      ["vídeo", "trechos", "palavras", "% do total",
                       "já validado"], esforco))
        tot_t = sum(int(l[1]) for l in esforco)
        tot_p = sum(int(l[2]) for l in esforco)
        print(f"\nTotal: {tot_t} trechos, {tot_p} palavras para ouvir. "
              f"A ~8 s por trecho, cerca de {tot_t * 8 / 60:.0f} min de "
              f"trabalho humano.")

    if d_linhas:
        print(_tabela("Cenário D/E — o que o revisor mexeu",
                      ["vídeo", "cenário", "propostas", "aplicadas",
                       "ignoradas", "inserções recusadas",
                       "tempo do Whisper preservado"], d_linhas))
        quebrou = [l for l in d_linhas if l[-1] == "NÃO"]
        if quebrou:
            print(f"\n⚠ {len(quebrou)} caso(s) em que a linha do tempo NÃO "
                  f"sobreviveu. Isso elimina o cenário sozinho — o alinhador "
                  f"deveria ter levantado antes; investigar.")
        else:
            print("\nA linha do tempo do Whisper sobreviveu em todos os casos.")

    if k_linhas:
        print(_tabela("Karaokê — quanto a produção teve de reparar",
                      ["vídeo", "motor", "palavras reparadas",
                       "pior deslocamento", "estado"], k_linhas))
        print("\nReparo é a palavra saindo de cima do áudio: na tela continua "
              "bonito e\nacende fora da hora. Zero é o que se espera de um "
              "transcript bom.")

    print(f"\n---\nPara a matriz final, valide os trechos em "
          f"{saida / 'validacao'} e rode relatorio.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
