"""Transcribe a video with Groq Whisper, ElevenLabs Scribe, or local whisper.cpp.

Extracts mono 16kHz audio via ffmpeg, uploads it to a speech-to-text
endpoint with word-level timestamps, and writes the result — normalized to
the ElevenLabs Scribe schema the rest of this skill consumes — to
<edit_dir>/transcripts/<video_stem>.json.

Two backends, chosen automatically by source length (backend="auto"):
  - Groq Whisper (whisper-large-v3) for SHORT sources (<= 5 min). Fast and
    cheap, but Groq's free tier struggles with big uploads / long files.
  - ElevenLabs Scribe (scribe_v1) for LONG sources (> 5 min) — e.g. YouTube
    videos and course lessons — when an ELEVENLABS_API_KEY is present. It
    handles long audio in a single request and returns the Scribe schema
    natively. If no ElevenLabs key is configured, long sources fall back to
    Groq (with chunking) so nothing breaks.
Pass backend="groq" or backend="elevenlabs" to force one regardless of length.

A third backend, whisper.cpp, runs entirely on this machine — no API key, no
upload cap, no network. It is OPT-IN ONLY (backend="whispercpp"); "auto" never
selects it, so installing whisper.cpp changes nothing until asked for. It needs
the binary built and a ggml model downloaded:

    cd ~/whisper.cpp && cmake -B build && cmake --build build -j --config Release
    bash ./models/download-ggml-model.sh large-v3

Both paths are auto-detected under ~/whisper.cpp; override with WHISPERCPP_BIN
and WHISPERCPP_MODEL in .env. Word timestamps come from `-ml 1 -sow`.
Use large-v3 for Portuguese — smaller models degrade badly.

ACCURACY, measured on a 16s Portuguese clip against speech_regions.py (the
acoustic ground truth):
  - TEXT is equivalent: 28 of 29 words identical to Groq, the one difference
    being a legitimate ambiguity ("Esse"/"Este").
  - TIMESTAMPS are markedly worse: 66% of words land inside a real speech
    region vs Groq's 97%. Median start deviation 240ms, worst case 2.5s; the
    first word was placed 1.67s early, inside silence.
So: fine for PHASE 1, whose cut edges come from speech_regions.py anyway, and
for anyone without a Groq key. Not recommended for PHASE 2 karaoke captions,
which read word times directly and will visibly drift.

Audio is uploaded as constant-bitrate mono 16kHz 64kbps MP3 (~0.5 MB/min),
so file size is predictable from duration. When the file exceeds the
provider's upload cap it is split by BYTES into evenly-sized chunks that are
guaranteed to fit (24 MB target under Groq's 25 MB limit — the failure mode
of the old time-based FLAC chunking, where a dense 600s slice could blow the
cap and 413 the whole job, is gone by construction). Word timestamps are
offset and stitched back into a single continuous transcript.

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
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3"

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_MODEL = "scribe_v1"

# whisper.cpp — fully local, no API key, no upload cap. Opt-in only: pass
# backend="whispercpp". Never chosen by "auto", so a machine with the binary
# installed keeps behaving exactly as before unless the user asks for it.
WHISPERCPP_DEFAULT_ROOT = Path.home() / "whisper.cpp"
# Maps a ggml model filename to the --dtw alignment preset. DTW gives real
# audio-aligned token times instead of the decoder's heuristic ones, which is
# what karaoke captions need. Longest keys first — "large-v3-turbo" must win
# over "large-v3".
WHISPERCPP_DTW_PRESETS = [
    ("large-v3-turbo", "large.v3.turbo"),
    ("large-v3", "large.v3"),
    ("large-v2", "large.v2"),
    ("large-v1", "large.v1"),
    ("medium.en", "medium.en"),
    ("medium", "medium"),
    ("small.en", "small.en"),
    ("small", "small"),
    ("base.en", "base.en"),
    ("base", "base"),
    ("tiny.en", "tiny.en"),
    ("tiny", "tiny"),
]

# Sources longer than this (seconds) transcribe via ElevenLabs Scribe when a
# key is available — Groq's free tier struggles with long/large uploads.
# 5 min = the practical line between short clips and lectures/YouTube.
LONG_SOURCE_SECONDS = 300

# Groq caps uploads at 25 MB (free tier). Target a margin under it so mp3
# frame boundaries / multipart overhead never push a chunk over. Chunk count
# is derived from the actual file size, so every chunk fits by construction.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024

# ElevenLabs Scribe accepts long single uploads, so don't chunk unless the
# source is very long; keep everything in one request to preserve continuity.
ELEVENLABS_CHUNK_SECONDS = 3600


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


def load_elevenlabs_key() -> str:
    """Return the ElevenLabs API key from .env (repo root or cwd) or env, or ""
    if none is configured. Optional — only long sources use it, and they fall
    back to Groq when it's absent.
    """
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, val = line.split("=", 1)
                if k.strip() == "ELEVENLABS_API_KEY":
                    val = val.strip().strip('"').strip("'")
                    if val:
                        return val
    return os.environ.get("ELEVENLABS_API_KEY", "")


class ModelLoadError(RuntimeError):
    """whisper.cpp could not load the ggml model — usually a partial download."""


def _env_value(name: str) -> str:
    """Read one setting from .env (repo root or cwd) or the environment."""
    for candidate in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, val = line.split("=", 1)
                if k.strip() == name:
                    val = val.strip().strip('"').strip("'")
                    if val:
                        return val
    return os.environ.get(name, "")


def resolve_whispercpp() -> tuple[Path, Path]:
    """Locate the whisper-cli binary and a usable ggml model.

    Override either with WHISPERCPP_BIN / WHISPERCPP_MODEL in .env. Otherwise
    looks in a standard clone at ~/whisper.cpp and on PATH. Exits with the
    exact fix when something is missing — a wrong path here is the single most
    likely failure of this backend, so it should never surface as a traceback.
    """
    override_bin = _env_value("WHISPERCPP_BIN")
    if override_bin:
        binary = Path(override_bin).expanduser()
    else:
        candidates = [
            WHISPERCPP_DEFAULT_ROOT / "build" / "bin" / "whisper-cli",
            WHISPERCPP_DEFAULT_ROOT / "build" / "bin" / "main",
        ]
        found = next((c for c in candidates if c.exists()), None)
        which = shutil.which("whisper-cli")
        binary = found or (Path(which) if which else candidates[0])
    if not binary.exists():
        sys.exit(
            f"whisper.cpp binary not found at {binary}\n"
            "Build it:  cd ~/whisper.cpp && cmake -B build && cmake --build build -j --config Release\n"
            "Or set WHISPERCPP_BIN=/path/to/whisper-cli in .env"
        )

    override_model = _env_value("WHISPERCPP_MODEL")
    if override_model:
        model = Path(override_model).expanduser()
        if not model.exists():
            sys.exit(f"WHISPERCPP_MODEL points at a missing file: {model}")
        return binary, model

    models_dir = WHISPERCPP_DEFAULT_ROOT / "models"
    # for-tests-* are the repo's tiny fixtures (~500 KB), not usable models.
    real = [p for p in sorted(models_dir.glob("ggml-*.bin"))
            if not p.name.startswith("for-tests-") and p.stat().st_size > 10 * 1024 * 1024]
    if not real:
        sys.exit(
            f"no whisper.cpp model found in {models_dir}\n"
            "Download one:  cd ~/whisper.cpp && bash ./models/download-ggml-model.sh large-v3\n"
            "large-v3 is the one to use for Portuguese — smaller models degrade badly.\n"
            "Or set WHISPERCPP_MODEL=/path/to/ggml-model.bin in .env"
        )
    # Prefer the most accurate available, then turbo, then whatever is there.
    for want in ("large-v3.bin", "large-v3-turbo", "large-v3", "large"):
        for p in real:
            if want in p.name:
                return binary, p
    return binary, real[0]


def _dtw_preset(model_path: Path) -> str:
    """Pick the --dtw alignment preset matching a ggml model file, or ""."""
    name = model_path.name.removeprefix("ggml-")
    for key, preset in WHISPERCPP_DTW_PRESETS:
        if name.startswith(key):
            return preset
    return ""


def call_whispercpp(
    audio_path: Path,
    binary: Path,
    model: Path,
    language: str | None = None,
    verbose: bool = False,
) -> dict:
    """Transcribe locally with whisper.cpp. Returns a dict in Groq's shape.

    -ml 1 -sow is whisper.cpp's documented way to get word-level timestamps
    (one word per segment, split on word rather than mid-token). The JSON is
    then reshaped to Groq's {"words": [{word, start, end}]} so the existing
    _to_scribe_words conversion is reused unchanged.
    """
    dtw = _dtw_preset(model)

    def run(use_dtw: bool) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            stem = Path(tmp) / "out"
            cmd = [
                str(binary),
                "-m", str(model),
                "-f", str(audio_path),
                "-ml", "1",           # one word per segment
                "-sow",               # split on word, not mid-token
                "-oj",                # JSON output
                "-of", str(stem),
                "-np",                # no per-segment spam on stdout
                # whisper-cli defaults to English. Without this, Portuguese
                # audio comes back translated/garbled — the single most
                # damaging default in this backend.
                "-l", language or "auto",
                "-t", str(min(8, os.cpu_count() or 4)),
            ]
            # -dtw asks for audio-aligned token timestamps. MEASURED: on a
            # stock cmake build it is accepted but computes nothing — every
            # t_dtw comes back -1 — so it currently buys no accuracy. Kept
            # because it costs nothing and starts working if the build gains
            # DTW support; do NOT treat it as a fix for the timing gap below.
            if use_dtw and dtw:
                cmd += ["-dtw", dtw]
            # Both streams are always captured. stdout: -np means "print
            # nothing but the results", so whisper.cpp still echoes every
            # segment — at -ml 1 that is one line per word, and a 10-minute
            # source would dump thousands of lines into the caller's terminal
            # (and an agent's context). stderr: on failure whisper.cpp prints
            # one useful 'error:' line followed by a long C++ backtrace, and
            # the backtrace is what a naive tail would show, so it has to be
            # read rather than streamed.
            proc = subprocess.run(cmd, capture_output=True, text=True)
            out_json = stem.with_suffix(".json")
            if proc.returncode == 0 and out_json.exists():
                return json.loads(out_json.read_text())
            err = proc.stderr or ""
            if "failed to initialize whisper context" in err:
                raise ModelLoadError(
                    f"whisper.cpp could not load the model: {model}\n"
                    f"    size on disk: {model.stat().st_size / 1e9:.2f} GB — a full large-v3 is ~3.1 GB.\n"
                    "    A partial or interrupted download is the usual cause. Re-download:\n"
                    "      cd ~/whisper.cpp && bash ./models/download-ggml-model.sh large-v3"
                )
            first = next((ln for ln in err.splitlines() if ln.startswith("error:")), "")
            raise RuntimeError(first or err.strip()[:300] or f"exit {proc.returncode}")

    try:
        raw = run(use_dtw=True)
    except ModelLoadError:
        raise                       # retrying without -dtw won't fix a bad model
    except RuntimeError as e:
        if not dtw:
            raise RuntimeError(f"whisper.cpp failed: {e}") from e
        # A model without matching alignment heads aborts on -dtw. Timestamps
        # get coarser without it, but a working transcript beats no transcript.
        if verbose:
            print(f"    -dtw {dtw} rejected, retrying without alignment", flush=True)
        raw = run(use_dtw=False)

    words: list[dict] = []
    text_parts: list[str] = []
    for seg in raw.get("transcription", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        offsets = seg.get("offsets") or {}
        start, end = offsets.get("from"), offsets.get("to")
        if start is None or end is None:
            continue
        # whisper.cpp reports offsets in milliseconds; the rest of the skill
        # works in seconds.
        words.append({"word": text, "start": float(start) / 1000.0, "end": float(end) / 1000.0})
        text_parts.append(text)

    detected = (raw.get("result") or {}).get("language") or language or ""
    return {"words": words, "text": " ".join(text_parts).strip(), "language": detected}


def extract_audio(video_path: Path, dest: Path) -> None:
    """Extract mono 16kHz 64kbps MP3 (~0.5 MB/min) for upload.

    Constant bitrate means size scales linearly with duration, which is what
    lets us plan upload chunks by bytes with a hard guarantee they fit under
    the provider's cap. Whisper is trained on 16kHz mono, so the lossy encode
    costs nothing in transcript quality.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k",
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


