"""Intenção de edição por job — o que fazer com ESTE vídeo.

Não é estilo de marca. Não mexe em motor de render.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

INTENTS = ("complete", "dynamic", "shorts")
INTENT_FILE = "job_intent.json"

# Vídeo ≥ isto (segundos) recomenda "Editar vídeo completo"
LONG_VIDEO_SEC = 90.0

CTA_HINTS = (
    "me segue", "segue a gente", "segue o", "comenta", "compartilha",
    "salva esse", "salva este", "manda para", "manda pra", "chama no direct",
    "chama no zap", "chama no whats", "clica no link", "link na bio",
    "fale conosco", "chama no whatsapp", "até o próximo", "te vejo no próximo",
    "se você gostou", "se voce gostou", "se fez sentido", "agora você já sabe",
    "agora voce ja sabe", "entre em contato", "fala comigo", "me chama",
)

DEFAULTS = {
    "complete": {
        "preserveHook": True,
        "preserveCTA": True,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    "dynamic": {
        "preserveHook": True,
        "preserveCTA": True,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    "shorts": {
        "preserveHook": False,
        "preserveCTA": False,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
}


def suggest_intent(duration_s: float | None) -> str:
    if duration_s is not None and float(duration_s) >= LONG_VIDEO_SEC:
        return "complete"
    return "dynamic"


def normalize(raw: dict | None, *, duration_s: float | None = None) -> dict:
    src = dict(raw or {})
    mode = str(src.get("editingIntent") or src.get("intent") or "").strip().lower()
    if mode not in INTENTS:
        mode = suggest_intent(duration_s)
    flags = dict(DEFAULTS[mode])
    for key in flags:
        if key in src:
            flags[key] = bool(src[key])
    ranges = _parse_ranges(src.get("protectedRanges"))
    brand = str(src.get("brandStyleSource") or "default").strip().lower()
    if brand not in ("default", "custom"):
        brand = "default"
    return {
        "editingIntent": mode,
        "preserveHook": flags["preserveHook"],
        "preserveCTA": flags["preserveCTA"],
        "preserveCompleteSentences": flags["preserveCompleteSentences"],
        "preserveContext": flags["preserveContext"],
        "protectedRanges": ranges,
        "brandStyleSource": brand,
        "suggestedIntent": suggest_intent(duration_s) if duration_s is not None else None,
        "sourceDurationSec": round(float(duration_s), 2) if duration_s else None,
    }


def _parse_ranges(raw: Any) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if end > start >= 0:
            out.append({"start": round(start, 3), "end": round(end, 3)})
    return out


def save(edit_dir: Path, intent: dict) -> dict:
    data = normalize(intent)
    path = Path(edit_dir) / INTENT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load(edit_dir: Path) -> dict | None:
    path = Path(edit_dir) / INTENT_FILE
    if not path.exists():
        return None
    try:
        return normalize(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def merge_into_preset(preset: dict, intent: dict | None) -> dict:
    """Copia a intenção para o preset usado no plano de corte. Sem alterar visual."""
    out = dict(preset or {})
    if not intent:
        return out
    data = normalize(intent)
    out["editingIntent"] = data["editingIntent"]
    out["preserveHook"] = data["preserveHook"]
    out["preserveCTA"] = data["preserveCTA"]
    out["preserveCompleteSentences"] = data["preserveCompleteSentences"]
    out["preserveContext"] = data["preserveContext"]
    out["protectedRanges"] = data["protectedRanges"]
    out["brandStyleSource"] = data["brandStyleSource"]
    return out


def prompt_rules(preset: dict | None) -> str:
    """Bloco extra para o system prompt da IA de corte."""
    p = preset or {}
    mode = str(p.get("editingIntent") or "dynamic").lower()
    if mode not in INTENTS:
        mode = "dynamic"
    hook = bool(p.get("preserveHook", DEFAULTS[mode]["preserveHook"]))
    cta = bool(p.get("preserveCTA", DEFAULTS[mode]["preserveCTA"]))
    sentences = bool(p.get("preserveCompleteSentences", True))
    context = bool(p.get("preserveContext", True))
    ranges = p.get("protectedRanges") or []

    if mode == "complete":
        intent_txt = (
            "INTENÇÃO=complete (Editar vídeo completo).\n"
            "O objetivo NÃO é encurtar. É manter o conteúdo completo e só limpar "
            "o que claramente não deveria estar no vídeo.\n"
            "PODE remover somente: silêncio excessivo; erro evidente + recomeço; "
            "frase abandonada e refeita; repetição literal/quase literal; "
            "ruído/trecho sem fala útil; preparação de gravação descartável.\n"
            "PROIBIDO remover fala por: ritmo, punchline, retenção, deixar mais rápido, "
            "achar a frase menos interessante, preferir outra parte mais forte.\n"
            "Na dúvida (contexto, humor, argumento, reação, continuidade): PRESERVAR.\n"
            "O primeiro bloco semântico da transcrição deve permanecer INTEIRO "
            "(só silêncio interno excessivo ou erro/recomeço evidente).\n"
            "Classifique cada remoção com um destes rótulos e só estes: "
            "silence | false_start | repetition | abandoned_take | non_content.\n"
        )
    elif mode == "shorts":
        intent_txt = (
            "INTENÇÃO=shorts (Criar Reels / Shorts).\n"
            "Prioridade: selecionar trechos independentes e fortes (cerca de 20–60s cada).\n"
            "Pode ignorar partes grandes do original — o objetivo é um conteúdo curto novo.\n"
            "Cada trecho precisa de começo e fim próprios (gancho + conclusão naturais).\n"
            "Nunca termine um short no meio de uma frase ou CTA.\n"
        )
    else:
        intent_txt = (
            "INTENÇÃO=dynamic (Deixar mais dinâmico).\n"
            "Prioridade: ritmo + preservação de informação.\n"
            "Pode remover pausas menores e aproximar frases.\n"
            "Nunca remover contexto necessário para entender a próxima fala.\n"
            "Preserve a estrutura: abertura → desenvolvimento → conclusão.\n"
        )

    guards = [
        "CORTES POR UNIDADE SEMÂNTICA (não só por silêncio/timestamp):",
        "- Só corte se a frase e o pensamento terminaram.",
        "- Se existe complemento logo depois, ou a fala explica a próxima, MANTENHA.",
        "- Prefira: fim de frase, pausa natural, mudança de assunto, erro+recomeço, repetição, silêncio inútil.",
        "- Evite: meio de oração, meio de raciocínio, entre pergunta e resposta, antes da conclusão, começo de CTA.",
    ]
    if sentences:
        guards.append("- NUNCA corte frase pela metade. Se duvidar, mantenha até o ponto final da ideia.")
    if context:
        guards.append("- Preserve o contexto: pergunta+resposta, setup+punchline, premissa+conclusão.")
    if hook:
        if mode == "complete":
            guards.append(
                "- GANCHO/COMPLETE: preserve o PRIMEIRO bloco packed inteiro. "
                "Não corte falas internas da abertura (ex.: 'Não é, pai?' / 'Aham, é sim, filha')."
            )
        else:
            guards.append(
                "- GANCHO: o primeiro bloco falado é protegido. Pode limpar respiração/falso começo minúsculo, "
                "mas NÃO troque a abertura por outra frase 'mais forte' nem apague os primeiros segundos sem motivo semântico."
            )
    if cta:
        guards.append(
            "- CTA/CONCLUSÃO: quando a finalização começar, preserve o bloco INTEIRO até a conclusão natural. "
            "Sinais (não exclusivos): me segue, comenta, compartilha, salva, link na bio, chama no direct/WhatsApp, "
            "se você gostou, se fez sentido, até o próximo, entre em contato. "
            "PROIBIDO terminar em 'me segue para…' ou qualquer CTA cortado."
        )
    if ranges:
        bits = ", ".join(f"{r['start']:.2f}–{r['end']:.2f}s" for r in ranges[:12])
        guards.append(f"- TRECHOS PROTEGIDOS (obrigatório manter): {bits}.")

    return intent_txt + "\n".join(guards) + "\n"


def first_hook_region(regions: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not regions:
        return None
    for a, b in regions:
        if b - a >= 0.35:
            return (a, b)
    return regions[0]


def last_cta_region(regions: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not regions:
        return None
    return regions[-1]


def _covers(ranges: list[dict], start: float, end: float, *, min_overlap: float = 0.35) -> bool:
    need = max(0.2, min(min_overlap, (end - start) * 0.5))
    for r in ranges:
        try:
            a, b = float(r["start"]), float(r["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if min(b, end) - max(a, start) >= need:
            return True
    return False


def _insert_range(ranges: list[dict], start: float, end: float, beat: str, reason: str) -> list[dict]:
    item = {
        "source": (ranges[0].get("source") if ranges else "SRC"),
        "start": round(start, 3),
        "end": round(end, 3),
        "beat": beat,
        "quote": "",
        "reason": reason,
        "gain_db": 0.0,
    }
    out = list(ranges) + [item]
    out.sort(key=lambda r: float(r.get("start") or 0))
    merged: list[dict] = []
    for r in out:
        if merged and float(r["start"]) <= float(merged[-1]["end"]) + 0.08:
            merged[-1]["end"] = round(max(float(merged[-1]["end"]), float(r["end"])), 3)
            if r.get("beat") == "HOOK":
                merged[-1]["beat"] = "HOOK"
            if r.get("beat") == "CTA":
                merged[-1]["beat"] = "CTA"
        else:
            merged.append(dict(r))
    return merged


def looks_like_cta(text: str) -> bool:
    low = re.sub(r"\s+", " ", (text or "").lower())
    return any(h in low for h in CTA_HINTS)


PHRASE_RE = re.compile(r"\[(\d{3}\.\d{2})-(\d{3}\.\d{2})\]\s+S\d+\s+(.*)")
COMPLETE_ALLOWED_CLASSES = (
    "silence", "false_start", "repetition", "abandoned_take", "non_content",
)
COMPLETE_ALLOWED = (
    "silence", "silencio", "silêncio", "false_start", "falso comeco", "falso começo",
    "repetition", "repeticao", "repetição", "abandoned_take", "abandonad", "refeit",
    "non_content", "sem fala", "ruido", "ruído", "preparacao", "preparação",
)
COMPLETE_REJECTED = (
    "pace", "rhythm", "ritmo", "punchline", "retention", "retencao", "retenção",
    "boring", "encurtar", "highlight", "viral", "mais rapido", "mais rápido",
    "mais forte", "energia", "dinamico", "dinâmico",
)
_PREP_HINTS = (
    "ta gravando", "tá gravando", "espera ai", "espera aí", "perai", "peraí",
    "um dois tres", "um dois três", "testando", "mic test",
)
_FILLERS = {"ah", "eh", "uhm", "hum", "hmm", "tipo", "ne", "né", "ta", "tá", "ok", "e"}


def load_packed_phrases(edit_dir: Path, stem: str | None = None) -> list[dict]:
    """Lê takes_packed.md (não transcripts/*.json)."""
    path = Path(edit_dir) / "takes_packed.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sections: dict[str, list[dict]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].split()[0].strip()
            sections.setdefault(current, [])
            continue
        m = PHRASE_RE.search(line)
        if not m or not current:
            continue
        sections[current].append({
            "start": float(m.group(1)),
            "end": float(m.group(2)),
            "text": m.group(3).strip(),
        })
    if stem and stem in sections and sections[stem]:
        return sections[stem]
    usable = [(k, v) for k, v in sections.items() if k.lower() not in ("cut", "base") and v]
    if not usable:
        return []
    return max(usable, key=lambda kv: kv[1][-1]["end"] - kv[1][0]["start"])[1]


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _coverage(start: float, end: float, ranges: list[dict]) -> float:
    return sum(
        _overlap(start, end, float(r.get("start") or 0), float(r.get("end") or 0))
        for r in ranges
    )


def _speech_inside(
    start: float, end: float, regions: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    bits = []
    for a, b in regions or []:
        s, e = max(float(a), start), min(float(b), end)
        if e - s >= 0.12:
            bits.append((s, e))
    if not bits:
        return [(start, end)] if end - start >= 0.12 else []
    bits.sort()
    merged = [list(bits[0])]
    for a, b in bits[1:]:
        if a <= merged[-1][1] + 0.80:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _norm_txt(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (text or "").lower())).strip()


def _class_from_blob(blob: str) -> str | None:
    low = (blob or "").lower().replace("-", "_")
    if any(k in low for k in COMPLETE_REJECTED):
        return None
    for cls in COMPLETE_ALLOWED_CLASSES:
        if cls in low:
            return cls
    if any(k in low for k in COMPLETE_ALLOWED):
        if "repet" in low:
            return "repetition"
        if "abandon" in low or "refeit" in low:
            return "abandoned_take"
        if "false" in low or "falso" in low or "recomec" in low or "recomeç" in low:
            return "false_start"
        if "silen" in low:
            return "silence"
        return "non_content"
    return None


def _near_dup(a: str, b: str, *, thresh: float = 0.86) -> bool:
    na, nb = _norm_txt(a), _norm_txt(b)
    if not na or not nb or min(len(na), len(nb)) < 10:
        return False
    if na == nb or na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= thresh


def _drop_class_for(start: float, end: float, drops: list[dict] | None) -> str | None:
    span = max(0.01, end - start)
    best = None
    best_ov = 0.0
    for d in drops or []:
        try:
            a, b = float(d.get("start")), float(d.get("end"))
        except (TypeError, ValueError):
            continue
        ov = _overlap(start, end, a, b)
        if ov < 0.25 * span and ov < 0.35:
            continue
        cls = _class_from_blob(str(d.get("class") or d.get("reason") or ""))
        if ov > best_ov:
            best_ov = ov
            best = cls
    return best


def classify_complete_removal(
    phrase: dict,
    phrases: list[dict],
    *,
    drops: list[dict] | None = None,
) -> str | None:
    """Classe permitida ou None (restaurar). Sem teto de duração."""
    labeled = _drop_class_for(float(phrase["start"]), float(phrase["end"]), drops)
    if labeled:
        return labeled
    text = str(phrase.get("text") or "")
    low = _norm_txt(text)
    if not low:
        return "non_content"
    if any(h in low for h in _PREP_HINTS):
        return "non_content"
    words = low.split()
    if words and all(w in _FILLERS for w in words) and len(words) <= 2:
        return "non_content"
    later = [p for p in phrases if float(p["start"]) > float(phrase["end"]) - 0.05]
    earlier = [p for p in phrases if float(p["end"]) < float(phrase["start"]) + 0.05]
    if any(_near_dup(text, p.get("text") or "") for p in later + earlier):
        return "repetition"
    abandoned = text.rstrip().endswith(("...", "…")) or (
        len(words) <= 4 and not text.rstrip().endswith((".", "!", "?"))
    )
    if abandoned:
        head = " ".join(words[:4])
        for p in later:
            other = _norm_txt(str(p.get("text") or ""))
            if head and other.startswith(head[:12]):
                return "abandoned_take" if text.rstrip().endswith(("...", "…")) else "false_start"
    return None


def load_complete_drops(edit_dir: Path | None) -> list[dict]:
    if not edit_dir:
        return []
    path = Path(edit_dir) / "llm_cut_plan.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    raw = data.get("drops")
    if raw is None and isinstance(data.get("raw"), str):
        try:
            parsed = json.loads(data["raw"])
            raw = parsed.get("drops") if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            raw = None
    return raw if isinstance(raw, list) else []


def enforce_complete_edl(
    ranges: list[dict],
    *,
    phrases: list[dict],
    regions: list[tuple[float, float]],
    drops: list[dict] | None = None,
) -> list[dict]:
    """Restaura fala removida sem classe permitida. Só complete."""
    out = [dict(r) for r in (ranges or [])]
    if not phrases:
        return out
    for i, phrase in enumerate(phrases):
        ps, pe = float(phrase["start"]), float(phrase["end"])
        spoken = _speech_inside(ps, pe, regions)
        first = i == 0
        for a, b in spoken:
            cov = _coverage(a, b, out)
            need = 0.95 if first else 0.88
            if cov >= need * (b - a):
                continue
            if first:
                out = _insert_range(out, a, b, "HOOK", "restore-complete-first-block")
                continue
            cls = classify_complete_removal(phrase, phrases, drops=drops)
            if cls:
                continue
            out = _insert_range(out, a, b, "KEEP", "restore-complete: no allowed class")
    return out


def guard_ranges(
    ranges: list[dict],
    *,
    preset: dict | None,
    regions: list[tuple[float, float]],
    duration_s: float | None = None,
    edit_dir: Path | None = None,
    source_stem: str | None = None,
    drops: list[dict] | None = None,
) -> list[dict]:
    """Garante gancho, CTA e trechos protegidos no EDL. Não mexe em render."""
    p = preset or {}
    mode = str(p.get("editingIntent") or "dynamic").lower()
    if mode not in INTENTS:
        mode = "dynamic"
    out = [dict(r) for r in (ranges or [])]
    if not out and not regions:
        return out

    if mode == "complete":
        phrases = load_packed_phrases(edit_dir, source_stem) if edit_dir else []
        drop_list = list(drops or []) or load_complete_drops(edit_dir)
        if phrases:
            first = phrases[0]
            if bool(p.get("preserveHook", True)):
                for a, b in _speech_inside(first["start"], first["end"], regions):
                    if _coverage(a, b, out) < 0.95 * (b - a):
                        out = _insert_range(out, a, b, "HOOK", "preserve-hook-complete")
            out = enforce_complete_edl(out, phrases=phrases, regions=regions, drops=drop_list)
        elif bool(p.get("preserveHook", True)):
            hook = first_hook_region(regions)
            if hook and not _covers(out, hook[0], hook[1]):
                out = _insert_range(out, hook[0], hook[1], "HOOK", "preserve-hook")
    elif bool(p.get("preserveHook", DEFAULTS[mode]["preserveHook"])):
        hook = first_hook_region(regions)
        if hook and not _covers(out, hook[0], hook[1]):
            out = _insert_range(out, hook[0], hook[1], "HOOK", "preserve-hook")

    if bool(p.get("preserveCTA", DEFAULTS[mode]["preserveCTA"])):
        cta = last_cta_region(regions)
        if cta:
            if out:
                last = out[-1]
                if float(last.get("end") or 0) < cta[1] - 0.15:
                    last["end"] = round(cta[1], 3)
                    last["beat"] = "CTA"
                    last["reason"] = (str(last.get("reason") or "") + " · preserve-cta").strip(" ·")
            else:
                out = _insert_range(out, cta[0], cta[1], "CTA", "preserve-cta")

    for pr in p.get("protectedRanges") or []:
        try:
            a, b = float(pr["start"]), float(pr["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if b <= a:
            continue
        if duration_s:
            b = min(b, float(duration_s))
        if not _covers(out, a, b, min_overlap=0.2):
            out = _insert_range(out, a, b, "KEEP", "protected-range")

    return out
