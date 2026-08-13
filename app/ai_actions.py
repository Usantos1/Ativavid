"""Ações estruturadas de edição por IA — sem FFmpeg livre do LLM."""
from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_ACTIONS = {
    "trim_range",
    "remove_range",
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
    "noop",
}

SYSTEM = (
    "Você edita projetos ATIVAVID. Responda SOMENTE JSON válido:\n"
    '{"actions":[{"action":"…","…":…}],"summary":"uma linha"}\n'
    "Ações permitidas: "
    + ", ".join(sorted(ALLOWED_ACTIONS))
    + ".\n"
    "remove_range: apaga o trecho [start,end] (segundos do vídeo).\n"
    "trim_range: mantém só [start,end] (corta o resto).\n"
    "set_duration_max: corta tudo depois de maxSec.\n"
    "regenerate_hook: text = nova headline (2 linhas curtas).\n"
    "Nunca invente FFmpeg. Prefira poucas ações claras."
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


def validate_actions(payload: dict, *, duration: float | None = None) -> list[dict[str, Any]]:
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
        if duration is not None:
            if "start" in item:
                item["start"] = max(0.0, min(item["start"], duration))
            if "end" in item:
                item["end"] = max(0.0, min(item["end"], duration))
            if "maxSec" in item:
                item["maxSec"] = max(0.5, min(item["maxSec"], duration))
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
) -> dict[str, Any]:
    """Aplica ações. timelineOps = instruções para o editor reescrever o corte."""
    style = dict(style or {})
    edit_data = dict(edit_data or {})
    notes = list(notes or [])
    applied: list[dict[str, Any]] = []
    timeline_ops: list[dict[str, Any]] = []

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
            # Estilo limpa = quadro cheio; inserts flutuantes/split só com tela dividida
            # (ou quando o usuário coloca à mão). Em limpa, fica só a nota.
            edit_style = (style.get("edit") or "limpa").lower().strip()
            if edit_style not in ("limpa", "clean", "limpo") and a.get("query"):
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

    return {
        "style": style,
        "editData": edit_data,
        "notes": notes,
        "applied": applied,
        "timelineOps": timeline_ops,
    }


def plan_from_prompt(user_text: str, *, duration: float | None = None) -> tuple[list[dict], str, str]:
    """Chama LLM sessão e valida. Retorna (actions, summary, backend)."""
    from app.llm_session import chat

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"DURAÇÃO≈{duration:.1f}s\n" if duration else ""
        ) + f"PEDIDO:\n{user_text.strip()}"},
    ]
    text, backend = chat(messages, model="gemini-web/default")
    data = extract_json(text)
    actions = validate_actions(data, duration=duration)
    summary = str(data.get("summary") or "Alterações planejadas")[:200]
    return actions, summary, backend