def _segment_audio(audio_path: Path, out_dir: Path, chunk_seconds: float) -> list[Path]:
    """Split audio into <= chunk_seconds MP3 pieces (stream copy, no re-encode).
    Returns them in order."""
    pattern = str(out_dir / "chunk_%04d.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-f", "segment", "-segment_time", f"{chunk_seconds:.3f}",
        "-c", "copy", pattern,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    # Frame-boundary drift can leave a sub-frame sliver as the final chunk; a
    # near-empty upload risks a 400 that aborts the whole job. <0.1s of tail
    # audio is inaudible — drop it.
    if len(chunks) > 1 and _probe_duration(chunks[-1]) < 0.1:
        chunks = chunks[:-1]
    return chunks


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

    # Groq occasionally returns transient 5xx/429s mid-job; on a long multi-chunk
    # transcription a single blip would otherwise abort everything. Retry those
    # with exponential backoff; fail fast on 4xx (bad key / bad request).
    last_err = ""
    for attempt in range(6):
        with open(audio_path, "rb") as f:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (audio_path.name, f, "audio/mpeg")},
                data=data,
                timeout=1800,
            )
        if resp.status_code == 200:
            return resp.json()
        last_err = f"Groq returned {resp.status_code}: {resp.text[:500]}"
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if not retryable or attempt == 5:
            break
        wait = min(2 ** attempt * 5, 60)  # 5,10,20,40,60,60s
        print(f"    {last_err.splitlines()[0]} — retry {attempt + 1}/5 in {wait}s", flush=True)
        time.sleep(wait)

    raise RuntimeError(last_err)


