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

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

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
    # ORDEM DO APP: `%USERPROFILE%/ATIVAVID/.env` primeiro. Numa
    # instalacao normal o codigo fica em Program Files (so leitura) e a
    # tela de Integracoes grava no do usuario; o .env ao lado do codigo
    # so existe na maquina de quem desenvolve. Sem esta linha o helper
    # depende de o app injetar a chave no ambiente, e quando isso falha
    # o sintoma e MUDO (a 3.26 consertou o mesmo no Groq).
    # 5.0.54: `chave_do_env` DECIFRA o que a 5.0.47 cifrou (DPAPI). Lendo o
    # arquivo cru, a chave virava `dpapi:...` e a API respondia 401.
    from chave_do_env import chave

    v = chave("GROQ_API_KEY")
    if v:
        return v
    # legado: uma chave `gsk_` gravada no campo do ElevenLabs
    legado = chave("ELEVENLABS_API_KEY")
    if legado.startswith("gsk_"):
        return legado
    v = os.environ.get("GROQ_API_KEY", "")
    if not v:
        sys.exit("GROQ_API_KEY not found in .env or environment")
    return v


def load_elevenlabs_key() -> str:
    """Return the ElevenLabs API key from .env (repo root or cwd) or env, or ""
    if none is configured. Optional — only long sources use it, and they fall
    back to Groq when it's absent.
    """
    # ORDEM DO APP: `%USERPROFILE%/ATIVAVID/.env` primeiro. Numa
    # instalacao normal o codigo fica em Program Files (so leitura) e a
    # tela de Integracoes grava no do usuario; o .env ao lado do codigo
    # so existe na maquina de quem desenvolve. Sem esta linha o helper
    # depende de o app injetar a chave no ambiente, e quando isso falha
    # o sintoma e MUDO (a 3.26 consertou o mesmo no Groq).
    # 5.0.54: `chave_do_env` DECIFRA o que a 5.0.47 cifrou (DPAPI). Lendo o
    # arquivo cru, a chave virava `dpapi:...` e a API respondia 401.
    from chave_do_env import chave

    return chave("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY", "")


class ModelLoadError(RuntimeError):
    """whisper.cpp could not load the ggml model — usually a partial download."""


def _env_value(name: str) -> str:
    """Read one setting from .env (repo root or cwd) or the environment."""
    # ORDEM DO APP: `%USERPROFILE%/ATIVAVID/.env` primeiro. Numa
    # instalacao normal o codigo fica em Program Files (so leitura) e a
    # tela de Integracoes grava no do usuario; o .env ao lado do codigo
    # so existe na maquina de quem desenvolve. Sem esta linha o helper
    # depende de o app injetar a chave no ambiente, e quando isso falha
    # o sintoma e MUDO (a 3.26 consertou o mesmo no Groq).
    # 5.0.54: `chave_do_env` DECIFRA o que a 5.0.47 cifrou (DPAPI) e conhece a
    # ordem dos arquivos. Valor que nao e segredo (caminho do whisper.cpp,
    # modelo) passa igual — nao tem prefixo `dpapi:`.
    from chave_do_env import chave

    return chave(name) or os.environ.get(name, "")


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
                return json.loads(out_json.read_text(encoding="utf-8"))
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


def _prender_ordem(words: list[dict]) -> list[dict]:
    """Starts estritamente crescentes, preservando a ORDEM DO ARRAY.

    A ordem do array e a ordem da fala (e a ordem do texto transcrito); o
    timestamp e a parte com jitter. Medido nos 178 transcripts reais do
    usuario: 133 tinham palavra "voltando" no tempo (746 pares, ate 0,98s) —
    e quem consome ordena por start, entao a legenda saia com as palavras
    TROCADAS ("Olha jeito!" onde a fala diz "jeito! Olha").

    O clamp move o start para 1ms depois do anterior, o minimo que garante a
    ordem sob qualquer sort. O end acompanha para a palavra nunca ter duracao
    negativa.
    """
    prev_s: float | None = None
    for w in words:
        if w.get("type") != "word":
            continue
        s = float(w.get("start") or 0.0)
        e = float(w.get("end") or s)
        if prev_s is not None and s < prev_s + 1e-3:
            s = prev_s + 1e-3
        if e < s + 0.04:
            e = s + 0.04
        w["start"], w["end"] = s, e
        prev_s = s
    return words


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
    return _prender_ordem(out)


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
    return _prender_ordem(out)


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
                return json.loads(cache.read_text(encoding="utf-8"))
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
                cache.write_text(json.dumps(payload), encoding="utf-8")
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


