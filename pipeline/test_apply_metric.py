"""Métrica local do Apply — sem FFmpeg."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import record_apply_metric


def test_record_apply_metric_appends(tmp_path: Path):
    edit = tmp_path / "edit"
    edit.mkdir()
    record_apply_metric(edit, {
        "type": "REUSE_CUT",
        "videoDuration": 9.97,
        "applyDuration": 79.7,
        "success": True,
    })
    record_apply_metric(edit, {
        "type": "REBUILD_CUT",
        "videoDuration": 9.27,
        "applyDuration": 206.1,
        "success": False,
        "error": "cut temporário tem 10 frames",
    })
    hist = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))
    assert len(hist) == 2
    assert hist[0]["type"] == "REUSE_CUT"
    assert hist[0]["success"] is True
    assert hist[0]["videoDuration"] == 9.97
    assert hist[0]["applyDuration"] == 79.7
    assert hist[1]["type"] == "REBUILD_CUT"
    assert hist[1]["success"] is False
    assert "error" in hist[1]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_record_apply_metric_appends(Path(d))
    print("ok")
