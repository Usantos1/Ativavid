"""Nota da estrutura deste corte — não é previsão de alcance."""
from __future__ import annotations

from typing import Any


def _take_dur(r: dict) -> float:
    try:
        return max(0.0, float(r.get("end") or 0) - float(r.get("start") or 0))
    except (TypeError, ValueError):
        return 0.0


def _clamp(n: float, lo: float = 35, hi: float = 98) -> int:
    return int(round(min(hi, max(lo, n))))


def _hook_score(ranges: list[dict]) -> tuple[int, str | None]:
    if not ranges:
        return 48, "Sem takes para avaliar a abertura."
    first = ranges[0]
    beat = str(first.get("beat") or "").upper()
    hd = _take_dur(first)
    named = any(str(r.get("beat") or "").upper() == "HOOK" for r in ranges)
    score = 54.0
    tip = None
    if named and beat == "HOOK":
        score = 70
    elif named:
        score = 62
        tip = "O gancho existe, mas não abre o vídeo."
    if 1.2 <= hd <= 3.4:
        score += 16
    elif 0.8 <= hd <= 5.0:
        score += 8
    else:
        score -= 8
        tip = tip or "A abertura está longa ou curta demais para prender nos primeiros segundos."
    quote = str(first.get("quote") or "").strip()
    if len(quote) >= 16:
        score += 6
    elif len(quote) < 6 and named:
        score -= 4
    return _clamp(score), tip


def _clarity_score(ranges: list[dict], *, transcript_ok: bool, spoken: str) -> tuple[int, str | None]:
    n = max(1, len(ranges))
    quotes = [str(r.get("quote") or "").strip() for r in ranges]
    filled = sum(1 for q in quotes if len(q) >= 8)
    spoken_n = len((spoken or "").strip())
    if not transcript_ok or spoken_n < 18:
        return 48, "A transcrição está fraca — confira o áudio."
    score = 62 + 22 * (filled / n)
    if spoken_n < 70:
        score -= 10
        return _clamp(score), "Pouca fala aproveitada — o sentido pode ter ficado raso."
    if filled / n < 0.5:
        return _clamp(score - 8), "Vários takes sem fala clara."
    return _clamp(score), None


def _rhythm_score(
    ranges: list[dict],
    duration: float,
    *,
    silence_flags: int,
) -> tuple[int, str | None]:
    n = len(ranges)
    if duration <= 0 or n == 0:
        return 50, None
    cuts_per_10 = (n / duration) * 10
    dist = abs(cuts_per_10 - 2.1)
    if dist <= 0.5:
        score = 90.0
    elif dist <= 1.4:
        score = 84 - dist * 10
    elif cuts_per_10 < 0.7:
        score = 56.0
    else:
        score = 70.0
    durs = [_take_dur(r) for r in ranges if _take_dur(r) > 0.05]
    tip = None
    if durs:
        avg = sum(durs) / len(durs)
        if avg > 9:
            score -= 10
            tip = "Os takes estão longos — o ritmo pode cansar."
        elif avg < 0.65 and n >= 6:
            score -= 12
            tip = "Cortes demais: o vídeo ficou picado."
        elif max(durs) > 14:
            score -= 6
            tip = tip or "Tem um trecho longo demais no meio."
    score -= min(18, silence_flags * 5)
    if silence_flags and not tip:
        tip = "Há pausas longas que dá para enxugar."
    return _clamp(score), tip


def _cta_score(ranges: list[dict]) -> tuple[int, str | None]:
    if not ranges:
        return 50, None
    last = ranges[-1]
    named = [r for r in ranges if str(r.get("beat") or "").upper() == "CTA"]
    if not named:
        return 56, "O CTA pode entrar antes do final."
    cd = _take_dur(named[-1])
    score = 68.0
    tip = None
    if 1.0 <= cd <= 4.2:
        score = 84
    elif cd <= 7:
        score = 72
    else:
        score = 60
        tip = "O fechamento está longo demais."
    if named[-1] is last:
        score += 6
    else:
        score -= 8
        tip = tip or "O CTA não é o último take."
    return _clamp(score), tip


def score_structural(
    *,
    duration: float,
    ranges: list[dict] | None,
    has_hook_beat: bool | None = None,
    has_cta: bool | None = None,
    silence_flags: int = 0,
    transcript_ok: bool = True,
    spoken: str = "",
) -> dict[str, Any]:
    ranges = list(ranges or [])
    hook, hook_tip = _hook_score(ranges)
    clarity, clarity_tip = _clarity_score(
        ranges, transcript_ok=transcript_ok, spoken=spoken,
    )
    rhythm, rhythm_tip = _rhythm_score(
        ranges, duration, silence_flags=silence_flags,
    )
    cta, cta_tip = _cta_score(ranges)
    if has_hook_beat is False:
        hook = min(hook, 58)
    if has_cta is False:
        cta = min(cta, 56)

    overall = _clamp(0.30 * hook + 0.25 * clarity + 0.25 * rhythm + 0.20 * cta)

    tips = [t for t in (hook_tip, clarity_tip, rhythm_tip, cta_tip) if t]
    if not tips:
        if overall >= 88:
            tips.append("A estrutura deste corte está bem resolvida.")
        else:
            tips.append("Estrutura ok — ainda vale revisar gancho, ritmo e fechamento.")

    return {
        "overall": overall,
        "hook": hook,
        "clarity": clarity,
        "rhythm": rhythm,
        "cta": cta,
        "tips": tips,
        "disclaimer": "Nota deste corte (gancho, clareza, ritmo e CTA) — não é previsão de alcance.",
    }


def _band(n: int | None) -> str:
    try:
        v = int(n or 0)
    except (TypeError, ValueError):
        return ""
    if v >= 85:
        return "forte"
    if v >= 70:
        return "boa"
    if v >= 55:
        return "ok"
    return "fraca"


def present_score(score: dict | None) -> dict:
    """Rótulos a partir dos números já existentes. Não inventa métrica."""
    s = dict(score or {})
    if not s:
        return {}
    return {
        "overall": s.get("overall"),
        "items": [
            {"id": "hook", "label": "Gancho", "value": s.get("hook"), "text": _band(s.get("hook"))},
            {"id": "clarity", "label": "Clareza", "value": s.get("clarity"), "text": _band(s.get("clarity"))},
            {"id": "rhythm", "label": "Ritmo", "value": s.get("rhythm"), "text": _band(s.get("rhythm"))},
            {"id": "cta", "label": "CTA", "value": s.get("cta"), "text": _band(s.get("cta"))},
        ],
        "tips": list(s.get("tips") or []),
        "disclaimer": s.get("disclaimer") or "",
    }