def source_signature(video: Path) -> str:
    st = Path(video).stat()
    return f"{int(st.st_size)}:{int(st.st_mtime)}"


def signature_path(transcripts_dir: Path, stem: str) -> Path:
    return Path(transcripts_dir) / f"{stem}.srcsig"


def _revisao():
    """O módulo de revisão textual, ou `None` se não der para importar.

    `transcribe.py` roda como script solto (`uv run python helpers/...`), e
    aí a raiz do repo não está no `sys.path`. Devolver `None` em vez de
    levantar mantém o helper funcionando exatamente como antes da revisão
    existir — que é o comportamento certo quando ela não está disponível.
    """
    try:
        raiz = Path(__file__).resolve().parent.parent
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        from app.transcricao import revisao

        return revisao
    except Exception:  # noqa: BLE001
        return None


def marca_da_assinatura(transcripts_dir: Path, stem: str) -> str | None:
    """A marca gravada no `.srcsig`, ou `None` se o arquivo não tem uma.

    `None` é assinatura LEGADA — escrita antes de a marca existir. Não é o
    mesmo que marca vazia, e a diferença importa: legado é tratado como está
    hoje, sem invalidar nada.
    """
    try:
        linhas = signature_path(transcripts_dir, stem).read_text(
            encoding="utf-8").splitlines()
    except OSError:
        return None
    for linha in linhas[1:]:
        if linha.startswith("marca="):
            return linha[len("marca="):].strip()
    return None


def write_source_signature(transcripts_dir: Path, video: Path,
                           marca: str = "") -> None:
    """Grava a assinatura da fonte e, quando dada, a marca do transcript.

    Linha 1 é o que sempre foi: `tamanho:mtime`. Linha 2, opcional, é
    `marca=<backend>-<modelo>[+rev1]` — o processo que produziu ESTE arquivo.
    Formato de duas linhas para que uma assinatura nova continue legível por
    qualquer código que só olhe a primeira.
    """
    path = signature_path(transcripts_dir, Path(video).stem)
    texto = source_signature(video)
    if marca:
        texto += f"\nmarca={marca}"
    path.write_text(texto, encoding="utf-8")


def _variante_compativel(gravada: str | None) -> bool:
    """O transcript gravado passou pelo mesmo processo que está pedido agora?

    Existe para uma coisa só: `ATIVAVID_REVISAO=off` tem de ser rollback de
    verdade. Sem isto, um transcript revisado já gravado em
    `transcripts/*.json` continuaria dando cache hit e voltaria a ser servido
    como se fosse Whisper puro — e o rollback exigiria apagar arquivo de cada
    projeto na mão.

    A comparação é DELIBERADAMENTE estreita, e só olha o sufixo de revisão de
    transcript LOCAL:

      assinatura legada (`None`)   nunca invalida. Foi escrita antes de a
                                   revisão existir, então é Whisper puro, e
                                   invalidar em massa retranscreveria a base
                                   inteira do usuário para não corrigir nada.

      marca de outro backend       nunca invalida. Um transcript do Scribe
                                   custou dinheiro; jogá-lo fora porque um
                                   interruptor do motor local mudou seria
                                   cobrar do usuário por uma decisão que não
                                   é sobre ele.

      marca local com sufixo       compara `+rev1` contra o que está pedido.
                                   Diferente → miss.

    Um miss aqui quase nunca custa transcrição: `_transcrever_local` procura
    a versão pura no cache entre projetos antes de acordar o Whisper.
    """
    if gravada is None or not gravada.startswith("local-"):
        return True
    rev = _revisao()
    if rev is None:
        return True
    tem = rev.SUFIXO if gravada.endswith(rev.SUFIXO) else ""
    return tem == rev.sufixo_desejado()


