"""Histórico leve por projeto: EDL + intent. Sem cut/final/mídia."""
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
    if extra:
        if extra.get("edl") is not None:
            body["edl"] = extra["edl"]
        if extra.get("intent") is not None:
            body["intent"] = extra["intent"]
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
    if data.get("edl") is not None:
        (edit / "edl.json").write_text(
            json.dumps(data["edl"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if data.get("intent") is not None:
        (edit / "job_intent.json").write_text(
            json.dumps(data["intent"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {"ok": True, "restored": version_id, "edl": data.get("edl"), "intent": data.get("intent")}
