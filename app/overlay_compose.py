"""Compose OVERLAY (alpha) sobre cut.mp4 + mix de áudio.

Áudio: voz do cut + SFX do render Overlay (se existir) + trilha + loudnorm
em duas passagens. O dim do end card vem do próprio overlay (EndCard com
alpha), não daqui.

Vídeo e áudio são cortados pela timeline canônica (durationInFrames),
não pela duração do container do cut.mp4.

Não altera o caminho FULL. Usado só com experimentalOverlay.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

LOUDNORM_I = -14.0
LOUDNORM_TP = -1.2
LOUDNORM_LRA = 11.0


def _hide() -> dict:
    try:
        from app.win_process import hide_console_kwargs

        return hide_console_kwargs()
    except Exception:
        return {}


def _ffmpeg() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _ffprobe() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin

        return ffprobe_bin()
    except Exception:
        return "ffprobe"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        **_hide(),
    )


def probe_json(path: Path) -> dict[str, Any]:
    r = _run([
        _ffprobe(), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def has_audio(path: Path) -> bool:
    data = probe_json(path)
    return any(s.get("codec_type") == "audio" for s in (data.get("streams") or []))


def count_frames(path: Path) -> int:
    data = probe_json(path)
    st = next((s for s in (data.get("streams") or []) if s.get("codec_type") == "video"), {})
    raw = st.get("nb_frames")
    if raw not in (None, "", "N/A"):
        try:
            n = int(raw)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    r = _run([
        _ffprobe(), "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries", "stream=nb_read_frames",
        "-of", "default=nw=1:nk=1", str(path),
    ])
    try:
        return int((r.stdout or "").strip() or 0)
    except ValueError:
        return 0


def video_info(path: Path) -> dict[str, Any]:
    data = probe_json(path)
    st = next((s for s in (data.get("streams") or []) if s.get("codec_type") == "video"), {})
    fmt = data.get("format") or {}
    fps_s = str(st.get("r_frame_rate") or "0/1")
    n, _, d = fps_s.partition("/")
    try:
        frames = int(st["nb_frames"]) if st.get("nb_frames") not in (None, "N/A") else None
    except (TypeError, ValueError):
        frames = None
    if not frames:
        counted = count_frames(path)
        frames = counted or None
    return {
        "duration": float(fmt.get("duration") or 0),
        "frames": frames,
        "width": int(st.get("width") or 0),
        "height": int(st.get("height") or 0),
        "fps": round(float(n) / float(d or 1), 3) if d else 0.0,
        "codec": str(st.get("codec_name") or ""),
        "pix_fmt": str(st.get("pix_fmt") or ""),
        "bit_rate": int(fmt.get("bit_rate") or st.get("bit_rate") or 0),
        "bytes": int(fmt.get("size") or (path.stat().st_size if path.exists() else 0)),
    }


def _canonical_args(
    *,
    duration_in_frames: int | None,
    fps: float | None,
    duration: float | None,
) -> tuple[int, float, float]:
    from app.timeline import canonical_timeline

    fps_f = float(fps) if fps and float(fps) > 0 else 30.0
    if duration_in_frames and int(duration_in_frames) > 0:
        frames = int(duration_in_frames)
        return frames, fps_f, frames / fps_f
    src = float(duration or 0)
    tl = canonical_timeline(duration_sec=src, fps=fps_f)
    return tl["durationInFrames"], fps_f, tl["durationSec"]


def validate_overlay_alpha(
    path: Path,
    *,
    width: int,
    height: int,
    duration: float | None = None,
    duration_in_frames: int | None = None,
    fps: float | None = None,
) -> dict[str, Any]:
    """Recusa overlay sem alpha real — evita compose preto.

    A duração oficial é em frames (mesma regra do FULL), não a do container.
    """
    frames, fps_f, duration_sec = _canonical_args(
        duration_in_frames=duration_in_frames, fps=fps, duration=duration,
    )
    info = video_info(path)
    pix = info["pix_fmt"]
    has_alpha = any(tok in pix for tok in ("a", "argb", "rgba", "yuva", "gbra"))
    got_frames = int(info["frames"] or 0)
    report = {
        **info,
        "ok": False,
        "hasAlpha": has_alpha,
        "opaque": None,
        "expectedFrames": frames,
        "overlayFrames": got_frames,
    }
    if not has_alpha:
        raise RuntimeError(
            f"OVERLAY_ALPHA_INVALID pix_fmt={pix} codec={info['codec']}"
        )
    if info["width"] != width or info["height"] != height:
        raise RuntimeError(
            f"OVERLAY_SIZE_INVALID {info['width']}x{info['height']} != {width}x{height}"
        )
    if got_frames != frames:
        raise RuntimeError(
            f"OVERLAY_FRAMES_INVALID {got_frames} != {frames}"
        )
    sample = path.parent / "_alpha_sample.png"
    opaque_hits = 0
    sample_frames = [6, max(6, frames // 2), max(6, frames - 12)]
    for idx in sample_frames:
        # -ss antes do -i: o overlay é all-intra (ProRes/VP8), então o seek cai
        # direto no frame alvo em vez de decodificar o arquivo inteiro até lá.
        # Meio frame antes do alvo para o próximo frame decodificado ser o idx.
        seek = max(0.0, (idx - 0.5) / fps_f)
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{seek:.6f}", "-i", str(path),
            "-frames:v", "1", "-pix_fmt", "rgba", str(sample),
        ])
        if sample.exists() and _png_fully_opaque(sample):
            opaque_hits += 1
    if sample.exists():
        sample.unlink(missing_ok=True)
    report["opaque"] = opaque_hits == 3
    if report["opaque"]:
        raise RuntimeError("OVERLAY_ALPHA_OPAQUE — alpha 100% opaco.")
    report["ok"] = True
    print(
        f"OVERLAY_ALPHA_OK codec={info['codec']} pix_fmt={pix} "
        f"{info['width']}x{info['height']} frames={got_frames}/{frames} "
        f"duration={duration_sec:.6f}s",
        flush=True,
    )
    return report


def _png_fully_opaque(path: Path) -> bool:
    try:
        from PIL import Image  # type: ignore

        im = Image.open(path)
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        extrema = im.getextrema()
        return len(extrema) == 4 and extrema[3][0] >= 255
    except Exception:
        return False


def ebur128_summary(path: Path) -> dict[str, float | None]:
    """Integrated / LRA / true peak do Summary do ebur128 (não o I: inicial)."""
    r = _run([
        _ffmpeg(), "-hide_banner", "-i", str(path),
        "-filter_complex", "ebur128=peak=true,volumedetect", "-f", "null", "-",
    ])
    log = r.stderr or ""
    idx = log.rfind("Summary:")
    summary = log[idx:] if idx >= 0 else log

    def _f(pat: str) -> float | None:
        m = re.search(pat, summary, flags=re.S)
        return float(m.group(1)) if m else None

    return {
        "integratedLufs": _f(r"I:\s+([-\d.]+)\s+LUFS"),
        "truePeakDb": _f(r"True peak:\s+Peak:\s+([-\d.]+)\s+dB(?:TP|FS)"),
        "lra": _f(r"LRA:\s+([-\d.]+)\s+LU"),
        "samplePeakDb": _f(r"max_volume:\s+([-\d.]+)\s+dB"),
    }


def measure_loudnorm(
    path: Path,
    *,
    I: float = LOUDNORM_I,
    TP: float = LOUDNORM_TP,
    LRA: float = LOUDNORM_LRA,
) -> dict[str, str] | None:
    """Passagem 1 do loudnorm — medições reais para a passagem 2."""
    r = _run([
        _ffmpeg(), "-y", "-hide_banner", "-nostats",
        "-i", str(path),
        "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json",
        "-vn", "-f", "null", "-",
    ])
    stderr = r.stderr or ""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stderr[start:end + 1])
    except json.JSONDecodeError:
        return None
    needed = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not needed.issubset(data.keys()):
        return None
    return data


def _loudnorm_filter(
    measured: dict[str, str] | None,
    *,
    I: float = LOUDNORM_I,
    TP: float = LOUDNORM_TP,
    LRA: float = LOUDNORM_LRA,
) -> str:
    if not measured:
        return f"loudnorm=I={I}:TP={TP}:LRA={LRA}"
    return (
        f"loudnorm=I={I}:TP={TP}:LRA={LRA}"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        f":linear=true"
    )


def _mix_audio_graph(
    *,
    sfx: bool,
    music: bool,
    trilha_volume: float,
    duration_sec: float,
    fade_out_at: float,
) -> list[str]:
    a_fmt = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    a_len = (
        f"{a_fmt},atrim=0:{duration_sec:.6f},asetpts=PTS-STARTPTS"
    )
    parts = [f"[0:a]{a_len}[voice]"]
    mix_in = ["[voice]"]
    if sfx:
        parts.append(f"[1:a]{a_len}[sfx]")
        mix_in.append("[sfx]")
    if music:
        parts.append(
            f"[2:a]volume={trilha_volume:.4f},"
            f"afade=t=in:st=0:d=0.4,afade=t=out:st={fade_out_at:.3f}:d=1.5,"
            f"{a_len}[music]"
        )
        mix_in.append("[music]")
    if len(mix_in) == 1:
        parts.append("[voice]anull[pre]")
    else:
        parts.append(
            f"{''.join(mix_in)}amix=inputs={len(mix_in)}:duration=first:"
            f"dropout_transition=0:normalize=0[pre]"
        )
    return parts


def compose_overlay(
    cut: Path,
    overlay: Path,
    dest: Path,
    *,
    duration: float | None = None,
    duration_in_frames: int | None = None,
    fps: float | None = None,
    trilha: Path | None = None,
    trilha_volume: float = 0.12,
) -> dict[str, Any]:
    """cut vídeo + overlay alpha; voz + SFX do overlay + trilha + loudnorm 2-pass."""
    from app.render_engine import encode_with_fallback

    frames, fps_f, duration_sec = _canonical_args(
        duration_in_frames=duration_in_frames, fps=fps, duration=duration,
    )
    cut_frames = count_frames(cut)
    print(
        f"COMPOSE_TIMELINE expectedFrames={frames} cutFrames={cut_frames} "
        f"canonicalSec={duration_sec:.6f} fps={fps_f:g}",
        flush=True,
    )

    sfx = has_audio(overlay)
    music = bool(trilha and trilha.exists())
    dec: list[str] = ["-c:v", "libvpx"] if overlay.suffix.lower() == ".webm" else []

    fade_out_at = max(0.0, duration_sec - 1.5)
    if cut_frames and cut_frames < frames:
        pad = frames - cut_frames
        cut_v = f"[0:v]tpad=stop_mode=clone:stop={pad},setpts=PTS-STARTPTS[cutv]"
        print(f"COMPOSE_CUT_PAD {pad} frames (cut {cut_frames} < {frames})", flush=True)
    else:
        cut_v = f"[0:v]trim=end_frame={frames},setpts=PTS-STARTPTS[cutv]"
        if cut_frames and cut_frames > frames:
            print(
                f"COMPOSE_CUT_TRIM {cut_frames - frames} frames "
                f"(cut {cut_frames} > {frames})",
                flush=True,
            )
    ov_v = f"[1:v]trim=end_frame={frames},setpts=PTS-STARTPTS[ov]"
    vid = (
        f"{cut_v};{ov_v};"
        "[cutv][ov]overlay=eof_action=pass:format=auto,"
        "format=yuv420p,"
        "scale=in_range=full:out_range=limited,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]"
    )
    audio_parts = _mix_audio_graph(
        sfx=sfx, music=music, trilha_volume=trilha_volume,
        duration_sec=duration_sec, fade_out_at=fade_out_at,
    )

    inputs = ["-i", str(cut), *dec, "-i", str(overlay)]
    if music:
        inputs += ["-i", str(trilha)]

    prenorm = dest.with_name(dest.stem + "._prenorm.mp4")
    fc_pre = vid + ";" + ";".join(audio_parts)

    def _cmd_pre(name: str, extra: list[str]) -> list[str]:
        return [
            _ffmpeg(), "-y", "-hide_banner", "-nostats",
            *inputs,
            "-filter_complex", fc_pre,
            "-map", "[vid]", "-map", "[pre]",
            "-c:v", name, *extra,
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-frames:v", str(frames),
            "-t", f"{duration_sec:.6f}",
            "-movflags", "+faststart",
            str(prenorm),
        ]

    proc = encode_with_fallback(_cmd_pre, label="overlay_compose_pre")
    if proc.returncode != 0 or not prenorm.exists():
        prenorm.unlink(missing_ok=True)
        raise RuntimeError(f"overlay_compose failed:\n{(proc.stderr or '')[-2000:]}")

    measured = measure_loudnorm(prenorm)
    tp_target = LOUDNORM_TP
    if measured:
        print(
            f"LOUDNORM_PASS1 I={measured['input_i']} TP={measured['input_tp']} "
            f"LRA={measured['input_lra']} offset={measured['target_offset']}",
            flush=True,
        )
    else:
        print("LOUDNORM_PASS1_FAILED fallback=1pass TP=-1.5", flush=True)
        tp_target = -1.5
    ln = _loudnorm_filter(measured, TP=tp_target)
    print(f"LOUDNORM_PASS2 target I={LOUDNORM_I} TP={tp_target} LRA={LOUDNORM_LRA}", flush=True)

    def _cmd_norm(name: str, extra: list[str]) -> list[str]:
        return [
            _ffmpeg(), "-y", "-hide_banner", "-nostats",
            "-i", str(prenorm),
            "-c:v", "copy",
            "-af", ln,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-frames:v", str(frames),
            "-t", f"{duration_sec:.6f}",
            "-movflags", "+faststart",
            str(dest),
        ]

    # encode_with_fallback espera um encoder de vídeo; pass 2 é copy.
    proc2 = _run(_cmd_norm("copy", []))
    if proc2.returncode != 0:
        prenorm.unlink(missing_ok=True)
        raise RuntimeError(f"overlay_loudnorm failed:\n{(proc2.stderr or '')[-2000:]}")
    prenorm.unlink(missing_ok=True)
    return {
        "sfxFromOverlay": sfx,
        "soundtrack": music,
        "out": str(dest),
        "probe": video_info(dest),
        "expectedFrames": frames,
        "cutFrames": cut_frames,
        "canonicalSec": duration_sec,
        "loudnorm": {
            "pass1": measured,
            "targetI": LOUDNORM_I,
            "targetTP": tp_target,
            "targetLRA": LOUDNORM_LRA,
        },
    }