def transcript_cache_hit(out_path: Path, video: Path,
                         backend: str = "") -> bool:
    """Reusa transcrição só se o arquivo fonte tem o mesmo tamanho e mtime.

    E, desde a revisão textual, só se o transcript gravado passou pelo mesmo
    processo que está pedido agora — ver `_variante_compativel`.

    `backend`: o que está sendo PEDIDO agora. A troca tem direção: pedido
    pago (elevenlabs) com transcript LOCAL gravado e miss — o usuario esta
    pagando pela qualidade e reusar o local seria "degradar calado" (as
    palavras do proprio cache entre projetos). O inverso (pedido local com
    transcript pago gravado) continua hit: um transcript do Scribe custou
    dinheiro e nao se joga fora. Caso real: o C066 saiu com legenda
    alucinada do Whisper e o refazer com o app ja em ElevenLabs reusava o
    transcript ruim — foi preciso apagar arquivo na mao.
    """
    if not out_path.exists():
        return False
    if str(backend or "").strip().lower() == "elevenlabs":
        marca = marca_da_assinatura(out_path.parent, Path(video).stem)
        if marca is not None and marca.startswith("local-"):
            print(f"  transcript local gravado, pedido elevenlabs — "
                  f"retranscrevendo {Path(video).stem}", flush=True)
            return False
    sig_path = signature_path(out_path.parent, Path(video).stem)
    wanted = source_signature(video)
    have = ""
    if sig_path.exists():
        try:
            have = sig_path.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, IndexError):
            have = ""
    if have and have != wanted:
        return False
    if not _variante_compativel(marca_da_assinatura(out_path.parent,
                                                    Path(video).stem)):
        return False
    if not have:
        # Transcript legado (pré-assinatura). Fontes nunca mudam depois do
        # import — adotar a assinatura atual é seguro e evita re-transcrever
        # (custo de API) todos os projetos antigos. O cut.mp4 é REGRAVADO a
        # cada render: sem assinatura não dá para saber de qual cut esse
        # transcript veio, e confiar nele é exatamente o bug da legenda velha.
        if Path(video).stem == "cut":
            return False
        try:
            sig_path.write_text(wanted, encoding="utf-8")
        except OSError:
            pass
    return True


# --- Cache de transcrição ENTRE projetos -----------------------------------
#
# O cache acima (`transcript_cache_hit`) vive dentro de `transcripts/` do
# projeto. Uma importação nova nasce com essa pasta vazia, então reimportar a
# MESMA fonte transcrevia tudo de novo — tempo e cota de API.
#
# Medido nos 129 projetos do usuário: 112 fontes distintas, **14 importadas
# mais de uma vez** (uma delas 5 vezes), somando 22 minutos de ANALYZE pagos
# em repetição.
CACHE_ENTRE_PROJETOS = Path(
    os.environ.get("ATIVAVID_TRANSCRIPT_CACHE")
    or (Path.home() / "ATIVAVID" / "transcript-cache")
)
_PONTA = 4 << 20          # 4 MB de cada ponta
_TETO_DO_CACHE = 400      # transcrições guardadas; a mais antiga sai primeiro


def chave_da_fonte(video: Path) -> str:
    """Identidade do ARQUIVO, independente de onde ele foi importado.

    Tamanho mais as duas pontas do conteúdo — não o arquivo inteiro: uma fonte
    de 500 MB sairia cara para uma consulta de cache, e as fontes do usuário
    passam disso. Nome não entra: a mesma gravação importada com outro nome é
    a mesma gravação, e dois arquivos diferentes com o mesmo tamanho E as
    mesmas duas pontas não acontecem por acidente.
    """
    import hashlib

    st = Path(video).stat()
    h = hashlib.sha256(str(st.st_size).encode())
    with Path(video).open("rb") as f:
        h.update(f.read(_PONTA))
        if st.st_size > 2 * _PONTA:
            f.seek(-_PONTA, os.SEEK_END)
            h.update(f.read(_PONTA))
    return h.hexdigest()[:32]


def _cacheavel(video: Path) -> bool:
    """O `cut.mp4` fica de fora.

    A chave é por CONTEÚDO, então um cut regravado diferente já daria outra
    chave — seria seguro. Mas o cut é o único arquivo que muda debaixo do
    mesmo nome, e confiar num transcript dele foi a origem do bug da legenda
    velha (ver `transcript_cache_hit`). O ganho medido está todo nas FONTES;
    não vale chegar perto dessa área para não ganhar nada.
    """
    return Path(video).stem != "cut"


def _caminho_no_cache(video: Path, backend: str, modelo: str) -> Path:
    # backend e modelo entram na chave: um transcript do Groq não serve quando
    # o pedido é ElevenLabs. O usuário paga pelo Scribe justamente pela
    # qualidade — reaproveitar o outro seria degradar calado.
    marca = f"{backend}-{modelo}".replace("/", "_").replace(":", "_")[:48]
    return CACHE_ENTRE_PROJETOS / f"{chave_da_fonte(video)}.{marca}.json"


