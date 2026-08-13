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
    if duration_sec <= 0:
        return False
    words = _word_items(json.loads(transcript_path.read_text(encoding="utf-8")))
    if not words:
        return False
    last = max(float(w.get("end") or w["start"]) for w in words)
    return last > duration_sec * slack


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


def build_captions(edl: dict, edit_dir: Path) -> list[dict]:
    """Map source transcripts through EDL ranges onto the cut timeline.

    When `jcut_timeline` exists, place words on the AUDIO timeline of the mixed
    cut (what the viewer hears), not the naive sum of range durations.
    """
    transcripts_dir = edit_dir / "transcripts"
    caps: list[dict] = []
    ranges = edl.get("ranges") or []
    jcut = edl.get("jcut_timeline") or []
    off = 0.0

    for i, r in enumerate(ranges):
        src = r["source"]
        a, b = float(r["start"]), float(r["end"])
        range_dur = max(0.0, b - a)
        tr_path = transcripts_dir / f"{src}.json"

        if i < len(jcut):
            out_a = float(jcut[i].get("audio_start_in_output") or 0.0)
            out_dur = float(jcut[i].get("audio_duration") or range_dur)
        else:
            out_a = off
            out_dur = range_dur

        if tr_path.exists():
            words = _word_items(json.loads(tr_path.read_text(encoding="utf-8")))
            seg = [w for w in words if (a - 0.08) <= float(w["start"]) < b]
            seg.sort(key=lambda w: float(w["start"]))
            for w in seg:
                rel_t = max(0.0, float(w["start"]) - a)
                rel_e = max(0.0, float(w.get("end") or w["start"]) - a)
                t = min(out_dur, rel_t) + out_a
                e = min(out_dur, rel_e) + out_a
                text = (w.get("text") or "").strip()
                if not text:
                    continue
                caps.append(_pack(text, t, e))

        if i >= len(jcut):
            off += range_dur

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
