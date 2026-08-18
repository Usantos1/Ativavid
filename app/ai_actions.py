"""Ações estruturadas de edição por IA — sem FFmpeg livre do LLM."""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from typing import Any

ALLOWED_ACTIONS = {
    "trim_range",
    "remove_range",
    "restore_range",
    "set_duration_max",
    "add_zoom",
    "remove_flashes",
    "set_headline",
    "set_captions_style",
    "set_rhythm",
    "set_intensity",
    "add_broll_hint",
    "mark_hook",
    "regenerate_hook",
    "fix_captions",
    "noop",
}

CONFIRM_EXACT = {
    "ok", "sim", "isso", "vai", "pode", "blz", "beleza", "fechou",
    "aplica", "aplicar", "faz", "faz isso", "manda ver",
    "ok pode aplicar", "pode aplicar", "ok aplicar", "ok aplica",
    "pode mandar", "pode fazer", "pode sim", "confirma", "confirmar",
    "aplica isso", "aplicar isso",
}

CONFIRM_RE = re.compile(
    r"^(ok|sim|blz|beleza|fechou)?\s*"
    r"(pode\s+)?"
    r"(aplicar|aplica|fazer|faz(\s+isso)?|mandar|manda\s+ver|confirmar|confirma)"
    r"(\s+isso)?\s*$",
    re.I,
)

RETRY_PROMPT = (
    "Formato inválido. Responda SOMENTE este JSON, sem prosa e sem markdown:\n"
    '{"actions":[{"action":"restore_range","start":0,"end":1,"reason":"…"}],'
    '"summary":"Vou…"}'
)
FAIL_PLAN = "Não consegui preparar essa alteração. Tente descrever de outra forma."
VAGUE_CUT_MSG = "Diga o que melhorar: um trecho para cortar, uma palavra da legenda, ou a headline."
MIN_KEEP_SEC = 3.0
CUT_ACTIONS = {"trim_range", "remove_range", "set_duration_max"}
CUT_INTENT_RE = re.compile(
    r"\b(corta|cortar|tira|tirar|remove|remover|apaga|apagar|"
    r"exclui|excluir|elimina|eliminar|reduz|reduzir|"
    r"encurta|encurtar|diminui|diminuir|trim|"
    r"deixa\s+s[oó]|s[oó]\s+os?\s+(primeiros?|[uú]ltimos?)|"
    r"[uú]ltimos?\s+\d+|primeiros?\s+\d+|no\s+m[aá]ximo\s+\d+)\b",
    re.I,
)

_CMD_FULL_RESTORE = re.compile(
    r"^(restaura|restaurar|volta|voltar|devolve|devolver)\s+"
    r"(o\s+)?(video|corte|original)\s+(completo|inteiro|todo|original)$"
)
_CMD_RESTORE_FIRST = re.compile(
    r"^(restaura|restaurar|volta|voltar|devolve|devolver)\s+"
    r"(os\s+)?(primeiros|primeiro)\s+(\d+(?:[.,]\d+)?)\s*(s|seg|segs|segundos?)?$"
)
_CMD_REMOVE_LAST = re.compile(
    r"^(remove|remover|tira|tirar|corta|cortar|apaga|apagar)\s+"
    r"(os\s+)?(ultimos|ultimo)\s+(\d+(?:[.,]\d+)?)\s*(s|seg|segs|segundos?)?$"
)
_CMD_FIX_CAPTION = re.compile(
    r"^(troca|trocar|corrige|corrigir|substitui|substituir|muda|mudar)\s+"
    r"(.+?)\s+(por|para|pra)\s+(.+)$"
)
_CMD_REMOVE_FIRST = re.compile(
    r"^(remove|remover|tira|tirar|corta|cortar|apaga|apagar)\s+"
    r"(os\s+)?(primeiros|primeiro)\s+(\d+(?:[.,]\d+)?)\s*(s|seg|segs|segundos?)?$"
)

TIMELINE_REQUIRED = {
    "restore_range": ("start", "end"),
    "trim_range": ("start", "end"),
    "remove_range": ("start", "end"),
    "set_duration_max": ("maxSec",),
}

