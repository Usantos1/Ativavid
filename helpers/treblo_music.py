"""Generate a background instrumental soundtrack with the Treblo API (Phase 3).

Async: start a generation → poll until SUCCESS → download the mp3. On FAILURE
no credit is charged. Result URLs expire ~168h, so we download immediately.

Needs TREBLO_API_KEY (env or .env at the edvid repo root).

Usage:
    python helpers/treblo_music.py "warm lo-fi ambient, unobtrusive" -o remotion/public/trilha.mp3
    python helpers/treblo_music.py "<vibe>" -o out.mp3 --length-min 30 --length-max 60
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.treblo.com/v1"


def load_api_key() -> str:
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line.startswith("TREBLO_API_KEY=") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    v = os.environ.get("TREBLO_API_KEY", "")
    if not v:
        sys.exit("TREBLO_API_KEY not found in .env or environment")
    return v


def generate(prompt: str, out: Path, api_key: str,
             length_min: int | None, length_max: int | None,
             bit_rate: int = 192, timeout_s: int = 600) -> None:
    H = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict = {
        "prompt": prompt,
        "instrumental": True,
        "output_format": "mp3",
        "output_bit_rate": bit_rate,
    }
    if length_min is not None and length_max is not None:
        payload["length_range"] = [length_min, length_max]

    r = requests.post(f"{BASE}/generations/v3", json=payload, headers=H, timeout=60)
    if r.status_code >= 400:
        sys.exit(f"Treblo start failed {r.status_code}: {r.text[:300]}")
    task_id = r.json().get("task_id")
    if not task_id:
        sys.exit(f"no task_id in response: {r.text[:300]}")
    print(f"  task {task_id} — polling…", flush=True)

    t0 = time.time()
    while True:
        s = requests.get(f"{BASE}/generations/status/{task_id}", headers=H, timeout=30).json()
        st = s if isinstance(s, str) else s.get("status")
        if st == "SUCCESS":
            break
        if st == "FAILURE":
            sys.exit("Treblo generation FAILURE (no credit charged) — retry")
        if time.time() - t0 > timeout_s:
            sys.exit("Treblo timed out")
        time.sleep(5)

    gen = requests.get(f"{BASE}/generations/{task_id}", headers=H, timeout=30).json()
    paths = gen.get("song_paths") or []
    if not paths:
        sys.exit(f"no song_paths in result: {str(gen)[:300]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = requests.get(paths[0], timeout=180).content
    out.write_bytes(audio)
    print(f"  saved: {out} ({len(audio)/1024:.0f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Treblo instrumental soundtrack")
    ap.add_argument("prompt", help="Vibe/mood prompt (let the model infer tags)")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--length-min", type=int, default=None, help="min seconds (multiple of 30)")
    ap.add_argument("--length-max", type=int, default=None, help="max seconds (multiple of 30)")
    ap.add_argument("--bit-rate", type=int, default=192)
    args = ap.parse_args()
    generate(args.prompt, args.output.resolve(), load_api_key(),
             args.length_min, args.length_max, args.bit_rate)


if __name__ == "__main__":
    main()
