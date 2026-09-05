"""Remapeia legendas pelo timeline map. Sem FFmpeg, sem Whisper.

captions.json vive no relógio de SAÍDA do cut atual (áudio do J-cut).
O EDL vive no relógio de cada FONTE. Fontes diferentes com o mesmo
0–2.7 s não se misturam.

Fluxo: cut atual → OLD map → (source, sourceTime) → NEW map → novo output.
O texto corrigido pelo operador não muda.
"""
from __future__ import annotations

from typing import Any

import sys

from app.timeline_map import (
    MIN_DUR,
    build_timeline_map,
    map_output_duration,
    validate_timeline_map,
)

__all__ = [
    "MIN_DUR",
    "attach_provenance_from_transcripts",
    "apply_inferred_provenance",
    "build_timeline_map",
    "map_interval",
    "output_duration",
    "output_to_source",
    "remap_captions_between_timelines",
    "remap_captions_through_edl",
    "retime_captions_for_edl",
    "source_to_output",
    "validate_remapped_captions",
    "validate_timeline_map",
]


def _ranges_as_edl(edl: Any) -> dict:
    if isinstance(edl, dict):
        return edl
    return {"ranges": edl or [], "jcut": False}


def output_duration(edl: Any) -> float:
    return map_output_duration(build_timeline_map(_ranges_as_edl(edl)))


def source_to_output(t: float, edl: Any, source: str | None = None) -> float | None:
    """Tempo na fonte → saída. `source` é obrigatório se houver mais de uma."""
    spans = build_timeline_map(_ranges_as_edl(edl))["spans"]
    x = float(t)
    src = str(source) if source else None
    for span in spans:
        if src is not None and span["source"] != src:
            continue
        a, b = float(span["sourceStart"]), float(span["sourceEnd"])
        if x < a - 1e-9:
            continue
        if x <= b + 1e-9:
            return float(span["outputStart"]) + max(0.0, min(x, b) - a)
    return None


def output_to_source(t: float, edl: Any, source: str | None = None) -> tuple[str, float] | None:
    """Saída → (source, sourceTime). Não cruza fonte."""
    spans = build_timeline_map(_ranges_as_edl(edl))["spans"]
    x = float(t)
    src = str(source) if source else None
    best = None
    best_ov = -1.0
    for span in spans:
        if src is not None and span["source"] != src:
            continue
        a, b = float(span["outputStart"]), float(span["outputEnd"])
        if x < a - 1e-9 or x > b + 1e-9:
            continue
        ov = min(b, x + 0.05) - max(a, x - 0.05)
        if ov >= best_ov:
            best_ov = ov
            rel = max(0.0, min(x, b) - a)
            best = (str(span["source"]), float(span["sourceStart"]) + rel)
    return best


def map_interval(start: float, end: float, edl: Any, source: str | None = None) -> list[tuple[float, float]]:
    """Interseção de um intervalo de FONTE com o mapa, já em saída."""
    spans = build_timeline_map(_ranges_as_edl(edl))["spans"]
    s, e = float(start), float(end)
    if e <= s:
        return []
    src = str(source) if source else None
    frags: list[tuple[float, float]] = []
    for span in spans:
        if src is not None and span["source"] != src:
            continue
        lo = max(s, float(span["sourceStart"]))
        hi = min(e, float(span["sourceEnd"]))
        if hi - lo > MIN_DUR:
            base = float(span["outputStart"])
            a0 = float(span["sourceStart"])
            frags.append((base + (lo - a0), base + (hi - a0)))
    return frags


def _item_span(item: dict) -> tuple[float, float, str]:
    if item.get("startMs") is not None or item.get("endMs") is not None:
        return float(item.get("startMs") or 0) / 1000.0, float(item.get("endMs") or 0) / 1000.0, "ms"
    return float(item.get("start") or 0), float(item.get("end") or 0), "s"


