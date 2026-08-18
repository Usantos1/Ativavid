"""Cadeia de estilo: projeto > preset da marca no import > marca > app."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.brand_presets import STYLE_KEYS, create
from app.editing_intent import save as save_intent
from app.preset_chain import resolve, resolve_for_edit
from app.style_defaults import APP_DEFAULT_STYLE, load_shipped_style


def test_precedence_project_beats_preset():
    used = resolve(
        app_default={"rhythm": "dinamico", "headline": "realce", "intensity": "medio"},
        brand={"rhythm": "calmo", "headline": "realce"},
        brand_preset={"rhythm": "rapido", "headline": "karaoke", "intensity": "forte"},
        project={"rhythm": "calmo"},
    )
    assert used["rhythm"] == "calmo"
    assert used["headline"] == "karaoke"
    assert used["intensity"] == "forte"


def test_brand_preset_beats_brand_and_app():
    used = resolve(
        app_default={"rhythm": "dinamico", "headline": "realce"},
        brand={"rhythm": "calmo", "headline": "stacked"},
        brand_preset={"headline": "karaoke"},
        project=None,
    )
    assert used["rhythm"] == "calmo"
    assert used["headline"] == "karaoke"


def test_intensity_is_on_whitelist():
    assert "intensity" in STYLE_KEYS
    snap = {k: "x" for k in ("rhythm", "intensity", "headline")}
    from app.brand_presets import style_snapshot

    out = style_snapshot({**snap, "ignored": 1})
    assert out["intensity"] == "x"
    assert "ignored" not in out


def test_import_preset_writes_preset_used(tmp_path: Path):
    root = tmp_path / "brand-presets"
    pack = create(
        "loja-teste",
        "Humor",
        style={"rhythm": "rapido", "headline": "karaoke", "intensity": "forte", "captions": "scatter"},
        content_type="humor",
        root=root,
        brand_name="Loja Teste",
    )
    preset_id = pack["activeId"]
    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    save_intent(edit, {
        "brandId": "loja-teste",
        "brandPresetId": preset_id,
        "editingIntent": "dynamic",
        "contentType": "humor",
    })
    used = resolve_for_edit(
        edit,
        app_default={"rhythm": "calmo", "headline": "realce", "intensity": "sutil", "captions": "stacked"},
        brand_style={"rhythm": "calmo", "headline": "realce", "intensity": "medio"},
        presets_root=root,
        write=True,
    )
    assert used["rhythm"] == "rapido"
    assert used["headline"] == "karaoke"
    assert used["intensity"] == "forte"
    assert used["brandPresetId"] == preset_id
    written = json.loads((edit / "preset-used.json").read_text(encoding="utf-8"))
    assert written["rhythm"] == "rapido"
    assert written["headline"] == "karaoke"
    assert written["intensity"] == "forte"
    assert written["brandPresetId"] == preset_id


def test_project_style_overrides_imported_preset(tmp_path: Path):
    root = tmp_path / "brand-presets"
    pack = create(
        "loja-teste",
        "Humor",
        style={"rhythm": "rapido", "headline": "karaoke"},
        root=root,
    )
    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    save_intent(edit, {"brandId": "loja-teste", "brandPresetId": pack["activeId"]})
    (edit / "preview_style.json").write_text(
        json.dumps({"rhythm": "calmo", "headline": "realce"}),
        encoding="utf-8",
    )
    used = resolve_for_edit(
        edit,
        app_default={"rhythm": "dinamico", "headline": "stacked"},
        brand_style={"rhythm": "dinamico"},
        presets_root=root,
        write=True,
    )
    assert used["rhythm"] == "calmo"
    assert used["headline"] == "realce"


def test_shipped_style_has_no_client_handle():
    shipped = load_shipped_style()
    blob = json.dumps(shipped)
    assert "lojaprimecamp" not in blob
    assert shipped["intensity"] == APP_DEFAULT_STYLE["intensity"]
    assert "intensity" in shipped
