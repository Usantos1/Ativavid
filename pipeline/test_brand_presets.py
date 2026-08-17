"""Presets por marca — só JSON, sem mídia."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.brand_presets import create, delete, duplicate, load, update_style


def test_create_duplicate_isolate(tmp_path: Path):
    root = tmp_path / "brand-presets"
    pack = create(
        "prime-camp",
        "Prime Camp - Humor",
        style={"rhythm": "dinamico", "headline": "stacked", "contentType": "humor"},
        content_type="humor",
        root=root,
        brand_name="Prime Camp",
    )
    humor_id = pack["activeId"]
    pack = duplicate("prime-camp", humor_id, "Prime Camp - Venda", root=root)
    venda_id = pack["activeId"]
    assert humor_id != venda_id
    assert len(pack["presets"]) >= 2

    pack = update_style(
        "prime-camp",
        venda_id,
        {"rhythm": "calmo", "headline": "karaoke", "contentType": "sales"},
        root=root,
    )
    by_id = {p["id"]: p for p in pack["presets"]}
    assert by_id[humor_id]["style"].get("rhythm") == "dinamico"
    assert by_id[humor_id]["style"].get("headline") == "stacked"
    assert by_id[venda_id]["style"].get("rhythm") == "calmo"
    assert by_id[venda_id]["contentType"] == "sales"
    assert by_id[humor_id].get("contentType") == "humor"


def test_cannot_delete_last(tmp_path: Path):
    root = tmp_path / "brand-presets"
    pack = load("loja", root=root, brand_name="Loja")
    only = pack["presets"][0]["id"]
    try:
        delete("loja", only, root=root)
        raise AssertionError("deveria recusar apagar o último")
    except ValueError as e:
        assert "último" in str(e)