def call_elevenlabs(
    audio_path: Path,
    api_key: str,
    language: str | None = None,
) -> dict:
    """Call ElevenLabs Scribe on one audio file. Returns the raw JSON dict,
    which already follows the Scribe schema (words with type/start/end/speaker).
    """
    data: list[tuple[str, str]] = [
        ("model_id", ELEVENLABS_MODEL),
        ("timestamps_granularity", "word"),
        ("diarize", "false"),
        ("tag_audio_events", "false"),
    ]
    if language:
        data.append(("language_code", language))

    # Same transient-failure posture as Groq: retry 429/5xx, fail fast on 4xx.
    last_err = ""
    for attempt in range(6):
        with open(audio_path, "rb") as f:
            resp = requests.post(
                ELEVENLABS_URL,
                headers={"xi-api-key": api_key},
                files={"file": (audio_path.name, f, "audio/mpeg")},
                data=data,
                timeout=1800,
            )
        if resp.status_code == 200:
            return resp.json()
        last_err = f"ElevenLabs returned {resp.status_code}: {resp.text[:500]}"
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if not retryable or attempt == 5:
            break
        wait = min(2 ** attempt * 5, 60)  # 5,10,20,40,60,60s
        print(f"    {last_err.splitlines()[0]} — retry {attempt + 1}/5 in {wait}s", flush=True)
        time.sleep(wait)

    raise RuntimeError(last_err)


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


