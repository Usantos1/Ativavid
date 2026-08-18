"""Clipes de podcast: parsing validado, retry e materialização dos filhos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import pytest  # noqa: E402

from app.podcast_clips import (  # noqa: E402
    materialize_clip_projects,
    parse_clips_plan,
    plan_clips,
)


def _plan_text(clips):
    return json.dumps({"clips": clips})


def test_parse_valid_plan():
    clips = parse_clips_plan(_plan_text([
        {"headline": "O segredo do preço", "ranges": [{"start": 10, "end": 45}]},
        {"headline": "Cliente difícil", "ranges": [{"start": 60, "end": 90},
                                                   {"start": 95, "end": 110}]},
    ]), duration=300)
    assert len(clips) == 2
    assert clips[0]["totalSec"] == 35.0
    assert clips[1]["totalSec"] == 45.0


def test_parse_drops_too_short_and_too_long():
    clips = parse_clips_plan(_plan_text([
        {"headline": "curto", "ranges": [{"start": 0, "end": 5}]},       # 5s
        {"headline": "ok", "ranges": [{"start": 10, "end": 40}]},        # 30s
        {"headline": "longo", "ranges": [{"start": 50, "end": 250}]},    # 200s
    ]), duration=300)
    assert [c["headline"] for c in clips] == ["ok"]


def test_parse_clamps_to_duration_and_rejects_overlap():
    clips = parse_clips_plan(_plan_text([
        {"headline": "a", "ranges": [{"start": 10, "end": 50}]},
        {"headline": "sobrepoe", "ranges": [{"start": 30, "end": 70}]},
        {"headline": "b", "ranges": [{"start": 200, "end": 9999}]},
    ]), duration=260)
    assert [c["headline"] for c in clips] == ["a", "b"]
    assert clips[1]["ranges"][0]["end"] == 260.0


def test_parse_raises_when_nothing_valid():
    with pytest.raises(ValueError):
        parse_clips_plan(_plan_text([{"headline": "x", "ranges": []}]), duration=100)


def test_plan_clips_retries_bad_json_then_succeeds(tmp_path):
    calls = []

    def chat_fn(messages, model=""):
        calls.append(list(messages))
        if len(calls) == 1:
            return "desculpa, aqui vai o plano em prosa", "fake"
        return _plan_text([
            {"headline": "Vale a pena?", "ranges": [{"start": 5, "end": 35}]},
        ]), "fake"

    clips = plan_clips(tmp_path, packed="fala", duration=120,
                       regions=[(0.0, 100.0)], chat_fn=chat_fn)
    assert len(clips) == 1
    assert len(calls) == 2
    saved = json.loads((tmp_path / "clips_plan.json").read_text(encoding="utf-8"))
    assert saved["clips"][0]["headline"] == "Vale a pena?"


def test_materialize_creates_child_projects(tmp_path):
    root = tmp_path / "Projetos"
    root.mkdir()
    src = tmp_path / "podcast.mp4"
    src.write_bytes(b"VIDEO")
    plan = [
        {"headline": "O segredo", "ranges": [{"start": 10.0, "end": 45.0}], "totalSec": 35.0},
        {"headline": "", "ranges": [{"start": 60.0, "end": 100.0}], "totalSec": 40.0},
    ]
    out = materialize_clip_projects(
        root, src, plan,
        intent={"editingIntent": "clips", "contentType": "sales", "brandId": "b1"},
    )
    assert len(out) == 2
    for i, ch in enumerate(out):
        source = Path(ch["source"])
        assert source.exists() and source.read_bytes() == b"VIDEO"
        pe = json.loads((Path(ch["editDir"]) / "preview_edits.json").read_text(encoding="utf-8"))
        assert pe["edl"]["ranges"] == plan[i]["ranges"]
    assert out[0]["name"] == "O segredo"
    assert out[1]["name"] == "Clipe 2"
    # intenção do filho vira dynamic, herdando o resto
    from app.editing_intent import load as load_intent

    child = load_intent(Path(out[0]["editDir"]))
    assert child["editingIntent"] == "dynamic"
    assert child["contentType"] == "sales"
