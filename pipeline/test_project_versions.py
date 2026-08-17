"""Histórico de versões — só EDL/intent, sem render."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.project_versions import list_versions, restore, snapshot


def _write_edl(edit: Path, ranges: list[dict]) -> None:
    (edit / "edl.json").write_text(
        json.dumps({"ranges": ranges}, ensure_ascii=False), encoding="utf-8"
    )


def test_v1_v2_v3_restore_v1(tmp_path: Path):
    edit = tmp_path / "edit"
    edit.mkdir()
    v1_ranges = [
        {"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"},
        {"source": "SRC", "start": 10.0, "end": 20.0, "beat": "B1"},
    ]
    _write_edl(edit, v1_ranges)
    (edit / "job_intent.json").write_text(
        json.dumps({"editingIntent": "dynamic", "protectedRanges": []}),
        encoding="utf-8",
    )
    snapshot(edit, origin="auto", description="Edição automática")

    _write_edl(edit, [{"source": "SRC", "start": 2.0, "end": 18.0, "beat": "B1"}])
    snapshot(edit, origin="ai", description="Editar com IA")

    _write_edl(edit, [{"source": "SRC", "start": 4.0, "end": 12.0, "beat": "B1"}])
    snapshot(edit, origin="manual", description="Ajuste manual")

    items = list_versions(edit)
    assert [x["n"] for x in items] == [1, 2, 3]
    out = restore(edit, "v1")
    assert out["ok"] is True
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert edl["ranges"][0]["start"] == 0.0
    assert edl["ranges"][0]["end"] == 10.0
    assert len(edl["ranges"]) == 2
    # restore cria snapshot da atual antes
    ids = [x["id"] for x in list_versions(edit)]
    assert "v1" in ids
    assert len(ids) >= 4