def _stamp(item: dict, start_s: float, end_s: float, unit: str, *, provenance: dict | None = None) -> dict:
    out = dict(item)
    if unit == "ms":
        out["startMs"] = int(round(start_s * 1000))
        out["endMs"] = int(round(end_s * 1000))
        if "timestampMs" in out:
            out["timestampMs"] = int(round((start_s + end_s) / 2 * 1000))
    else:
        out["start"] = round(start_s, 3)
        out["end"] = round(end_s, 3)
    if provenance:
        out["source"] = provenance.get("source")
        out["sourceStart"] = round(float(provenance.get("sourceStart") or 0), 3)
        out["sourceEnd"] = round(float(provenance.get("sourceEnd") or 0), 3)
    return out


ALIGN_TOL_S = 0.12
OVERLAP_FAIL = "overlap sem provenance reconstruível"


def _span_overlap(s: float, e: float, a: float, b: float) -> float:
    return max(0.0, min(e, b) - max(s, a))


def output_covering_spans(start_s: float, end_s: float, old_map: dict[str, Any]) -> list[dict]:
    """Spans de áudio que cobrem o intervalo de saída. J-cut pode devolver 2+."""
    hits: list[dict] = []
    for span in old_map.get("spans") or []:
        ov = _span_overlap(start_s, end_s, float(span["outputStart"]), float(span["outputEnd"]))
        if ov > MIN_DUR:
            hits.append(span)
    return hits


def _has_explicit_provenance(cap: dict) -> bool:
    return bool(
        str(cap.get("source") or "").strip()
        and cap.get("sourceStart") is not None
        and cap.get("sourceEnd") is not None
    )


def align_captions_to_reconstructed(
    captions: list, reconstructed: list
) -> tuple[list[dict], list[int]]:
    """Casa captions atuais com tokens reconstruídos por ordem + timing.

    Texto pode ter sido corrigido (Perico → Película). Não casa por texto.
    Empate de startMs (overlap de J-cut) segue a ordem estável do build_captions.
    """
    rec = [r for r in reconstructed if isinstance(r, dict)]
    ri = 0
    attached: list[dict] = []
    unmatched: list[int] = []
    for idx, cap in enumerate(captions or []):
        if not isinstance(cap, dict):
            continue
        if _has_explicit_provenance(cap):
            attached.append(dict(cap))
            continue
        s, _e, _u = _item_span(cap)
        while ri < len(rec) and _item_span(rec[ri])[0] < s - ALIGN_TOL_S:
            ri += 1
        if ri < len(rec) and abs(_item_span(rec[ri])[0] - s) <= ALIGN_TOL_S:
            src = rec[ri]
            merged = dict(cap)
            merged["source"] = src.get("source")
            merged["sourceStart"] = float(src.get("sourceStart") or 0)
            merged["sourceEnd"] = float(src.get("sourceEnd") or 0)
            attached.append(merged)
            ri += 1
        else:
            attached.append(dict(cap))
            unmatched.append(idx)
    return attached, unmatched


def apply_inferred_provenance(captions: list, old_map: dict[str, Any]) -> list[dict]:
    """Completa source só quando o overlap é da mesma fonte. Não escolhe A vs B."""
    out: list[dict] = []
    for cap in captions or []:
        if not isinstance(cap, dict):
            continue
        if _has_explicit_provenance(cap):
            out.append(dict(cap))
            continue
        prov = caption_to_provenance(cap, old_map)
        if not prov:
            out.append(dict(cap))
            continue
        s, e, unit = _item_span(cap)
        out.append(_stamp(cap, s, e, unit, provenance=prov))
    return out


