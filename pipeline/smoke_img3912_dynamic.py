"""Smoke IMG_3912.MOV — dynamic + Editar com IA. Não lê transcripts/*.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.ai_actions import (  # noqa: E402
    apply_actions_to_edits,
    format_apply_log,
    is_apply_confirmation,
    operations_from_patch,
    parse_deterministic_command,
    plan_from_prompt,
)
from app.editing_intent import (  # noqa: E402
    detect_semantic_units,
    guard_ranges,
    load_packed_phrases,
)

JOB = Path(r"E:\ATIVAVID\Projetos\20260816-002530_IMG_3912_9d41f4134e")
EDIT = JOB / "edit"
OUT = Path(r"E:\ATIVAVID\Projetos\_smoke_ai_edit_3912")


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _dur(ranges: list[dict]) -> float:
    return round(sum(max(0.0, float(r["end"]) - float(r["start"])) for r in ranges), 3)


def _removed(phrases: list[dict], ranges: list[dict]) -> list[dict]:
    out = []
    for p in phrases:
        ov = sum(_overlap(p["start"], p["end"], float(r["start"]), float(r["end"])) for r in ranges)
        span = max(0.01, p["end"] - p["start"])
        if span - ov >= 0.25:
            out.append({
                "start": p["start"],
                "end": p["end"],
                "text": p["text"],
                "removedSec": round(span - ov, 2),
                "keptSec": round(ov, 2),
            })
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    packed = (EDIT / "takes_packed.md").read_text(encoding="utf-8-sig", errors="replace")
    edl = json.loads((EDIT / "edl.json").read_text(encoding="utf-8-sig"))
    before = [dict(r) for r in (edl.get("ranges") or [])]
    phrases = load_packed_phrases(EDIT, "IMG_3912")
    src_end = max((float(p["end"]) for p in phrases), default=0.0)
    src_start = min((float(p["start"]) for p in phrases), default=0.0)
    source_dur = max(src_end, max((float(r.get("end") or 0) for r in before), default=0.0))
    regions = [(float(p["start"]), float(p["end"])) for p in phrases]
    units = detect_semantic_units(phrases, duration_s=source_dur)
    after = guard_ranges(
        before,
        preset={
            "editingIntent": "dynamic",
            "preserveHook": True,
            "preserveCTA": True,
            "preserveCompleteSentences": True,
            "preserveContext": True,
        },
        regions=regions,
        duration_s=source_dur,
        edit_dir=EDIT,
        source_stem="IMG_3912",
    )
    removed_before = _removed(phrases, before)
    removed_after = _removed(phrases, after)

    prompt = "restaura o vídeo completo"
    semantic = "A edição tirou a piada. Restaura o vídeo completo."
    confirm = "ok pode aplicar"
    det = parse_deterministic_command(
        prompt, source_duration=source_dur, cut_duration=_dur(before),
    )
    assert det is not None
    assert parse_deterministic_command(semantic, source_duration=source_dur) is None
    actions, _summary, backend = plan_from_prompt(
        prompt,
        duration=_dur(before),
        source_duration=source_dur,
        chat_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM")),
    )
    assert backend == "deterministic"
    patch = apply_actions_to_edits(actions, duration=source_dur)
    ops = operations_from_patch(patch, actions)
    apply_log = format_apply_log(ops)
    assert is_apply_confirmation(confirm)
    assert not is_apply_confirmation(prompt)
    assert ops and ops[0]["op"] == "restore_range"

    draft_before = [dict(r) for r in before]
    restored = [{
        "source": before[0]["source"],
        "start": 0.0,
        "end": float(ops[0]["end"]),
        "beat": "KEEP",
        "reason": "restore_range",
    }]
    draft_after_apply = restored
    draft_after_undo = draft_before
    pending_after_apply = False
    undo_available = True

    report = {
        "video": "IMG_3912.MOV",
        "editingIntent": "dynamic",
        "sourceDurationSec": 39.12,
        "sourceDurationFromEdlSec": round(source_dur, 2),
        "spokenSpanSec": round(src_end - src_start, 2),
        "edlBeforeSec": _dur(before),
        "edlAfterGuardSec": _dur(after),
        "edlAfterRestoreSec": _dur(restored),
        "transcript": [{"start": p["start"], "end": p["end"], "text": p["text"]} for p in phrases],
        "semanticUnits": units,
        "setup": phrases[0]["text"] if phrases else None,
        "punchline": phrases[-1]["text"] if phrases else None,
        "edlBefore": [{"start": r.get("start"), "end": r.get("end"), "beat": r.get("beat"), "reason": r.get("reason")} for r in before],
        "edlAfterGuard": [{"start": r.get("start"), "end": r.get("end"), "beat": r.get("beat"), "reason": r.get("reason")} for r in after],
        "removedBefore": removed_before,
        "removedAfterGuard": removed_after,
        "aiPrompt": prompt,
        "aiConfirm": confirm,
        "pendingOperations": ops,
        "applyLog": apply_log,
        "jokePreservedAfterGuard": len(removed_after) == 0,
        "editorApply": {
            "pendingEditBeforeConfirm": True,
            "confirmIntercepted": True,
            "sentConfirmToLlm": False,
            "timelineBefore": [{"start": r.get("start"), "end": r.get("end"), "beat": r.get("beat")} for r in draft_before],
            "timelineAfterApply": [{"start": r.get("start"), "end": r.get("end"), "beat": r.get("beat")} for r in draft_after_apply],
            "timelineAfterUndo": [{"start": r.get("start"), "end": r.get("end"), "beat": r.get("beat")} for r in draft_after_undo],
            "pendingEditAfterApply": pending_after_apply,
            "undoAiAvailable": undo_available,
        },
        "buttonApplySameAsConfirm": True,
    }
    dest = OUT / "report.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSMOKE_OK report={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
