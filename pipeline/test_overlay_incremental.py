"""Diff de insumos do overlay incremental: só texto/gancho vira parcial."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from app.overlay_path import (  # noqa: E402
    _incremental_ranges,
    _texts_only_first_change_ms,
)

FPS = 30.0
FRAMES = 900  # 30s


def _snap(hook=None, caps=None, cues=None, template="t1", extra=None):
    ed = {"width": 1080, "height": 1920, "captions": {"style": "karaoke"}}
    if hook is not None:
        ed["hook"] = hook
    if extra:
        ed.update(extra)
    return {
        "_template": template,
        "edit-data.json": ed,
        "captions.json": caps if caps is not None else [],
        "caption-cues.json": cues,
    }


def test_texts_only_equal_returns_none():
    caps = [{"text": "oi", "startMs": 100, "endMs": 400}]
    assert _texts_only_first_change_ms(caps, caps) is None


def test_texts_only_change_returns_first_ms():
    a = [{"text": "perico", "startMs": 5000, "endMs": 5400},
         {"text": "bom", "startMs": 6000, "endMs": 6300}]
    b = [{"text": "película", "startMs": 5000, "endMs": 5400},
         {"text": "bom", "startMs": 6000, "endMs": 6300}]
    assert _texts_only_first_change_ms(a, b) == 5000


def test_timing_change_is_not_texts_only():
    a = [{"text": "oi", "startMs": 100, "endMs": 400}]
    b = [{"text": "oi", "startMs": 150, "endMs": 400}]
    assert _texts_only_first_change_ms(a, b) is None


def test_length_change_is_not_texts_only():
    a = [{"text": "oi", "startMs": 100, "endMs": 400}]
    assert _texts_only_first_change_ms(a, a + a) is None


def test_identical_snapshots_yield_empty_plan():
    s = _snap(hook={"lines": ["a", "b"], "endSec": 4})
    assert _incremental_ranges(s, s, FPS, FRAMES) == []


def test_hook_only_change_yields_hook_window():
    old = _snap(hook={"lines": ["a", "b"], "endSec": 4})
    new = _snap(hook={"lines": ["c", "d"], "endSec": 4})
    plan = _incremental_ranges(old, new, FPS, FRAMES)
    assert plan == [(0, int(4 * FPS) + 12)]


def test_caption_text_fix_renders_from_change_to_end():
    caps_a = [{"text": "perico", "startMs": 12000, "endMs": 12400}]
    caps_b = [{"text": "película", "startMs": 12000, "endMs": 12400}]
    old = _snap(hook={"endSec": 4}, caps=caps_a)
    new = _snap(hook={"endSec": 4}, caps=caps_b)
    plan = _incremental_ranges(old, new, FPS, FRAMES)
    assert plan == [(int(12.0 * FPS) - 30, FRAMES)]


def test_hook_and_caption_changes_merge():
    old = _snap(hook={"lines": ["a"], "endSec": 4},
                caps=[{"text": "x", "startMs": 1000, "endMs": 1300}])
    new = _snap(hook={"lines": ["b"], "endSec": 4},
                caps=[{"text": "y", "startMs": 1000, "endMs": 1300}])
    plan = _incremental_ranges(old, new, FPS, FRAMES)
    # gancho (0-132) e legenda (0-900) se sobrepõem → um range só até o fim
    assert plan == [(0, FRAMES)]


def test_style_change_forces_full_render():
    old = _snap(hook={"endSec": 4})
    new = _snap(hook={"endSec": 4}, extra={"captions": {"style": "impacto"}})
    assert _incremental_ranges(old, new, FPS, FRAMES) is None


def test_template_change_forces_full_render():
    old = _snap(hook={"endSec": 4}, template="t1")
    new = _snap(hook={"endSec": 4}, template="t2")
    assert _incremental_ranges(old, new, FPS, FRAMES) is None


def test_cache_slots_are_per_project(tmp_path):
    """edit_dir.name é sempre "edit" — o slot tem que vir do PROJETO."""
    from app.overlay_path import _cache_dir_for

    a = _cache_dir_for(tmp_path / "Projetos" / "proj_A" / "edit")
    b = _cache_dir_for(tmp_path / "Projetos" / "proj_B" / "edit")
    assert a != b
    assert a == _cache_dir_for(tmp_path / "Projetos" / "proj_A" / "edit")
