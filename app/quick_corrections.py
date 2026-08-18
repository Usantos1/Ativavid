"""Correções rápidas do operador — persistência + EDL manual, sem pipeline.

Fontes de verdade (preview e render futuro leem as mesmas):

- HEADLINE  remotion/public/edit-data.json → hook.lines
- CAPTIONS  remotion/public/captions.json  (texto corrigido > Whisper)
- EDL       edl.json → ranges
- ESTADO    corrections.json → dirty / finalStale / captionsTimedTo (nunca o texto)
- AUDITORIA caption_fixes.json → histórico; nunca fonte do render

Não transcreve, não chama IA, não renderiza.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.apply_plan import DIRTY_KEYS, empty_dirty, normalize_dirty, plan_apply_changes

FILE_NAME = "corrections.json"
MIN_SEG = 0.2


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _ranges_snapshot(raw: Any) -> list[dict] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        if end <= start:
            continue
        item = {
            "source": r.get("source") or "SRC",
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if r.get("beat"):
            item["beat"] = r["beat"]
        out.append(item)
    return out or None


def _jcut_snapshot(raw: Any) -> list[dict] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
    return out or None


def empty_corrections() -> dict[str, Any]:
    return {
        "version": 1,
        "dirty": empty_dirty(),
        "finalStale": False,
        "pending": {k: 0 for k in DIRTY_KEYS},
        "revertVersionId": None,
        "appliedAt": None,
        "captionsTimedTo": None,
        "captionsTimedToJcut": None,
        "captionsTimedToFps": None,
    }


def load(edit_dir: Path) -> dict[str, Any]:
    data = _read_json(Path(edit_dir) / FILE_NAME, None)
    if not isinstance(data, dict):
        return empty_corrections()
    out = empty_corrections()
    out["dirty"] = normalize_dirty(data.get("dirty"))
    pending = data.get("pending") if isinstance(data.get("pending"), dict) else {}
    out["pending"] = {k: int(pending.get(k) or 0) for k in DIRTY_KEYS}
    out["revertVersionId"] = data.get("revertVersionId")
    out["appliedAt"] = data.get("appliedAt")
    out["version"] = int(data.get("version") or 1)
    out["finalStale"] = bool(data.get("finalStale")) or any(out["dirty"].values())
    out["captionsTimedTo"] = _ranges_snapshot(data.get("captionsTimedTo"))
    out["captionsTimedToJcut"] = _jcut_snapshot(data.get("captionsTimedToJcut"))
    try:
        fps = float(data.get("captionsTimedToFps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    out["captionsTimedToFps"] = fps if fps > 0 else None
    return out


def save(edit_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    body = empty_corrections()
    body["dirty"] = normalize_dirty((data or {}).get("dirty"))
    pending = (data or {}).get("pending") if isinstance((data or {}).get("pending"), dict) else {}
    body["pending"] = {k: int(pending.get(k) or 0) for k in DIRTY_KEYS}
    body["revertVersionId"] = (data or {}).get("revertVersionId")
    body["appliedAt"] = (data or {}).get("appliedAt")
    body["finalStale"] = bool((data or {}).get("finalStale")) or any(body["dirty"].values())
    body["captionsTimedTo"] = _ranges_snapshot((data or {}).get("captionsTimedTo"))
    body["captionsTimedToJcut"] = _jcut_snapshot((data or {}).get("captionsTimedToJcut"))
    try:
        fps = float((data or {}).get("captionsTimedToFps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    body["captionsTimedToFps"] = fps if fps > 0 else None
    # Nunca gravar headline/captions aqui — isso duplicaria a fonte de verdade.
    _write_json(Path(edit_dir) / FILE_NAME, body)
    return body


def edit_data_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / "remotion" / "public" / "edit-data.json"


def captions_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / "remotion" / "public" / "captions.json"


def edl_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / "edl.json"


def _ensure_revert_snapshot(edit_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    if data.get("revertVersionId"):
        return data
    try:
        from app.project_versions import snapshot

        item = snapshot(
            Path(edit_dir),
            origin="corrections",
            description="Antes das correções rápidas",
        )
        data["revertVersionId"] = item.get("id")
    except Exception:
        pass
    return data


def prepare_correction(edit_dir: Path) -> dict[str, Any]:
    """Snapshot do estado atual ANTES de gravar a correção."""
    data = load(edit_dir)
    if data.get("revertVersionId"):
        return data
    data = _ensure_revert_snapshot(edit_dir, data)
    return save(edit_dir, data)


def mark_dirty(edit_dir: Path, *keys: str) -> dict[str, Any]:
    data = load(edit_dir)
    dirty = normalize_dirty(data.get("dirty"))
    pending = dict(data.get("pending") or {})
    for key in keys:
        if key not in DIRTY_KEYS:
            continue
        dirty[key] = True
        pending[key] = int(pending.get(key) or 0) + 1
    data["dirty"] = dirty
    data["pending"] = pending
    data["finalStale"] = True
    return save(edit_dir, data)


def as_headline_lines(text_or_lines: Any) -> list[str]:
    if isinstance(text_or_lines, list):
        lines = [str(x).strip() for x in text_or_lines]
    else:
        raw = str(text_or_lines or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.strip() for ln in raw.split("\n")]
    return [ln for ln in lines if ln]


def read_headline_lines(edit_dir: Path) -> list[str]:
    data = _read_json(edit_data_path(edit_dir), {})
    if not isinstance(data, dict):
        return []
    hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    lines = hook.get("lines") or hook.get("text") or []
    if isinstance(lines, str):
        return as_headline_lines(lines)
    if isinstance(lines, list):
        return [str(x).strip() for x in lines if str(x).strip()]
    return []


def set_headline(edit_dir: Path, text_or_lines: Any) -> dict[str, Any]:
    """Grava a headline neste projeto. Não toca preset da marca."""
    lines = as_headline_lines(text_or_lines)
    if not lines:
        return {"ok": False, "error": "headline vazia"}
    prepare_correction(edit_dir)
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    hook = dict(data.get("hook") or {}) if isinstance(data.get("hook"), dict) else {}
    hook["enabled"] = True
    hook["lines"] = lines
    data["hook"] = hook
    _write_json(path, data)
    corr = mark_dirty(edit_dir, "headline")
    return {"ok": True, "headline": lines, "corrections": corr}


def fix_caption(edit_dir: Path, *, src: str, dst: str, **target: Any) -> dict[str, Any]:
    """Aplica o texto corrigido na fonte real da legenda. Preserva timings."""
    from app.caption_fixes import apply_caption_fixes

    src = str(src or "").strip()
    dst = str(dst or "").strip()
    if not src or not dst or src == dst:
        return {"ok": True, "changed": 0, "corrections": load(edit_dir)}
    fix: dict[str, Any] = {"from": src, "to": dst}
    for key in (
        "index", "cueId", "tokenId", "id", "wordId",
        "start", "end", "startMs", "endMs", "cueIndex",
        "renderedStart", "renderedEnd",
    ):
        if target.get(key) is not None:
            fix[key] = target[key]
    prepare_correction(edit_dir)
    out = apply_caption_fixes(Path(edit_dir), [fix])
    if not out.get("ok"):
        return {**out, "captionWords": _read_json(captions_path(edit_dir), []) or [], "corrections": load(edit_dir)}
    changed = int((out or {}).get("changed") or 0)
    corr = mark_dirty(edit_dir, "captions") if changed else load(edit_dir)
    words = _read_json(captions_path(edit_dir), [])
    return {
        "ok": True,
        "changed": changed,
        "captionWords": words if isinstance(words, list) else [],
        "corrections": corr,
    }


def read_edl_ranges(edit_dir: Path) -> list[dict]:
    data = _read_json(edl_path(edit_dir), {})
    if not isinstance(data, dict):
        return []
    ranges = data.get("ranges") or []
    return [r for r in ranges if isinstance(r, dict)]


def _norm_range(r: dict) -> tuple:
    return (
        str(r.get("source") or "SRC"),
        round(float(r.get("start") or 0), 3),
        round(float(r.get("end") or 0), 3),
        str(r.get("beat") or ""),
    )


def _same_ranges(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    return all(_norm_range(x) == _norm_range(y) for x, y in zip(a, b) if isinstance(x, dict) and isinstance(y, dict))


def write_edl_ranges(edit_dir: Path, ranges: list[dict], *, mark: bool = True) -> dict[str, Any]:
    path = edl_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    clean: list[dict] = []
    for r in ranges or []:
        if not isinstance(r, dict):
            continue
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        if end <= start:
            continue
        item = {
            "source": r.get("source") or "SRC",
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if r.get("beat"):
            item["beat"] = r["beat"]
        clean.append(item)
    old = [r for r in (data.get("ranges") or []) if isinstance(r, dict)]
    if _same_ranges(old, clean):
        return {"ok": True, "ranges": clean, "corrections": load(edit_dir), "changed": False}
    old_jcut = data.get("jcut_timeline")
    if mark:
        prepare_correction(edit_dir)
        data = _read_json(path, {}) or data
        if not isinstance(data, dict):
            data = {}
        old_jcut = data.get("jcut_timeline") if old_jcut is None else old_jcut
    data["ranges"] = clean
    # Ranges mudaram: a timeline gravada descreve o cut antigo, não este EDL.
    data.pop("jcut_timeline", None)
    _write_json(path, data)
    if mark:
        # Não reescrever captions.json: o cut.mp4 ainda é o antigo até o Apply.
        # O remapeamento temporal fica derivado (captionsTimedTo → EDL atual).
        corr = load(edit_dir)
        if not corr.get("captionsTimedTo"):
            snap = _ranges_snapshot(old)
            if snap:
                corr["captionsTimedTo"] = snap
                corr["captionsTimedToJcut"] = _jcut_snapshot(old_jcut)
                try:
                    fps = float(data.get("fps") or 0)
                except (TypeError, ValueError):
                    fps = 0.0
                corr["captionsTimedToFps"] = fps if fps > 0 else None
                save(edit_dir, corr)
    corr = mark_dirty(edit_dir, "edl") if mark else load(edit_dir)
    return {"ok": True, "ranges": clean, "corrections": corr, "changed": True}


def range_at_timeline(
    ranges: list[dict], playhead_sec: float
) -> tuple[int, float] | None:
    """Devolve (índice, tempo na fonte) do take que contém a agulha na timeline."""
    acc = 0.0
    t = float(playhead_sec)
    for i, r in enumerate(ranges):
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        dur = end - start
        if dur <= 0:
            continue
        if t < acc + dur - 1e-9:
            return i, start + (t - acc)
        acc += dur
    return None


def split_at_playhead(
    ranges: list[dict], playhead_sec: float, *, min_seg: float = MIN_SEG
) -> list[dict]:
    """Corta o take da agulha em dois. Sem FFmpeg. Timeline fecha o espaço sozinha."""
    hit = range_at_timeline(ranges, playhead_sec)
    if hit is None:
        return [dict(r) for r in ranges]
    i, source_t = hit
    r = dict(ranges[i])
    start = float(r.get("start") or 0)
    end = float(r.get("end") or 0)
    if source_t - start < min_seg or end - source_t < min_seg:
        return [dict(x) for x in ranges]
    left = dict(r)
    left["end"] = round(source_t, 3)
    right = dict(r)
    right["start"] = round(source_t, 3)
    return [dict(x) for x in ranges[:i]] + [left, right] + [dict(x) for x in ranges[i + 1 :]]


def delete_range_index(ranges: list[dict], index: int) -> list[dict]:
    """Remove o take e fecha o buraco (ripple). Sem IA."""
    if index < 0 or index >= len(ranges):
        return [dict(r) for r in ranges]
    return [dict(r) for j, r in enumerate(ranges) if j != index]


def split_project_at(edit_dir: Path, playhead_sec: float) -> dict[str, Any]:
    ranges = read_edl_ranges(edit_dir)
    nxt = split_at_playhead(ranges, playhead_sec)
    if nxt == ranges:
        return {"ok": True, "ranges": ranges, "changed": False, "corrections": load(edit_dir)}
    out = write_edl_ranges(edit_dir, nxt)
    out["changed"] = True
    return out


def delete_project_range(edit_dir: Path, index: int) -> dict[str, Any]:
    ranges = read_edl_ranges(edit_dir)
    nxt = delete_range_index(ranges, index)
    if nxt == ranges:
        return {"ok": True, "ranges": ranges, "changed": False, "corrections": load(edit_dir)}
    out = write_edl_ranges(edit_dir, nxt)
    out["changed"] = True
    return out


def mark_style(edit_dir: Path) -> dict[str, Any]:
    prepare_correction(edit_dir)
    return {"ok": True, "corrections": mark_dirty(edit_dir, "style")}


def plan_for_edit(edit_dir: Path) -> dict[str, Any]:
    return plan_apply_changes(load(edit_dir))


def discard(edit_dir: Path) -> dict[str, Any]:
    """Restaura o snapshot feito antes das correções. Não apaga o final.mp4."""
    data = load(edit_dir)
    vid = data.get("revertVersionId")
    restored = None
    if vid:
        try:
            from app.project_versions import restore

            restored = restore(Path(edit_dir), str(vid))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    save(edit_dir, empty_corrections())
    return {"ok": True, "restored": restored, "corrections": empty_corrections()}


def _busy_if_applying(edit_dir: Path) -> dict[str, Any] | None:
    try:
        from app.apply_execute import is_apply_running
    except Exception:
        return None
    if not is_apply_running(edit_dir):
        return None
    return {
        "ok": False,
        "busy": True,
        "error": "Estou aplicando as alterações. Espere terminar para editar.",
        "corrections": load(edit_dir),
    }


def handle(edit_dir: Path, body: dict[str, Any], *, hooks: Any = None) -> dict[str, Any]:
    """API do editor. Apply dispara o executor; o planner continua puro."""
    op = str((body or {}).get("op") or (body or {}).get("action") or "").strip().lower()
    edit = Path(edit_dir)
    if op in ("plan", "apply-plan"):
        plan = plan_for_edit(edit)
        return {
            "ok": True,
            "plan": plan,
            "execute": False,
            "corrections": load(edit),
        }
    if op == "apply":
        from app.apply_execute import execute_apply_plan, start_apply

        if body.get("sync") or hooks is not None:
            plan = plan_for_edit(edit)
            return execute_apply_plan(edit, plan, hooks=hooks)
        return start_apply(edit)
    busy = _busy_if_applying(edit)
    if busy and op not in ("load", "get", "plan", "apply-plan", ""):
        return busy
    if op in ("set_headline", "headline"):
        return set_headline(edit, body.get("lines") or body.get("text") or body.get("headline"))
    if op in ("fix_caption", "caption", "captions"):
        return fix_caption(
            edit,
            src=str(body.get("from") or body.get("src") or ""),
            dst=str(body.get("to") or body.get("dst") or body.get("text") or ""),
            index=body.get("index"),
            cueIndex=body.get("cueIndex"),
            cueId=body.get("cueId"),
            tokenId=body.get("tokenId") or body.get("id") or body.get("wordId"),
            start=body.get("start"),
            end=body.get("end"),
            startMs=body.get("startMs"),
            endMs=body.get("endMs"),
            renderedStart=body.get("renderedStart"),
            renderedEnd=body.get("renderedEnd"),
        )
    if op in ("set_edl", "edl"):
        ranges = body.get("ranges")
        if not isinstance(ranges, list):
            return {"ok": False, "error": "ranges ausentes"}
        return write_edl_ranges(edit, ranges)
    if op in ("split", "cut"):
        return split_project_at(edit, float(body.get("playhead") or body.get("t") or 0))
    if op in ("delete_range", "delete"):
        return delete_project_range(edit, int(body.get("index") if body.get("index") is not None else -1))
    if op in ("mark_style", "style"):
        return mark_style(edit)
    if op in ("discard", "revert"):
        return discard(edit)
    if op in ("load", "get", ""):
        return {"ok": True, "corrections": load(edit), "plan": plan_for_edit(edit)}
    return {"ok": False, "error": f"op desconhecida: {op}"}
