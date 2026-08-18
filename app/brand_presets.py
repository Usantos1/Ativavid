"""Vários presets de estilo por marca. Só JSON — sem mídia pesada."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.brand_kits import USER_DIR, _slug

PRESETS_DIR = USER_DIR / "brand-presets"

STYLE_KEYS = (
    "edit", "headline", "captions", "accent", "captionAccent",
    "emphasisAccent", "circleAccent", "elements", "rhythm", "intensity",
    "speechClean", "videoGoal", "brollMode", "captionChunk", "exportPreset",
    "colorGrade", "endCardCopy", "fastMode", "oneClick", "contentType",
    "brandId", "brandName", "note", "smartEmphasis", "endCardType",
    "captionPosition", "captionSize", "captionFont", "headlineFont",
)


def _safe_id(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower(), flags=re.UNICODE)
    return (s.strip("-") or "preset")[:40]


def _path(brand_id: str, *, root: Path | None = None) -> Path:
    base = (root or PRESETS_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{_slug(brand_id)}.json"


def _empty(brand_id: str, brand_name: str = "") -> dict:
    pid = "padrao"
    label = (brand_name or brand_id or "Padrão").strip() or "Padrão"
    return {
        "brandId": _slug(brand_id),
        "activeId": pid,
        "presets": [{
            "id": pid,
            "name": f"{label} - Padrão",
            "isDefault": True,
            "contentType": None,
            "style": {},
        }],
    }


def load(brand_id: str, *, root: Path | None = None, brand_name: str = "") -> dict:
    path = _path(brand_id, root=root)
    if not path.exists():
        return _empty(brand_id, brand_name)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _empty(brand_id, brand_name)
    presets = [p for p in (data.get("presets") or []) if isinstance(p, dict) and p.get("id")]
    if not presets:
        return _empty(brand_id, brand_name)
    active = str(data.get("activeId") or presets[0]["id"])
    if not any(p["id"] == active for p in presets):
        active = presets[0]["id"]
    return {"brandId": _slug(brand_id), "activeId": active, "presets": presets}


def save(brand_id: str, data: dict, *, root: Path | None = None) -> dict:
    payload = {
        "brandId": _slug(brand_id),
        "activeId": data.get("activeId"),
        "presets": list(data.get("presets") or []),
    }
    if not payload["presets"]:
        raise ValueError("a marca precisa de pelo menos um preset")
    if not payload["activeId"]:
        payload["activeId"] = payload["presets"][0]["id"]
    path = _path(brand_id, root=root)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def style_snapshot(style: dict | None) -> dict:
    src = dict(style or {})
    return {k: src[k] for k in STYLE_KEYS if k in src}


def create(
    brand_id: str,
    name: str,
    *,
    style: dict | None = None,
    content_type: str | None = None,
    root: Path | None = None,
    brand_name: str = "",
) -> dict:
    pack = load(brand_id, root=root, brand_name=brand_name)
    pid = _safe_id(name)
    used = {p["id"] for p in pack["presets"]}
    n = 2
    base = pid
    while pid in used:
        pid = f"{base}-{n}"
        n += 1
    pack["presets"].append({
        "id": pid,
        "name": (name or "Preset").strip() or "Preset",
        "isDefault": False,
        "contentType": content_type,
        "style": style_snapshot(style),
    })
    pack["activeId"] = pid
    return save(brand_id, pack, root=root)


def duplicate(brand_id: str, preset_id: str, new_name: str, *, root: Path | None = None) -> dict:
    pack = load(brand_id, root=root)
    src = next((p for p in pack["presets"] if p["id"] == preset_id), None)
    if not src:
        raise ValueError("preset não encontrado")
    return create(
        brand_id,
        new_name,
        style=dict(src.get("style") or {}),
        content_type=src.get("contentType"),
        root=root,
    )


def rename(brand_id: str, preset_id: str, new_name: str, *, root: Path | None = None) -> dict:
    pack = load(brand_id, root=root)
    found = False
    for p in pack["presets"]:
        if p["id"] == preset_id:
            p["name"] = (new_name or p["name"]).strip() or p["name"]
            found = True
    if not found:
        raise ValueError("preset não encontrado")
    return save(brand_id, pack, root=root)


def update_style(brand_id: str, preset_id: str, style: dict, *, root: Path | None = None) -> dict:
    pack = load(brand_id, root=root)
    found = False
    for p in pack["presets"]:
        if p["id"] == preset_id:
            p["style"] = style_snapshot(style)
            if "contentType" in style:
                p["contentType"] = style.get("contentType")
            found = True
    if not found:
        raise ValueError("preset não encontrado")
    return save(brand_id, pack, root=root)


def set_default(brand_id: str, preset_id: str, *, root: Path | None = None) -> dict:
    pack = load(brand_id, root=root)
    if not any(p["id"] == preset_id for p in pack["presets"]):
        raise ValueError("preset não encontrado")
    for p in pack["presets"]:
        p["isDefault"] = p["id"] == preset_id
    pack["activeId"] = preset_id
    return save(brand_id, pack, root=root)


def delete(brand_id: str, preset_id: str, *, root: Path | None = None) -> dict:
    pack = load(brand_id, root=root)
    if len(pack["presets"]) <= 1:
        raise ValueError("não dá para apagar o último preset da marca")
    pack["presets"] = [p for p in pack["presets"] if p["id"] != preset_id]
    if pack["activeId"] == preset_id:
        pack["activeId"] = pack["presets"][0]["id"]
    return save(brand_id, pack, root=root)


def get_active(brand_id: str, *, root: Path | None = None) -> dict | None:
    pack = load(brand_id, root=root)
    return next((p for p in pack["presets"] if p["id"] == pack["activeId"]), pack["presets"][0])