def buscar_no_cache(video: Path, backend: str, modelo: str) -> dict | None:
    if not _cacheavel(video):
        return None
    try:
        p = _caminho_no_cache(video, backend, modelo)
        if not p.is_file():
            return None
        dados = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(dados, dict) or not dados.get("words"):
            return None
        os.utime(p, None)      # marca uso, para a poda tirar o mais parado
        return dados
    except (OSError, ValueError):
        return None


def guardar_no_cache(video: Path, backend: str, modelo: str, payload: dict) -> None:
    """Nunca derruba a transcrição: o cache é conveniência, não resultado."""
    try:
        if not (_cacheavel(video) and isinstance(payload, dict) and payload.get("words")):
            return
        CACHE_ENTRE_PROJETOS.mkdir(parents=True, exist_ok=True)
        destino = _caminho_no_cache(video, backend, modelo)
        tmp = destino.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, destino)
        guardados = sorted(CACHE_ENTRE_PROJETOS.glob("*.json"),
                           key=lambda p: p.stat().st_mtime)
        for velho in guardados[:-_TETO_DO_CACHE]:
            velho.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _telemetria_da_revisao(meta: dict) -> dict:
    """Os campos da revisão para a linha de telemetria. Vazio quando não houve."""
    if not meta:
        return {}
    return {
        "revisao": "ok" if meta.get("revisado") else "nao",
        "revisao_motivo": (meta.get("motivo") or "")[:160] or None,
        "revisao_seg": meta.get("seg"),
        "revisao_propostas": meta.get("propostas"),
        "revisao_aplicadas": meta.get("aplicadas"),
        "revisao_ignoradas": meta.get("ignoradas"),
        "revisao_ts_preservados": meta.get("ts_preservados"),
    }


def _revisar_payload(rev, payload: dict, marca: str, marca_revisada: str
                     ) -> tuple[dict, str, dict]:
    """Revisa o texto do payload. Devolve `(payload, marca, meta)`.

    A marca devolvida é a REGRA do rollback, e é por isso que ela sai daqui
    em vez de ser decidida pelo chamador:

        revisão concluída e `conferir()` passou → `marca_revisada`
        qualquer outra coisa                    → `marca`, sem sufixo

    Gravar um Whisper puro como se fosse revisado envenenaria o cache: uma
    queda de rede de dez segundos marcaria aquele vídeo como já processado, e
    a próxima chance de revisá-lo só voltaria quando a versão virasse `rev2`.
    Marcando pelo que de fato aconteceu, a falha é temporária de verdade — a
    próxima passada tenta de novo, e sem retranscrever, porque o Whisper puro
    já está no cache entre projetos.

    Nunca levanta. `rev.revisar` já devolve as palavras do Whisper intactas
    quando algo dá errado, e o que sobra aqui é escolher a marca e falar.
    """
    palavras = rev.palavras_do_schema(payload)
    revisadas, meta = rev.revisar(palavras, str(payload.get("text") or ""))
    if not meta.get("revisado"):
        # `REVISAO_GEMINI_PULADA` é decisão de política (fonte longa);
        # `REVISAO_GEMINI_FALHOU` é o Gemini ou o gate. Marcadores separados
        # porque um deles não é problema e o outro pode ser.
        rotulo = ("REVISAO_GEMINI_PULADA" if meta.get("pulada")
                  else "REVISAO_GEMINI_FALHOU")
        print(f"{rotulo} {meta.get('motivo') or 'sem motivo'} "
              f"— seguindo com o Whisper puro", flush=True)
        return payload, marca, meta

    from app.transcricao import schema_scribe

    novo = schema_scribe(
        revisadas, " ".join(p.texto for p in revisadas),
        idioma=str(payload.get("language_code") or ""),
        motor=str(payload.get("_motor") or ""),
        modelo=str(payload.get("_modelo") or ""),
        backend=str(payload.get("_backend") or ""),
    )
    # Campos que não pertencem ao schema mas o projeto usa. Preservados um a
    # um de propósito: um `update` cego devolveria `words` e `text` velhos.
    for extra in ("_seg_transcricao",):
        if extra in payload:
            novo[extra] = payload[extra]
    novo["_revisao"] = rev.VERSAO
    novo["_revisao_aplicadas"] = meta.get("aplicadas")

    print(f"REVISAO_GEMINI ok correcoes={meta.get('aplicadas')}/"
          f"{meta.get('propostas')} ignoradas={meta.get('ignoradas')} "
          f"ts_preservados={meta.get('ts_preservados')} "
          f"seg={meta.get('seg')}", flush=True)
    return novo, marca_revisada, meta