def _el_to_scribe_words(el_words: list[dict], offset: float) -> list[dict]:
    """Offset ElevenLabs Scribe words onto the global timeline. Scribe already
    emits the schema this skill consumes (word + spacing entries with
    start/end/speaker_id), so we only shift times and drop audio_event/junk.
    """
    out: list[dict] = []
    for w in el_words:
        wtype = w.get("type", "word")
        if wtype not in ("word", "spacing"):
            continue  # skip audio_event and anything unexpected
        start = w.get("start")
        end = w.get("end")
        if start is None or end is None:
            continue
        out.append({
            "text": w.get("text", ""),
            "start": float(start) + offset,
            "end": float(end) + offset,
            "type": wtype,
            "speaker_id": w.get("speaker_id") or "speaker_0",
        })
    return out


def _transcribe_audio(
    audio_path: Path,
    api_key: str,
    model: str,
    language: str | None,
    verbose: bool,
    cache_dir: Path | None = None,
    chunk_seconds: float | None = None,
    backend: str = "groq",
    wcpp: tuple[Path, Path] | None = None,
) -> dict:
    """Transcribe one prepared audio file (chunking if large). Returns a
    payload dict in ElevenLabs Scribe shape.

    Chunking is planned by BYTES for Groq: n = ceil(size / MAX_UPLOAD_BYTES)
    even time slices, so every chunk lands under the 25 MB cap regardless of
    duration (the mp3 is constant-bitrate). chunk_seconds, when given, acts as
    an additional upper bound — drop to ~300 when the provider is shedding
    load on big payloads.

    Chunks are fetched in parallel (offsets are precomputed, so order doesn't
    matter) and each chunk's raw payload is cached in cache_dir — a failed run
    resumes from the chunks that already succeeded instead of redoing them.
    """
    duration = _probe_duration(audio_path)
    size = audio_path.stat().st_size

    # Effective chunk length: byte-derived guarantee for Groq, plus any
    # explicit time cap. ElevenLabs takes big uploads, so only the time cap
    # applies there.
    eff_chunk = duration
    if backend == "groq" and size > MAX_UPLOAD_BYTES and duration > 0:
        eff_chunk = duration / math.ceil(size / MAX_UPLOAD_BYTES)
    # whisper.cpp reads the file off disk — no upload, no cap, nothing to
    # split. Chunking it would only cost accuracy at the seams.
    if chunk_seconds and backend != "whispercpp":
        eff_chunk = min(eff_chunk, chunk_seconds)

    with tempfile.TemporaryDirectory() as seg_tmp:
        if duration > eff_chunk:
            chunks = _segment_audio(audio_path, Path(seg_tmp), eff_chunk)
        else:
            chunks = [audio_path]

        # offsets up-front so chunk results are order-independent
        offsets = [0.0]
        for c in chunks[:-1]:
            offsets.append(offsets[-1] + _probe_duration(c))

        def fetch(i: int, chunk: Path) -> dict:
            cache = cache_dir / f"chunk_{i:04d}.json" if cache_dir else None
            if cache and cache.exists():
                if verbose:
                    print(f"    chunk {i + 1}/{len(chunks)} (cached)", flush=True)
                return json.loads(cache.read_text())
            if verbose and len(chunks) > 1:
                print(f"    chunk {i + 1}/{len(chunks)}", flush=True)
            if backend == "elevenlabs":
                payload = call_elevenlabs(chunk, api_key, language=language)
            elif backend == "whispercpp":
                payload = call_whispercpp(chunk, wcpp[0], wcpp[1], language=language, verbose=verbose)
            else:
                payload = call_groq(chunk, api_key, model=model, language=language)
            if cache:
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(payload))
            return payload

        if len(chunks) == 1:
            payloads = [fetch(0, chunks[0])]
        else:
            # 2 workers, not 4: byte-based chunks are big (up to ~50 min of
            # audio each), and Groq's free tier rate-limits aggressive
            # concurrency — two in flight keeps throughput without tripping 429s.
            with ThreadPoolExecutor(max_workers=min(2, len(chunks))) as ex:
                payloads = list(ex.map(fetch, range(len(chunks)), chunks))

    words: list[dict] = []
    text_parts: list[str] = []
    detected_lang = language or ""
    for i, payload in enumerate(payloads):
        if backend == "elevenlabs":
            words.extend(_el_to_scribe_words(payload.get("words", []), offsets[i]))
        else:
            words.extend(_to_scribe_words(payload.get("words", []), offsets[i]))
        if payload.get("text"):
            text_parts.append(payload["text"].strip())
        if not detected_lang:
            detected_lang = payload.get("language") or payload.get("language_code") or ""

    if backend == "elevenlabs":
        backend_tag = f"elevenlabs/{ELEVENLABS_MODEL}"
    elif backend == "whispercpp":
        backend_tag = f"whispercpp/{wcpp[1].name}" if wcpp else "whispercpp"
    else:
        backend_tag = f"groq/{model}"
    return {
        "language_code": detected_lang,
        "language": detected_lang,
        "text": " ".join(text_parts).strip(),
        "words": words,
        "_transcription_backend": backend_tag,
    }


