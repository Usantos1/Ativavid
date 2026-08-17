"""Proteção de trechos — EDL isolado, sem render."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.ai_actions import apply_actions_to_edits, operations_from_patch
from app.protected_ranges import add_range, filter_ai_ops, format_blocked_log, remove_overlapping


def test_protect_and_unblock():
    ranges = add_range([], {"start": 2.0, "end": 5.0, "label": "gancho", "draftStart": 2.0, "draftEnd": 5.0})
    assert len(ranges) == 1
    assert ranges[0]["start"] == 2.0
    cleared = remove_overlapping(ranges, 2.0, 5.0)
    assert cleared == []


def test_ai_remove_blocked_on_isolated_edl(tmp_path: Path):
    edl = {
        "ranges": [
            {"source": "SRC", "start": 0.0, "end": 8.0, "beat": "HOOK"},
            {"source": "SRC", "start": 8.0, "end": 20.0, "beat": "B1"},
        ]
    }
    copy = tmp_path / "edl.json"
    copy.write_text(json.dumps(edl), encoding="utf-8")
    loaded = json.loads(copy.read_text(encoding="utf-8"))
    assert loaded["ranges"][0]["beat"] == "HOOK"

    protected = [{"start": 0.0, "end": 8.0, "draftStart": 0.0, "draftEnd": 8.0, "label": "gancho"}]
    ops = [{"op": "remove_range", "start": 0.0, "end": 6.0}]
    filtered = filter_ai_ops(ops, protected)
    assert filtered["kept"] == []
    assert filtered["blocked"][0]["reason"] == "PROTECTED_RANGE_BLOCKED"
    log = format_blocked_log(filtered["blocked"])
    assert any("PROTECTED_RANGE_BLOCKED" in line for line in log)

    patch = apply_actions_to_edits(
        [{"action": "remove_range", "start": 0.0, "end": 6.0}],
        duration=20.0,
        protected_ranges=protected,
    )
    assert patch["timelineOps"] == []
    assert patch["blockedOps"]
    # restore_range passa
    ok = filter_ai_ops([{"op": "restore_range", "start": 0.0, "end": 8.0}], protected)
    assert len(ok["kept"]) == 1


def test_remove_outside_protected_passes():
    protected = [{"start": 0.0, "end": 4.0, "draftStart": 0.0, "draftEnd": 4.0}]
    ops = [{"op": "remove_range", "start": 10.0, "end": 12.0}]
    filtered = filter_ai_ops(ops, protected)
    assert len(filtered["kept"]) == 1
    assert filtered["blocked"] == []
    patch = apply_actions_to_edits(
        [{"action": "remove_range", "start": 10.0, "end": 12.0}],
        duration=20.0,
        protected_ranges=protected,
    )
    ops2 = operations_from_patch(patch, [{"action": "remove_range", "start": 10.0, "end": 12.0}])
    assert ops2