def _gravar_json_atomico(path: Path, payload: dict) -> None:
    """Escreve num temporario e troca de uma vez.

    A revisao ADIADA (5.0.72) reescreve o transcript enquanto o pipeline pode
    estar lendo o arquivo (o `spoken` do plano, por exemplo). Uma escrita
    direta deixaria um leitor ver meio JSON. No Windows o `replace` falha se
    alguem esta com o arquivo aberto naquele instante — as leituras aqui sao
    de milissegundos, entao tentar de novo resolve.
    """
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    ultimo: Exception | None = None
    for _ in range(25):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:
            ultimo = e
            time.sleep(0.2)
    tmp.unlink(missing_ok=True)
    raise RuntimeError(f"nao consegui trocar {path.name}: {ultimo}")


def _so_revisar(
    video: Path, transcripts_dir: Path, out_path: Path, *,
    rev, motor, marca: str, marca_revisada: str, verbose: bool,
) -> Path:
    """A segunda metade de uma transcricao com `--revisao depois`.

    O pipeline mandou o Whisper puro para o disco e seguiu para o plano e o
    corte; esta chamada roda em paralelo com eles e so as legendas esperam
    por ela. Reusa o que ja existe: o revisado em cache (nada a fazer), ou o
    puro em cache/no arquivo (revisa e troca).
    """
    from app.transcricao import telemetria

    t0 = time.time()
    if not (rev and rev.ligada()):
        print("REVISAO_DESLIGADA nada a revisar", flush=True)
        return out_path
    gravada = marca_da_assinatura(transcripts_dir, video.stem)
    if gravada == marca_revisada:
        print("REVISAO_JA_FEITA transcript ja esta revisado", flush=True)
        return out_path

    pronto = buscar_no_cache(video, marca_revisada, motor.modelo.chave)
    if pronto is not None:
        _gravar_json_atomico(out_path, pronto)
        try:
            write_source_signature(transcripts_dir, video, marca_revisada)
        except OSError:
            pass
        print(f"TRANSCRIPTION CACHE HIT {video.name} motor={marca_revisada} "
              f"modelo={motor.modelo.chave} — revisao ja estava no cache", flush=True)
        telemetria.registrar(
            video=telemetria.identificador(video), motor="whisper-local",
            modelo=motor.modelo.chave, cache="HIT",
            seg_total=round(time.time() - t0, 3), revisao="ok",
            revisao_motivo="revisada em outro projeto")
        return out_path

    base = buscar_no_cache(video, marca, motor.modelo.chave)
    if base is None and out_path.is_file():
        try:
            base = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base = None
    if base is None:
        print("REVISAO_SEM_BASE nao achei o Whisper puro para revisar", flush=True)
        return out_path

    payload, marca_final, meta = _revisar_payload(rev, base, marca, marca_revisada)
    if marca_final == marca_revisada:
        guardar_no_cache(video, marca_revisada, motor.modelo.chave, payload)
        _gravar_json_atomico(out_path, payload)
        try:
            write_source_signature(transcripts_dir, video, marca_final)
        except OSError:
            pass
    telemetria.registrar(
        video=telemetria.identificador(video), motor="whisper-local",
        modelo=motor.modelo.chave, cache="REVISAO-ADIADA",
        seg_total=round(time.time() - t0, 3),
        palavras=sum(1 for w in payload.get("words") or [] if w.get("type") == "word"),
        **_telemetria_da_revisao(meta))
    if verbose:
        print(f"  revisao adiada: {out_path.name} marca={marca_final} "
              f"em {time.time() - t0:.1f}s")
    return out_path


