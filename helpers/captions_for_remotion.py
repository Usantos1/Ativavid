"""Emit a @remotion/captions Caption[] JSON for the Remotion (Phase 2) project.

Two modes:
  --transcript <cut.json>   Transcribe the FINAL cut.mp4 first, then feed that
      transcript here. Prefer when Whisper timings stay within the cut duration.
  <edl.json>                Map per-source word times through the EDL (and
      jcut_timeline when present). More reliable when cut-transcript timings
      stretch past cut.mp4 (common Groq/Whisper failure).

Each spoken word becomes one Caption (word-level) so the word-highlight /
karaoke component can drive per-word timing.

Caption shape (from @remotion/captions): { text, startMs, endMs, timestampMs, confidence }

Usage:
    python helpers/captions_for_remotion.py --transcript <edit>/transcripts/cut.json -o captions.json
    python helpers/captions_for_remotion.py <edl.json> -o captions.json --max-sec 20.6
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import json
import re
from pathlib import Path


def _norm_token(t) -> str:
    return re.sub(r"[\W_]+", "", str(t or "").casefold())


def _word_items(raw: dict) -> list[dict]:
    out = [
        dict(w) for w in (raw.get("words") or [])
        if w.get("type") == "word" and w.get("start") is not None
    ]
    # LOOP DE ALUCINACAO do Whisper (caso real, projeto C066 de 31/08: 132
    # palavras, 121 duplicatas EXATAS, "ei," repetido 107 vezes — 9 delas no
    # mesmo instante). O usuario clicou em refazer varias vezes e a legenda
    # saia "toda errada e remontada": o lixo estava no transcript, e nada
    # filtrava. Duas regras, ANTES do clamp (que espalharia as duplicatas
    # por 1ms e as tornaria "diferentes"):
    # 1. duplicata exata (start, end, texto) cai;
    # 2. a MESMA palavra repetida em metralhadora (gap < 0,25s) para na
    #    terceira — gente repete "ei, ei, ei"; so o loop repete 100x.
    vistos: set = set()
    dedup: list[dict] = []
    for w in out:
        k = (w.get("start"), w.get("end"), str(w.get("text") or "").strip())
        if k in vistos:
            continue
        vistos.add(k)
        dedup.append(w)
    filtrado: list[dict] = []
    seguidos = 0
    tok_ant = ""
    start_ant = -10.0
    for w in dedup:
        tok = _norm_token(w.get("text"))
        gap = float(w["start"]) - start_ant
        if tok and tok == tok_ant and gap < 0.25:
            # o intervalo e ate a ocorrencia ANTERIOR (mantida ou nao):
            # medir ate a ultima MANTIDA deixava passar 1 a cada 0,25s e a
            # rajada continuava pingando na tela.
            seguidos += 1
        else:
            seguidos = 0
        tok_ant, start_ant = tok, float(w["start"])
        if seguidos >= 3:
            continue
        filtrado.append(w)
    if len(filtrado) < len(out):
        print(f"[legenda] alucinacao filtrada: {len(out) - len(filtrado)} "
              f"palavra(s) repetida(s)/duplicada(s) fora", flush=True)
    out = filtrado
    # Os transcripts JA GRAVADOS tem palavra voltando no tempo (133 de 178 nos
    # projetos do usuario) e quem consome ordena por start — a legenda saia
    # com palavras trocadas. A ordem do array e a da fala; o clamp so garante
    # starts crescentes. O mesmo conserto existe na escrita (transcribe.py),
    # mas os arquivos antigos passam por AQUI a cada rebuild de legenda.
    prev = None
    for w in out:
        s = float(w["start"])
        e = float(w.get("end") or s)
        if prev is not None and s < prev + 1e-3:
            s = prev + 1e-3
        if e < s + 0.04:
            e = s + 0.04
        w["start"], w["end"] = s, e
        prev = s
    return out


def _pack(text: str, t: float, e: float) -> dict:
    if e <= t:
        e = t + 0.12
    return {
        "text": text,
        "startMs": round(t * 1000),
        "endMs": round(e * 1000),
        "timestampMs": round((t + e) / 2 * 1000),
        "confidence": None,
    }


def clamp_captions(caps: list[dict], max_sec: float | None) -> list[dict]:
    """Drop / trim words past the cut duration so Remotion never seeks past EOF."""
    if not max_sec or max_sec <= 0 or not caps:
        return caps
    limit_ms = int(max_sec * 1000)
    out: list[dict] = []
    for c in caps:
        if c["startMs"] >= limit_ms:
            continue
        if c["endMs"] > limit_ms:
            c = dict(c)
            c["endMs"] = limit_ms
            c["timestampMs"] = (c["startMs"] + c["endMs"]) // 2
        if c["endMs"] > c["startMs"]:
            out.append(c)
    return out


def transcript_overruns(transcript_path: Path, duration_sec: float, slack: float = 1.08) -> bool:
    """True when last word ends clearly after the media duration (Whisper stretch)."""
    return transcript_timing_issue(transcript_path, duration_sec) == "overrun"


def transcript_timing_issue(
    transcript_path: Path,
    duration_sec: float,
    *,
    overrun_slack: float = 1.08,
    underrun_slack: float = 0.90,
) -> str | None:
    """Return 'overrun' | 'underrun' | 'empty' | None for cut-transcript quality."""
    if duration_sec <= 0:
        return None
    if not transcript_path.exists():
        return "empty"
    words = _word_items(json.loads(transcript_path.read_text(encoding="utf-8")))
    if not words:
        return "empty"
    last = max(float(w.get("end") or w["start"]) for w in words)
    if last > duration_sec * overrun_slack:
        return "overrun"
    # Whisper often drops the final phrases — treat early endings as bad coverage.
    if last < duration_sec * underrun_slack:
        return "underrun"
    return None


# Quanta cauda SEM legenda ainda e normal. Um video que acaba num cartao de
# CTA, num b-roll ou numa pausa termina em silencio de proposito — e ate a
# 5.0.67 qualquer sobra acima de 0,45 s mandava transcrever o corte inteiro.
#
# MEDIDO em 133 jobs desde 01/09 e nos 332 projetos do disco:
#
#   - 29 dos 133 (22%) cairam nesse fallback. Em TODOS os 29 a transcricao
#     do corte devolveu as MESMAS palavras do remap (razao mediana 1,00,
#     faixa 0,91-1,09) e o mesmo fim (mediana -0,02 s). Custo: 27,8 s de
#     CAPTIONS contra 0,4 s, e job mediano de 170,4 s contra 83,4 s — o
#     dobro, para nao mudar nada.
#   - Em 332 projetos so DOIS tiveram remap de fato incompleto (47% e 67%
#     das palavras). Nos dois a cauda sem legenda foi de 10,41 s (26,7%) e
#     9,92 s (30,3%).
#   - Nos 29 falsos alarmes a cauda nunca passou de 8,05 s, e a fracao
#     mediana foi 0,067.
#
# Dai a regra dupla: so vale transcrever quando a sobra e grande nos DOIS
# sentidos. Ela pega os dois remaps ruins e deixa passar 28 dos 29 falsos
# alarmes. Os limiares sao os mais BAIXOS (mais cautelosos) que ainda pegam
# os dois — errar para o lado de transcrever custa 28 s, errar para o outro
# entrega um video com legenda faltando no fim.
CAUDA_SEM_LEGENDA_S = 6.0
CAUDA_SEM_LEGENDA_FRACAO = 0.15


def cauda_sem_legenda(caps: list[dict], duration_sec: float) -> tuple[float, float]:
    """(segundos, fracao) do fim do video que ficou sem nenhuma legenda."""
    if duration_sec <= 0 or not caps:
        return (0.0, 0.0)
    fim = max(int(c.get("endMs") or 0) for c in caps) / 1000.0
    sobra = max(0.0, duration_sec - fim)
    return (sobra, sobra / duration_sec)


def captions_coverage_ok(caps: list[dict], duration_sec: float, *,
                         slack_end: float | None = None) -> bool:
    """True quando as legendas cobrem a FALA do corte.

    `slack_end` (segundos) ainda e aceito para quem quiser a regra antiga de
    "chega perto do fim do video"; sem ele vale a regra dupla acima.
    """
    if duration_sec <= 0 or not caps:
        return False
    if slack_end is not None:
        last_ms = max(int(c.get("endMs") or 0) for c in caps)
        return last_ms >= int((duration_sec - slack_end) * 1000)
    sobra, fracao = cauda_sem_legenda(caps, duration_sec)
    return not (sobra > CAUDA_SEM_LEGENDA_S
                and fracao > CAUDA_SEM_LEGENDA_FRACAO)


def captions_from_transcript(transcript_path: Path) -> list[dict]:
    """Words already on the output timeline (transcript of the final cut)."""
    caps: list[dict] = []
    for w in _word_items(json.loads(transcript_path.read_text(encoding="utf-8"))):
        t = float(w["start"])
        e = float(w.get("end") or w["start"])
        text = (w.get("text") or "").strip()
        if not text:
            continue
        caps.append(_pack(text, t, e))
    caps.sort(key=lambda c: c["startMs"])
    return caps


def _transcript_path_for_source(edl: dict, edit_dir: Path, source_key: str) -> Path | None:
    """Resolve transcript JSON — EDL key may differ from video.stem on disk."""
    transcripts_dir = edit_dir / "transcripts"
    candidates = [transcripts_dir / f"{source_key}.json"]
    src_path = (edl.get("sources") or {}).get(source_key)
    if src_path:
        stem = Path(str(src_path)).stem
        if stem and stem != source_key:
            candidates.append(transcripts_dir / f"{stem}.json")
    for p in candidates:
        if p.exists():
            return p
    return None


def _indices_in_range(words: list[dict], a: float, b: float,
                      pad: float = 0.12) -> list[int]:
    """Indices das palavras cujo [start,end] cruza o trecho (nao so o start)."""
    out: list[int] = []
    for k, w in enumerate(words):
        ws = float(w["start"])
        we = float(w.get("end") or ws)
        if we < a - pad or ws > b + pad:
            continue
        out.append(k)
    out.sort(key=lambda k: float(words[k]["start"]))
    return out


def _words_in_range(words: list[dict], a: float, b: float, pad: float = 0.12) -> list[dict]:
    """Words whose [start,end] overlaps the range (not start-only)."""
    return [words[k] for k in _indices_in_range(words, a, b, pad)]


def _dono_de_cada_palavra(
    ranges: list, palavras_por_fonte: dict, pad: float = 0.12,
) -> dict:
    """`(fonte, indice) -> indice do trecho` que fica com aquela palavra.

    `_words_in_range` escolhe por SOBREPOSICAO, entao uma palavra que atravessa
    dois trechos era emitida nos DOIS. Como a transcricao as vezes junta uma
    fala inteira numa "palavra" so, isso nao e raro: medido nos 127 projetos do
    usuario, **93 (73%)** tinham pelo menos uma palavra em mais de um trecho —
    298 copias extras, ate 5x a mesma palavra.

    E aparece na tela. Num projeto a fonte diz "bora" UMA vez (0,32 -> 4,22s, a
    transcricao juntou tudo) e os tres trechos guardados caem dentro dela: a
    primeira legenda do video desenhava "bora / bora / bora 32".

    O criterio e a maior SOBREPOSICAO — o trecho que ficou com a maior parte da
    palavra e quem a mostra. Empate fica com o primeiro, que preserva a ordem
    da fala.
    """
    melhor: dict = {}
    for i, r in enumerate(ranges):
        src = str(r.get("source") or "")
        a, b = float(r.get("start") or 0), float(r.get("end") or 0)
        for k, w in enumerate(palavras_por_fonte.get(src) or []):
            ws = float(w["start"])
            we = float(w.get("end") or ws)
            if we < a - pad or ws > b + pad:
                continue
            cobre = min(we, b) - max(ws, a)
            chave = (src, k)
            atual = melhor.get(chave)
            if atual is None or cobre > atual[0] + 1e-9:
                melhor[chave] = (cobre, i)
    return {chave: i for chave, (_, i) in melhor.items()}


def build_captions(edl: dict, edit_dir: Path) -> list[dict]:
    """Map source transcripts through EDL ranges onto the cut timeline.

    When `jcut_timeline` exists, place words on the AUDIO timeline of the mixed
    cut (what the viewer hears), not the naive sum of range durations.
    """
    return [
        {k: v for k, v in w.items() if k in ("text", "startMs", "endMs", "timestampMs", "confidence")}
        for w in build_captions_with_provenance(edl, edit_dir)
    ]


def build_captions_with_provenance(edl: dict, edit_dir: Path, *, quiet: bool = False) -> list[dict]:
    """A mesma associação source→token que criou as captions, com proveniência.

    sourceStart/sourceEnd são o relógio da FONTE (transcript), não o do cut.
    """
    caps: list[dict] = []
    ranges = edl.get("ranges") or []
    jcut = edl.get("jcut_timeline") or []
    off = 0.0
    missing: list[str] = []

    # Le cada transcricao UMA vez: o laco abaixo relia por trecho, e um video
    # com 40 trechos abria o mesmo arquivo 40 vezes.
    por_fonte: dict[str, list] = {}
    for r in ranges:
        src = str(r.get("source") or "")
        if src in por_fonte:
            continue
        tr = _transcript_path_for_source(edl, edit_dir, src)
        try:
            por_fonte[src] = (
                _word_items(json.loads(tr.read_text(encoding="utf-8")))
                if tr is not None else []
            )
        except (OSError, json.JSONDecodeError):
            por_fonte[src] = []
    dono = _dono_de_cada_palavra(ranges, por_fonte)

    for i, r in enumerate(ranges):
        src = r["source"]
        a, b = float(r["start"]), float(r["end"])
        range_dur = max(0.0, b - a)
        tr_path = _transcript_path_for_source(edl, edit_dir, src)

        if i < len(jcut):
            out_a = float(jcut[i].get("audio_start_in_output") or 0.0)
            out_dur = float(jcut[i].get("audio_duration") or range_dur)
        else:
            out_a = off
            out_dur = range_dur

        if tr_path is None:
            missing.append(src)
        else:
            words = por_fonte.get(src) or []
            for k_w in _indices_in_range(words, a, b):
                if dono.get((src, k_w), i) != i:
                    continue      # esta palavra e de outro trecho
                w = words[k_w]
                ws = float(w["start"])
                we = float(w.get("end") or ws)
                # Palavra que o corte removeu quase inteira nao vira legenda.
                # Sem isto sobra uma lasca de milissegundos que o espectador
                # nao ouve — e, com J-cut (o audio do trecho seguinte comeca
                # antes), ela ainda cai DENTRO da fala seguinte: um "ne?" de
                # 8ms rendeu "Prime ne? Camp" na tela. O dono ja e o trecho de
                # MAIOR sobreposicao, entao descartar aqui descarta de vez.
                audivel = min(we, b) - max(ws, a)
                if audivel < 0.06 and audivel < 0.25 * max(we - ws, 1e-9):
                    continue
                rel_t = max(0.0, float(w["start"]) - a)
                rel_e = max(rel_t + 0.04, float(w.get("end") or w["start"]) - a)
                t = min(out_dur, rel_t) + out_a
                e = min(out_dur, rel_e) + out_a
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                item = _pack(text, t, e)
                item["source"] = str(src)
                # Relógio da fonte DENTRO do take que gerou o cue — não o
                # timestamp cru se o pad do range puxou a palavra vizinha.
                src_s = a + min(out_dur, rel_t)
                src_e = a + min(out_dur, rel_e)
                lo, hi = a, a + out_dur
                src_s = min(max(src_s, lo), hi)
                src_e = min(max(src_e, lo), hi)
                if src_e - src_s <= 1e-4:
                    src_e = min(hi, src_s + 0.04)
                    if src_e - src_s <= 1e-4:
                        src_s = max(lo, src_e - 0.04)
                item["sourceStart"] = src_s
                item["sourceEnd"] = src_e
                caps.append(item)

        if i >= len(jcut):
            off += range_dur

    if missing and not quiet:
        print(f"  [warn] transcript ausente para source(s): {', '.join(sorted(set(missing)))}")

    caps.sort(key=lambda c: c["startMs"])
    return caps


def main() -> None:
    ap = argparse.ArgumentParser(description="→ @remotion/captions Caption[] JSON")
    ap.add_argument("edl", type=Path, nargs="?", help="edl.json (EDL-remap mode)")
    ap.add_argument("--transcript", type=Path, default=None,
                    help="Transcript of the final cut.mp4")
    ap.add_argument("--max-sec", type=float, default=None,
                    help="Clamp captions to this duration (cut.mp4 length)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output captions.json path")
    args = ap.parse_args()

    if args.transcript:
        caps = captions_from_transcript(args.transcript.resolve())
    elif args.edl:
        edl_path = args.edl.resolve()
        caps = build_captions(json.loads(edl_path.read_text(encoding="utf-8")), edl_path.parent)
    else:
        ap.error("provide --transcript <cut.json> or an edl.json")

    before = len(caps)
    caps = clamp_captions(caps, args.max_sec)
    if args.max_sec and before != len(caps):
        print(f"  clamped {before - len(caps)} words past {args.max_sec:.2f}s")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(caps, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.output} — {len(caps)} word captions")


if __name__ == "__main__":
    main()
