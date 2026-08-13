#!/usr/bin/env python3
"""Headless short-form fast-mode runner: source → final.mp4.

Deterministic Phase-1 cut (speech regions + voice levels + color detect),
then Remotion Phase 2/3 from a brand preset (same schema as
assets/preview/default-style.json). Stops with needs_review on the same
gates as Modo rápido.

Usage:
    uv run python pipeline/run_fast.py <source.mp4> --edit-dir <dir>/edit \\
        --preset assets/preview/default-style.json
    uv run python pipeline/run_fast.py <source.mp4> --edit-dir <dir>/edit \\
        --preset-json '{"edit":"limpa",...}'
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "helpers"
SHORTFORM = REPO / "assets" / "shortform"
LONGFORM = REPO / "assets" / "longform"
DEFAULT_PRESET = REPO / "assets" / "preview" / "default-style.json"

LEAD_S = 0.05
TRAIL_S = 0.12
MIN_SILENCE_DROP = 0.40  # keep speech regions; gaps longer than this are cuts
ZOOM_CYCLE = [1.14, 1.2, 1.12, 1.22, 1.16, 1.1, 1.18]


class NeedsReview(Exception):
    """Material problem — stop and surface to the user."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def set_stage(edit_dir: Path, stage: str, message: str, progress: int | None = None) -> None:
    """UI-facing progress for the hub (read while worker is busy)."""
    payload = {
        "stage": stage,
        "message": message,
        "progress": progress,
    }
    try:
        (edit_dir / "pipeline_status.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass
    print(f"[{stage}] {message}", flush=True)


def _uv_python(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["uv", "run", "python", *args]
    env = os.environ.copy()
    # helpers import _utf8 from the helpers dir
    env["PYTHONPATH"] = str(HELPERS) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        from app.win_process import hide_console_kwargs  # type: ignore
        hide = hide_console_kwargs()
    except Exception:
        hide = {}
    proc = subprocess.run(
        cmd,
        cwd=cwd or REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **hide,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"cmd failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}"
        )
    return proc


def _helper(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return _uv_python(str(HELPERS / name), *args, check=check)


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nokey=1:noprint_wrappers=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out or 0.0)


def _ffprobe_fps(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=nokey=1:noprint_wrappers=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if "/" in out:
        a, b = out.split("/", 1)
        return float(a) / float(b) if float(b) else 30.0
    return float(out or 30.0)


def _ffprobe_wh(path: Path) -> tuple[int, int]:
    from app.ffmpeg_tools import ffprobe_bin
    from app.win_process import hide_console_kwargs

    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(path),
    ]
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hide_console_kwargs(),
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        raise RuntimeError(
            f"ffprobe falhou ao ler o vídeo ({path.name}): {err}\n"
            "Confira se o arquivo abre no player e se o FFmpeg está instalado."
        )
    parts = [p for p in (r.stdout or "").strip().split(",") if p.strip()]
    if len(parts) < 2:
        raise RuntimeError(f"ffprobe não retornou width/height para {path.name}: {r.stdout!r}")
    return int(parts[0]), int(parts[1])


def _ffprobe_rotation(path: Path) -> int:
    """Display-matrix rotation in degrees (0 if none). Phone clips often store
    landscape pixels with ±90 so the *display* is vertical — render.py already
    accounts for this; the format gate must too."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream_side_data=rotation",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True,
        )
        vals = [v for v in r.stdout.split() if v.lstrip("-").replace(".", "", 1).isdigit()]
        if vals:
            return int(float(vals[0]))
    except Exception:
        pass
    # fallback: stream tag
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream_tags=rotate",
                "-of", "default=nw=1:nk=1", str(path),
            ],
            capture_output=True, text=True,
        )
        tag = (r.stdout or "").strip()
        if tag.lstrip("-").isdigit():
            return int(tag)
    except Exception:
        pass
    return 0


def _display_wh(path: Path) -> tuple[int, int]:
    w, h = _ffprobe_wh(path)
    if abs(_ffprobe_rotation(path)) % 180 == 90:
        return h, w
    return w, h


def _count_frames(path: Path) -> int:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries", "stream=nb_read_frames",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out or 0)


def load_preset(path: Path | None, raw: str | None) -> dict:
    if raw:
        return json.loads(raw)
    p = path or DEFAULT_PRESET
    if not p.exists():
        # fallback baked-in house style (matches default-style shape)
        return {
            "edit": "limpa",
            "headline": "realce",
            "captions": "stacked",
            "accent": "#E30004",
            "captionAccent": "#FFFFFF",
            "emphasisAccent": "#ff0000",
            "circleAccent": None,
            "elements": {
                "tracking": False,
                "zoomAuto": True,
                "zoomCuts": True,
                "flashCut": True,
                "musicAI": False,
                "endCard": True,
            },
            "fastMode": True,
            "endCardCopy": {"line1": "", "line2": ""},
        }
    return json.loads(p.read_text(encoding="utf-8-sig"))


def parse_speech_regions(stdout: str) -> list[tuple[float, float]]:
    regions: list[tuple[float, float]] = []
    for m in re.finditer(r"([\d.]+)\s*->\s*([\d.]+)", stdout):
        a, b = float(m.group(1)), float(m.group(2))
        if b > a:
            regions.append((a, b))
    return regions


def load_preview_edit_ranges(edit_dir: Path, source_key: str) -> list[dict] | None:
    """Lê ajustes do editor (IN/OUT, trims). Se houver ranges, o pipeline usa eles."""
    path = edit_dir / "preview_edits.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    edl = data.get("edl") or {}
    raw = edl.get("ranges") or []
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        try:
            start = float(r["start"])
            end = float(r["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end - start < 0.05:
            continue
        item = {
            "source": str(r.get("source") or source_key),
            "start": round(start, 3),
            "end": round(end, 3),
            "beat": str(r.get("beat") or ""),
        }
        if r.get("gain_db") is not None:
            try:
                item["gain_db"] = float(r["gain_db"])
            except (TypeError, ValueError):
                pass
        out.append(item)
    if not out:
        return None
    # Arquiva para não reaplicar em loop infinito se o job falhar depois
    try:
        applied = edit_dir / "preview_edits.applied.json"
        path.replace(applied)
    except OSError:
        try:
            path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    return out


def build_edl_ranges(
    source_key: str,
    regions: list[tuple[float, float]],
    voice: dict,
    quote: str,
    source_dur: float | None = None,
) -> list[dict]:
    if not regions:
        raise NeedsReview("no_speech", "speech_regions found no speech")

    # Merge tiny gaps (< MIN_SILENCE_DROP) so we don't over-cut
    merged: list[tuple[float, float]] = [regions[0]]
    for a, b in regions[1:]:
        la, lb = merged[-1]
        if a - lb < MIN_SILENCE_DROP:
            merged[-1] = (la, b)
        else:
            merged.append((a, b))

    # Drop leading micro "false starts" (éé… / hum) when a real island follows.
    while len(merged) >= 2 and (merged[0][1] - merged[0][0]) < 0.55:
        gap = merged[1][0] - merged[0][1]
        if gap < 1.5:
            merged.pop(0)
        else:
            break

    # Map low-run gains onto ranges (worst run overlapping each range)
    low_runs = voice.get("low_runs") or []
    ranges: list[dict] = []
    for i, (a, b) in enumerate(merged):
        start = max(0.0, a - LEAD_S)
        end = b + TRAIL_S
        if source_dur and source_dur > 0:
            end = min(end, source_dur)
            if end - start < 0.12:
                continue
        gain = 0.0
        worst = 0.0
        for run in low_runs:
            rs, re_ = float(run["start"]), float(run["end"])
            if re_ < start or rs > end:
                continue
            g = float(run.get("suggest_gain_db") or 0)
            if g > gain:
                gain = g
            d = float(run.get("delta_db") or 0)
            if d < worst:
                worst = d
        # Inaudible: apply the suggested gain instead of hard-stopping the
        # product path. Agent/skill mode can still warn; 1-click must deliver.
        if worst <= -12.0 and gain >= 10.0:
            print(
                f"[warn] under-level run delta={worst:.1f}dB on range {i} — "
                f"applying gain_db={min(gain, 12.0):.1f}",
                flush=True,
            )
        ranges.append({
            "source": source_key,
            "start": round(start, 3),
            "end": round(end, 3),
            "beat": "HOOK" if i == 0 else f"B{i}",
            "quote": quote[:120],
            "reason": "auto speech region",
            "gain_db": round(min(gain, 12.0), 1),
        })
    if not ranges:
        raise NeedsReview("no_speech", "speech regions collapsed after polish")
    return ranges


def transcript_text(edit_dir: Path, stem: str) -> str:
    p = edit_dir / "transcripts" / f"{stem}.json"
    if not p.exists():
        return ""
    data = json.loads(p.read_text(encoding="utf-8"))
    return (data.get("text") or "").strip()


def transcript_looks_bad(text: str) -> bool:
    if len(text) < 8:
        return True
    # mostly non-letters
    letters = sum(1 for c in text if c.isalpha())
    if letters < max(4, len(text) // 5):
        return True
    return False


def hook_lines_from_text(text: str) -> list[str]:
    words = [w for w in re.split(r"\s+", text) if w]
    if not words:
        return ["Assista", "até o final"]
    if len(words) <= 4:
        mid = max(1, len(words) // 2)
        return [" ".join(words[:mid]), " ".join(words[mid:]) or words[-1]]
    # first ~8 words → two balanced lines
    chunk = words[:8]
    mid = len(chunk) // 2
    return [" ".join(chunk[:mid]), " ".join(chunk[mid:])]


def _clean_quote(q: str) -> str:
    q = re.sub(r"\s+", " ", (q or "").strip())
    # drop obvious ASR garbage tails
    q = re.sub(r"\s+\S{1,3}$", "", q) if q.endswith("…") else q
    return q.strip(" \"'")


def _legenda_from_edl(edit_dir: Path, spoken: str, preset: dict) -> str:
    """Post caption from structure (hook/headline/quotes) — not a raw ASR dump."""
    edl: dict = {}
    try:
        edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    llm = edl.get("llm") or {}
    hook = _clean_quote(str(llm.get("hook") or ""))
    headline = _clean_quote(str(llm.get("headline") or ""))

    # Prefer on-screen hook from edit-data when present
    try:
        ed = json.loads(
            (edit_dir / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8")
        )
        h = ed.get("hook") or {}
        if h.get("enabled", True):
            lines = [str(x).strip() for x in (h.get("lines") or []) if str(x).strip()]
            if lines:
                hook = hook or " ".join(lines)
                headline = headline or " ".join(lines)
    except (OSError, json.JSONDecodeError):
        pass

    quotes: list[str] = []
    for r in edl.get("ranges") or []:
        q = _clean_quote(str(r.get("quote") or ""))
        beat = str(r.get("beat") or "").upper()
        if not q or len(q) < 8:
            continue
        # Keep punchy beats; skip ultra-long ASR blobs
        if len(q) > 140:
            q = q[:137].rsplit(" ", 1)[0] + "…"
        quotes.append((beat, q))

    gancho = headline or hook
    lines: list[str] = []
    if gancho:
        lines.append(gancho if gancho.endswith(("?", "!", "…")) else gancho)
        lines.append("")

    # 1–2 falas marcantes (HOOK + CTA/último), não o monólogo inteiro
    picked: list[str] = []
    for prefer in ("HOOK", "PROBLEM", "CTA", "PROOF", "BENEFIT", "SOLUTION"):
        for beat, q in quotes:
            if beat == prefer and q not in picked:
                picked.append(q)
                break
        if len(picked) >= 2:
            break
    if not picked:
        for _, q in quotes[:2]:
            if q not in picked:
                picked.append(q)
    for q in picked:
        lines.append(f"“{q}”" if not q.startswith(("“", '"')) else q)

    if not lines:
        # last resort: short slice of spoken, never 400 chars of ASR
        spoken = re.sub(r"\s+", " ", (spoken or "").strip())
        if spoken:
            cut = spoken[:180].rsplit(" ", 1)[0]
            lines.append(cut + ("…" if len(spoken) > 180 else ""))

    copy = preset.get("endCardCopy") or {}
    handle = (copy.get("line1") or "").strip()
    cta = (copy.get("line2") or "").strip()
    if handle or cta:
        lines.append("")
        if handle:
            lines.append(handle)
        if cta:
            lines.append(cta)

    # Niche-first tags; #reels only as filler if we have room
    tags: list[str] = []
    brand = re.sub(r"^Segue\s+", "", handle, flags=re.I).strip()
    if brand.startswith("@"):
        tags.append("#" + re.sub(r"[^A-Za-z0-9_]", "", brand[1:])[:24])
    goal = (preset.get("videoGoal") or "reels").lower()
    if goal in ("reels", "tiktok", "shorts"):
        tags.append("#" + goal if goal != "tiktok" else "#tiktok")
    tags.append("#shorts" if "#shorts" not in tags else "#loja")
    # unique, max 4
    seen: set[str] = set()
    uniq = []
    for t in tags:
        tl = t.lower()
        if tl not in seen and t.startswith("#") and len(t) > 1:
            seen.add(tl)
            uniq.append(t)
    lines.append("")
    lines.append(" ".join(uniq[:4]))
    return "\n".join(lines).strip() + "\n"


def _llm_polish_legenda(draft: str, *, spoken: str, preset: dict) -> str | None:
    """Optional short IG caption via sessão IA. Soft-fail → keep draft."""
    try:
        from app.llm_session import chat  # type: ignore
    except Exception:
        return None
    copy = preset.get("endCardCopy") or {}
    system = (
        "Você escreve legendas curtas de Reels/TikTok em português do Brasil.\n"
        "Responda SOMENTE com o texto final da legenda (sem markdown, sem aspas).\n"
        "Regras: 1ª linha = gancho; 2–4 linhas no máximo no corpo; NÃO cole a "
        "transcrição inteira; corrija erros óbvios de ASR; no máximo 4 hashtags "
        "de nicho (evite #viral #fyp); preserve o CTA da marca se houver."
    )
    user = (
        f"CTA marca: {(copy.get('line1') or '').strip()} | {(copy.get('line2') or '').strip()}\n"
        f"Rascunho atual:\n{draft}\n\n"
        f"Fala (referência, NÃO copiar inteira):\n{(spoken or '')[:500]}"
    )
    try:
        text, _backend = chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] legenda LLM: {e}", flush=True)
        return None
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text).removesuffix("```").strip()
    if len(text) < 12 or len(text) > 900:
        return None
    if text.count("#") > 6:
        return None
    return text if text.endswith("\n") else text + "\n"


def write_legenda(edit_dir: Path, spoken: str, preset: dict) -> Path:
    """Escreve legenda.txt — legenda do POST (Instagram), não a legenda queimada.

    Antes: dump da transcrição Whisper truncada em 400 chars (lixo legível).
    Agora: gancho + 1–2 falas do EDL + CTA da marca + hashtags; tenta polir com IA.
    """
    draft = _legenda_from_edl(edit_dir, spoken, preset)
    polished = _llm_polish_legenda(draft, spoken=spoken, preset=preset)
    body = polished or draft
    path = edit_dir / "legenda.txt"
    path.write_text(body, encoding="utf-8")
    print(f"[legenda] {'IA' if polished else 'EDL'} → {path.name} ({len(body)} chars)", flush=True)
    return path


def write_segments_json(edit_dir: Path, fps: float) -> None:
    clips = edit_dir / "clips_graded"
    segs = sorted(clips.glob("seg_*_v.mp4")) or sorted(clips.glob("seg_*.mp4"))
    edl = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8"))
    nranges = len(edl["ranges"])
    if len(segs) != nranges:
        raise RuntimeError(f"{len(segs)} segments for {nranges} ranges — clips_graded dirty")
    cum = [0]
    t = 0
    for f in segs:
        n = _count_frames(f)
        t += n
        cum.append(t)
    real = _count_frames(edit_dir / "cut.mp4")
    if t != real:
        # Sub-frame audio drift after loudnorm used to amputate a few picture
        # frames via -shortest. Tolerate a tiny gap and absorb into the last
        # segment so Phase 2 can still ship; large gaps stay hard errors.
        drift = abs(t - real)
        soft = max(6, int(round(fps * 0.2)))
        if drift > soft:
            raise RuntimeError(f"segments sum {t}f != cut.mp4 {real}f")
        print(
            f"[warn] segments sum {t}f vs cut.mp4 {real}f (Δ{real - t}f) — "
            f"ajustando último segmento",
            flush=True,
        )
        cum[-1] = real
        if len(cum) >= 2 and cum[-1] <= cum[-2]:
            # cut shorter than all-but-last: shrink from the end proportionally
            raise RuntimeError(f"segments sum {t}f != cut.mp4 {real}f")
    out = {
        "segments": [
            {
                "start": round(cum[i] / fps, 4),
                "dur": round((cum[i + 1] - cum[i]) / fps, 4),
            }
            for i in range(len(cum) - 1)
        ]
    }
    dest = edit_dir / "remotion" / "public" / "segments.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")


def write_neutral_track(public: Path, edit_data: dict) -> None:
    n = max(1, round(edit_data["durationSec"] * edit_data["fps"]))
    tx = edit_data["camera"]["targetX"]
    ty = edit_data["camera"]["targetY"]
    data = {
        "fps": edit_data["fps"],
        "width": edit_data["width"],
        "height": edit_data["height"],
        "count": n,
        "points": [[tx, ty]] * n,
        "neutral": True,
    }
    (public / "track.json").write_text(json.dumps(data), encoding="utf-8")


def build_edit_data(cut: Path, preset: dict, hook: list[str], duration: float, fps: float) -> dict:
    elems = dict(preset.get("elements") or {})
    intensity = (preset.get("intensity") or "medio").lower()
    if intensity == "sutil":
        elems["flashCut"] = False
        elems["zoomAuto"] = bool(elems.get("zoomAuto"))
        zoom_scale = 0.5
    elif intensity == "forte":
        elems["flashCut"] = True if elems.get("flashCut") is not False else False
        elems["zoomAuto"] = True
        zoom_scale = 1.15
    else:
        zoom_scale = 1.0

    headline = preset.get("headline") or "outline"
    captions = preset.get("captions") or "karaoke"
    copy = preset.get("endCardCopy") or {}
    n_segs = max(1, len(json.loads((cut.parent / "edl.json").read_text(encoding="utf-8"))["ranges"]))
    zooms = (ZOOM_CYCLE * ((n_segs // len(ZOOM_CYCLE)) + 1))[:n_segs]
    zooms = [round(1.0 + (z - 1.0) * zoom_scale, 3) for z in zooms]
    if not elems.get("zoomCuts", True) or intensity == "sutil":
        if intensity == "sutil":
            zooms = [round(1.0 + (z - 1.0) * 0.35, 3) for z in zooms]
        if not elems.get("zoomCuts", True):
            zooms = [1.0] * n_segs

    hook_enabled = headline != "nenhuma"
    cap_enabled = captions != "nenhuma"
    accent = preset.get("accent") or "#ff5200"

    # Prefer AI-generated headline text when present
    ai_hl = (preset.get("aiHeadline") or "").strip()
    if ai_hl and hook_enabled:
        words = ai_hl.split()
        mid = max(1, len(words) // 2)
        hook = [" ".join(words[:mid]), " ".join(words[mid:]) or words[-1]]

    # Dimensões pelo preset de export (reels 9:16 / youtube 16:9 / square)
    try:
        from app.brand_kits import export_preset_info  # type: ignore
        exp = export_preset_info(preset.get("exportPreset") or preset.get("videoGoal"))
    except Exception:
        exp = {"width": 1080, "height": 1920, "id": "reels"}
    ed: dict = {
        "width": int(exp.get("width") or 1080),
        "height": int(exp.get("height") or 1920),
        "fps": int(round(fps)),
        "durationSec": round(duration, 4),
        "exportPreset": exp.get("id") or "reels",
        "camera": {
            "enabled": True,
            "zooms": zooms,
            "pushIn": (0.04 if elems.get("zoomAuto", True) else 0.0) * zoom_scale,
            "targetX": 0.5,
            "targetY": 0.4,
        },
        "hook": {
            "enabled": hook_enabled,
            "endSec": min(4.0, max(1.5, duration * 0.25)),
            "style": headline if hook_enabled else "outline",
            "lines": hook if hook_enabled else ["", ""],
            "accent": accent,
            "logo": None,
            "sign": None,
        },
        "captions": {
            "enabled": cap_enabled,
            "style": captions if cap_enabled else "karaoke",
            "fontSize": 76,
            "maxWords": 3,
            "safeWidth": 720,
            "paddingBottom": 420,
            "windows": [],
        },
        "inserts": [],
        "behind": [],
        "soundtrack": {
            "enabled": False,
            "file": "trilha.mp3",
            "volume": 0.12,
        },
        "endCard": {
            "enabled": bool(elems.get("endCard", True)),
            "lastSec": 2.5,
            "lines": [
                (copy.get("line1") or "").strip() or "@marca",
                (copy.get("line2") or "").strip() or "",
            ],
            "logo": None,
            "accent": accent,
            "dim": 0.82,
        },
    }
    if elems.get("flashCut"):
        # flash at each junction after the first
        segs = json.loads((cut.parent / "remotion" / "public" / "segments.json").read_text(encoding="utf-8"))
        transitions = []
        for s in segs.get("segments", [])[1:]:
            transitions.append({"at": s["start"], "type": "flash", "frames": 2})
        if transitions:
            ed["transitions"] = transitions

    ca = preset.get("captionAccent")
    if ca and captions in ("karaoke", "simples", "serifada", "classica", "bloco"):
        ed["captions"]["accent"] = ca
    ea = preset.get("emphasisAccent")
    if ea and captions in ("stacked", "scatter"):
        ed["captions"]["emphasisAccent"] = ea
    circ = preset.get("circleAccent")
    if circ and captions == "stacked":
        ed["captions"]["circleAccent"] = circ

    chunk = (preset.get("captionChunk") or "frase_curta").lower()
    if chunk in ("palavra", "word"):
        ed["captions"]["maxWords"] = 1
    elif chunk in ("frase", "frase_longa", "sentence"):
        ed["captions"]["maxWords"] = 5
    else:
        ed["captions"]["maxWords"] = 3

    return ed


def _attach_auto_broll(edit_data: dict, public: Path, preset: dict, transcript: str, duration: float) -> dict:
    """Auto image cards / B-roll.

    Style `limpa` is full-frame talking-head — no automatic inserts (skill +
    references/shortform.md). Images only belong there when the user places
    them by hand. Auto B-roll is for split styles (or an explicit non-limpa edit).
    """
    edit_style = (preset.get("edit") or "limpa").lower().strip()
    if edit_style in ("limpa", "clean", "limpo"):
        edit_data["inserts"] = []
        print("[broll] estilo limpa — sem inserts automáticos", flush=True)
        return edit_data

    mode = (preset.get("brollMode") or "quando_necessario").lower()
    if mode in ("off", "nenhum", "none", "desligado"):
        return edit_data
    # 1) biblioteca local
    try:
        from app.broll_library import pick_for_query  # type: ignore
        from auto_broll import keywords_from_text  # type: ignore

        kws = keywords_from_text(transcript, limit=3)
        query = " ".join(kws) if kws else "produto"
        local = pick_for_query(query, limit=2)
        if local:
            hook_end = float((edit_data.get("hook") or {}).get("endSec") or 3.0)
            end_card = float((edit_data.get("endCard") or {}).get("lastSec") or 2.5)
            inserts = []
            pexels_dir = public / "pexels"
            pexels_dir.mkdir(parents=True, exist_ok=True)
            usable = max(0.0, duration - hook_end - end_card - 0.4)
            slot = usable / max(1, len(local))
            for i, it in enumerate(local):
                src_path = Path(it["path"])
                if not src_path.exists() or it.get("kind") != "image":
                    continue
                name = f"lib-{src_path.stem[:30]}.jpg"
                dest = pexels_dir / name
                if src_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    shutil.copy2(src_path, dest)
                else:
                    continue
                start = hook_end + 0.3 + i * slot
                end = min(duration - end_card - 0.2, start + min(1.6, max(1.0, slot * 0.55)))
                if end <= start + 0.6:
                    continue
                inserts.append({"src": f"pexels/{name}", "start": round(start, 3), "end": round(end, 3), "local": True})
            if inserts:
                edit_data["inserts"] = inserts
                print(f"[broll] biblioteca local · {len(inserts)} insert(s)", flush=True)
                return edit_data
    except Exception as e:  # noqa: BLE001
        print(f"[warn] broll local: {e}", flush=True)

    try:
        sys.path.insert(0, str(HELPERS))
        from auto_broll import build_auto_inserts  # type: ignore

        hook_end = float((edit_data.get("hook") or {}).get("endSec") or 3.0)
        end_card = float((edit_data.get("endCard") or {}).get("lastSec") or 2.5)
        inserts = build_auto_inserts(
            public_dir=public,
            transcript=transcript,
            duration=duration,
            mode=mode,
            hook_end=hook_end,
            end_card_sec=end_card,
        )
        if inserts:
            edit_data["inserts"] = inserts
    except Exception as e:  # noqa: BLE001
        print(f"[warn] auto broll: {e}", flush=True)
    return edit_data


def _maybe_proxy(cut: Path, edit_dir: Path) -> None:
    if os.environ.get("ATIVAVID_PROXY", "1") in ("0", "false", "False"):
        return
    try:
        sys.path.insert(0, str(HELPERS))
        from make_proxy import make_cut_proxy  # type: ignore

        h = int(os.environ.get("ATIVAVID_PROXY_HEIGHT") or 540)
        enc = os.environ.get("ATIVAVID_ENCODER") or "libx264"
        dest = edit_dir / "cut_proxy.mp4"
        out = make_cut_proxy(cut, dest, height=h, encoder=enc)
        if out:
            print(f"[proxy] {out.name} height={h}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] proxy: {e}", flush=True)


def remux_final(edit_dir: Path, with_music: bool, duration: float) -> Path:
    """Color-convert Remotion render → final.mp4.

    Audio MUST come from the Remotion render ([0:a]): it already mixes voice +
    caption click/scratch + whoosh/flash SFX + soundtrack (when enabled in
    edit-data). Mixing cut.mp4 + trilha here used to strip every ASMR layer.
    ``with_music`` is kept for call-site compatibility / logging only.
    """
    render = edit_dir / "remotion" / "out" / "render.mp4"
    final = edit_dir / "final.mp4"
    _ = with_music  # soundtrack already baked in Remotion when enabled

    vid_chain = (
        "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]"
    )
    fc = f"{vid_chain};[0:a]loudnorm=I=-14:TP=-1:LRA=11[out]"
    try:
        from app.win_process import hide_console_kwargs  # type: ignore
        hide = hide_console_kwargs()
    except Exception:
        hide = {}
    cmd = [
        "ffmpeg", "-y",
        "-i", str(render),
        "-filter_complex", fc,
        "-map", "[vid]", "-map", "[out]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-color_range", "tv",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{duration:.3f}", "-movflags", "+faststart",
        str(final),
    ]

    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **hide
    )
    if proc.returncode != 0:
        raise RuntimeError(f"remux failed:\n{proc.stderr[-3000:]}")
    print("[remux] audio Remotion (voz+SFX+trilha) -> final.mp4", flush=True)
    return final


def _npm_cmd() -> str:
    if os.name == "nt":
        return "npm.cmd"
    return "npm"


def _npx_cmd() -> str:
    if os.name == "nt":
        return "npx.cmd"
    return "npx"



def build_longform_edit_data(cut: Path, preset: dict, duration: float, fps: float, edl_ranges: list[dict]) -> dict:
    """edit-data for assets/longform (16:9) — sem legendas queimadas."""
    try:
        from app.brand_kits import export_preset_info  # type: ignore
        exp = export_preset_info(preset.get("exportPreset") or "youtube")
    except Exception:
        exp = {"width": 1920, "height": 1080, "id": "youtube"}
    try:
        w, h = _display_wh(cut)
        if w >= 640 and h >= 360:
            exp = {**exp, "width": w, "height": h}
    except Exception:
        pass
    accent = preset.get("accent") or "#33e0a3"
    copy = preset.get("endCardCopy") or {}
    name = (copy.get("line1") or "").lstrip("@").split()[0] if copy.get("line1") else "Marca"
    title = (copy.get("line2") or "ATIVAVID").strip() or "YouTube"
    chapters = []
    for r in edl_ranges:
        ch = (r.get("chapter") or "").strip()
        beat = str(r.get("beat") or "").upper()
        if ch:
            chapters.append({"title": ch, "start": float(r.get("start") or 0), "dur": 2.4})
        elif beat in ("HOOK", "COLD", "COLD_OPEN", "INTRO") and not chapters:
            chapters.append({"title": "Abertura", "start": 0.0, "dur": 2.2})
    if not chapters and duration >= 30:
        chapters = [
            {"title": "Abertura", "start": 0.0, "dur": 2.2},
            {"title": "Desenvolvimento", "start": min(duration * 0.25, duration - 5), "dur": 2.2},
            {"title": "Fechamento", "start": max(0.0, duration - 12), "dur": 2.2},
        ]
    lower = [{
        "name": name[:40],
        "title": title[:60],
        "start": min(6.0, max(1.0, duration * 0.08)),
        "dur": 3.5,
    }]
    return {
        "width": int(exp.get("width") or 1920),
        "height": int(exp.get("height") or 1080),
        "fps": float(fps),
        "durationSec": round(duration, 4),
        "accent": accent,
        "exportPreset": "youtube",
        "broll": [],
        "lowerThirds": lower,
        "chapters": chapters,
        "callouts": [],
        "soundtrack": {"enabled": False, "file": "trilha.mp3", "volume": 0.1},
    }


def _inserts_to_longform_broll(edit_data: dict) -> dict:
    """Converte inserts short-form (se houver) para broll[] longform."""
    inserts = edit_data.get("inserts") or []
    if not inserts:
        return edit_data
    broll = list(edit_data.get("broll") or [])
    for it in inserts:
        src = it.get("src") or ""
        if not src:
            continue
        start = float(it.get("start") or 0)
        end = float(it.get("end") or start + 3)
        broll.append({
            "kind": "image",
            "src": src,
            "start": start,
            "dur": max(1.0, end - start),
        })
    edit_data["broll"] = broll
    edit_data.pop("inserts", None)
    return edit_data


def scaffold_remotion(edit_dir: Path, *, track: str = "shortform") -> Path:
    dest = edit_dir / "remotion"
    if dest.exists():
        shutil.rmtree(dest)
    src = LONGFORM if track == "longform" else SHORTFORM
    if not src.exists():
        raise RuntimeError(f"template missing: {src}")
    shutil.copytree(src, dest)
    proc = subprocess.run(
        [_npm_cmd(), "install"],
        cwd=dest,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"npm install failed:\n{proc.stderr[-3000:]}")
    return dest


def run(
    source: Path,
    edit_dir: Path,
    preset: dict,
    language: str = "pt",
    skip_phase2: bool = False,
) -> dict:
    """Run the full pipeline. Returns a result dict; raises NeedsReview on gates."""
    source = source.resolve()
    edit_dir = edit_dir.resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    status: dict = {"status": "processing", "phase": 1, "edit_dir": str(edit_dir)}

    # --- brand gate ---
    elems = preset.get("elements") or {}
    copy = preset.get("endCardCopy") or {}
    if elems.get("endCard", True) and not (
        (copy.get("line1") or "").strip() or (copy.get("line2") or "").strip()
    ):
        raise NeedsReview("missing_brand_copy", "endCardCopy.line1/line2 empty in preset")

    # Format gate — short-form vertical by default; YouTube/16:9 se exportPreset/videoGoal pedir
    w, h = _display_wh(source)
    dur = _ffprobe_duration(source)
    export_id = str(preset.get("exportPreset") or preset.get("videoGoal") or "reels").lower()
    allow_landscape = export_id in ("youtube", "longform", "horizontal", "16:9", "16x9")
    max_dur = 1800 if allow_landscape else 180
    if dur < 3 or dur > max_dur:
        raise NeedsReview("out_of_format", f"duration {dur:.1f}s outside window")
    if w > h * 1.15 and not allow_landscape:
        raise NeedsReview(
            "out_of_format",
            f"source displays as landscape {w}x{h}; use exportPreset=youtube no estilo para 16:9",
        )
    status["format"] = "youtube" if allow_landscape else "reels"
    is_longform = bool(allow_landscape)

    stem = source.stem
    source_key = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:32] or "SRC"

    print(f"[1/9] transcribe {source.name}")
    set_stage(edit_dir, "transcribing", "Transcrevendo o áudio…", 12)
    _helper("transcribe.py", str(source), "--edit-dir", str(edit_dir), "--language", language)
    _helper("pack_transcripts.py", "--edit-dir", str(edit_dir))
    # EDL source_key may differ from video.stem (accents/spaces) — alias so
    # captions_for_remotion EDL remap finds the words.
    stem_tr = edit_dir / "transcripts" / f"{stem}.json"
    key_tr = edit_dir / "transcripts" / f"{source_key}.json"
    if stem_tr.exists() and stem != source_key and not key_tr.exists():
        try:
            shutil.copy2(stem_tr, key_tr)
        except OSError:
            pass
    spoken = transcript_text(edit_dir, stem)
    if transcript_looks_bad(spoken):
        raise NeedsReview("bad_transcript", spoken[:200] or "(empty)")

    print("[2/9] speech regions + voice + color")
    set_stage(edit_dir, "analyzing", "Analisando fala e áudio…", 22)
    sr = _helper("speech_regions.py", str(source))
    regions = parse_speech_regions(sr.stdout)
    vl = _helper("voice_levels.py", str(source), "--edit-dir", str(edit_dir), "--json")
    voice = json.loads(vl.stdout)
    # Product path: never hard-stop on under-level speech — build_edl_ranges
    # already sizes gain_db from the worst run. Log a warning only.
    low_phrases = [p for p in voice.get("phrases") or [] if p.get("flag") == "LOW"]
    if low_phrases:
        print(f"[warn] {len(low_phrases)} under-level phrase(s) — applying per-range gain_db", flush=True)

    color = json.loads(_helper("detect_color.py", str(source), "--json").stdout)
    # Product 1-click: do NOT hard-stop on low confidence. Empty grade (= Rec.709 /
    # no look) is the safe default when analysis fails; if the detector still
    # proposed a grade string, use it. Agent mode can still surface the warning.
    if color.get("confidence") == "low":
        print(
            f"[warn] color confidence low (profile={color.get('profile')}) — "
            f"continuing with grade={color.get('grade')!r}",
            flush=True,
        )

    # --- IA no centro: transcript + estilo → plano de corte profissional ---
    # Ajustes salvos no editor (preview_edits.json) têm prioridade sobre novo plano IA.
    print("[2b/9] IA avaliando corte (transcrição + estilo)")
    set_stage(edit_dir, "planning", "IA montando o corte…", 35)
    llm_meta: dict = {"ok": False}
    ranges: list[dict] | None = load_preview_edit_ranges(edit_dir, source_key)
    if ranges:
        llm_meta = {"ok": True, "backend": "preview_edits"}
        print(f"[edits] corte do editor · {len(ranges)} takes", flush=True)
        set_stage(edit_dir, "planning", "Aplicando seus ajustes…", 38)
    else:
        try:
            sys.path.insert(0, str(HELPERS))
            from llm_cut_plan import try_plan_cut  # type: ignore

            ranges, llm_meta = try_plan_cut(
                edit_dir=edit_dir,
                source_key=source_key,
                preset=preset,
                regions=regions,
                voice=voice,
                duration_s=dur,
            )
        except Exception as e:  # noqa: BLE001
            llm_meta = {"ok": False, "error": str(e)[:300]}
            ranges = None

        if ranges:
            print(
                f"[ia] corte via {llm_meta.get('backend')} · {len(ranges)} takes"
                + (f" · hook={llm_meta.get('hook')!r}" if llm_meta.get("hook") else ""),
                flush=True,
            )
        else:
            print(
                f"[ia] fallback heurístico ({llm_meta.get('error') or 'sem plano'})",
                flush=True,
            )
            ranges = build_edl_ranges(source_key, regions, voice, spoken, source_dur=dur)

    edl = {
        "version": 1,
        "sources": {source_key: str(source)},
        "grade": color.get("grade") or "",
        "voice_master": True,
        "ranges": ranges,
        "llm": llm_meta,
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")

    print("[3/9] render cut.mp4")
    set_stage(edit_dir, "cutting", "Criando a edição…", 48)
    cut_path = edit_dir / "cut.mp4"
    render_args = [str(edl_path), "-o", str(cut_path), "--no-subtitles", "--voice-master"]
    if is_longform:
        render_args.append("--keep-resolution")
    _helper("render.py", *render_args)
    verify_args = [str(edl_path), str(cut_path), "--json"]
    if is_longform:
        verify_args.extend(["--min-silence", "1.2"])
    verify = _helper("verify_cut.py", *verify_args, check=False)
    vdata = {}
    try:
        vdata = json.loads(verify.stdout)
    except json.JSONDecodeError:
        pass
    if vdata.get("black"):
        raise NeedsReview("black_frames", str(vdata.get("black")))
    status["phase"] = 1
    status["cut"] = str(cut_path)
    status["verify_flags"] = vdata.get("flags", verify.returncode)

    fps_guess = 30 if _ffprobe_fps(cut_path) >= 29.5 else 24
    style_blob = {
        "edit": preset.get("edit"),
        "captions": preset.get("captions"),
        "headline": preset.get("headline"),
        "elements": elems,
    }
    _write_preview_state(
        edit_dir, source.name, phase=1, message="Fase 1 — corte pronto",
        fps=fps_guess, style=style_blob,
    )

    if skip_phase2:
        status["status"] = "cut_ready"
        return status

    # --- Phase 2 ---
    track = "longform" if is_longform else "shortform"
    print(f"[4/9] scaffold Remotion ({track})")
    set_stage(edit_dir, "visuals", "Preparando legendas e visual…", 62)
    remotion = scaffold_remotion(edit_dir, track=track)
    public = remotion / "public"
    # Dense keyframes matter for OffthreadVideo; sparse GOPs from concat fail mid-render.
    sys.path.insert(0, str(HELPERS))
    from remotion_gate import (  # type: ignore
        ensure_seekable_for_remotion,
        offthread_cache_bytes,
        remotion_concurrency,
        remotion_slot,
    )

    fps_for_gop = 30.0 if _ffprobe_fps(cut_path) >= 29.5 else 24.0
    ensure_seekable_for_remotion(cut_path, public / "cut.mp4", fps=fps_for_gop)

    print("[5/9] captions from cut")
    _helper("transcribe.py", str(cut_path), "--edit-dir", str(edit_dir), "--language", language)
    cut_spoken = transcript_text(edit_dir, "cut") or spoken

    fps_raw = _ffprobe_fps(cut_path)
    if is_longform:
        fps = float(fps_raw) if fps_raw > 1 else 30.0
    else:
        fps = 30.0 if fps_raw >= 29.5 else 24.0
        if 23.5 <= fps_raw <= 24.5:
            fps = 24.0
        elif 29.5 <= fps_raw <= 30.5:
            fps = 30.0
    duration = _ffprobe_duration(cut_path)

    if is_longform:
        # YouTube CC (.srt) + chapters — não queima legenda no vídeo
        _helper(
            "captions_srt.py",
            "--transcript", str(edit_dir / "transcripts" / "cut.json"),
            "-o", str(edit_dir / "captions.srt"),
            check=False,
        )
        _helper("chapters.py", str(edit_dir / "edl.json"), "-o", str(edit_dir / "chapters.txt"), check=False)
        (public / "captions.json").write_text("[]", encoding="utf-8")
        (public / "caption-cues.json").write_text("[]", encoding="utf-8")
    else:
        cut_tr = edit_dir / "transcripts" / "cut.json"
        edl_path = edit_dir / "edl.json"
        # Groq/Whisper often stretches OR truncates word times vs the real cut —
        # either breaks full-video karaoke. Prefer EDL remap from the source then.
        use_edl_caps = False
        timing_issue = None
        if cut_tr.exists() and duration > 0:
            try:
                sys.path.insert(0, str(HELPERS))
                from captions_for_remotion import transcript_timing_issue  # type: ignore

                timing_issue = transcript_timing_issue(cut_tr, duration)
                if timing_issue in ("overrun", "underrun", "empty"):
                    use_edl_caps = True
                    print(
                        f"[warn] transcript do cut ({timing_issue}) — "
                        "legendas via EDL (fonte)",
                        flush=True,
                    )
            except Exception as e:  # noqa: BLE001
                print(f"[warn] caption mode check: {e}", flush=True)

        def _write_caps_from_edl() -> None:
            _helper(
                "captions_for_remotion.py",
                str(edl_path),
                "-o", str(public / "captions.json"),
                "--max-sec", f"{duration:.6f}",
            )

        def _write_caps_from_cut() -> None:
            _helper(
                "captions_for_remotion.py",
                "--transcript", str(cut_tr),
                "-o", str(public / "captions.json"),
                "--max-sec", f"{duration:.6f}",
            )

        if use_edl_caps and edl_path.exists():
            _write_caps_from_edl()
        else:
            _write_caps_from_cut()

        # If captions still stop early, force EDL remap once.
        try:
            sys.path.insert(0, str(HELPERS))
            from captions_for_remotion import captions_coverage_ok  # type: ignore

            caps_path = public / "captions.json"
            caps_data = json.loads(caps_path.read_text(encoding="utf-8")) if caps_path.exists() else []
            if duration > 1 and not captions_coverage_ok(caps_data, duration):
                if edl_path.exists() and not use_edl_caps:
                    print(
                        "[warn] legendas cobrem só o começo — regenerando via EDL",
                        flush=True,
                    )
                    _write_caps_from_edl()
                    caps_data = json.loads(caps_path.read_text(encoding="utf-8"))
                if not captions_coverage_ok(caps_data, duration):
                    last = max((c.get("endMs") or 0) for c in caps_data) / 1000 if caps_data else 0
                    print(
                        f"[warn] cobertura de legendas fraca "
                        f"(última palavra {last:.1f}s / cut {duration:.1f}s)",
                        flush=True,
                    )
        except Exception as e:  # noqa: BLE001
            print(f"[warn] caption coverage check: {e}", flush=True)

        cap_style = preset.get("captions") or "karaoke"
        if cap_style == "stacked":
            # Prefer captions.json timings (already clamped / EDL-mapped) over a
            # stretched cut.json so stacked cues stay in sync with the audio.
            _helper(
                "caption_style.py",
                "--captions", str(public / "captions.json"),
                "-o", str(public / "caption-cues.json"),
                "--lang", language,
                "--max-sec", f"{duration:.6f}",
            )
        else:
            cues = public / "caption-cues.json"
            if not cues.exists():
                cues.write_text("[]", encoding="utf-8")

    print("[6/9] segments + edit-data")
    set_stage(edit_dir, "preview", "Preparando preview…", 70)
    if not is_longform:
        write_segments_json(edit_dir, fps)
    edl_ranges = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8")).get("ranges") or []
    if is_longform:
        edit_data = build_longform_edit_data(cut_path, preset, duration, fps, edl_ranges)
        tmp = {"inserts": [], "hook": {"endSec": 3}, "endCard": {"lastSec": 2.5}}
        tmp = _attach_auto_broll(tmp, public, preset, cut_spoken, duration)
        if tmp.get("inserts"):
            edit_data["inserts"] = tmp["inserts"]
            edit_data = _inserts_to_longform_broll(edit_data)
    else:
        hook = hook_lines_from_text(cut_spoken)
        if llm_meta.get("headline"):
            preset = dict(preset)
            preset["aiHeadline"] = llm_meta["headline"]
        edit_data = build_edit_data(cut_path, preset, hook, duration, fps)
        edit_data = _attach_auto_broll(edit_data, public, preset, cut_spoken, duration)
    (public / "edit-data.json").write_text(
        json.dumps(edit_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _maybe_proxy(cut_path, edit_dir)
    if (not is_longform) and elems.get("tracking"):
        _helper("face_track.py", str(cut_path), "-o", str(public / "track.json"), check=False)
        if not (public / "track.json").exists():
            write_neutral_track(public, edit_data)
    elif not is_longform:
        write_neutral_track(public, edit_data)

    music = bool(elems.get("musicAI"))
    if music:
        print("[7/9] soundtrack")
        vibe = (
            "calm cinematic instrumental bed, soft piano and pads, 90 bpm, no vocals"
            if is_longform else
            "upbeat modern brazilian pop instrumental, light guitars and soft drums, "
            "120 bpm, warm confident mood, no vocals"
        )
        _helper(
            "elevenlabs_music.py", vibe,
            "-o", str(public / "trilha.mp3"),
            "--length-sec", str(int(duration) + 2),
            check=False,
        )
        if (public / "trilha.mp3").exists():
            edit_data["soundtrack"]["enabled"] = True
            (public / "edit-data.json").write_text(
                json.dumps(edit_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            music = False
    else:
        print("[7/9] soundtrack skipped")

    print("[8/9] Remotion render")
    set_stage(edit_dir, "rendering", "Renderizando o vídeo final…", 85)
    _helper("check_template_integrity.py", str(remotion), "--track", track)
    (remotion / "out").mkdir(exist_ok=True)
    comp_id = "Longform" if is_longform else "Reels"
    conc = remotion_concurrency()
    cache_b = offthread_cache_bytes()
    with remotion_slot():
        try:
            from app.win_process import hide_console_kwargs  # type: ignore
            hide = hide_console_kwargs()
        except Exception:
            hide = {}
        rend = subprocess.run(
            [
                _npx_cmd(), "remotion", "render", comp_id, "out/render.mp4",
                f"--concurrency={conc}",
                f"--offthreadvideo-cache-size-in-bytes={cache_b}",
            ],
            cwd=remotion,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            **hide,
        )
    if rend.returncode != 0:
        raise RuntimeError(f"remotion render failed:\n{rend.stderr[-4000:]}\n{rend.stdout[-2000:]}")

    print("[9/9] remux final + legenda")
    set_stage(edit_dir, "exporting", "Finalizando exportação…", 95)
    final = remux_final(edit_dir, music, duration)
    if is_longform:
        srt = edit_dir / "captions.srt"
        legenda = srt if srt.exists() else write_legenda(edit_dir, cut_spoken, preset)
        if (edit_dir / "chapters.txt").exists():
            print(f"[chapters] {edit_dir / 'chapters.txt'}", flush=True)
    else:
        legenda = write_legenda(edit_dir, cut_spoken, preset)

    # Score estrutural (não é métrica de viralização)
    try:
        sys.path.insert(0, str(HELPERS))
        from video_score import score_structural  # type: ignore

        edl_ranges = json.loads((edit_dir / "edl.json").read_text(encoding="utf-8")).get("ranges") or []
        score = score_structural(
            duration=duration,
            ranges=edl_ranges,
            has_hook_beat=any(str(r.get("beat") or "").upper() == "HOOK" for r in edl_ranges),
            has_cta=any(str(r.get("beat") or "").upper() == "CTA" for r in edl_ranges),
            transcript_ok=not transcript_looks_bad(cut_spoken),
        )
        (edit_dir / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        score = None
        print(f"[warn] score: {e}", flush=True)

    set_stage(edit_dir, "done", "Pronto", 100)
    _write_preview_state(
        edit_dir, source.name, phase=3, message="Pronto",
        fps=int(fps), style=style_blob,
    )
    (edit_dir / "result.json").write_text(
        json.dumps({
            "status": "done",
            "final": str(final),
            "legenda": str(legenda),
            "durationSec": duration,
            "fps": fps,
            "score": score,
            "llm": llm_meta,
        }, indent=2),
        encoding="utf-8",
    )

    status.update({
        "status": "done",
        "phase": 3,
        "final": str(final),
        "legenda": str(legenda),
        "durationSec": duration,
        "score": score,
    })
    return status


def _write_preview_state(
    edit_dir: Path,
    source_name: str,
    phase: int,
    message: str,
    fps: int,
    style: dict | None = None,
    final_name: str = "final.mp4",
) -> None:
    state: dict = {
        "project": source_name,
        "phase": phase,
        "video": "cut.mp4",
        "edl": "edl.json",
        "fps": fps,
        "message": message,
        "awaitingStyle": False,
    }
    if phase >= 2:
        state["finalVideo"] = final_name
        rem = edit_dir / "remotion" / "public"
        if (rem / "captions.json").exists():
            state["captions"] = "remotion/public/captions.json"
        if (rem / "edit-data.json").exists():
            state["editData"] = "remotion/public/edit-data.json"
    if style:
        state["style"] = style
    (edit_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="ATIVAVID fast-mode headless runner (short-form, single source)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Exit codes:
              0  done (or cut_ready with --skip-phase2)
              2  needs_review (material gate)
              1  hard failure
        """),
    )
    ap.add_argument("source", type=Path, help="source video (vertical short-form)")
    ap.add_argument("--edit-dir", type=Path, required=True, help="output edit/ directory")
    ap.add_argument("--preset", type=Path, default=None, help="path to preset JSON")
    ap.add_argument("--preset-json", default=None, help="inline preset JSON")
    ap.add_argument("--language", default="pt")
    ap.add_argument("--skip-phase2", action="store_true", help="stop after cut.mp4")
    ap.add_argument("--json", action="store_true", help="print result JSON on stdout")
    args = ap.parse_args()

    try:
        from app.ffmpeg_tools import ensure_ffmpeg_on_path

        ensure_ffmpeg_on_path()
    except Exception:
        pass

    if not args.source.exists():
        print(f"not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    preset = load_preset(args.preset, args.preset_json)
    try:
        result = run(
            args.source,
            args.edit_dir,
            preset,
            language=args.language,
            skip_phase2=args.skip_phase2,
        )
    except NeedsReview as e:
        payload = {"status": "needs_review", "reason": e.reason, "detail": e.detail}
        (args.edit_dir.resolve()).mkdir(parents=True, exist_ok=True)
        (args.edit_dir / "result.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"needs_review: {e.reason} — {e.detail}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        payload = {"status": "error", "error": str(e)}
        try:
            args.edit_dir.mkdir(parents=True, exist_ok=True)
            (args.edit_dir / "result.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"done: {result.get('final') or result.get('cut')}")
    sys.exit(0)


if __name__ == "__main__":
    main()