def transcribe_one(
    video: Path,
    edit_dir: Path,
    api_key: str,
    language: str | None = None,
    num_speakers: int | None = None,
    model: str = DEFAULT_MODEL,
    verbose: bool = True,
    chunk_seconds: float | None = None,
    elevenlabs_key: str | None = None,
    backend: str = "auto",
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists.
    num_speakers is accepted for CLI compatibility but ignored (Groq Whisper
    does not diarize; ElevenLabs Scribe is called with diarize=false here).

    backend: "auto" (default) uses ElevenLabs Scribe for sources longer than
    LONG_SOURCE_SECONDS when an elevenlabs_key is available, else Groq. Pass
    "groq" or "elevenlabs" to force one. ElevenLabs with no key falls back to
    Groq so long sources never hard-fail.
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcripts_dir / f"{video.stem}.json"

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    # Pick the backend up front from source length (backend="auto").
    duration = _probe_duration(video)
    resolved = backend
    if resolved == "auto":
        # "auto" never picks whispercpp: local transcription is a deliberate
        # choice (build + model download + minutes of CPU), never a surprise.
        resolved = "elevenlabs" if (duration > LONG_SOURCE_SECONDS and elevenlabs_key) else "groq"
    elif resolved == "elevenlabs" and not elevenlabs_key:
        resolved = "groq"

    wcpp: tuple[Path, Path] | None = None
    if resolved == "whispercpp":
        wcpp = resolve_whispercpp()
        active_key = ""
        active_model = wcpp[1].name
        active_chunk = None
        backend_label = f"whisper.cpp ({wcpp[1].name})"
    elif resolved == "elevenlabs":
        active_key = elevenlabs_key or ""
        active_model = ELEVENLABS_MODEL
        # don't chunk normal-length lectures; Scribe takes one long upload
        active_chunk = chunk_seconds or ELEVENLABS_CHUNK_SECONDS
        backend_label = "ElevenLabs Scribe"
    else:
        active_key = api_key
        active_model = model
        active_chunk = chunk_seconds
        backend_label = "Groq"

    if verbose:
        mins = duration / 60.0
        print(f"  extracting audio from {video.name} ({mins:.1f} min → {backend_label})", flush=True)

    # chunk-level resume cache, keyed by source identity + backend + params —
    # survives a failed run (e.g. a provider outage mid-job) so a retry only
    # redoes what failed. Backend is in the key so switching providers re-fetches.
    st = video.stat()
    chunk_cache = (transcripts_dir / ".chunks"
                   / f"{video.stem}-{st.st_size}-{int(st.st_mtime)}-{resolved}-{active_model}-{language or 'auto'}-{active_chunk or 'auto'}")

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.mp3"
        extract_audio(video, audio)
        size_mb = audio.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"  transcribing {video.stem}.mp3 ({size_mb:.1f} MB) via {backend_label}", flush=True)
        payload = _transcribe_audio(audio, active_key, active_model, language, verbose,
                                    cache_dir=chunk_cache, chunk_seconds=active_chunk,
                                    backend=resolved, wcpp=wcpp)

    out_path.write_text(json.dumps(payload, indent=2))
    # only THIS video's chunk dir — siblings may belong to parallel batch workers
    shutil.rmtree(chunk_cache, ignore_errors=True)
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
    ap.add_argument(
        "--chunk-seconds",
        type=float,
        default=None,
        help="Optional upper bound on chunk length. By default chunks are sized "
             "by BYTES so each upload is guaranteed under Groq's 25MB cap; set "
             "this (e.g. 300) only when the provider is shedding load on big "
             "payloads (5xx on large chunks).",
    )
    ap.add_argument(
        "--backend",
        type=str,
        default="auto",
        choices=["auto", "groq", "elevenlabs", "whispercpp"],
        help=f"Transcription backend. 'auto' (default) uses ElevenLabs Scribe for "
             f"sources longer than {LONG_SOURCE_SECONDS}s when ELEVENLABS_API_KEY is set, "
             "else Groq. Force with 'groq', 'elevenlabs', or 'whispercpp' (fully "
             "local, no API key, no upload cap — needs whisper.cpp built and a "
             "ggml model downloaded).",
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    # Local transcription must not require a cloud key — that's the whole point.
    api_key = "" if args.backend == "whispercpp" else load_api_key()
    elevenlabs_key = load_elevenlabs_key()

    transcribe_one(
        video=video,
        edit_dir=edit_dir,
        api_key=api_key,
        language=args.language,
        num_speakers=args.num_speakers,
        model=args.model,
        chunk_seconds=args.chunk_seconds,
        elevenlabs_key=elevenlabs_key,
        backend=args.backend,
    )


if __name__ == "__main__":
    main()
