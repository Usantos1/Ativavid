"""Plano de corte via IA (sessão local /v1) — centro do 1-clique.

Lê takes_packed.md + preset da marca, pede à IA (Gemini/ChatGPT cookies ou
fallback) um EDL profissional, e encaixa os ranges nas speech regions.
Se a IA falhar, o caller deve cair no corte heurístico.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LEAD_S = 0.05
TRAIL_S = 0.12
MAX_PACKED_CHARS = 14000


def _load_packed(edit_dir: Path) -> str:
    p = edit_dir / "takes_packed.md"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8-sig", errors="replace").strip()
    if len(text) > MAX_PACKED_CHARS:
        text = text[:MAX_PACKED_CHARS] + "\n\n[…transcript truncado…]"
    return text


def _preset_brief(preset: dict) -> str:
    copy = preset.get("endCardCopy") or {}
    elems = preset.get("elements") or {}
    return json.dumps({
        "edit": preset.get("edit") or "limpa",
        "headline": preset.get("headline"),
        "captions": preset.get("captions"),
        "accent": preset.get("accent"),
        "rhythm": preset.get("rhythm") or "dinamico",
        "intensity": preset.get("intensity") or "medio",
        "speechClean": preset.get("speechClean") or "medio",
        "videoGoal": preset.get("videoGoal") or "reels",
        "brollMode": preset.get("brollMode") or "quando_necessario",
        "oneClick": bool(preset.get("oneClick", preset.get("fastMode", True))),
        "elements": {
            "zoomAuto": elems.get("zoomAuto"),
            "zoomCuts": elems.get("zoomCuts"),
            "flashCut": elems.get("flashCut"),
            "endCard": elems.get("endCard"),
            "musicAI": elems.get("musicAI"),
        },
        "brand": {
            "line1": (copy.get("line1") or "").strip(),
            "line2": (copy.get("line2") or "").strip(),
            "endCardType": preset.get("endCardType") or "seguir",
        },
    }, ensure_ascii=False, indent=2)


def _rhythm_rules(preset: dict) -> str:
    rhythm = (preset.get("rhythm") or "dinamico").lower()
    intensity = (preset.get("intensity") or "medio").lower()
    clean = (preset.get("speechClean") or "medio").lower()
    goal = (preset.get("videoGoal") or "reels").lower()

    rhythm_map = {
        "natural": "Poucos cortes; cenas 3–6s; pausas naturais curtas ok.",
        "dinamico": "Ritmo comercial; cenas 1.5–4s; silêncios longos fora.",
        "viral": "Muitos cortes; cenas 0.8–2.5s; energia alta; hook agressivo.",
        "muito_rapido": "Corte máximo; cenas ≤2s; quase sem pausa; só o essencial.",
    }
    intensity_map = {
        "sutil": "Zoom/efeitos discretos; flash raro ou nenhum.",
        "medio": "Zoom nos beats importantes; flash só em viradas.",
        "forte": "Zoom frequente; punch-ins; flash em mudanças de ideia.",
    }
    clean_map = {
        "desativado": "Não remova fillers agressivamente — só silêncios longos óbvios.",
        "leve": "Remova silêncios >0.8s e falsos começos claros.",
        "medio": "Remova silêncios longos, gaguejos e retomadas óbvias; preserve naturalidade.",
        "agressivo": "Compacte ao máximo, mas NUNCA corte no meio da palavra; se duvidar, mantenha.",
    }
    goal_map = {
        "reels": "Objetivo Reels: retenção + curiosidade + CTA leve.",
        "tiktok": "Objetivo TikTok: hook imediato + ritmo alto.",
        "shorts": "Objetivo Shorts: clareza + ritmo + CTA.",
        "anuncio": "Objetivo anúncio: HOOK → problema → benefício → CTA claro.",
        "educativo": "Objetivo educativo: clareza didática; menos flash.",
        "venda": "Objetivo venda: benefício + prova + CTA forte.",
        "depoimento": "Objetivo depoimento: edição limpa; preserve autenticidade.",
        "institucional": "Objetivo institucional: sóbrio; poucos efeitos.",
    }
    return (
        f"RITMO={rhythm}: {rhythm_map.get(rhythm, rhythm_map['dinamico'])}\n"
        f"INTENSIDADE={intensity}: {intensity_map.get(intensity, intensity_map['medio'])}\n"
        f"LIMPEZA_FALA={clean}: {clean_map.get(clean, clean_map['medio'])}\n"
        f"OBJETIVO={goal}: {goal_map.get(goal, goal_map['reels'])}\n"
    )


def _system_prompt(preset: dict | None = None) -> str:
    extra = _rhythm_rules(preset or {})
    return (
        "Você é o editor-chefe do ATIVAVID (Reels/TikTok/Shorts vertical 9:16).\n"
        "Recebe a transcrição empacotada e o estilo da marca. Monte um corte "
        "profissional, ritmado e comercial.\n\n"
        "REGRAS:\n"
        "- Ordem cronológica no mesmo source.\n"
        "- Comece com HOOK forte nos primeiros 1–3s.\n"
        "- Remova silêncios longos, gaguejos, falsos começos e trechos sem valor "
        "(respeitando LIMPEZA_FALA).\n"
        "- Prefira bordas em silêncio / fim de frase; pad ~30–200ms implícito.\n"
        "- Alvo típico: 15–45s se o material permitir; senão o melhor compacto "
        "(ajuste ao RITMO).\n"
        "- Beats úteis: HOOK, PROBLEM, SOLUTION, BENEFIT, PROOF, CTA (pule o que não existir).\n"
        "- start/end em segundos no vídeo ORIGINAL (não invente timestamps fora da fala).\n"
        "- Também devolva headline curta (máx 6 palavras) em \"headline\".\n"
        "- Responda SOMENTE JSON válido (sem markdown, sem prosa).\n\n"
        f"PARÂMETROS DO PRESET:\n{extra}\n"
        "FORMATO:\n"
        '{"ranges":[{"source":"SRC","start":1.2,"end":4.5,"beat":"HOOK",'
        '"quote":"…","reason":"…"}],"hook":"uma linha","headline":"…","notes":"opcional"}'
    )


def _user_prompt(
    *,
    source_key: str,
    packed: str,
    preset: dict,
    regions: list[tuple[float, float]],
    duration_hint: float | None,
) -> str:
    reg_lines = "\n".join(f"- {a:.2f} → {b:.2f}" for a, b in regions[:80])
    dur = f"{duration_hint:.1f}s" if duration_hint else "desconhecida"
    return (
        f"SOURCE_KEY={source_key}\n"
        f"DURAÇÃO≈{dur}\n"
        f"TIPO=short-form vertical (Reels/TikTok)\n\n"
        f"## Estilo / marca\n{_preset_brief(preset)}\n\n"
        f"## Regiões de fala detectadas (ancore os cortes nelas)\n{reg_lines}\n\n"
        f"## Transcrição (takes_packed)\n{packed or '(vazia)'}\n"
    )


def _extract_json(text: str) -> dict | list:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", raw)
        if not m:
            raise
        return json.loads(m.group(0))


def _snap_to_regions(
    start: float,
    end: float,
    regions: list[tuple[float, float]],
    source_dur: float | None = None,
) -> tuple[float, float] | None:
    if end <= start:
        return None
    if not regions:
        s, e = max(0.0, start - LEAD_S), end + TRAIL_S
        if source_dur and source_dur > 0:
            e = min(e, source_dur)
        return (s, e) if e - s >= 0.12 else None

    # Merge speech islands across short gaps so a multi-phrase AI beat
    # (e.g. 40.0→45.3 with three regions) is not crushed into the first island.
    gap = 0.45
    hits = [(a, b) for a, b in regions if b >= start - 0.05 and a <= end + 0.05]
    if not hits:
        mid = (start + end) / 2
        hits = [min(regions, key=lambda r: abs((r[0] + r[1]) / 2 - mid))]

    hits.sort()
    blocks: list[list[float]] = [[hits[0][0], hits[0][1]]]
    for a, b in hits[1:]:
        if a <= blocks[-1][1] + gap:
            blocks[-1][1] = max(blocks[-1][1], b)
        else:
            blocks.append([a, b])

    def _overlap(block: list[float]) -> float:
        return max(0.0, min(end, block[1]) - max(start, block[0]))

    a, b = max(blocks, key=_overlap)
    # Prefer the AI span when it sits inside the merged speech block
    s = max(a, min(start, b - 0.15))
    e = min(b, max(end, a + 0.15))
    if e - s < 0.25:
        s, e = a, b
    s, e = max(0.0, s - LEAD_S), e + TRAIL_S
    if source_dur and source_dur > 0:
        e = min(e, source_dur)
    return (s, e) if e - s >= 0.12 else None


def _apply_gain(start: float, end: float, voice: dict) -> float:
    gain = 0.0
    for run in voice.get("low_runs") or []:
        rs, re_ = float(run.get("start") or 0), float(run.get("end") or 0)
        if re_ < start or rs > end:
            continue
        g = float(run.get("suggest_gain_db") or 0)
        if g > gain:
            gain = g
    return round(min(gain, 12.0), 1)


def _normalize_ranges(
    data: dict | list,
    *,
    source_key: str,
    regions: list[tuple[float, float]],
    voice: dict,
    source_dur: float | None = None,
) -> list[dict]:
    if isinstance(data, list):
        items = data
    else:
        items = data.get("ranges") or data.get("cuts") or []
    if not isinstance(items, list) or not items:
        raise ValueError("IA não devolveu ranges")

    out: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        snapped = _snap_to_regions(start, end, regions, source_dur=source_dur)
        if not snapped:
            continue
        s, e = snapped
        if out and s < out[-1]["end"] - 0.05:
            # keep chronological; skip overlap heavy
            if e <= out[-1]["end"]:
                continue
            s = max(s, out[-1]["end"])
            if e - s < 0.2:
                continue
        beat = str(item.get("beat") or ("HOOK" if i == 0 else f"B{i}")).upper()[:24]
        quote = str(item.get("quote") or "")[:160]
        reason = str(item.get("reason") or "IA")[:200]
        out.append({
            "source": source_key,
            "start": round(s, 3),
            "end": round(e, 3),
            "beat": beat,
            "quote": quote,
            "reason": reason,
            "gain_db": _apply_gain(s, e, voice),
        })
    if not out:
        raise ValueError("ranges IA vazios após snap")
    return out


def plan_cut(
    *,
    edit_dir: Path,
    source_key: str,
    preset: dict,
    regions: list[tuple[float, float]],
    voice: dict,
    duration_s: float | None = None,
) -> tuple[list[dict], dict]:
    """Return (ranges, meta). Raises on failure."""
    from app.llm_session import chat, status as sess_status

    st = sess_status()
    if not st.get("ok"):
        raise RuntimeError(st.get("message") or "sem sessão IA")

    packed = _load_packed(edit_dir)
    if len(packed) < 20:
        raise RuntimeError("takes_packed.md insuficiente para a IA")

    messages = [
        {"role": "system", "content": _system_prompt(preset)},
        {"role": "user", "content": _user_prompt(
            source_key=source_key,
            packed=packed,
            preset=preset,
            regions=regions,
            duration_hint=duration_s,
        )},
    ]
    text, backend = chat(messages, model="gemini-web/default")
    parsed = _extract_json(text)
    ranges = _normalize_ranges(
        parsed,
        source_key=source_key,
        regions=regions,
        voice=voice,
        source_dur=duration_s,
    )
    meta = {
        "backend": backend,
        "hook": (parsed.get("hook") if isinstance(parsed, dict) else None),
        "headline": (parsed.get("headline") if isinstance(parsed, dict) else None),
        "notes": (parsed.get("notes") if isinstance(parsed, dict) else None),
        "rangeCount": len(ranges),
        "rawChars": len(text or ""),
    }
    # Persist for editor / doutor
    (edit_dir / "llm_cut_plan.json").write_text(
        json.dumps({"ranges": ranges, "meta": meta, "raw": text[:8000]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ranges, meta


def try_plan_cut(**kwargs: Any) -> tuple[list[dict] | None, dict]:
    """Best-effort wrapper — never raises."""
    try:
        ranges, meta = plan_cut(**kwargs)
        meta["ok"] = True
        return ranges, meta
    except Exception as e:  # noqa: BLE001
        return None, {"ok": False, "error": str(e)[:500]}
