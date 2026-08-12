#!/usr/bin/env python3
"""Generate a background instrumental soundtrack with the ElevenLabs Music API
(Phase 3). Replaces the old Treblo helper — reuses the same ELEVENLABS_API_KEY
already configured for Phase-1 transcription, so there is no second service to
sign up for or pay separately. Requires a PAID ElevenLabs plan (Music is not on
the free tier); a 401/403 here usually means the plan, not the key, is the issue.

Synchronous: POST /v1/music returns the finished audio bytes directly in the
response body — no task/poll loop like Treblo needed.

Needs ELEVENLABS_API_KEY (env or .env at the ativa-vid repo root).

Usage:
    python helpers/elevenlabs_music.py "warm lo-fi ambient, unobtrusive" -o remotion/public/trilha.mp3
    python helpers/elevenlabs_music.py "<vibe>" -o out.mp3 --length-sec 45
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import os
import sys
from pathlib import Path

import requests

BASE = "https://api.elevenlabs.io/v1/music"
MIN_MS, MAX_MS = 3000, 600000  # ElevenLabs' documented music_length_ms bounds


def build_music_prompt(vibe: str) -> str:
    """Frame the caller's vibe as a real, composed instrumental piece.

    Same failure mode as every text-to-music API: a bare vibe that reads as
    texture ("bed", "beat", "sound design") tends to come back as an ambient
    drone or an SFX-ish loop instead of a song. Wrapping it in an explicit
    "composed instrumental song" frame — and banning SFX/risers/vocals —
    reliably yields an actual musical track. `force_instrumental=True` in the
    request is belt-and-suspenders on top of this; the caller's vibe should
    still name a genre, instruments, tempo and mood (see the skill's Phase-3
    guidance) — this frame only guarantees it renders AS music.
    """
    vibe = vibe.strip().rstrip(".")
    return (
        "Instrumental music track with a full musical arrangement — a clear "
        "melody, chords/harmony and a steady rhythm section that develops over "
        f"time. Style and mood: {vibe}. It must sound like a composed song, "
        "NOT sound design: no isolated sound effects, no risers/whooshes/impacts, "
        "no ambient drones, and no vocals."
    )


def load_api_key() -> str:
    """Same key as transcribe.py's ElevenLabs backend — one .env entry covers both."""
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ELEVENLABS_API_KEY=") and "=" in line:
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        return v
    v = os.environ.get("ELEVENLABS_API_KEY", "")
    if not v:
        sys.exit("ELEVENLABS_API_KEY not found in .env or environment")
    return v


def generate(prompt: str, out: Path, api_key: str,
             length_sec: int | None, model_id: str = "music_v2",
             raw: bool = False, timeout_s: int = 300) -> None:
    final_prompt = prompt if raw else build_music_prompt(prompt)
    print(f"  prompt -> {final_prompt}", flush=True)

    payload: dict = {
        "prompt": final_prompt,
        "model_id": model_id,
        "force_instrumental": True,
    }
    if length_sec is not None:
        payload["music_length_ms"] = max(MIN_MS, min(MAX_MS, length_sec * 1000))

    H = {"xi-api-key": api_key, "Content-Type": "application/json"}
    print("  requesting…", flush=True)
    r = requests.post(BASE, json=payload, headers=H, timeout=timeout_s)
    if r.status_code >= 400:
        hint = ""
        if r.status_code in (401, 403):
            hint = " (Music needs a PAID ElevenLabs plan — check that, not just the key)"
        sys.exit(f"ElevenLabs Music failed {r.status_code}{hint}: {r.text[:400]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    print(f"  saved: {out} ({len(r.content)/1024:.0f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="ElevenLabs instrumental soundtrack (Music v2)")
    ap.add_argument("prompt", help="MUSICAL vibe for the video's context: name a "
                    "genre + instruments + tempo/BPM + mood (e.g. 'upbeat modern "
                    "electronic, catchy synth melody, warm bass, light drums, ~110 "
                    "BPM, bright and motivational'). Avoid SFX-y words like 'bed', "
                    "bare 'beat', or 'sound design'. It is auto-framed as a composed "
                    "instrumental song unless --raw is passed.")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--length-sec", type=int, default=None,
                     help="target duration in seconds (3-600s); omit to let the model pick")
    ap.add_argument("--model", default="music_v2", choices=["music_v1", "music_v2"],
                     help="music_v2 (default): current model, better prompt adherence")
    ap.add_argument("--raw", action="store_true", help="send the prompt verbatim "
                    "(skip the composed-music framing)")
    args = ap.parse_args()
    generate(args.prompt, args.output.resolve(), load_api_key(),
             args.length_sec, args.model, raw=args.raw)


if __name__ == "__main__":
    main()
