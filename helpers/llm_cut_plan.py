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
    from app.editing_intent import prompt_rules

    if (preset.get("editingIntent") or "").lower() == "complete":
        return (
            prompt_rules(preset)
            + "RITMO/INTENSIDADE/TIPO do preset NÃO autorizam cortar fala. "
            "Ignore punchline, retenção, ritmo ou 'deixar mais rápido' como motivo.\n"
            "LIMPEZA_FALA=complete: só silêncio excessivo, erro+recomeço, "
            "frase abandonada/refeita, repetição literal, ruído sem fala, "
            "preparação de gravação descartável.\n"
        )

    rhythm = (preset.get("rhythm") or "dinamico").lower()
    intensity = (preset.get("intensity") or "medio").lower()
    clean = (preset.get("speechClean") or "medio").lower()
    from app.content_type import CONTENT_TYPES

    goal_raw = preset.get("videoGoal")
    extra_type = str(preset.get("contentType") or "").strip().lower()
    if not goal_raw and extra_type not in CONTENT_TYPES:
        goal_raw = extra_type
    goal = (goal_raw or "reels").lower()

    # Aliases da UI (Estilos) → chaves do prompt
    rhythm_alias = {
        "calmo": "natural",
        "rapido": "viral",
        "rápido": "viral",
        "muito_rapido": "muito_rapido",
    }
    goal_alias = {
        "tutorial": "educativo",
        "educativo": "educativo",
        "shorts": "shorts",
        "tiktok": "tiktok",
        "vendas": "venda",
    }
    rhythm = rhythm_alias.get(rhythm, rhythm)
    goal = goal_alias.get(goal, goal)

    natural_txt = (
        "Poucos cortes; cenas 3–8s; preserve o fio da conversa. "
        "NÃO pule frases do meio só para encurtar. "
        "Só corte silêncio longo, falso começo e repetição óbvia."
    )
    viral_txt = "Muitos cortes; cenas 0.8–2.5s; energia alta; hook agressivo."
    rhythm_map = {
        "natural": natural_txt,
        # A UI manda "calmo"/"rapido" — sem estes aliases os presets Natural
        # e Intenso caíam em silêncio no fallback "dinamico" (bug real).
        "calmo": natural_txt,
        "dinamico": "Ritmo comercial; cenas 1.5–4s; silêncios longos fora; mantenha contexto entre beats.",
        "viral": viral_txt,
        "rapido": viral_txt,
        "muito_rapido": "Corte máximo; cenas ≤2s; quase sem pausa; só o essencial.",
        "cirurgico": (
            "Corte CIRÚRGICO: um corte a cada frase completa; remova TODA "
            "pausa, respiração e conector vazio entre frases; cenas 1–3s. "
            "A frase nunca é quebrada no meio — corta-se ENTRE frases, sempre."
        ),
        "narrativa": (
            "Ritmo de NARRATIVA: blocos longos de 5–15s que preservam a "
            "história inteira; nunca corte dentro de um arco (setup → "
            "desenvolvimento → conclusão). Só remova o que está FORA da "
            "história: silêncio longo, erro de gravação, tangente abandonada."
        ),
    }
    intensity_map = {
        "sutil": "Zoom/efeitos discretos; flash raro ou nenhum.",
        "medio": "Zoom nos beats importantes; flash só em viradas.",
        "forte": "Zoom frequente; punch-ins; flash em mudanças de ideia.",
    }
    clean_map = {
        "desativado": "Não remova fillers agressivamente — só silêncios longos óbvios.",
        "leve": "Remova só silêncios >0.8s e falsos começos claros. Preserve hesitações naturais e o contexto.",
        "medio": "Remova silêncios longos, gaguejos e retomadas óbvias; preserve naturalidade e o sentido da fala.",
        "agressivo": "Compacte ao máximo, mas NUNCA corte no meio da palavra; se duvidar, mantenha.",
    }
    goal_map = {
        "reels": "Objetivo Reels: retenção + curiosidade + CTA leve — sem apagar o raciocínio.",
        "tiktok": "Objetivo TikTok: hook imediato + ritmo alto.",
        "shorts": "Objetivo Shorts: clareza + ritmo + CTA.",
        "anuncio": "Objetivo anúncio: HOOK → problema → benefício → CTA claro.",
        "educativo": "Objetivo educativo/tutorial: clareza didática; preserve passos e explicação; menos flash.",
        "venda": "Objetivo venda: benefício + prova + CTA forte.",
        "depoimento": "Objetivo depoimento: edição limpa; preserve autenticidade.",
        "vlog": "Objetivo vlog: tom natural; poucos cortes; preserve contexto e personalidade.",
        "institucional": "Objetivo institucional: sóbrio; poucos efeitos.",
        "humor": "Objetivo humor: preserve setup + punchline + reação; não corte a graça.",
        "informativo": "Objetivo informativo: clareza; preserve dados e conclusão.",
        "vendas": "Objetivo venda: benefício + prova + CTA forte.",
    }
    keep_ctx = (
        "PRIORIDADE: não tire do contexto. Se uma frase depende da anterior, mantenha as duas. "
        "Prefira um corte um pouco mais longo a um highlight confuso.\n"
        "HUMOR: se houver piada, punchline, ironia ou 'reação engraçada', NÃO corte o setup "
        "nem a queda — sem isso o vídeo perde o sentido cômico. Melhor 3s a mais do que matar a piada.\n"
    )
    return (
        prompt_rules(preset)
        + keep_ctx
        + f"RITMO={rhythm}: {rhythm_map.get(rhythm, rhythm_map['dinamico'])}\n"
        + f"INTENSIDADE={intensity}: {intensity_map.get(intensity, intensity_map['medio'])}\n"
        + f"LIMPEZA_FALA={clean}: {clean_map.get(clean, clean_map['medio'])}\n"
        + f"TIPO_CONTEUDO={goal}: {goal_map.get(goal, goal_map['reels'])}\n"
    )