def attach_provenance_from_transcripts(
    captions: list,
    old_edl: dict[str, Any],
    edit_dir,
) -> tuple[list[dict], str | None]:
    """Reconstrói a associação original. Overlap de fontes diferentes continua ambíguo."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    helpers = str(root / "helpers")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)
    from helpers.captions_for_remotion import build_captions_with_provenance

    words = list(captions or [])
    if edit_dir:
        try:
            reconstructed = build_captions_with_provenance(old_edl, Path(edit_dir), quiet=True)
        except Exception:
            reconstructed = []
        if reconstructed:
            words, _unmatched = align_captions_to_reconstructed(words, reconstructed)
    old_wrap = _ranges_as_edl(old_edl)
    fps = old_wrap.get("fps") if isinstance(old_wrap, dict) else None
    prior = old_wrap.get("jcut_timeline") if isinstance(old_wrap, dict) else None
    old_map = build_timeline_map(old_wrap, fps=fps, prior_jcut=prior)
    return apply_inferred_provenance(words, old_map), None


def _hits_same_source(hits: list[dict]) -> bool:
    sources = {str(h.get("source") or "").strip() for h in hits}
    return len(sources) == 1 and bool(next(iter(sources)))


def _provenance_from_span(s: float, e: float, span: dict[str, Any]) -> dict[str, Any] | None:
    a0, b0 = float(span["outputStart"]), float(span["outputEnd"])
    lo = min(max(s, a0), b0)
    hi = min(max(e, a0), b0)
    if hi <= lo:
        hi = min(b0, lo + MIN_DUR)
    src_s = float(span["sourceStart"]) + (lo - a0)
    src_e = float(span["sourceStart"]) + (hi - a0)
    src_s = min(max(src_s, float(span["sourceStart"])), float(span["sourceEnd"]))
    src_e = min(max(src_e, src_s + MIN_DUR), float(span["sourceEnd"]))
    src = str(span.get("source") or "").strip()
    if not src:
        return None
    return {"source": src, "sourceStart": src_s, "sourceEnd": src_e}


def caption_to_provenance(cap: dict, old_map: dict[str, Any]) -> dict | None:
    """Uma palavra → uma fonte. Overlap de J-cut não escolhe entre fontes diferentes."""
    s, e, _unit = _item_span(cap)
    if e <= s:
        return None
    if _has_explicit_provenance(cap):
        return {
            "source": str(cap.get("source") or "").strip(),
            "sourceStart": float(cap["sourceStart"]),
            "sourceEnd": float(cap["sourceEnd"]),
        }
    hits = output_covering_spans(s, e, old_map)
    if len(hits) == 1:
        return _provenance_from_span(s, e, hits[0])
    if len(hits) >= 2:
        if _hits_same_source(hits):
            best = max(
                hits,
                key=lambda h: _span_overlap(s, e, float(h["outputStart"]), float(h["outputEnd"])),
            )
            return _provenance_from_span(s, e, best)
        cap["_overlapAmbiguous"] = True
        return None
    return None


def provenance_error(original: list, remapped_inputs: list, old_map: dict[str, Any]) -> str | None:
    """Bloqueia Apply se um token no overlap não tem source reconstruída."""
    for cap in remapped_inputs or []:
        if not isinstance(cap, dict):
            continue
        if _has_explicit_provenance(cap):
            continue
        s, e, _u = _item_span(cap)
        hits = output_covering_spans(s, e, old_map)
        if len(hits) >= 2 and not _hits_same_source(hits):
            return OVERLAP_FAIL
    return None


def map_source_interval(
    source: str, src_s: float, src_e: float, new_map: dict[str, Any]
) -> list[tuple[float, float, float, float]]:
    """(out_s, out_e, src_lo, src_hi) na NEW map, só da mesma source."""
    frags: list[tuple[float, float, float, float]] = []
    for span in new_map.get("spans") or []:
        if span["source"] != source:
            continue
        lo = max(float(src_s), float(span["sourceStart"]))
        hi = min(float(src_e), float(span["sourceEnd"]))
        if hi - lo <= MIN_DUR:
            continue
        base = float(span["outputStart"])
        a0 = float(span["sourceStart"])
        frags.append((base + (lo - a0), base + (hi - a0), lo, hi))
    frags.sort(key=lambda x: x[0])
    return frags


def remap_captions_between_timelines(
    captions: list, old_map: dict[str, Any], new_map: dict[str, Any]
) -> list[dict]:
    result: list[dict] = []
    for cap in captions or []:
        if not isinstance(cap, dict):
            continue
        _s, _e, unit = _item_span(cap)
        prov = caption_to_provenance(cap, old_map)
        if not prov:
            continue
        frags = map_source_interval(
            prov["source"], prov["sourceStart"], prov["sourceEnd"], new_map
        )
        if not frags:
            continue
        for o0, o1, s0, s1 in frags:
            item = _stamp(cap, o0, o1, unit, provenance={
                "source": prov["source"], "sourceStart": s0, "sourceEnd": s1,
            })
            item[_ORDEM] = len(result)
            result.append(item)
    result.sort(key=lambda c: _item_span(c)[0])
    _respeitar_ordem_original(result, unit)
    for item in result:
        item.pop(_ORDEM, None)
    return result


_ORDEM = "_ordemOriginal"
TROCA_PEQUENA_S = 0.30


def _respeitar_ordem_original(result: list, unit: str) -> None:
    """Troca pequena de posição depois do remap volta à ordem original.

    Caso real (Elizangela, 04/09): uma correção de palavra deixou três
    palavras com tempo sintético de +1 ms cada ("A" 19440, "parte" 19441,
    "da" 19442). Remapeadas por provenance, saíram "da" 19209 e "parte"
    19240 — o `sort` por início trocou as duas, o validador recusou
    ("ordem das palavras invertida") e o app refez o vídeo inteiro (2,5 min
    no lugar de 1). A ordem das palavras é o que o vídeo mostra; uma
    diferença de dezenas de ms no início, ninguém vê. Então: quando duas
    vizinhas estão fora da ordem original e a diferença de início é
    pequena, as PALAVRAS trocam de lugar e os TEMPOS ficam onde estão.
    Troca grande (> TROCA_PEQUENA_S) é reordenação de verdade: fica, e o
    validador decide.
    """
    ks, ke, kt = ("startMs", "endMs", "timestampMs") if unit == "ms" else ("start", "end", None)
    tol = TROCA_PEQUENA_S * (1000 if unit == "ms" else 1)
    trocou = True
    voltas = 0
    while trocou and voltas < len(result):
        trocou = False
        voltas += 1
        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            if a.get(_ORDEM) is None or b.get(_ORDEM) is None:
                continue
            if a[_ORDEM] <= b[_ORDEM]:
                continue
            if abs(float(b.get(ks) or 0) - float(a.get(ks) or 0)) > tol:
                continue
            tempos_a = {k: a.get(k) for k in (ks, ke, kt) if k}
            tempos_b = {k: b.get(k) for k in (ks, ke, kt) if k}
            result[i], result[i + 1] = b, a
            for k, v in tempos_a.items():
                b[k] = v
            for k, v in tempos_b.items():
                a[k] = v
            trocou = True


def retime_captions_for_edl(
    captions: list,
    old_edl: Any,
    new_edl: Any,
    *,
    fps: float | None = None,
    prior_jcut: list | None = None,
    edit_dir=None,
) -> list[dict]:
    old_wrap = _ranges_as_edl(old_edl)
    new_wrap = _ranges_as_edl(new_edl)
    old_jcut = old_wrap.get("jcut_timeline") if isinstance(old_wrap, dict) else None
    old_map = build_timeline_map(old_wrap, fps=fps, prior_jcut=prior_jcut)
    new_map = build_timeline_map(
        new_wrap,
        fps=fps,
        prior_jcut=old_jcut or prior_jcut,
    )
    words = list(captions or [])
    if edit_dir:
        words, _err = attach_provenance_from_transcripts(words, old_wrap, edit_dir)
    else:
        words = apply_inferred_provenance(words, old_map)
    return remap_captions_between_timelines(words, old_map, new_map)


def remap_captions_through_edl(captions: list, edl: Any) -> list[dict]:
    """Legado: captions já no tempo de FONTE de uma source. Lista → sem J-cut."""
    wrapped = _ranges_as_edl(edl)
    new_map = build_timeline_map(wrapped)
    result: list[dict] = []
    default_src = None
    spans = new_map.get("spans") or []
    if spans:
        default_src = str(spans[0]["source"])
    for cap in captions or []:
        if not isinstance(cap, dict):
            continue
        s, e, unit = _item_span(cap)
        src = str(cap.get("source") or default_src or "SRC")
        frags = map_source_interval(src, s, e, new_map)
        if not frags:
            continue
        for o0, o1, s0, s1 in frags:
            result.append(_stamp(cap, o0, o1, unit, provenance={
                "source": src, "sourceStart": s0, "sourceEnd": s1,
            }))
    result.sort(key=lambda c: _item_span(c)[0])
    return result


def validate_remapped_captions(
    original: list,
    remapped: list,
    new_map: dict[str, Any],
) -> str | None:
    err = validate_timeline_map(new_map)
    if err:
        return err
    if not isinstance(remapped, list):
        return "legendas inválidas"
    prev = -1.0
    audio_end = float(new_map.get("audioDuration") or new_map.get("outputDuration") or 0)
    for cap in remapped:
        if not isinstance(cap, dict):
            return "legendas inválidas"
        s, e, _u = _item_span(cap)
        if e + 1e-9 < s:
            return "segmento com duração negativa"
        if s + 1e-6 < prev:
            return "legendas fora de ordem"
        prev = s
        if audio_end > 0.4 and e > audio_end + 0.35:
            return "timestamp fora da duração"
    # Duplicata sem justificativa: a mesma palavra de MAIN não pode reaparecer no CTA.
    from collections import Counter

    orig_has_src = any(str(c.get("source") or "") for c in original or [] if isinstance(c, dict))
    new_has_src = any(str(c.get("source") or "") for c in remapped if isinstance(c, dict))
    if orig_has_src:
        orig_ts = Counter(
            (str(c.get("text") or ""), str(c.get("source") or ""))
            for c in original or []
            if isinstance(c, dict) and str(c.get("source") or "")
        )
        new_ts = Counter(
            (str(c.get("text") or ""), str(c.get("source") or ""))
            for c in remapped
            if isinstance(c, dict) and str(c.get("source") or "")
        )
        for key, n in new_ts.items():
            if n > orig_ts.get(key, 0):
                return "token duplicado sem justificativa"
    elif new_has_src:
        orig_text = Counter(str(c.get("text") or "") for c in original or [] if isinstance(c, dict))
        new_text = Counter(str(c.get("text") or "") for c in remapped if isinstance(c, dict))
        for text, n in new_text.items():
            if n > orig_text.get(text, 0):
                return "token duplicado sem justificativa"
    else:
        seen_src: dict[tuple[str, str, int], int] = {}
        for cap in remapped:
            text = str(cap.get("text") or "")
            src = str(cap.get("source") or "")
            bucket = int(round(float(cap.get("sourceStart") or 0) * 20))
            key = (text, src, bucket)
            seen_src[key] = seen_src.get(key, 0) + 1
            if seen_src[key] > 1 and src:
                return "token duplicado sem justificativa"
    orig_texts = [str(c.get("text") or "") for c in original or [] if isinstance(c, dict)]
    new_texts = [str(c.get("text") or "") for c in remapped if isinstance(c, dict)]
    if orig_texts and new_texts:
        oi = 0
        for t in new_texts:
            if oi < len(orig_texts) and orig_texts[oi] == t:
                oi += 1
                continue
            if oi > 0 and orig_texts[oi - 1] == t:
                continue
            while oi < len(orig_texts) and orig_texts[oi] != t:
                oi += 1
            if oi >= len(orig_texts):
                return "ordem das palavras invertida"
            oi += 1
    return None