SYSTEM = (
    "Você edita projetos ATIVAVID. Responda SOMENTE JSON válido:\n"
    '{"actions":[{"action":"…","start":0,"end":0,"reason":"…"}],'
    '"summary":"proposta em uma linha"}\n'
    "Ações permitidas: "
    + ", ".join(sorted(ALLOWED_ACTIONS))
    + ".\n"
    "CONVERSA ≠ AÇÃO: se for alterar o corte, OBRIGATÓRIO emitir actions reais. "
    "Nunca escreva que restaurou/aplicou/cortou se actions estiver vazio ou só noop.\n"
    "summary é PROPOSTA (futuro): 'Vou restaurar…'. Nunca pretérito de conclusão.\n"
    "restore_range: recoloca o trecho [start,end] do ORIGINAL (use para "
    "restaurar o vídeo completo ou um pedaço que a edição tirou).\n"
    "trim_range: mantém só [start,end] do corte atual (corta o resto).\n"
    "remove_range: apaga [start,end] do corte atual.\n"
    "set_duration_max: corta tudo depois de maxSec.\n"
    "regenerate_hook: text = nova headline (2 linhas curtas).\n"
    "Se o pedido for restaurar o vídeo/piada/sentido: use restore_range "
    "do início ao fim do ORIGINAL (sourceDuration), não do corte atual.\n"
    "fix_captions: from/to ou replacements=[{from,to}] para corrigir palavra "
    "errada na legenda (ex.: pericô→Película). Não corta o vídeo.\n"
    "Nunca invente FFmpeg. Prefira poucas ações claras.\n"
    "trim_range/remove_range/set_duration_max usam o relógio do CORTE ATUAL "
    "(0 até DURAÇÃO_CORTE_ATUAL). Os números do EDL_ATUAL são tempo da FONTE — "
    "não copie esses valores para trim/remove.\n"
    "Pedido vago (melhoria, melhora, deixa melhor) sem dizer O QUE cortar: "
    "não emita trim/remove/set_duration_max. Use noop.\n"
    "Nunca deixe o corte com menos de 3 segundos, salvo pedido explícito "
    "de um trecho curto."
)