def _system_prompt(preset: dict | None = None) -> str:
    extra = _rhythm_rules(preset or {})
    intent = ((preset or {}).get("editingIntent") or "dynamic").lower()
    if intent == "complete":
        role = (
            "Você é o editor-chefe do ATIVAVID. Este job é EDITAR O VÍDEO COMPLETO: "
            "o objetivo NÃO é encurtar. Mantenha o conteúdo e só limpe o que "
            "claramente não deveria estar no vídeo.\n"
        )
        hook_rule = (
            "- Preserve o PRIMEIRO bloco packed INTEIRO. Não corte falas internas "
            "da abertura só para melhorar ritmo (ex.: pergunta/resposta, reação).\n"
        )
        target = (
            "- Não há alvo de duração. Um vídeo bem gravado fica quase do mesmo tamanho. "
            "PROIBIDO remover fala por ritmo, punchline, retenção ou 'parte mais forte'.\n"
            "- Se remover um trecho, liste em \"drops\" com class exatamente um de: "
            "silence | false_start | repetition | abandoned_take | non_content.\n"
        )
    elif intent == "shorts":
        role = (
            "Você é o editor-chefe do ATIVAVID. Este job é CRIAR REELS/SHORTS: "
            "escolha trechos independentes e fortes do material.\n"
        )
        hook_rule = (
            "- Cada short precisa de um gancho próprio no começo do TRECHO escolhido.\n"
        )
        target = (
            "- Alvo: 20–60s por trecho. Pode ignorar o restante do original.\n"
        )
    else:
        role = (
            "Você é o editor-chefe do ATIVAVID. Este job é DEIXAR MAIS DINÂMICO: "
            "acelere o ritmo sem destruir a estrutura narrativa, o humor nem o CTA.\n"
            "Dynamic NÃO é 'encurtar a qualquer custo' e NÃO é obrigado a cortar.\n"
        )
        hook_rule = (
            "- Preserve o gancho inicial. Pode limpar respiração, não a intenção da abertura.\n"
            "- HUMOR: setup + resposta + reação + punchline/callback formam UMA unidade. "
            "Se a frase seguinte perde o sentido ou a graça sem o trecho, PRESERVE o bloco.\n"
            "- Punchline ≠ CTA. Uma punchline pode estar no meio e não ter palavra de CTA.\n"
        )
        target = (
            "- Alvo: mais rápido que o original só se sobrar silêncio/erro/repetição real. "
            "Não remova fala lenta, 'contexto' ou setup para chegar na punchline.\n"
            "- Vídeo curto (cerca de ≤15s): quase não corte fala; só silêncio/erro/"
            "falso começo/pausa morta. Um clipe de ~4s provavelmente já é a peça final.\n"
        )
    cut_rule = (
        "- Remova SOMENTE silêncio excessivo, erro+recomeço, take abandonada, "
        "repetição literal ou ruído sem fala. Na dúvida, PRESERVE a fala.\n"
        if intent == "complete"
        else
        "- Remova silêncios longos, gaguejos e falsos começos "
        "(respeitando LIMPEZA_FALA e a INTENÇÃO). NÃO remova frases só porque 'encurtam'.\n"
    )
    return (
        role
        + "Recebe a transcrição empacotada e o estilo da marca. Monte um corte "
        "fiel ao que a pessoa disse.\n\n"
        "REGRAS:\n"
        "- Ordem cronológica no mesmo source.\n"
        f"{hook_rule}"
        f"{cut_rule}"
        "- HUMOR/COMÉDIA: preserve setup + punchline + reação. Nunca deixe só o começo "
        "da piada nem corte a frase que faz a graça.\n"
        "- Prefira bordas em silêncio / fim de frase; pad ~30–200ms implícito.\n"
        f"{target}"
        "- Beats úteis: HOOK, PROBLEM, SOLUTION, BENEFIT, PROOF, CTA "
        "(pule o que não existir — mas não pule o miolo que liga um beat ao outro).\n"
        "- start/end em segundos no vídeo ORIGINAL (não invente timestamps fora da fala).\n"
        "- Também devolva headline curta (máx 6 palavras) em \"headline\" E mais "
        "2 alternativas com ângulos DIFERENTES (curiosidade, benefício, urgência…) "
        "em \"headlineAlts\".\n"
        "- Devolva também \"headlineQuestion\" (pergunta curta que o vídeo "
        "responde, máx 6 palavras, terminada em ?) e \"headlineAnswer\" "
        "(a resposta em máx 5 palavras).\n"
        "- Responda SOMENTE JSON válido (sem markdown, sem prosa).\n\n"
        f"PARÂMETROS DO PRESET:\n{extra}\n"
        "FORMATO:\n"
        '{"ranges":[{"source":"SRC","start":1.2,"end":4.5,"beat":"HOOK",'
        '"quote":"…","reason":"…"}],"hook":"uma linha","headline":"…",'
        '"headlineAlts":["…","…"],"notes":"opcional"}'
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
    intent = (preset.get("editingIntent") or "dynamic").lower()
    tipo = (
        "vídeo completo (preservar conteúdo; NÃO é highlight/Reels)"
        if intent == "complete"
        else (
            "vídeo curto — preserve fala; só limpe silêncio/erro"
            if (duration_hint is not None and float(duration_hint) <= 15)
            else "deixar mais dinâmico sem destruir narrativa/humor"
        )
        if intent == "dynamic"
        else "short-form vertical (Reels/TikTok)"
    )
    return (
        f"SOURCE_KEY={source_key}\n"
        f"DURAÇÃO≈{dur}\n"
        f"TIPO={tipo}\n\n"
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
    try:
        from app.editing_intent import guard_ranges

        ranges = guard_ranges(
            ranges,
            preset=preset,
            regions=regions,
            duration_s=duration_s,
            edit_dir=edit_dir,
            source_stem=source_key,
            drops=parsed.get("drops") if isinstance(parsed, dict) else None,
        )
    except Exception:
        pass
    drops = parsed.get("drops") if isinstance(parsed, dict) else None
    alts = parsed.get("headlineAlts") if isinstance(parsed, dict) else None
    if isinstance(alts, list):
        alts = [str(a).strip()[:80] for a in alts if str(a or "").strip()][:3]
    else:
        alts = []
    meta = {
        "backend": backend,
        "hook": (parsed.get("hook") if isinstance(parsed, dict) else None),
        "headline": (parsed.get("headline") if isinstance(parsed, dict) else None),
        "headlineAlts": alts,
        "headlineQuestion": (
            str(parsed.get("headlineQuestion") or "").strip()[:80]
            if isinstance(parsed, dict) else ""
        ),
        "headlineAnswer": (
            str(parsed.get("headlineAnswer") or "").strip()[:80]
            if isinstance(parsed, dict) else ""
        ),
        "notes": (parsed.get("notes") if isinstance(parsed, dict) else None),
        "rangeCount": len(ranges),
        "rawChars": len(text or ""),
    }
    # Persist for editor / doutor
    (edit_dir / "llm_cut_plan.json").write_text(
        json.dumps(
            {"ranges": ranges, "meta": meta, "drops": drops, "raw": text[:8000]},
            ensure_ascii=False,
            indent=2,
        ),
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