def _transcrever_local(
    video: Path,
    transcripts_dir: Path,
    out_path: Path,
    *,
    language: str | None,
    verbose: bool,
    modelo: str | None = None,
    revisao: str = "junto",
) -> Path:
    """Ponte para `app.transcricao`: transcreve nesta maquina e grava o JSON.

    O resultado sai no MESMO schema dos outros backends (`para_schema_scribe`),
    entao `captions_for_remotion`, `pack_transcripts`, `timeline_view` e os
    demais nao sabem que o motor mudou.

    O cache ENTRE projetos entra aqui tambem, com a chave marcando modelo e
    backend: um transcript do `small` nao pode ser servido para quem pediu
    `medium`.
    """
    import sys as _sys

    raiz = Path(__file__).resolve().parent.parent
    if str(raiz) not in _sys.path:
        _sys.path.insert(0, str(raiz))
    from app.transcricao.whisper_local import MotorWhisperLocal

    from app.transcricao import primeiro_uso, telemetria

    # Primeira vez nesta maquina: baixar o que falta antes de qualquer coisa.
    # Depois disso `ja_pronto()` responde em milissegundos e nada acontece.
    if not primeiro_uso.ja_pronto():
        plano = primeiro_uso.planejar()
        print(f"{primeiro_uso.TITULO}: {primeiro_uso.BAIXANDO} "
              f"({plano.humano()})", flush=True)

        def _andar(fracao: float, rotulo: str) -> None:
            print(f"PRIMEIRO_USO {fracao * 100:.0f}% {rotulo} "
                  f"({plano.total_mb * fracao / 1024:.1f} GB de "
                  f"{plano.total_mb / 1024:.1f} GB)", flush=True)

        primeiro_uso.preparar(progresso=_andar)

    motor = MotorWhisperLocal(modelo)
    ok, motivo = motor.disponivel()
    if not ok:
        raise RuntimeError(motivo)

    rev = _revisao()
    quer_revisar = bool(rev and rev.ligada())
    marca = f"local-{motor.modelo.chave}"
    marca_revisada = f"{marca}{rev.SUFIXO}" if rev else marca

    # 5.0.72: `--revisao so` e a segunda metade de um `--revisao depois`.
    if revisao == "so":
        return _so_revisar(video, transcripts_dir, out_path, rev=rev, motor=motor,
                           marca=marca, marca_revisada=marca_revisada, verbose=verbose)
    # `--revisao depois`: o Whisper puro sai AGORA e a revisao fica para
    # depois, em paralelo com o plano e o corte. MEDIDO na telemetria real:
    # a revisao e uma ida a IA de 13 s (mediana em dias normais) a 24 s (num
    # lote), com casos de 84 s — e o job ficava parado esperando por ela,
    # sendo que so as legendas usam as palavras revisadas. Se o revisado JA
    # esta no cache entre projetos, nao ha o que adiar.
    if revisao == "depois" and quer_revisar:
        if buscar_no_cache(video, marca_revisada, motor.modelo.chave) is None:
            quer_revisar = False
            print("REVISAO_ADIADA o Whisper puro segue; a revisao roda em paralelo",
                  flush=True)
    # A variante PEDIDA. E so ela: servir um transcript revisado para quem
    # desligou a revisao -- ou o contrario -- e o que faz `ATIVAVID_REVISAO`
    # deixar de ser rollback.
    marca_pedida = marca_revisada if quer_revisar else marca

    t_cache = time.time()
    guardado = buscar_no_cache(video, marca_pedida, motor.modelo.chave)
    if guardado is not None:
        out_path.write_text(json.dumps(guardado, indent=2), encoding="utf-8")
        try:
            write_source_signature(transcripts_dir, video, marca_pedida)
        except OSError:
            pass
        # Marcador explicito: o tempo economizado e a diferenca entre o que
        # a transcricao custou quando foi feita (gravado no proprio cache) e
        # os milissegundos de agora.
        gasto = time.time() - t_cache
        telemetria.registrar(
            video=telemetria.identificador(video), motor="whisper-local",
            modelo=motor.modelo.chave, cache="HIT", seg_total=round(gasto, 3),
            palavras=sum(1 for w in guardado.get("words") or []
                         if w.get("type") == "word"))
        print(f"TRANSCRIPTION CACHE HIT {video.name} motor={marca_pedida} "
              f"modelo={motor.modelo.chave} custou={gasto:.2f}s "
              f"economizou~{max(0.0, float(guardado.get('_seg_transcricao') or 0) - gasto):.1f}s",
              flush=True)
        return out_path

    t0 = time.time()

    # Revisao ligada e o Whisper PURO ja esta no cache entre projetos? Entao
    # o que falta e so a revisao. Nao acordar a GPU para refazer trabalho que
    # ja esta no disco e o que torna barato ligar a revisao numa base ja
    # transcrita -- e, no caminho inverso, ter tentado revisar e falhado.
    base = buscar_no_cache(video, marca, motor.modelo.chave) if quer_revisar else None
    resultado = None
    t_audio = 0.0

    if base is not None:
        payload = base
        print(f"TRANSCRIPTION CACHE HIT {video.name} motor={marca} "
              f"modelo={motor.modelo.chave} — falta so a revisao", flush=True)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            # WAV mono 16 kHz PCM: e o que o Whisper consome nativamente. Passar
            # o mp4 direto tambem funciona, mas ai o decode acontece dentro do
            # motor e some da medicao -- e este projeto mede fase por fase.
            audio = Path(tmp) / f"{video.stem}.wav"
            t_audio = time.time()
            _extrair_wav16k(video, audio)
            t_audio = time.time() - t_audio
            # 5.0.73: pelo servico residente quando ele existe (o modelo
            # fica carregado entre jobs); senao aqui mesmo, como antes.
            from app.transcricao import residente

            resultado = residente.transcrever(motor, audio, idioma=language,
                                              fonte_original=video)

        payload = resultado.para_schema_scribe()
        payload["_seg_transcricao"] = round(
            float(resultado.tempos.get("transcrever") or 0.0) + t_audio, 3)
        # O Whisper puro vai para o cache ANTES da revisao, e sempre. Ele
        # custou GPU; a revisao pode falhar, e se falhar nao pode levar junto
        # a transcricao que ja esta pronta.
        guardar_no_cache(video, marca, motor.modelo.chave, payload)

    marca_final = marca
    meta_revisao: dict = {}
    if quer_revisar:
        payload, marca_final, meta_revisao = _revisar_payload(
            rev, payload, marca, marca_revisada)
        if marca_final == marca_revisada:
            guardar_no_cache(video, marca_revisada, motor.modelo.chave, payload)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    try:
        write_source_signature(transcripts_dir, video, marca_final)
    except OSError:
        pass

    if resultado is None:
        # Veio do cache puro e so foi revisado: nao ha medicao de motor para
        # registrar, e inventar uma sujaria a telemetria de velocidade.
        telemetria.registrar(
            video=telemetria.identificador(video), motor="whisper-local",
            modelo=motor.modelo.chave, cache="HIT-REVISADO",
            seg_total=round(time.time() - t0, 3),
            palavras=sum(1 for w in payload.get("words") or []
                         if w.get("type") == "word"),
            **_telemetria_da_revisao(meta_revisao))
        if verbose:
            print(f"  saved: {out_path.name} "
                  f"({out_path.stat().st_size / 1024:.1f} KB)")
        return out_path

    tempos = dict(resultado.tempos)
    tempos["extrair_audio"] = round(t_audio, 3)
    tempos["total"] = round(time.time() - t0, 3)
    seg_tr = float(resultado.tempos.get("transcrever") or 0.0)
    palavras = sum(1 for w in payload["words"] if w.get("type") == "word")
    telemetria.registrar(
        video=telemetria.identificador(video),
        motor=resultado.motor, modelo=resultado.modelo,
        device=resultado.backend, cache="MISS",
        seg_audio=round(resultado.duracao, 2),
        seg_transcricao=round(seg_tr, 3),
        seg_carregar_modelo=resultado.tempos.get("carregar_modelo"),
        residente=residente.ultimo(),
        seg_residente=resultado.tempos.get("residente"),
        seg_extrair_audio=round(t_audio, 3),
        seg_total=tempos["total"],
        realtime=(round(resultado.duracao / seg_tr, 2) if seg_tr > 0 else None),
        palavras=palavras,
        guarda_acionada=bool(resultado.tempos.get("_guarda_cortou")),
        queda=(resultado.backend != detectar_backend_pedido()),
        **_telemetria_da_revisao(meta_revisao),
    )
    if verbose:
        print(f"  saved: {out_path.name} "
              f"({out_path.stat().st_size / 1024:.1f} KB)")
        print(f"    words: {sum(1 for w in payload['words'] if w.get('type') == 'word')}")
        print("    tempos: " + "  ".join(f"{k}={v}s" for k, v in tempos.items()))
    return out_path


