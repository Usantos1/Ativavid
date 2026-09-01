"""Histórico leve por projeto: EDL, headline, legendas, intent. Sem cut/final/mídia."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

MAX_VERSIONS = 20
DIR_NAME = "versions"
INDEX_NAME = "index.json"


def _dir(edit_dir: Path) -> Path:
    d = Path(edit_dir) / DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path(edit_dir: Path) -> Path:
    return _dir(edit_dir) / INDEX_NAME


def _read_index(edit_dir: Path) -> dict:
    path = _index_path(edit_dir)
    if not path.exists():
        return {"next": 1, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"next": 1, "items": []}
    items = [x for x in (data.get("items") or []) if isinstance(x, dict)]
    return {"next": int(data.get("next") or (len(items) + 1)), "items": items}


def _write_index(edit_dir: Path, data: dict) -> None:
    _index_path(edit_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _payload(edit_dir: Path, extra: dict | None = None) -> dict:
    edit = Path(edit_dir)
    body: dict[str, Any] = {"savedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for name, key in (("edl.json", "edl"), ("job_intent.json", "intent")):
        p = edit / name
        if not p.exists():
            continue
        try:
            body[key] = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
    ed_path = edit / "remotion" / "public" / "edit-data.json"
    if ed_path.exists():
        try:
            ed = json.loads(ed_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            ed = None
        if isinstance(ed, dict):
            hook = ed.get("hook") if isinstance(ed.get("hook"), dict) else {}
            body["headline"] = {
                "lines": hook.get("lines") or [],
                "enabled": hook.get("enabled"),
            }
    caps_path = edit / "remotion" / "public" / "captions.json"
    if caps_path.exists():
        try:
            caps = json.loads(caps_path.read_text(encoding="utf-8-sig"))
            if isinstance(caps, list):
                body["captions"] = caps
        except (OSError, json.JSONDecodeError):
            pass
    for name, key in (("caption_fixes.json", "captionFixes"), ("corrections.json", "corrections")):
        p = edit / name
        if not p.exists():
            continue
        try:
            body[key] = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
    if extra:
        if extra.get("edl") is not None:
            body["edl"] = extra["edl"]
        if extra.get("intent") is not None:
            body["intent"] = extra["intent"]
        if extra.get("headline") is not None:
            body["headline"] = extra["headline"]
        if extra.get("captions") is not None:
            body["captions"] = extra["captions"]
        if extra.get("captionFixes") is not None:
            body["captionFixes"] = extra["captionFixes"]
        if extra.get("corrections") is not None:
            body["corrections"] = extra["corrections"]
        if extra.get("protectedRanges") is not None:
            intent = dict(body.get("intent") or {})
            intent["protectedRanges"] = extra["protectedRanges"]
            body["intent"] = intent
    return body


def list_versions(edit_dir: Path) -> list[dict]:
    return list(_read_index(edit_dir)["items"])


def snapshot(
    edit_dir: Path,
    *,
    origin: str,
    description: str,
    extra: dict | None = None,
) -> dict:
    idx = _read_index(edit_dir)
    n = int(idx["next"])
    vid = f"v{n}"
    item = {
        "id": vid,
        "n": n,
        "origin": str(origin or "manual")[:40],
        "description": str(description or "Versão")[:120],
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "file": f"{vid}.json",
        "keep": n == 1,
    }
    payload = _payload(edit_dir, extra)
    (_dir(edit_dir) / item["file"]).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    idx["items"].append(item)
    idx["next"] = n + 1
    overflow = [x for x in idx["items"] if not x.get("keep")]
    while len(idx["items"]) > MAX_VERSIONS and overflow:
        drop = overflow.pop(0)
        idx["items"] = [x for x in idx["items"] if x["id"] != drop["id"]]
        try:
            (_dir(edit_dir) / drop["file"]).unlink()
        except OSError:
            pass
    _write_index(edit_dir, idx)
    return item


def restore(edit_dir: Path, version_id: str) -> dict:
    items = list_versions(edit_dir)
    hit = next((x for x in items if x["id"] == version_id), None)
    if not hit:
        raise ValueError("versão não encontrada")
    path = _dir(edit_dir) / hit["file"]
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    snapshot(edit_dir, origin="restore", description=f"Antes de restaurar {version_id}")
    edit = Path(edit_dir)
    wrote_edl = False
    wrote_headline = False
    wrote_captions = False
    if data.get("edl") is not None:
        (edit / "edl.json").write_text(
            json.dumps(data["edl"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        wrote_edl = True
    if data.get("intent") is not None:
        (edit / "job_intent.json").write_text(
            json.dumps(data["intent"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    headline = data.get("headline")
    if headline is not None:
        ed_path = edit / "remotion" / "public" / "edit-data.json"
        ed: dict[str, Any] = {}
        if ed_path.exists():
            try:
                loaded = json.loads(ed_path.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    ed = loaded
            except (OSError, json.JSONDecodeError):
                ed = {}
        from app.caption_fixes import sem_emoji

        hook = dict(ed.get("hook") or {}) if isinstance(ed.get("hook"), dict) else {}
        # versao antiga pode carregar emoji de antes da regra — limpa ao voltar
        if isinstance(headline, dict):
            if headline.get("lines") is not None:
                hook["lines"] = [sem_emoji(x) for x in (headline["lines"] or [])]
            if headline.get("enabled") is not None:
                hook["enabled"] = headline["enabled"]
        elif isinstance(headline, list):
            hook["lines"] = [sem_emoji(x) for x in headline]
        ed["hook"] = hook
        ed_path.parent.mkdir(parents=True, exist_ok=True)
        ed_path.write_text(json.dumps(ed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        wrote_headline = True
    if data.get("captions") is not None:
        caps_path = edit / "remotion" / "public" / "captions.json"
        caps_path.parent.mkdir(parents=True, exist_ok=True)
        caps_path.write_text(
            json.dumps(data["captions"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        wrote_captions = True
    if data.get("captionFixes") is not None:
        (edit / "caption_fixes.json").write_text(
            json.dumps(data["captionFixes"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        wrote_captions = True
    if data.get("corrections") is not None:
        (edit / "corrections.json").write_text(
            json.dumps(data["corrections"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    from app.quick_corrections import empty_dirty, load, save

    corr = load(edit)
    dirty = empty_dirty()
    dirty["edl"] = wrote_edl or bool((corr.get("dirty") or {}).get("edl"))
    dirty["headline"] = wrote_headline or bool((corr.get("dirty") or {}).get("headline"))
    dirty["captions"] = wrote_captions or bool((corr.get("dirty") or {}).get("captions"))
    dirty["style"] = bool((corr.get("dirty") or {}).get("style"))
    corr["dirty"] = dirty
    corr["finalStale"] = True
    corr = save(edit, corr)
    return {
        "ok": True,
        "restored": version_id,
        "edl": data.get("edl"),
        "intent": data.get("intent"),
        "headline": data.get("headline"),
        "corrections": corr,
        "finalStale": True,
        "render": False,
    }
