"""Emit a @remotion/captions Caption[] JSON for the Remotion (Phase 2) project.

Two modes:
  --transcript <cut.json>   Transcribe the FINAL cut.mp4 first, then feed that
      transcript here. Prefer when Whisper timings stay within the cut duration.
  <edl.json>                Map per-source word times through the EDL (and
      jcut_timeline when present). More reliable when cut-transcript timings
      stretch past cut.mp4 (common Groq/Whisper failure).

Each spoken word becomes one Caption (word-level) so the word-highlight /
karaoke component can drive per-word timing.

Caption shape (from @remotion/captions): { text, startMs, endMs, timestampMs, confidence }

Usage:
    python helpers/captions_for_remotion.py --transcript <edit>/transcripts/cut.json -o captions.json
    python helpers/captions_for_remotion.py <edl.json> -o captions.json --max-sec 20.6
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import json
from pathlib import Path


def _word_items(raw: dict) -> list[dict]:
    return [
        w for w in (raw.get("words") or [])
        if w.get("type") == "word" and w.get("start") is not None
    ]


def _pack(text: str, t: float, e: float) -> dict:
    if e <= t:
        e = t + 0.12
    return {
        "text": text,
        "startMs": round(t * 1000),
        "endMs": round(e * 1000),
        "timestampMs": round((t + e) / 2 * 1000),
        "confidence": None,
    }


def clamp_captions(caps: list[dict], max_sec: float | None) -> list[dict]:
    """Drop / trim words past the cut duration so Remotion never seeks past EOF."""
    if not max_sec or max_sec <= 0 or not caps:
        return caps
    limit_ms = int(max_sec * 1000)
    out: list[dict] = []
    for c in caps:
        if c["startMs"] >= limit_ms:
            continue
        if c["endMs"] > limit_ms:
            c = dict(c)
            c["endMs"] = limit_ms
            c["timestampMs"] = (c["startMs"] + c["endMs"]) // 2
        if c["endMs"] > c["startMs"]:
            out.append(c)
    return out


def transcript_overruns(transcript_path: Path, duration_sec: float, slack: float = 1.08) -> bool:
    """True when last word ends clearly after the media duration (Whisper stretch)."""
    return transcript_timing_issue(transcript_path, duration_sec) == "overrun"


def transcript_timing_issue(
    transcript_path: Path,
    duration_sec: float,
    *,
    overrun_slack: float = 1.08,
    underrun_slack: float = 0.90,
) -> str | None:
    """Return 'overrun' | 'underrun' | 'empty' | None for cut-transcript quality."""
    if duration_sec <= 0:
        return None
    if not transcript_path.exists():
        return "empty"
    words = _word_items(json.loads(transcript_path.read_text(encoding="utf-8")))
    if not words:
        return "empty"
    last = max(float(w.get("end") or w["start"]) for w in words)
    if last > duration_sec * overrun_slack:
        return "overrun"
    # Whisper often drops the final phrases — treat early endings as bad coverage.
    if last < duration_sec * underrun_slack:
        return "underrun"
    return None


def captions_coverage_ok(caps: list[dict], duration_sec: float, *, slack_end: float = 0.45) -> bool:
    """True when captions roughly span the spoken cut (not just a prefix)."""
    if duration_sec <= 0 or not caps:
        return False
    last_ms = max(int(c.get("endMs") or 0) for c in caps)
    return last_ms >= int((duration_sec - slack_end) * 1000)


def captions_from_transcript(transcript_path: Path) -> list[dict]:
    """Words already on the output timeline (transcript of the final cut)."""
    caps: list[dict] = []
    for w in _word_items(json.loads(transcript_path.read_text(encoding="utf-8"))):
        t = float(w["start"])
        e = float(w.get("end") or w["start"])
        text = (w.get("text") or "").strip()
        if not text:
            continue
        caps.append(_pack(text, t, e))
    caps.sort(key=lambda c: c["startMs"])
    return caps


def _transcript_path_for_source(edl: dict, edit_dir: Path, source_key: str) -> Path | None:
    """Resolve transcript JSON — EDL key may differ from video.stem on disk."""
    transcripts_dir = edit_dir / "transcripts"
    candidates = [transcripts_dir / f"{source_key}.json"]
    src_path = (edl.get("sources") or {}).get(source_key)
    if src_path:
        stem = Path(str(src_path)).stem
        if stem and stem != source_key:
            candidates.append(transcripts_dir / f"{stem}.json")
    for p in candidates:
        if p.exists():
            return p
    return None


def _words_in_range(words: list[dict], a: float, b: float, pad: float = 0.12) -> list[dict]:
    """Words whose [start,end] overlaps the range (not start-only)."""
    out: list[dict] = []
    for w in words:
        ws = float(w["start"])
        we = float(w.get("end") or ws)
        if we < a - pad or ws > b + pad:
            continue
        out.append(w)
    out.sort(key=lambda w: float(w["start"]))
    return out


def build_captions(edl: dict, edit_dir: Path) -> list[dict]:
    """Map source transcripts through EDL ranges onto the cut timeline.

    When `jcut_timeline` exists, place words on the AUDIO timeline of the mixed
    cut (what the viewer hears), not the naive sum of range durations.
    """
    caps: list[dict] = []
    ranges = edl.get("ranges") or []
    jcut = edl.get("jcut_timeline") or []
    off = 0.0
    missing: list[str] = []

    for i, r in enumerate(ranges):
        src = r["source"]
        a, b = float(r["start"]), float(r["end"])
        range_dur = max(0.0, b - a)
        tr_path = _transcript_path_for_source(edl, edit_dir, src)

        if i < len(jcut):
            out_a = float(jcut[i].get("audio_start_in_output") or 0.0)
            out_dur = float(jcut[i].get("audio_duration") or range_dur)
        else:
            out_a = off
            out_dur = range_dur

        if tr_path is None:
            missing.append(src)
        else:
            words = _word_items(json.loads(tr_path.read_text(encoding="utf-8")))
            for w in _words_in_range(words, a, b):
                rel_t = max(0.0, float(w["start"]) - a)
                rel_e = max(rel_t + 0.04, float(w.get("end") or w["start"]) - a)
                t = min(out_dur, rel_t) + out_a
                e = min(out_dur, rel_e) + out_a
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                caps.append(_pack(text, t, e))

        if i >= len(jcut):
            off += range_dur

    if missing:
        print(f"  [warn] transcript ausente para source(s): {', '.join(sorted(set(missing)))}")

    caps.sort(key=lambda c: c["startMs"])
    return caps


def main() -> None:
    ap = argparse.ArgumentParser(description="→ @remotion/captions Caption[] JSON")
    ap.add_argument("edl", type=Path, nargs="?", help="edl.json (EDL-remap mode)")
    ap.add_argument("--transcript", type=Path, default=None,
                    help="Transcript of the final cut.mp4")
    ap.add_argument("--max-sec", type=float, default=None,
                    help="Clamp captions to this duration (cut.mp4 length)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output captions.json path")
    args = ap.parse_args()

    if args.transcript:
        caps = captions_from_transcript(args.transcript.resolve())
    elif args.edl:
        edl_path = args.edl.resolve()
        caps = build_captions(json.loads(edl_path.read_text(encoding="utf-8")), edl_path.parent)
    else:
        ap.error("provide --transcript <cut.json> or an edl.json")

    before = len(caps)
    caps = clamp_captions(caps, args.max_sec)
    if args.max_sec and before != len(caps):
        print(f"  clamped {before - len(caps)} words past {args.max_sec:.2f}s")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(caps, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.output} — {len(caps)} word captions")


if __name__ == "__main__":
    main()