def detectar_backend_pedido() -> str:
    """O backend que a maquina anunciaria SEM queda. So para a telemetria."""
    try:
        from app.transcricao.plataforma import detectar

        return detectar().backend
    except Exception:  # noqa: BLE001
        return ""


def _extrair_wav16k(video: Path, dest: Path) -> None:
    """WAV mono 16 kHz PCM 16-bit -- o formato nativo do Whisper.

    Sem `-c:a libmp3lame` como o caminho de rede usa: ali o mp3 existe para
    caber no limite de upload da API. Local nao tem upload, entao comprimir
    so tiraria qualidade e gastaria CPU.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        check=True, capture_output=True)


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
    revisao: str = "junto",
    whisper_model: str | None = None,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    Cached: returns existing path immediately if the transcript already exists
    and the source still has the same size and mtime. A replaced file with the
    same name is transcribed again.
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

    # `--revisao so` SEMPRE entra: o arquivo existe (e o puro) e a saida
    # antecipada por cache o deixaria sem revisao para sempre.
    if revisao != "so" and transcript_cache_hit(out_path, video, backend):
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

    # Motor LOCAL (faster-whisper). Nao usa chave, nao usa rede e nao tem
    # limite de taxa. Fica fora do `auto` de proposito: baixar 1,4 GB de
    # modelo na primeira vez tem de ser escolha, nunca surpresa.
    if resolved == "local":
        return _transcrever_local(
            video, transcripts_dir, out_path, language=language,
            verbose=verbose, modelo=whisper_model, revisao=revisao,
        )

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

    # Já transcrevemos ESTE arquivo, em outro projeto, com este mesmo backend?
    # Consultado aqui e não antes de propósito: a resposta depende do backend
    # resolvido, e resolver custa um ffprobe que já aconteceu acima.
    guardado = buscar_no_cache(video, resolved, active_model)
    if guardado is not None:
        out_path.write_text(json.dumps(guardado, indent=2), encoding="utf-8")
        try:
            write_source_signature(transcripts_dir, video)
        except OSError:
            pass
        print(f"TRANSCRIPTION CACHE HIT {video.name} motor={resolved} "
              f"modelo={active_model} — sem chamar a API", flush=True)
        return out_path

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
        try:
            payload = _transcribe_audio(audio, active_key, active_model, language, verbose,
                                        cache_dir=chunk_cache, chunk_seconds=active_chunk,
                                        backend=resolved, wcpp=wcpp)
        except Exception as e:  # noqa: BLE001
            # Forçar um provedor não pode derrubar o job quando ele cai. Só o
            # ElevenLabs desce para o Groq: é o caminho que o `auto` já usava
            # para fonte curta, então a queda leva ao comportamento antigo, e
            # não a um desconhecido. O Groq não sobe para lugar nenhum.
            if resolved != "elevenlabs" or not api_key:
                raise
            print(f"  ELEVENLABS_FALHOU ({str(e)[:140]}) — caindo para o Groq",
                  flush=True)
            resolved, active_key, active_model = "groq", api_key, model
            active_chunk = chunk_seconds
            backend_label = "Groq (queda do ElevenLabs)"
            chunk_cache = chunk_cache.with_name(chunk_cache.name + "-groq")
            payload = _transcribe_audio(audio, active_key, active_model, language, verbose,
                                        cache_dir=chunk_cache, chunk_seconds=active_chunk,
                                        backend=resolved, wcpp=wcpp)

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        write_source_signature(transcripts_dir, video)
    except OSError:
        pass
    # Guarda para a PRÓXIMA importação desta mesma fonte. Depois de gravar o
    # resultado no projeto: o cache nunca pode ser motivo de perder uma
    # transcrição que já custou a chamada de API.
    guardar_no_cache(video, resolved, active_model, payload)
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
        "--whisper-model",
        type=str,
        default=None,
        choices=["small", "medium", "large-v3"],
        help="Modelo do motor local. Por padrao escolhido pela VRAM da maquina.",
    )
    ap.add_argument(
        "--backend",
        type=str,
        default="auto",
        choices=["auto", "groq", "elevenlabs", "whispercpp", "local"],
        help=f"Transcription backend. 'auto' (default) uses ElevenLabs Scribe for "
             f"sources longer than {LONG_SOURCE_SECONDS}s when ELEVENLABS_API_KEY is set, "
             "else Groq. Force with 'groq', 'elevenlabs', or 'whispercpp' (fully "
             "local, no API key, no upload cap — needs whisper.cpp built and a "
             "ggml model downloaded).",
    )
    ap.add_argument(
        "--revisao",
        default="junto",
        choices=["junto", "depois", "so"],
        help="5.0.72: 'junto' revisa antes de devolver (padrao); 'depois' devolve o "
             "Whisper puro e deixa a revisao para uma segunda chamada; 'so' e essa "
             "segunda chamada. So vale no backend local.",
    )
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()
    # Local transcription must not require a cloud key — that's the whole point.
    # `load_api_key()` encerra o processo se a chave faltar. Motor que nao
    # usa rede nao pode morrer por causa de chave que ele nunca vai ler.
    sem_chave = args.backend in ("whispercpp", "local")
    api_key = "" if sem_chave else load_api_key()
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
        whisper_model=args.whisper_model,
        revisao=args.revisao,
    )


if __name__ == "__main__":
    main()