def extract_json(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise ValueError("IA não devolveu JSON")
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON inválido")
    return data


def validate_actions(
    payload: dict,
    *,
    duration: float | None = None,
    source_duration: float | None = None,
) -> list[dict[str, Any]]:
    items = payload.get("actions") or []
    if not isinstance(items, list):
        raise ValueError("actions deve ser lista")
    out: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").strip()
        if action not in ALLOWED_ACTIONS:
            continue
        item = {"action": action}
        for key in ("start", "end", "scale", "maxSec"):
            if key in raw:
                try:
                    item[key] = float(raw[key])
                except (TypeError, ValueError):
                    continue
        for key in ("text", "style", "rhythm", "intensity", "query", "reason"):
            if key in raw and raw[key] is not None:
                item[key] = str(raw[key])[:240]
        cap = source_duration if action == "restore_range" else duration
        if cap is None:
            cap = duration or source_duration
        if cap is not None:
            if "start" in item:
                item["start"] = max(0.0, min(item["start"], cap))
            if "end" in item:
                item["end"] = max(0.0, min(item["end"], cap))
            if "maxSec" in item:
                item["maxSec"] = max(0.5, min(item["maxSec"], cap))
            if "start" in item and "end" in item and item["end"] <= item["start"]:
                continue
        if "scale" in item:
            item["scale"] = max(1.0, min(float(item["scale"]), 1.35))
        out.append(item)
    return out


def apply_actions_to_edits(
    actions: list[dict[str, Any]],
    *,
    style: dict[str, Any] | None = None,
    edit_data: dict[str, Any] | None = None,
    notes: list[dict[str, Any]] | None = None,
    duration: float | None = None,
    protected_ranges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aplica ações. timelineOps = instruções para o editor reescrever o corte."""
    from app.protected_ranges import filter_ai_ops, format_blocked_log

    style = dict(style or {})
    edit_data = dict(edit_data or {})
    notes = list(notes or [])
    applied: list[dict[str, Any]] = []
    timeline_ops: list[dict[str, Any]] = []
    blocked_ops: list[dict[str, Any]] = []

    for a in actions:
        act = a["action"]
        if act == "set_headline":
            style["headlineText"] = a.get("text") or style.get("headlineText")
            hook = dict(edit_data.get("hook") or {})
            text = (a.get("text") or "").strip()
            if text:
                words = text.split()
                mid = max(1, len(words) // 2)
                hook["lines"] = [" ".join(words[:mid]), " ".join(words[mid:]) or words[-1]]
                hook["enabled"] = True
                edit_data["hook"] = hook
            applied.append(a)
        elif act == "regenerate_hook":
            text = (a.get("text") or a.get("reason") or "").strip()
            hook = dict(edit_data.get("hook") or {})
            if text:
                parts = [p.strip() for p in re.split(r"[\n|/]+", text) if p.strip()]
                if len(parts) == 1:
                    words = parts[0].split()
                    mid = max(1, len(words) // 2)
                    parts = [" ".join(words[:mid]), " ".join(words[mid:]) or words[-1]]
                hook["lines"] = (parts + ["", ""])[:2]
                hook["enabled"] = True
                edit_data["hook"] = hook
                style["headlineText"] = " ".join(hook["lines"])
            timeline_ops.append({"op": "regenerate_hook", "lines": hook.get("lines") or []})
            applied.append(a)
        elif act == "mark_hook":
            start = float(a.get("start") or 0)
            end = float(a.get("end") or min(3.0, (duration or 4.0)))
            hook = dict(edit_data.get("hook") or {})
            hook["enabled"] = True
            hook["endSec"] = max(1.0, end - start) if end > start else max(1.5, float(hook.get("endSec") or 3))
            edit_data["hook"] = hook
            timeline_ops.append({"op": "mark_hook", "start": start, "end": end})
            applied.append(a)
        elif act == "set_captions_style" and a.get("style"):
            style["captions"] = a["style"]
            applied.append(a)
        elif act == "fix_captions":
            reps = list(a.get("replacements") or [])
            if a.get("from") and a.get("to"):
                reps.append({"from": a["from"], "to": a["to"]})
            reps = [r for r in reps if isinstance(r, dict) and r.get("from") and r.get("to")]
            if reps:
                timeline_ops.append({"op": "fix_captions", "replacements": reps})
                applied.append({**a, "replacements": reps})
        elif act == "set_rhythm" and a.get("rhythm"):
            style["rhythm"] = a["rhythm"]
            applied.append(a)
        elif act == "set_intensity" and a.get("intensity"):
            style["intensity"] = a["intensity"]
            applied.append(a)
        elif act == "remove_flashes":
            elems = dict(style.get("elements") or {})
            elems["flashCut"] = False
            style["elements"] = elems
            applied.append(a)
        elif act == "add_zoom":
            zooms = list((edit_data.get("camera") or {}).get("zooms") or [])
            zooms.append({
                "start": a.get("start", 0),
                "end": a.get("end", 1),
                "scale": a.get("scale", 1.12),
            })
            cam = dict(edit_data.get("camera") or {})
            cam["zooms"] = zooms
            edit_data["camera"] = cam
            applied.append(a)
        elif act == "remove_range" and "start" in a and "end" in a:
            timeline_ops.append({"op": "remove_range", "start": a["start"], "end": a["end"]})
            applied.append(a)
        elif act == "trim_range" and "start" in a and "end" in a:
            timeline_ops.append({"op": "trim_range", "start": a["start"], "end": a["end"]})
            applied.append(a)
        elif act == "restore_range" and "start" in a and "end" in a:
            timeline_ops.append({
                "op": "restore_range",
                "start": a["start"],
                "end": a["end"],
                "reason": a.get("reason") or "",
            })
            applied.append(a)
        elif act == "set_duration_max" and "maxSec" in a:
            timeline_ops.append({"op": "set_duration_max", "maxSec": a["maxSec"]})
            applied.append(a)
        elif act == "add_broll_hint":
            notes.append({
                "id": f"ai-{len(notes)+1}",
                "start": a.get("start", 0),
                "end": a.get("end", a.get("start", 0)),
                "text": a.get("query") or a.get("reason") or "b-roll",
                "kind": act,
                "fromAI": True,
            })
            # Quem decide é o brollMode (mesma regra do pipeline): em `limpa`
            # com b-roll no padrão fica só a nota; b-roll pedido de propósito
            # ("Sempre"/"Raro") coloca o insert mesmo em quadro cheio.
            edit_style = (style.get("edit") or "limpa").lower().strip()
            _bm = str(style.get("brollMode") or "quando_necessario").lower().strip()
            _broll_ok = _bm not in ("off", "nenhum", "none", "desligado") and (
                edit_style not in ("limpa", "clean", "limpo", "moldura", "barra", "desfocado", "degrade")
                or _bm not in ("quando_necessario", "", "auto")
            )
            if _broll_ok and a.get("query"):
                inserts = list(edit_data.get("inserts") or [])
                inserts.append({
                    "src": "",
                    "start": a.get("start", 0),
                    "end": a.get("end", (a.get("start") or 0) + 1.5),
                    "query": a["query"],
                    "hint": True,
                })
                edit_data["inserts"] = inserts
            applied.append(a)
        elif act == "noop":
            applied.append(a)

    filtered = filter_ai_ops(timeline_ops, protected_ranges or [])
    kept = filtered["kept"]
    blocked_ops = filtered["blocked"]
    if blocked_ops:
        print("\n".join(format_blocked_log(blocked_ops)), flush=True)

    return {
        "style": style,
        "editData": edit_data,
        "notes": notes,
        "applied": applied,
        "timelineOps": kept,
        "blockedOps": blocked_ops,
    }


def is_apply_confirmation(text: str) -> bool:
    """Frase de confirmação — não é um pedido novo para a IA."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"[.!,…]+$", "", t).strip()
    if not t:
        return False
    if t in CONFIRM_EXACT:
        return True
    return bool(CONFIRM_RE.match(t))


def _norm_cmd(text: str) -> str:
    raw = unicodedata.normalize("NFD", text or "")
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    raw = re.sub(r"\s+", " ", raw.strip().lower())
    return re.sub(r"[.!,…:;]+$", "", raw).strip()


def _cmd_num(raw: str) -> float:
    return float(str(raw).replace(",", "."))


def parse_deterministic_command(
    text: str,
    *,
    source_duration: float | None = None,
    cut_duration: float | None = None,
) -> dict[str, Any] | None:
    """Comando explícito → ação. Não interpreta pedido semântico."""
    t = _norm_cmd(text)
    if not t:
        return None
    if _CMD_FULL_RESTORE.match(t):
        end = source_duration or cut_duration
        if not end or float(end) <= 0.05:
            return None
        return {
            "actions": [{
                "action": "restore_range",
                "start": 0.0,
                "end": round(float(end), 3),
                "reason": "restore_full",
            }],
            "summary": f"Vou restaurar o vídeo completo (0–{float(end):.2f}s).",
            "backend": "deterministic",
        }
    m = _CMD_RESTORE_FIRST.match(t)
    if m:
        sec = _cmd_num(m.group(4))
        cap = source_duration or cut_duration
        if cap:
            sec = min(sec, float(cap))
        if sec <= 0.05:
            return None
        return {
            "actions": [{
                "action": "restore_range",
                "start": 0.0,
                "end": round(sec, 3),
                "reason": "restore_first",
            }],
            "summary": f"Vou restaurar os primeiros {sec:.2f}s.",
            "backend": "deterministic",
        }
    m = _CMD_REMOVE_LAST.match(t)
    if m:
        sec = _cmd_num(m.group(4))
        total = cut_duration or source_duration
        if not total or sec <= 0.05:
            return None
        keep = max(0.5, float(total) - sec)
        return {
            "actions": [{
                "action": "set_duration_max",
                "maxSec": round(keep, 3),
                "reason": "remove_last",
            }],
            "summary": f"Vou remover os últimos {sec:.2f}s.",
            "backend": "deterministic",
        }
    m = _CMD_FIX_CAPTION.match(t)
    if m:
        src = m.group(2).strip(" \"'")
        dst = m.group(4).strip(" \"'")
        if src and dst and src != dst:
            return {
                "actions": [{
                    "action": "fix_captions",
                    "from": src,
                    "to": dst,
                    "reason": "caption_typo",
                }],
                "summary": f"Vou trocar “{src}” por “{dst}” na legenda.",
                "backend": "deterministic",
            }
    m = _CMD_REMOVE_FIRST.match(t)
    if m:
        sec = _cmd_num(m.group(4))
        total = cut_duration or source_duration
        if sec <= 0.05:
            return None
        if total:
            sec = min(sec, float(total) - 0.05)
        return {
            "actions": [{
                "action": "remove_range",
                "start": 0.0,
                "end": round(sec, 3),
                "reason": "remove_first",
            }],
            "summary": f"Vou remover os primeiros {sec:.2f}s.",
            "backend": "deterministic",
        }
    return None


def structured_actions_ok(actions: list[dict[str, Any]] | None) -> bool:
    real = [a for a in (actions or []) if a.get("action") not in ("", "noop")]
    if not real:
        return False
    for a in real:
        need = TIMELINE_REQUIRED.get(str(a.get("action") or ""))
        if need and any(k not in a for k in need):
            return False
    return True


def interpret_llm_reply(
    text: str,
    *,
    duration: float | None = None,
    source_duration: float | None = None,
) -> tuple[list[dict[str, Any]], str] | None:
    """None se não houver JSON + actions válidas. Não inventa operação."""
    try:
        data = extract_json(text)
        actions = validate_actions(
            data, duration=duration, source_duration=source_duration,
        )
    except (ValueError, json.JSONDecodeError, TypeError):
        return None
    if not structured_actions_ok(actions):
        return None
    summary = str(data.get("summary") or "Alteração planejada")[:200]
    return actions, summary


def prompt_allows_cut(text: str) -> bool:
    return bool(CUT_INTENT_RE.search(_norm_cmd(text)))


def _estimated_remaining(actions: list[dict[str, Any]], cut_duration: float | None) -> float | None:
    if not cut_duration or float(cut_duration) <= 0:
        return None
    remaining = float(cut_duration)
    for a in actions or []:
        act = str(a.get("action") or "")
        if act == "restore_range":
            return None
        if act == "trim_range" and "start" in a and "end" in a:
            remaining = min(remaining, max(0.0, float(a["end"]) - float(a["start"])))
        elif act == "remove_range" and "start" in a and "end" in a:
            remaining -= max(0.0, float(a["end"]) - float(a["start"]))
        elif act == "set_duration_max" and "maxSec" in a:
            remaining = min(remaining, float(a["maxSec"]))
    return remaining


def filter_unsafe_cuts(
    actions: list[dict[str, Any]],
    *,
    prompt: str,
    cut_duration: float | None = None,
) -> list[dict[str, Any]]:
    """Pedido vago não corta. Trecho restante < 3s só com pedido explícito e curto."""
    if not any(str(a.get("action") or "") in CUT_ACTIONS for a in actions or []):
        return list(actions or [])
    allow = prompt_allows_cut(prompt)
    rem = _estimated_remaining(actions, cut_duration)
    drop = False
    if not allow:
        drop = True
    elif rem is not None and rem + 1e-9 < MIN_KEEP_SEC and (cut_duration or 0) > MIN_KEEP_SEC:
        drop = True
    if not drop:
        return list(actions or [])
    return [a for a in (actions or []) if str(a.get("action") or "") not in CUT_ACTIONS]


def edl_revision(ranges: list | None) -> str:
    rows = []
    for r in ranges or []:
        if not isinstance(r, dict):
            continue
        try:
            rows.append({
                "s": str(r.get("source") or ""),
                "a": round(float(r.get("start") or 0), 3),
                "b": round(float(r.get("end") or 0), 3),
                "rm": bool(r.get("removed")),
            })
        except (TypeError, ValueError):
            continue
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]  # revisão curta e estável


def make_pending_edit(
    *,
    project_id: str,
    ranges: list | None,
    operations: list,
    actions: list | None = None,
    patch: dict | None = None,
    summary: str = "",
) -> dict[str, Any]:
    ops = [dict(o) for o in (operations or []) if o]
    return {
        "projectId": project_id or "",
        "edlRevision": edl_revision(ranges),
        "operations": ops,
        "timestamp": int(time.time() * 1000),
        "actions": list(actions or []),
        "patch": dict(patch or {}),
        "summary": summary,
        "hasPendingEdit": bool(ops),
    }


def pending_is_stale(
    pending: dict | None,
    *,
    project_id: str,
    ranges: list | None,
) -> bool:
    if not pending:
        return False
    if str(pending.get("projectId") or "") != str(project_id or ""):
        return True
    return str(pending.get("edlRevision") or "") != edl_revision(ranges)


def has_timeline_action(actions: list[dict[str, Any]] | None) -> bool:
    for a in actions or []:
        if (a.get("action") or "") in {
            "restore_range", "trim_range", "remove_range", "set_duration_max",
        }:
            return True
    return False


def operations_from_patch(patch: dict[str, Any] | None, actions: list[dict] | None = None) -> list[dict]:
    """Operações reais (não prosa). timelineOps + ações de estilo sem noop."""
    ops = [dict(o) for o in (patch or {}).get("timelineOps") or [] if o]
    seen = {(o.get("op"), o.get("start"), o.get("end"), o.get("maxSec")) for o in ops}
    for a in actions or []:
        act = str(a.get("action") or "")
        if act in ("", "noop"):
            continue
        if act in {"restore_range", "trim_range", "remove_range", "set_duration_max"}:
            continue
        key = (act, a.get("start"), a.get("end"), a.get("maxSec"))
        if key in seen:
            continue
        extra = {k: v for k, v in a.items() if k != "action"}
        ops.append({"op": act, **extra})
        seen.add(key)
    return ops


def format_apply_log(operations: list[dict]) -> list[str]:
    lines = [f"AI_EDIT_APPLY operations={len(operations)}"]
    for op in operations:
        kind = str(op.get("op") or op.get("type") or op.get("action") or "?").upper()
        if "start" in op and "end" in op:
            try:
                lines.append(f"{kind} {float(op['start']):.2f}-{float(op['end']):.2f}")
            except (TypeError, ValueError):
                lines.append(kind)
        elif "maxSec" in op:
            try:
                lines.append(f"{kind} max={float(op['maxSec']):.2f}")
            except (TypeError, ValueError):
                lines.append(kind)
        else:
            lines.append(kind)
    return lines


def sanitize_proposal_summary(summary: str, *, has_ops: bool) -> str:
    text = (summary or "").strip() or "Alteração planejada"
    if has_ops:
        low = text.lower()
        if re.match(r"^(restaurad|aplicad|pronto|feito|cortei|removi)", low):
            text = re.sub(
                r"^(Restaurad[oa]|Aplicad[oa]|Pronto\.?|Feito\.?)\s*",
                "Vou aplicar: ",
                text,
                count=1,
                flags=re.I,
            )
        return text[:200]
    if re.search(r"restaurad|apliquei|aplicad|pronto|mantendo o projeto", text, re.I):
        return FAIL_PLAN
    return text[:200]


def plan_from_prompt(
    user_text: str,
    *,
    duration: float | None = None,
    source_duration: float | None = None,
    current_ranges: list | None = None,
    chat_fn=None,
) -> tuple[list[dict], str, str]:
    """Comando determinístico ou LLM com schema. Não inventa ação a partir de prosa."""
    det = parse_deterministic_command(
        user_text, source_duration=source_duration, cut_duration=duration,
    )
    if det:
        return det["actions"], det["summary"], "deterministic"

    if chat_fn is None:
        from app.llm_session import chat as chat_fn

    orig = source_duration or duration
    cut_bits = []
    for r in current_ranges or []:
        if not isinstance(r, dict):
            continue
        try:
            cut_bits.append(f"{float(r.get('start')):.2f}-{float(r.get('end')):.2f}")
        except (TypeError, ValueError):
            continue
    ctx = ""
    if orig:
        ctx += f"DURAÇÃO_ORIGINAL≈{float(orig):.2f}s\n"
    if duration and (not orig or abs(float(duration) - float(orig)) > 0.15):
        ctx += f"DURAÇÃO_CORTE_ATUAL≈{float(duration):.2f}s\n"
    if cut_bits:
        ctx += "EDL_ATUAL: " + ", ".join(cut_bits[:24]) + "\n"

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": ctx + f"PEDIDO:\n{user_text.strip()}"},
    ]
    backend = "llm"
    for attempt in (1, 2):
        text, backend = chat_fn(messages, model="gemini-web/default")
        parsed = interpret_llm_reply(
            text, duration=duration, source_duration=orig,
        )
        if parsed:
            actions, summary = parsed
            actions = filter_unsafe_cuts(
                actions, prompt=user_text, cut_duration=duration,
            )
            if not structured_actions_ok(actions):
                return [], VAGUE_CUT_MSG, backend
            return actions, sanitize_proposal_summary(summary, has_ops=True), backend
        if attempt == 1:
            messages.append({"role": "assistant", "content": text or ""})
            messages.append({"role": "user", "content": RETRY_PROMPT})
    return [], FAIL_PLAN, backend
