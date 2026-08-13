"""Score estrutural do vídeo (não é 'chance de viralizar')."""
from __future__ import annotations

from typing import Any


def score_structural(
    *,
    duration: float,
    ranges: list[dict] | None,
    has_hook_beat: bool,
    has_cta: bool,
    silence_flags: int = 0,
    transcript_ok: bool = True,
) -> dict[str, Any]:
    ranges = ranges or []
    n = len(ranges)
    hook = 70
    if has_hook_beat:
        hook = 90
    elif n and float(ranges[0].get("end", 0) - ranges[0].get("start", 0)) <= 3.5:
        hook = 82

    clarity = 85 if transcript_ok else 55
    # ritmo: mais takes em vídeo curto = mais dinâmico (até um ponto)
    if duration <= 0:
        rhythm = 50
    else:
        cuts_per_10 = (n / max(duration, 1)) * 10
        if 1.2 <= cuts_per_10 <= 3.5:
            rhythm = 86
        elif cuts_per_10 < 0.8:
            rhythm = 62
        else:
            rhythm = 74
    rhythm = max(40, rhythm - min(20, silence_flags * 4))

    cta = 88 if has_cta else 58
    overall = round(0.3 * hook + 0.25 * clarity + 0.25 * rhythm + 0.2 * cta)

    tips: list[str] = []
    if hook < 80:
        tips.append("A abertura pode ser mais direta nos primeiros 1–3s.")
    if not has_cta:
        tips.append("O CTA pode entrar antes do final.")
    if silence_flags:
        tips.append("Há pausas longas que dá para enxugar.")
    if clarity < 70:
        tips.append("A transcrição está fraca — confira o áudio.")
    if not tips:
        tips.append("A estrutura está sólida para revisão humana.")

    return {
        "overall": overall,
        "hook": hook,
        "clarity": clarity,
        "rhythm": rhythm,
        "cta": cta,
        "tips": tips,
        "disclaimer": "Análise estrutural por boas práticas — não é previsão de alcance.",
    }
