"""Cadeia de estilo do render.

Precedência (quem está à esquerda ganha o campo):
  ajuste do projeto > preset da marca escolhido no import > marca > default do app

O resultado gravado em preset-used.json é o que o pipeline lê.
Não misturar as três fontes sem esta ordem — foi assim que o preset da
marca no import ficou morto.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRESET_USED = "preset-used.json"
PROJECT_STYLE = "preview_style.json"

LAYER_PROJECT = "project"
LAYER_BRAND_PRESET = "brand_preset"
LAYER_BRAND = "brand"
LAYER_APP = "app"
PRECEDENCE = (LAYER_PROJECT, LAYER_BRAND_PRESET, LAYER_BRAND, LAYER_APP)


def _merge(base: dict | None, overlay: dict | None) -> dict[str, Any]:
    from app.local_server import merge_preset

    return merge_preset(base or {}, overlay)


def resolve(
    *,
    app_default: dict | None,
    brand: dict | None = None,
    brand_preset: dict | None = None,
    project: dict | None = None,
) -> dict[str, Any]:
    """Aplica a cadeia. Camadas vazias são ignoradas."""
    out = _merge({}, app_default)
    out = _merge(out, brand)
    out = _merge(out, brand_preset)
    out = _merge(out, project)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _project_style(edit_dir: Path) -> dict[str, Any] | None:
    body = _read_json(Path(edit_dir) / PROJECT_STYLE)
    if not body:
        return None
    from app.local_server import preset_from_style_payload

    return preset_from_style_payload(body, base={})


def _brand_preset_style(
    brand_id: str | None,
    preset_id: str | None,
    *,
    root: Path | None = None,
) -> dict[str, Any] | None:
    if not brand_id or not preset_id:
        return None
    from app.brand_presets import load as load_presets, style_snapshot

    pack = load_presets(brand_id, root=root)
    found = next((p for p in pack["presets"] if p.get("id") == preset_id), None)
    if not found:
        return None
    snap = style_snapshot(found.get("style") or {})
    return snap or None


def resolve_for_edit(
    edit_dir: Path,
    *,
    job: dict | None = None,
    app_default: dict | None = None,
    presets_root: Path | None = None,
    brand_style: dict | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Monta o preset deste job e, por padrão, grava preset-used.json."""
    from app.brand_kits import get_active_id, load_brand
    from app.brand_presets import style_snapshot
    from app.editing_intent import load as load_intent
    from app.style_defaults import load_shipped_style

    edit = Path(edit_dir)
    intent = load_intent(edit) or {}
    brand_id = (
        str(intent.get("brandId") or "").strip()
        or str((job or {}).get("brandId") or "").strip()
        or (get_active_id() if brand_style is None else "")
    )
    preset_id = str(intent.get("brandPresetId") or "").strip() or None

    app_layer = dict(app_default if app_default is not None else load_shipped_style())
    if brand_style is not None:
        brand_layer = style_snapshot(brand_style)
    else:
        try:
            brand_layer = style_snapshot(load_brand(brand_id))
        except Exception:
            brand_layer = {}
    preset_layer = _brand_preset_style(brand_id, preset_id, root=presets_root) or {}
    project_layer = _project_style(edit) or {}

    used = resolve(
        app_default=app_layer,
        brand=brand_layer or None,
        brand_preset=preset_layer or None,
        project=project_layer or None,
    )
    if brand_id:
        used["brandId"] = brand_id
    if preset_id:
        used["brandPresetId"] = preset_id
    used["styleSource"] = {
        "project": bool(project_layer),
        "brandPreset": bool(preset_layer),
        "brand": bool(brand_layer),
    }
    if write:
        path = edit / PRESET_USED
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(used, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return used
