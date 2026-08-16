"""Compara takes_packed.md x edl.json — sem ler transcripts/*.json."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.editing_intent import (  # noqa: E402
    COMPLETE_ALLOWED_CLASSES,
    classify_complete_removal,
    load_complete_drops,
    looks_like_cta,
)

PHRASE_RE = re.compile(
    r"\[(\d{3}\.\d{2})-(\d{3}\.\d{2})\]\s+S\d+\s+(.*)"
)


def _phrases(packed: str, stem: str) -> list[dict]:
    lines = packed.splitlines()
    keep = False
    out: list[dict] = []
    header = re.compile(rf"^##\s+{re.escape(stem)}\b", re.I)
    for line in lines:
        if line.startswith("## "):
            keep = bool(header.match(line))
            continue
        if not keep:
            continue
        m = PHRASE_RE.search(line)
        if not m:
            continue
        out.append({
            "start": float(m.group(1)),
            "end": float(m.group(2)),
            "text": m.group(3).strip(),
        })
    return out


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _kept(phrases: list[dict], ranges: list[dict]) -> list[dict]:
    kept = []
    for p in phrases:
        ov = sum(_overlap(p["start"], p["end"], float(r["start"]), float(r["end"])) for r in ranges)
        if ov >= 0.25 or ov >= 0.45 * max(0.01, p["end"] - p["start"]):
            kept.append({**p, "keptSec": round(ov, 2)})
    return kept


def _removed(phrases: list[dict], ranges: list[dict]) -> list[dict]:
    out = []
    for p in phrases:
        ov = sum(_overlap(p["start"], p["end"], float(r["start"]), float(r["end"])) for r in ranges)
        span = max(0.01, p["end"] - p["start"])
        gap = span - ov
        if gap >= 0.35:
            out.append({**p, "removedSec": round(gap, 2), "keptSec": round(ov, 2)})
    return out


def _removed_with_reason(
    removed: list[dict],
    phrases: list[dict],
    edit_dir: Path,
    intent: str | None,
) -> list[dict]:
    drops = load_complete_drops(edit_dir)
    out = []
    for r in removed:
        cls = None
        if (intent or "").lower() == "complete":
            cls = classify_complete_removal(r, phrases, drops=drops)
        nearby = [
            str(x.get("reason") or "")
            for x in (json.loads((edit_dir / "edl.json").read_text(encoding="utf-8-sig")).get("ranges") or [])
            if _overlap(r["start"], r["end"], float(x.get("start") or 0), float(x.get("end") or 0)) > 0.05
        ]
        out.append({
            "start": r["start"],
            "end": r["end"],
            "text": r["text"],
            "removedSec": r.get("removedSec"),
            "keptSec": r.get("keptSec"),
            "class": cls,
            "allowedInComplete": bool(cls in COMPLETE_ALLOWED_CLASSES) if cls else False,
            "nearbyReasons": [x for x in nearby if x],
        })
    return out


def _incomplete(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith(("...", "…", ",", ";", ":", "pra", "para", "porque", "que", "de", "do", "da")):
        return True
    if looks_like_cta(t) and not t.endswith((".", "!", "?")):
        # CTA cortado se termina no meio (sem pontuação e muito curto após o sinal)
        if re.search(r"(me segue|segue a gente|comenta|compartilha)\s+\S+$", t.lower()):
            return len(t.split()) < 8
    return False


def report(edit_dir: Path, stem: str, source_dur: float) -> dict:
    packed = (edit_dir / "takes_packed.md").read_text(encoding="utf-8-sig", errors="replace")
    edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8-sig"))
    intent = {}
    ip = edit_dir / "job_intent.json"
    if ip.exists():
        intent = json.loads(ip.read_text(encoding="utf-8-sig"))
    ranges = edl.get("ranges") or []
    phrases = _phrases(packed, stem)
    kept = _kept(phrases, ranges)
    removed = _removed(phrases, ranges)
    edited = sum(max(0.0, float(r["end"]) - float(r["start"])) for r in ranges)
    first_orig = phrases[0] if phrases else None
    last_orig = phrases[-1] if phrases else None
    first_kept = kept[0] if kept else None
    last_kept = kept[-1] if kept else None
    cta_hits = [p for p in phrases if looks_like_cta(p["text"])]
    incomplete = [p for p in kept if _incomplete(p["text"])]
    return {
        "editDir": str(edit_dir),
        "intent": intent.get("editingIntent"),
        "llm": (edl.get("llm") or {}).get("backend"),
        "sourceDurationSec": source_dur,
        "editedDurationSec": round(edited, 2),
        "firstSpokenOriginal": first_orig,
        "firstBlockKept": first_kept,
        "lastSpokenOriginal": last_orig,
        "ctaDetected": cta_hits,
        "lastBlockKept": last_kept,
        "removed": _removed_with_reason(removed, phrases, edit_dir, intent.get("editingIntent")),
        "incompleteSentences": incomplete,
        "firstBlockCoverage": round(
            (
                sum(_overlap(first_orig["start"], first_orig["end"], float(r["start"]), float(r["end"])) for r in ranges)
                / max(0.01, first_orig["end"] - first_orig["start"])
            ) if first_orig else 0.0,
            3,
        ),
        "hookPreserved": bool(
            first_orig
            and first_kept
            and first_kept["start"] <= first_orig["start"] + 0.35
            and sum(_overlap(first_orig["start"], first_orig["end"], float(r["start"]), float(r["end"])) for r in ranges)
            >= 0.90 * (first_orig["end"] - first_orig["start"])
        ),
        "ctaPreserved": bool(last_orig and last_kept and last_kept["end"] >= last_orig["end"] - 0.35),
        "rangeCount": len(ranges),
        "ranges": [{"start": r.get("start"), "end": r.get("end"), "beat": r.get("beat"), "reason": r.get("reason")} for r in ranges],
    }


def main() -> None:
    jobs = [
        (Path(r"E:\ATIVAVID\Projetos\_smoke_intent_20260815\long_complete2\edit"), "parte_1", 93.3),
        (Path(r"E:\ATIVAVID\Projetos\_smoke_intent_20260815\long_complete\edit"), "parte_1", 93.3),
        (Path(r"E:\ATIVAVID\Projetos\_smoke_intent_20260815\long_dynamic\edit"), "parte_1", 93.3),
        (Path(r"E:\ATIVAVID\Projetos\_smoke_intent_20260815\short_dynamic\edit"), "tem_capinha", 46.2),
    ]
    out = []
    for edit, stem, dur in jobs:
        if not (edit / "edl.json").exists():
            out.append({"editDir": str(edit), "error": "edl.json ausente"})
            continue
        out.append(report(edit, stem, dur))
    dest = Path(r"E:\ATIVAVID\Projetos\_smoke_intent_20260815\report.json")
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
