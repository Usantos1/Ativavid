"""Decide o menor trabalho para Aplicar alterações — sem executar mídia.

Fonte: flags dirty do projeto (corrections.json). Nunca liga Whisper, LLM,
FFmpeg ou Remotion. A execução real fica para uma etapa posterior.
"""
from __future__ import annotations

from typing import Any

DIRTY_KEYS = ("headline", "captions", "edl", "style")
REASON = {
    "headline": "HEADLINE_DIRTY",
    "captions": "CAPTIONS_DIRTY",
    "edl": "EDL_DIRTY",
    "style": "STYLE_DIRTY",
}
LABEL_PT = {
    "headline": "headline",
    "captions": "legenda",
    "edl": "corte",
    "style": "estilo",
}

# O planner nunca executa mídia. A execução vive em apply_execute.py.
EXECUTE_APPLY = False


def empty_dirty() -> dict[str, bool]:
    return {k: False for k in DIRTY_KEYS}


def normalize_dirty(raw: Any) -> dict[str, bool]:
    src = raw if isinstance(raw, dict) else {}
    out = empty_dirty()
    for key in DIRTY_KEYS:
        out[key] = bool(src.get(key))
    return out


def dirty_from(project: Any) -> dict[str, bool]:
    """Aceita o dict de flags, corrections.json ou um projeto com .dirty."""
    if not isinstance(project, dict):
        return empty_dirty()
    if isinstance(project.get("corrections"), dict):
        return dirty_from(project["corrections"])
    if isinstance(project.get("dirty"), dict):
        return normalize_dirty(project["dirty"])
    if any(k in project for k in DIRTY_KEYS):
        return normalize_dirty(project)
    return empty_dirty()


def pending_keys(project: Any) -> list[str]:
    flags = dirty_from(project)
    return [k for k in DIRTY_KEYS if flags.get(k)]


def pending_count(project: Any) -> int:
    return len(pending_keys(project))


def pending_summary(project: Any) -> list[str]:
    return [LABEL_PT[k] for k in pending_keys(project)]


def plan_apply_changes(project: Any) -> dict[str, Any]:
    """Plano testável sem mídia.

    Visual (headline/legenda/estilo) → reaproveita cut.mp4, só Fase 2.
    Corte (EDL) → reconstrói cut pelo EDL, depois Fase 2.
    Nunca transcrição, nunca IA.
    """
    dirty = dirty_from(project)
    reasons = [REASON[k] for k in DIRTY_KEYS if dirty.get(k)]
    any_dirty = bool(reasons)
    edl = bool(dirty.get("edl"))
    if not any_dirty:
        mode = "NOOP"
        render_mode = "NONE"
    elif edl:
        mode = "REBUILD_CUT"
        render_mode = "RENDER_VISUAL"
    else:
        mode = "REUSE_CUT"
        render_mode = "RENDER_VISUAL_ONLY"
    remap = bool(edl)
    if remap:
        reasons = list(reasons)
        if "REMAP_CAPTIONS" not in reasons:
            # Corte novo sempre remapeia timings de legenda (mesmo sem edição de texto).
            reasons.append("REMAP_CAPTIONS")
    return {
        "reuseCut": bool(any_dirty) and not edl,
        "rebuildCut": edl,
        "remapCaptions": remap,
        "runTranscription": False,
        "runAI": False,
        "renderVisual": any_dirty,
        "exportFinal": any_dirty,
        "reasons": reasons,
        "mode": mode,
        "renderMode": render_mode,
        "pending": pending_summary(dirty),
        "pendingCount": len([r for r in reasons if r != "REMAP_CAPTIONS"]),
        "execute": EXECUTE_APPLY,
        "dirty": dirty,
    }
