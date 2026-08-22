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
    evaluate_text, levenshtein_ops)
from tools.bench_transcricao.motores import Saida               # noqa: E402

COLUNAS = ["scribe", "whisper_local", "gemini_audio", "whisper_gemini"]
EXTRA = "whisper_gemini_texto"
ROTULO = {"scribe": "Scribe", "whisper_local": "Whisper", 
          "gemini_audio": "Gemini áudio", "whisper_gemini": "Whisper + Gemini",
          EXTRA: "Whisper + Gemini (só texto)"}
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


def karaoke(palavras: list[Palavra]) -> dict:
    """Riscos visuais, com os mesmos limiares que `conferir_legendas` usa.

    Duração <= 0 é o que aquele conferidor reprova. Palavra curta demais e
    sobreposição não reprovam nada hoje, mas são o que faz o realce piscar.
    """
    r = {"duracao_invalida": 0, "palavra_curta": 0, "sobreposicao": 0}
    for i, p in enumerate(palavras):
        if p.fim - p.inicio <= 0:
            r["duracao_invalida"] += 1
        elif p.fim - p.inicio < 0.12:
            r["palavra_curta"] += 1
        if i + 1 < len(palavras) and palavras[i + 1].inicio < p.fim - 1e-6:
            r["sobreposicao"] += 1
    return r


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

        linhas: dict[str, dict] = {"_cobertura": cobertura}
        for nome, s in motores_.items():
            m = evaluate_text(ref_texto, s.texto)
            linha = {
                "wer": m.counts.wer, "cer": m.cer,
                "acertos": m.counts.accuracy,
                "correcoes_100": m.edits_100w,
                "trocas": m.counts.sub, "omitidas": m.counts.dele,
                "inventadas": m.counts.ins,
                "nomes_proprios": m.entities.rate,
                "numeros": m.numbers.rate,
                "coloquial": m.colloquial.rate,
                "tempo_s": s.tempos.get("total"),
                "granularidade": s.granularidade,
            }
            if s.granularidade == "palavra" and s.palavras:
                linha["karaoke"] = karaoke(s.palavras)
                if base is not None and nome.startswith("whisper_gemini"):
                    linha["linha_do_tempo_preservada"] = \
                        s.meta.get("linha_do_tempo_preservada")
                    linha["retencao_de_fronteiras"] = \
                        s.meta.get("retencao_de_fronteiras")
            else:
                linha["nota_timestamp"] = s.meta.get(
                    "nota_timestamp", f"granularidade '{s.granularidade}'")
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
        linha("correções humanas/100 palavras",
              lambda a, c: _n(a.get("correcoes_100"))),
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
        linha("karaoke: duração inválida",
              lambda a, c: _n(a.get("karaoke_duracao_invalida"))),
        linha("karaoke: palavra curta",
              lambda a, c: _n(a.get("karaoke_palavra_curta"))),
        linha("tempo (s/vídeo)", lambda a, c: _n(a.get("tempo_s"))),
        linha("custo (US$/hora de áudio)",
              lambda a, c: _custo(custos, c)),
        linha("offline", lambda a, c: "sim" if c == "whisper_local" else "não"),
        linha("privacidade", lambda a, c:
              "local" if c == "whisper_local" else "áudio → nuvem"),
    ])


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

    e = r["agregado"].get(EXTRA)
    if e:
        print(f"\nExperimento E (revisão sem ouvir o áudio): "
              f"WER {_p(e.get('wer'))}, "
              f"correções/100 {_n(e.get('correcoes_100'))}.")

    (saida / "relatorio.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print(f"\nDetalhe por vídeo em {saida / 'relatorio.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
