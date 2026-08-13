"""Brand kits multi-marca + presets de export."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
BRANDS_DIR = REPO / "assets" / "brands"
PREVIEW = REPO / "assets" / "preview"
ACTIVE_PATH = BRANDS_DIR / "active.json"

EXPORT_PRESETS = {
    "reels": {
        "id": "reels",
        "label": "Reels / Shorts / TikTok",
        "aspect": "9:16",
        "width": 1080,
        "height": 1920,
        "videoGoal": "reels",
    },
    "youtube": {
        "id": "youtube",
        "label": "YouTube 16:9",
        "aspect": "16:9",
        "width": 1920,
        "height": 1080,
        "videoGoal": "youtube",
    },
    "square": {
        "id": "square",
        "label": "Quadrado 1:1",
        "aspect": "1:1",
        "width": 1080,
        "height": 1080,
        "videoGoal": "anuncio",
    },
}


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", (name or "").strip().lower(), flags=re.UNICODE)
    return (s.strip("-") or "marca")[:40]


def ensure_brands_dir() -> None:
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    default = PREVIEW / "default-style.json"
    seed = BRANDS_DIR / "padrao.json"
    if default.exists() and not seed.exists():
        data = json.loads(default.read_text(encoding="utf-8-sig"))
        data["brandId"] = "padrao"
        data["brandName"] = "Padrão"
        seed.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not ACTIVE_PATH.exists():
        ACTIVE_PATH.write_text(
            json.dumps({"activeId": "padrao"}, indent=2) + "\n", encoding="utf-8"
        )


def list_brands() -> list[dict[str, Any]]:
    ensure_brands_dir()
    active = get_active_id()
    out: list[dict[str, Any]] = []
    for p in sorted(BRANDS_DIR.glob("*.json")):
        if p.name == "active.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        bid = data.get("brandId") or p.stem
        out.append({
            "id": bid,
            "name": data.get("brandName") or bid,
            "active": bid == active,
            "endCardCopy": data.get("endCardCopy"),
            "accent": data.get("accent"),
            "exportPreset": data.get("exportPreset") or "reels",
        })
    return out


def get_active_id() -> str:
    ensure_brands_dir()
    try:
        return str(json.loads(ACTIVE_PATH.read_text(encoding="utf-8-sig")).get("activeId") or "padrao")
    except (OSError, json.JSONDecodeError):
        return "padrao"


def load_brand(brand_id: str | None = None) -> dict[str, Any]:
    ensure_brands_dir()
    bid = brand_id or get_active_id()
    path = BRANDS_DIR / f"{_slug(bid)}.json"
    if not path.exists():
        path = BRANDS_DIR / "padrao.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    # fallback preview default
    d = PREVIEW / "default-style.json"
    if d.exists():
        return json.loads(d.read_text(encoding="utf-8-sig"))
    return {"brandId": "padrao", "brandName": "Padrão", "exportPreset": "reels"}


def save_brand(body: dict[str, Any]) -> dict[str, Any]:
    ensure_brands_dir()
    name = str(body.get("brandName") or body.get("name") or "Marca").strip() or "Marca"
    bid = _slug(str(body.get("brandId") or body.get("id") or name))
    data = dict(body)
    data["brandId"] = bid
    data["brandName"] = name
    if not data.get("exportPreset"):
        data["exportPreset"] = "reels"
    path = BRANDS_DIR / f"{bid}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def activate_brand(brand_id: str) -> dict[str, Any]:
    ensure_brands_dir()
    bid = _slug(brand_id)
    path = BRANDS_DIR / f"{bid}.json"
    if not path.exists():
        raise ValueError("marca não encontrada")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    ACTIVE_PATH.write_text(json.dumps({"activeId": bid}, indent=2) + "\n", encoding="utf-8")
    # espelha no default-style usado pelo pipeline
    preset = dict(data)
    out = PREVIEW / "default-style.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "activeId": bid, "brand": {
        "id": bid, "name": data.get("brandName") or bid,
    }}


def export_preset_info(preset_id: str | None) -> dict[str, Any]:
    pid = (preset_id or "reels").lower().strip()
    return dict(EXPORT_PRESETS.get(pid) or EXPORT_PRESETS["reels"])


def list_export_presets() -> list[dict[str, Any]]:
    return [dict(v) for v in EXPORT_PRESETS.values()]
