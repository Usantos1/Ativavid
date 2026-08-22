# -*- coding: utf-8 -*-
"""Mede os transcripts contra a referência humana e monta a matriz final.

    python tools/bench_transcricao/relatorio.py --saida bench/

Célula sem dado real sai como "sem dado". Nunca estimada: a matriz existe para
decidir uma arquitetura de produção, e um número inventado ali decide errado
com a mesma confiança de um medido.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra                            # noqa: E402
from tools.bench_transcricao.alinhar import chave              # noqa: E402
from tools.bench_transcricao.discordancia import (              # noqa: E402
    encontrar, referencia_por_consenso)
from tools.bench_transcricao.metricas import (                  # noqa: E402
    evaluate_text, levenshtein_ops, tokens)
from tools.bench_transcricao.impacto import conferir_karaoke    # noqa: E402
from tools.bench_transcricao.motores import Saida               # noqa: E402

# TODOS os cenários viram coluna, inclusive os que não rodaram. O leitor
# precisa ver a lacuna (C e D) do lado dos que rodaram, e o E deixou de ser
# "experimento adicional" no momento em que virou um dos três executados —
# esconder a coluna dele tornava o critério principal (tempo humano)
# ilegível justamente para o cenário que disputa a vitória.
COLUNAS = ["scribe", "whisper_local", "gemini_audio", "whisper_gemini",
           "whisper_gemini_texto"]
EXTRA = "whisper_gemini_texto"
ROTULO = {"scribe": "A Scribe", "whisper_local": "B Whisper",
          "gemini_audio": "C Gem.áudio", "whisper_gemini": "D W+Gem.áudio",
          EXTRA: "E W+Gem.texto"}
SD = "sem dado"


def _pct_lista(v: list[float], q: float) -> float:
    s = sorted(v)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _media(v: list) -> float | None:
    v = [float(x) for x in v if x is not None and x == x]
    return sum(v) / len(v) if v else None


def erro_de_timestamp(ref: list[Palavra], hip: list[Palavra]) -> dict | None:
    """Erro de início por palavra, só nas que casam textualmente.

    Palavra trocada ou omitida fica de fora: comparar o tempo de uma palavra
    errada mede sorte, não alinhamento.
    """
    if not ref or not hip:
        return None
    _, ops = levenshtein_ops([chave(p.texto) for p in ref],
                             [chave(p.texto) for p in hip])
    erros = [abs(hip[j].inicio - ref[i].inicio)
             for op, i, j in ops if op == "eq" and i is not None and j is not None]
    if not erros:
        return None
    n = len(erros)
    return {"n": n, "mediana": statistics.median(erros),
            "p90": _pct_lista(erros, 0.90), "p95": _pct_lista(erros, 0.95),
            "pior": max(erros),
            "ate_50ms": sum(e <= .050 for e in erros) / n,
            "ate_100ms": sum(e <= .100 for e in erros) / n,
            "ate_200ms": sum(e <= .200 for e in erros) / n}


def _cortes_do_video(saida: Path, vid: str) -> dict:
    """Planos de corte gravados pelo rodar.py --cortes, se existirem."""
    p = saida / vid / "_cortes.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def tempo_humano_por_motor(saida: Path, vid: str) -> dict[str, dict]:
    """Quanto trabalho humano CADA motor teria custado, medido no relógio.

    A terceira medida do benchmark, e a única que não é proxy:

        WER              precisão textual
        corridas de erro concentração dos erros
        tempo humano     retrabalho real

    Não se misturam. A atribuição é direta: num trecho divergente, o motor que
    propôs o que a pessoa confirmou não teria gerado trabalho nenhum ali; os
    outros teriam custado aquele trecho inteiro — o tempo cronometrado na
    página, e uma intervenção.

    `trocas` e `digitou` vêm da telemetria da página: são intervenção humana
    de verdade, não estimativa.
    """
    dec_p = saida / "validacao" / f"validacao_{vid}.json"
    props_p = saida / "validacao" / f"propostas_{vid}.json"
    if not (dec_p.is_file() and props_p.is_file()):
        return {}

    d = json.loads(dec_p.read_text(encoding="utf-8"))
    decisoes = d.get("decisoes", {})
    tel = d.get("telemetria", {})
    propostas = json.loads(props_p.read_text(encoding="utf-8"))

    out: dict[str, dict] = {}
    for carimbo, por_motor in propostas.items():
        verdade = decisoes.get(carimbo)
        if verdade is None:
            continue                     # não validado: não conta para ninguém
        t = tel.get(carimbo) or {}
        ms = float(t.get("ms") or 0.0)
        for motor, dito in por_motor.items():
            reg = out.setdefault(motor, {"ms": 0.0, "intervencoes": 0,
                                         "pontos": 0, "digitou": 0})
            reg["pontos"] += 1
            if _mesmo(dito, verdade):
                continue                 # acertou: não custaria nada aqui
            reg["ms"] += ms
            reg["intervencoes"] += 1
            if t.get("digitou"):
                reg["digitou"] += 1
    return out


def _mesmo(a: str, b: str) -> bool:
    from tools.bench_transcricao.metricas import tokens as _tk

    return _tk(a or "") == _tk(b or "")


def _referencia(saida: Path, vid: str, motores_: dict[str, Saida]
                ) -> tuple[str, dict] | None:
    """A referência humana: consenso onde todos concordam, ouvido onde não."""
    dec_p = saida / "validacao" / f"validacao_{vid}.json"
    if not dec_p.is_file():
        return None
    decisoes = json.loads(dec_p.read_text(encoding="utf-8")).get("decisoes", {})
    palavras = {n: s.palavras for n, s in motores_.items() if s.palavras}
    texto, contagem = referencia_por_consenso(palavras, decisoes)
    return " ".join(texto), contagem


def avaliar(saida: Path) -> dict:
    por_video: dict[str, dict] = {}
    for pasta in sorted(p for p in saida.iterdir() if p.is_dir()
                        and p.name not in ("validacao",)):
        vid = pasta.name
        motores_ = {}
        for f in pasta.glob("*.json"):
            try:
                motores_[f.stem] = Saida.de_json(
                    json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, KeyError):
                continue
        if not motores_:
            continue

        ref = _referencia(saida, vid, motores_)
        if ref is None:
            por_video[vid] = {"_sem_referencia": True}
            continue
        ref_texto, cobertura = ref
        base = motores_.get("whisper_local")
        cortes = _cortes_do_video(saida, vid)
        humano = tempo_humano_por_motor(saida, vid)

        linhas: dict[str, dict] = {"_cobertura": cobertura}
        for nome, s in motores_.items():
            m = evaluate_text(ref_texto, s.texto)
            linha = {
                "wer": m.counts.wer, "cer": m.cer,
                "acertos": m.counts.accuracy,
                "correcoes_100": m.correcoes_100w,
                "operacoes_100": m.edits_100w,
                "trocas": m.counts.sub, "omitidas": m.counts.dele,
                "inventadas": m.counts.ins,
                "nomes_proprios": m.entities.rate,
                "numeros": m.numbers.rate,
                "coloquial": m.colloquial.rate,
                "tempo_s": s.tempos.get("total"),
                "granularidade": s.granularidade,
            }
            if s.granularidade == "palavra" and s.palavras:
                k = conferir_karaoke(s)
                linha["karaoke"] = {
                    "duracao_invalida": k.duracao_invalida,
                    "palavra_curta": k.palavra_curta,
                    "duplicadas": k.duplicadas,
                    "fora_de_ordem": k.fora_de_ordem,
                    "sobreposicoes": k.sobreposicoes,
                    "reparadas": k.palavras_reparadas,
                    "deslocamento_total_ms": k.deslocamento_total_ms,
                    "deslocamento_mediano_ms": k.deslocamento_mediano_ms,
                    "deslocamento_p95_ms": k.deslocamento_p95_ms,
                    "pior_deslocamento_ms": k.deslocamento_maximo_ms,
                    "intacto": float(k.intacto),
                }
                linha["_karaoke_problemas"] = k.problemas[:5]
                if base is not None and nome.startswith("whisper_gemini"):
                    linha["linha_do_tempo_preservada"] = \
                        s.meta.get("linha_do_tempo_preservada")
                    linha["retencao_de_fronteiras"] = \
                        s.meta.get("retencao_de_fronteiras")
            else:
                linha["nota_timestamp"] = s.meta.get(
                    "nota_timestamp", f"granularidade '{s.granularidade}'")
            h = humano.get(nome)
            if h and h["pontos"]:
                palavras = max(len(tokens(ref_texto)), 1)
                linha["humano_s_100w"] = 100.0 * (h["ms"] / 1000.0) / palavras
                linha["humano_intervencoes"] = h["intervencoes"]
                linha["humano_intervencoes_100w"] = \
                    100.0 * h["intervencoes"] / palavras
                linha["humano_digitou"] = h["digitou"]
            c = cortes.get(nome)
            if c and not c.get("erro"):
                linha["cortes_n"] = c["n"]
                linha["cortes_duracao_s"] = c["duracao_s"]
                linha["cortes_divergencia"] = c.get("divergencia")
            linhas[nome] = linha

        # Erro de timestamp: contra o motor que o produto usa hoje como
        # referência temporal, já que a referência humana não traz tempos.
        if base is not None and base.palavras:
            for nome, s in motores_.items():
                if nome == "whisper_local" or s.granularidade != "palavra":
                    continue
                e = erro_de_timestamp(base.palavras, s.palavras)
                if e:
                    linhas[nome]["ts_vs_whisper"] = e
        por_video[vid] = linhas

    return {"por_video": por_video, "agregado": _agregar(por_video)}


def _agregar(por_video: dict) -> dict:
    acc: dict[str, dict[str, list]] = {}
    for linhas in por_video.values():
        for nome, l in linhas.items():
            if nome.startswith("_") or not isinstance(l, dict):
                continue
            d = acc.setdefault(nome, {})
            for k, v in l.items():
                if isinstance(v, bool):
                    d.setdefault(k, []).append(float(v))
                elif isinstance(v, (int, float)):
                    d.setdefault(k, []).append(float(v))
                elif isinstance(v, dict):
                    for sk, sv in v.items():
                        if isinstance(sv, (int, float)):
                            d.setdefault(f"{k}_{sk}", []).append(float(sv))
    return {n: {k: _media(v) for k, v in d.items()} for n, d in acc.items()}


# ----------------------------------------------------------------- impressão

def _p(x, casas=1, sufixo="%"):
    return SD if x is None else f"{100*x:.{casas}f}{sufixo}"


def _n(x, casas=1, sufixo=""):
    return SD if x is None else f"{x:.{casas}f}{sufixo}"


def _ms(x):
    return SD if x is None else f"{1000*x:.0f} ms"


def matriz(ag: dict, custos: dict | None) -> str:
    cols = [c for c in COLUNAS]
    cab = "| Critério                       | " + " | ".join(
        ROTULO[c].rjust(16) for c in cols) + " |"
    sep = "| ------------------------------ | " + " | ".join(
        "-" * 15 + ":" for _ in cols) + " |"

    def linha(rotulo, fn):
        return "| " + rotulo.ljust(30) + " | " + " | ".join(
            fn(ag.get(c) or {}, c).rjust(16) for c in cols) + " |"

    def ts(a, campo):
        if a.get("granularidade") is None and not a:
            return SD
        return _ms(a.get(f"ts_vs_whisper_{campo}"))

    return "\n".join([cab, sep,
        linha("WER", lambda a, c: _p(a.get("wer"))),
        linha("CER", lambda a, c: _p(a.get("cer"))),
        linha("— precisão textual —", lambda a, c: ""),
        linha("operações de edição/100", lambda a, c: _n(a.get("operacoes_100"))),
        linha("— concentração do erro —", lambda a, c: ""),
        linha("corridas de erro/100 (proxy)",
              lambda a, c: _n(a.get("correcoes_100"))),
        linha("— retrabalho real (relógio) —", lambda a, c: ""),
        linha("tempo humano s/100 palavras",
              lambda a, c: _n(a.get("humano_s_100w"), 1, "s")),
        linha("intervenções humanas/100",
              lambda a, c: _n(a.get("humano_intervencoes_100w"))),
        linha("nomes próprios", lambda a, c: _p(a.get("nomes_proprios"))),
        linha("números", lambda a, c: _p(a.get("numeros"))),
        linha("gírias/coloquial", lambda a, c: _p(a.get("coloquial"))),
        linha("palavras inventadas", lambda a, c: _n(a.get("inventadas"))),
        linha("palavras omitidas", lambda a, c: _n(a.get("omitidas"))),
        linha("timestamp mediano", lambda a, c:
              "referência" if c == "whisper_local" else ts(a, "mediana")),
        linha("p90", lambda a, c:
              "referência" if c == "whisper_local" else ts(a, "p90")),
        linha("p95", lambda a, c:
              "referência" if c == "whisper_local" else ts(a, "p95")),
        linha("— defeito temporal do transcript —", lambda a, c: ""),
        linha("sem defeito (nada movido)",
              lambda a, c: _p(a.get("karaoke_intacto"), 0)),
        linha("palavras_reparadas",
              lambda a, c: _n(a.get("karaoke_reparadas"))),
        linha("deslocamento_total_ms", lambda a, c: _mms(a, "total")),
        linha("deslocamento_mediano_ms", lambda a, c: _mms(a, "mediano")),
        linha("p95_deslocamento_ms", lambda a, c: _mms(a, "p95")),
        linha("pior_deslocamento_ms", lambda a, c:
              SD if a.get("karaoke_pior_deslocamento_ms") is None
              else f"{a['karaoke_pior_deslocamento_ms']:.0f} ms"),
        linha("cortes (n)", lambda a, c: _n(a.get("cortes_n"))),
        linha("cortes: duração final",
              lambda a, c: _n(a.get("cortes_duracao_s"), 1, "s")),
        linha("cortes: divergência do plano", lambda a, c:
              "base" if c == "whisper_local"
              else _p(a.get("cortes_divergencia"))),
        linha("tempo (s/vídeo)", lambda a, c: _n(a.get("tempo_s"))),
        linha("custo (US$/hora de áudio)",
              lambda a, c: _custo(custos, c)),
        linha("offline", lambda a, c: "sim" if c == "whisper_local" else "não"),
        linha("privacidade", lambda a, c:
              "local" if c == "whisper_local"
              else ("texto → nuvem" if c == EXTRA else "áudio → nuvem")),
    ])


def _mms(a: dict, campo: str) -> str:
    """Deslocamento que a produção teve de aplicar. Não é sucesso: é a
    medida do defeito temporal que o motor entregou."""
    v = a.get(f"karaoke_deslocamento_{campo}_ms")
    return SD if v is None else f"{v:.0f} ms"


def _custo(custos: dict | None, motor: str) -> str:
    if not custos:
        return SD
    p = (custos.get(motor) or {}).get("usd_por_minuto_de_audio")
    extra = (custos.get(motor) or {}).get("usd_por_minuto_gpu_local")
    if p is None:
        return SD
    if "usd_por_minuto_gpu_local" in (custos.get(motor) or {}):
        if extra is None:
            return SD          # custo indireto declarado e não preenchido
        p += extra
    return f"US$ {p * 60:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default="bench")
    ap.add_argument("--custos", default="tools/bench_transcricao/custos.json")
    a = ap.parse_args()

    saida = Path(a.saida)
    if not saida.is_dir():
        print(f"não existe: {saida}. Rode rodar.py antes.", file=sys.stderr)
        return 2

    # Corpus sintético não pontua e não escolhe vencedor. Voz de espeak não
    # tem prosódia, hesitação, sobreposição de locutor nem acústica de
    # gravação: um número tirado dali não diz nada sobre o material real, e
    # publicado numa matriz decidiria arquitetura de produção pelo motivo
    # errado. O harness aceita esse corpus para se testar; o relatório, não.
    estado_p = saida / "estado.json"
    if estado_p.is_file():
        try:
            if json.loads(estado_p.read_text(encoding="utf-8")).get("_sintetico"):
                print("RECUSADO: esta pasta veio de corpus SINTÉTICO.\n"
                      "A matriz final usa somente vídeo real do ATIVAVID — "
                      "espeak valida o encanamento, não decide arquitetura.\n"
                      "Rode o benchmark com corpus.json de vídeos reais.",
                      file=sys.stderr)
                return 3
        except ValueError:
            pass

    r = avaliar(saida)
    medidos = {k: v for k, v in r["por_video"].items()
               if not v.get("_sem_referencia")}
    if not medidos:
        print("Nenhum vídeo tem referência humana ainda.\n"
              f"Abra as páginas em {saida / 'validacao'}, marque os trechos e "
              "salve o JSON de volta na mesma pasta.")
        return 2

    custos = None
    cp = Path(a.custos)
    if cp.is_file():
        custos = json.loads(cp.read_text(encoding="utf-8"))

    print(f"# Matriz final — {len(medidos)} vídeo(s) com referência humana\n")
    print(matriz(r["agregado"], custos))

    cob = [v["_cobertura"] for v in medidos.values() if "_cobertura" in v]
    if cob:
        h = sum(c["humano"] for c in cob)
        p = sum(c["pendentes"] for c in cob)
        cns = sum(c["consenso"] for c in cob)
        print(f"\nReferência: {cns} palavras por consenso dos motores, "
              f"{h} verificadas por ouvido humano, {p} ainda pendentes.")
        if p:
            print(f"  ⚠ {p} palavra(s) divergente(s) sem validação — os "
                  f"números acima tratam a versão do Whisper como correta "
                  f"nesses pontos, o que favorece o Whisper e os cenários D/E.")

    d = r["agregado"].get("whisper_gemini") or {}
    if "linha_do_tempo_preservada" in d:
        print(f"\nWhisper + Gemini preservou a linha do tempo em "
              f"{100 * d['linha_do_tempo_preservada']:.0f}% dos vídeos; "
              f"retenção de fronteiras "
              f"{100 * (d.get('retencao_de_fronteiras') or 0):.1f}%.")

    print("\nC e D não rodaram: a integração Gemini do projeto envia só "
          "texto.\nE é a revisão do Gemini SEM ouvir o áudio — é o que dá "
          "para ter hoje.")

    (saida / "relatorio.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print(f"\nDetalhe por vídeo em {saida / 'relatorio.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
