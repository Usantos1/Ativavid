"""Transcribe a video with Groq Whisper (whisper-large-v3).

Extracts mono 16kHz audio via ffmpeg, uploads to Groq's OpenAI-compatible
speech-to-text endpoint with word-level timestamps, and writes the result
— normalized to the ElevenLabs Scribe schema the rest of this skill
consumes — to <edit_dir>/transcripts/<video_stem>.json.

Long audio is automatically split into chunks (default 600s) to stay under
Groq's upload size limit; word timestamps are offset and stitched back into
a single continuous transcript.

Notes vs. the original ElevenLabs Scribe backend:
  - Groq Whisper does NOT diarize, so every word gets speaker_id
    "speaker_0". The --num-speakers flag is accepted but ignored.
  - Groq Whisper does NOT tag audio events.
  - 'spacing' entries are reconstructed from inter-word gaps so silence
    detection (pack_transcripts / timeline_view) keeps working.

Cached: if the output file already exists, the upload is skipped.

Usage:
    python helpers/transcribe.py <video_path>
    python helpers/transcribe.py <video_path> --edit-dir /custom/edit
    python helpers/transcribe.py <video_path> --language en
    python helpers/transcribe.py <video_path> --model whisper-large-v3-turbo
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3"

# Split audio into chunks no longer than this (seconds) before upload.
# 16kHz mono FLAC runs well under Groq's 25MB free-tier limit at 600s.
CHUNK_SECONDS = 600


def load_api_key() -> str:
    """Return the Groq API key from .env (repo root or cwd) or environment.

    Accepts GROQ_API_KEY. Falls back to the legacy ELEVENLABS_API_KEY name
    only if it clearly holds a Groq key (starts with 'gsk_').
    """
    wanted = ("GROQ_API_KEY", "ELEVENLABS_API_KEY")
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            found: dict[str, str] = {}
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k in wanted:
                    found[k] = v.strip().strip('"').strip("'")
            if found.get("GROQ_API_KEY"):
                return found["GROQ_API_KEY"]
            legacy = found.get("ELEVENLABS_API_KEY", "")
            if legacy.startswith("gsk_"):
                return legacy
    v = os.environ.get("GROQ_API_KEY", "")
    if not v:
        sys.exit("GROQ_API_KEY not found in .env or environment")
    return v


def extract_audio(video_path: Path, dest: Path) -> None:
    """Extract mono 16kHz FLAC (lossless, compact) for upload."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _segment_audio(audio_path: Path, out_dir: Path, chunk_seconds: int) -> list[Path]:
    """Split audio into <= chunk_seconds FLAC pieces. Returns them in order."""
    pattern = str(out_dir / "chunk_%04d.flac")
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-f", "segment", "-segment_time", str(chunk_seconds),
        "-c:a", "flac", pattern,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return sorted(out_dir.glob("chunk_*.flac"))


def call_groq(
    audio_path: Path,
    api_key: str,
    model: str = DEFAULT_MODEL,
    language: str | None = None,
) -> dict:
    """Call Groq Whisper on one audio file. Returns the raw verbose_json dict."""
    data: list[tuple[str, str]] = [
        ("model", model),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
        ("timestamp_granularities[]", "segment"),
        ("temperature", "0"),
    ]
    if language:
        data.append(("language", language))

    with open(audio_path, "rb") as f:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (audio_path.name, f, "audio/flac")},
            data=data,
            timeout=1800,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Groq returned {resp.status_code}: {resp.text[:500]}")

    return resp.json()


def _to_scribe_words(groq_words: list[dict], offset: float) -> list[dict]:
    """Convert Groq word list to Scribe-schema entries, inserting 'spacing'
    entries for inter-word gaps so downstream silence detection works.
    """
    out: list[dict] = []
    prev_end: float | None = None
    for w in groq_words:
        start = w.get("start")
        end = w.get("end")
        if start is None or end is None:
            continue
        s = float(start) + offset
        e = float(end) + offset
        text = (w.get("word") or w.get("text") or "").strip()
        if not text:
            continue
        if prev_end is not None and s > prev_end + 1e-3:
            out.append({
                "text": " ",
                "start": prev_end,
                "end": s,
                "type": "spacing",
                "speaker_id": "speaker_0",
            })
        out.append({
            "text": text,
            "start": s,
            "end": e,
            "type": "word",
            "speaker_id": "speaker_0",
        })
        prev_end = e
    return out


def _transcribe_audio(
    audio_path: Path,
    api_key: str,
    model: str,
    language: str | None,
    verbose: bool,
) -> dict:
    """Transcribe one prepared audio file (chunking if large). Returns a
    payload dict in ElevenLabs Scribe shape."""
    duration = _probe_duration(audio_path)
    words: list[dict] = []
    text_parts: list[str] = []
    detected_lang = language or ""

    with tempfile.TemporaryDirectory() as seg_tmp:
        if duration > CHUNK_SECONDS:
            chunks = _segment_audio(audio_path, Path(seg_tmp), CHUNK_SECONDS)
        else:
            chunks = [audio_path]

        offset = 0.0
        for i, chunk in enumerate(chunks):
            if verbose and len(chunks) > 1:
                print(f"    chunk {i + 1}/{len(chunks)}", flush=True)
            payload = call_groq(chunk, api_key, model=model, language=language)
            words.extend(_to_scribe_words(payload.get("words", []), offset))
            if payload.get("text"):
                text_parts.append(payload["text"].strip())
            if not detected_lang and payload.get("language"):
                detected_lang = payload["language"]
            offset += _probe_duration(chunk)

    return {
        "language_code": detected_lang,
        "language": detected_lang,
        "text": " ".join(text_parts).strip(),
        "words": words,
        "_transcription_backend": f"groq/{model}",
    }


def transcribe_one(
    video: Path,
    edit_dir: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
    model: str = DEFAULT_MODEL,
    verbose: bool = True,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists.
    num_speakers is accepted for CLI compatibility but ignored (Groq Whisper
    does not diarize).
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    if verbose:
        print(f"  extracting audio from {video.name}", flush=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.flac"
        extract_audio(video, audio)
        size_mb = audio.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"  transcribing {video.stem}.flac ({size_mb:.1f} MB) via Groq", flush=True)
        payload = _transcribe_audio(audio, api_key, model, language, verbose)

    out_path.write_text(json.dumps(payload, indent=2))
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s")
        print(f"    words: {sum(1 for w in payload['words'] if w.get('type') == 'word')}")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video with Groq Whisper")
    ap.add_argument("video", type=Path, help="Path to video file")
    ap.add_argument(
        "--edit-dir",
        type=Path,
        default=None,
        help="Edit output directory (default: <video_parent>/edit)",
    )
    ap.add_argument(
        "--language",
        type=str,
        default=None,
        help="Optional ISO language code (e.g., 'en'). Omit to auto-detect.",
    )
    ap.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Accepted for compatibility but ignored (Groq Whisper does not diarize).",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Groq transcription model (default: {DEFAULT_MODEL}).",
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    api_key = load_api_key()

    transcribe_one(
        video=video,
        edit_dir=edit_dir,
        api_key=api_key,
        language=args.language,
        num_speakers=args.num_speakers,
        model=args.model,
    )


if __name__ == "__main__":
    main()
