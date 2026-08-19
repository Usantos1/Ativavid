"""Reprocesso não pode desfazer corte manual; lascas da IA não viram flash."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO / "pipeline"))

from run_fast import load_manual_edl_ranges  # noqa: E402


def _project(tmp_path: Path, *, applied: bool = True, preset_used: dict | None = None) -> Path:
    edit = tmp_path / "edit"
    edit.mkdir()
    if applied:
        (edit / "preview_edits.applied.json").write_text("{}", encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps({
        "ranges": [
            {"source": "IMG", "start": 1.0, "end": 5.0, "beat": "HOOK"},
            {"source": "IMG", "start": 7.0, "end": 12.0, "beat": "B1", "gain_db": 3.0},
        ],
    }), encoding="utf-8")
    if preset_used is not None:
        (edit / "preset-used.json").write_text(json.dumps(preset_used), encoding="utf-8")
    return edit


PRESET = {"rhythm": "dinamico", "intensity": "medio", "editingIntent": "dynamic",
          "contentType": "humor", "speechClean": "medio"}


def test_reuses_manual_edl_when_cut_knobs_unchanged(tmp_path):
    edit = _project(tmp_path, preset_used=dict(PRESET))
    ranges = load_manual_edl_ranges(edit, "IMG", dict(PRESET))
    assert ranges is not None
    assert [(r["start"], r["end"]) for r in ranges] == [(1.0, 5.0), (7.0, 12.0)]
    assert ranges[1]["gain_db"] == 3.0


def test_replans_when_rhythm_changed(tmp_path):
    edit = _project(tmp_path, preset_used=dict(PRESET))
    changed = dict(PRESET, rhythm="muito_rapido")
    assert load_manual_edl_ranges(edit, "IMG", changed) is None


def test_no_reuse_without_prior_manual_edit(tmp_path):
    edit = _project(tmp_path, applied=False, preset_used=dict(PRESET))
    assert load_manual_edl_ranges(edit, "IMG", dict(PRESET)) is None


def test_no_reuse_for_other_source(tmp_path):
    edit = _project(tmp_path, preset_used=dict(PRESET))
    assert load_manual_edl_ranges(edit, "OUTRO", dict(PRESET)) is None


def test_headline_only_change_still_reuses(tmp_path):
    # headline/estilo visual não são knobs de corte
    edit = _project(tmp_path, preset_used=dict(PRESET, headline="realce"))
    preset = dict(PRESET, headline="pilula", headlineText="Nova headline")
    assert load_manual_edl_ranges(edit, "IMG", preset) is not None


def test_llm_plan_drops_sliver_takes():
    from llm_cut_plan import MIN_TAKE_S, _normalize_ranges

    # região de fala minúscula: o snap não tem para onde expandir e o take
    # sai com ~0,2s — exatamente a lasca vista em produção (1.48→1.65)
    regions = [(1.48, 1.65), (3.0, 10.0)]
    data = {"ranges": [
        {"start": 1.48, "end": 1.65, "beat": "HOOK"},
        {"start": 3.5, "end": 9.5, "beat": "B1"},
    ]}
    out = _normalize_ranges(data, source_key="IMG", regions=regions, voice={})
    assert all(r["end"] - r["start"] >= MIN_TAKE_S for r in out)
    assert len(out) == 1


def test_mark_interrupted_unsticks_apply_status(tmp_path):
    from app.apply_tasks import INTERRUPTED_MSG, mark_interrupted

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "apply_status.json").write_text(json.dumps({
        "running": True, "ok": None, "message": "Aplicando edição...",
        "stage": "visual", "pid": 12345, "error": None,
    }), encoding="utf-8")
    mark_interrupted(edit, {"projectId": "p", "editDir": str(edit)})
    row = json.loads((edit / "apply_status.json").read_text(encoding="utf-8"))
    assert row["running"] is False
    assert row["ok"] is False
    assert INTERRUPTED_MSG in row["message"]
