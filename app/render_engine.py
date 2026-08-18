"""Motor de render inteligente — detecção, probe, fallback, perfil persistido.

Quem precisa de encoder / concurrency / flags Remotion chama daqui.
Não espalha if NVIDIA / QSV / AMF pelo pipeline.

Modos (arquitetura; default AUTO):
  auto     — melhor encoder validado + concurrency segura
  turbo    — GPU se validada; qualidade ainda ok para Reels
  quality  — libx264 mais lento / CRF mais baixo
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from app.win_process import hide_console_kwargs

PROFILE_PATH = Path.home() / "ATIVAVID" / "hardware-profile.json"
REMOTION_PIN = "4.0.482"
# NVENC no encoder interno do Remotion (Windows/Linux) entrou em 4.0.484
# (PR #7733). Em 4.0.482 a flag --hardware-acceleration NÃO acelera H.264
# via NVENC no Windows. Não atualizar ainda — o encode GPU é o FFmpeg
# do ATIVAVID em encode_final, não o Remotion.
REMOTION_NVENC_MIN = "4.0.484"

# NVIDIA → Intel → AMD → CPU
_H264_ORDER = ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")

_ENCODER_FLAGS: dict[str, list[str]] = {
    "h264_nvenc": [
        "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0",
        "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "15",
    ],
    "h264_qsv": [
        "-preset", "medium", "-global_quality", "23",
        "-pix_fmt", "nv12", "-g", "30", "-keyint_min", "15",
    ],
    "h264_amf": [
        "-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24",
        "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "15",
    ],
    "libx264": [
        "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-g", "30", "-keyint_min", "15",
    ],
}

_QUALITY_FLAGS: dict[str, list[str]] = {
    "h264_nvenc": [
        "-preset", "p5", "-rc", "vbr", "-cq", "18", "-b:v", "0",
        "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "15",
    ],
    "libx264": [
        "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-g", "30", "-keyint_min", "15",
    ],
}

_PROBE_FLAGS: dict[str, list[str]] = {
    "h264_nvenc": ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"],
    "h264_qsv": ["-preset", "medium", "-global_quality", "23", "-pix_fmt", "nv12"],
    "h264_amf": ["-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24", "-pix_fmt", "yuv420p"],
    "libx264": ["-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p"],
}


def _log(msg: str) -> None:
    print(msg, flush=True)


def _ffmpeg() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _ff_version() -> str:
    try:
        r = subprocess.run(
            [_ffmpeg(), "-hide_banner", "-version"],
            capture_output=True, text=True, timeout=8,
            encoding="utf-8", errors="replace",
            **hide_console_kwargs(),
        )
        line = ((r.stdout or "") + (r.stderr or "")).splitlines()
        return (line[0] if line else "")[:120]
    except (OSError, subprocess.SubprocessError):
        return ""


def _listed_encoders() -> set[str]:
    try:
        r = subprocess.run(
            [_ffmpeg(), "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=12,
            encoding="utf-8", errors="replace",
            **hide_console_kwargs(),
        )
        blob = (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return set()
    return {n for n in _H264_ORDER if n in blob}


def probe_encoder(name: str) -> tuple[bool, str]:
    """Encode de 1 frame. True só se o encoder realmente abre."""
    extra = _PROBE_FLAGS.get(name, [])
    # NVENC/QSV/AMF recusam 64x64 (Invalid argument) — probe no tamanho de Reels.
    size = "64x64" if name == "libx264" else "1280x720"
    cmd = [
        _ffmpeg(), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={size}:d=0.04",
        "-frames:v", "1", "-an", "-c:v", name, *extra, "-f", "null", "-",
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=12,
            encoding="utf-8", errors="replace",
            **hide_console_kwargs(),
        )
        err = (r.stderr or "").strip()
        if r.returncode == 0:
            return True, ""
        return False, err[-400:]
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)[:240]


def _bench_encoder(name: str, seconds: float = 3.0) -> float | None:
    """FPS aproximado de um encode curto (lavfi). None se falhar."""
    extra = list(_PROBE_FLAGS.get(name, []))
    fd, tmp = tempfile.mkstemp(suffix=".mp4", prefix="ativavid_bench_")
    os.close(fd)
    out = Path(tmp)
    cmd = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc=size=1280x720:rate=30:duration={seconds:.2f}",
        "-an", "-c:v", name, *extra, str(out),
    ]
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=25,
            encoding="utf-8", errors="replace",
            **hide_console_kwargs(),
        )
        elapsed = max(0.001, time.perf_counter() - t0)
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 200:
            return None
        return round((seconds * 30.0) / elapsed, 1)
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass


def _gpu_vendor(gpus: list[dict[str, Any]]) -> str:
    names = " ".join((g.get("name") or "") for g in gpus).lower()
    if "nvidia" in names:
        return "NVIDIA"
    if "intel" in names:
        return "Intel"
    if "amd" in names or "radeon" in names:
        return "AMD"
    return "unknown"


def _recommend_concurrency(cores: int, ram_gb: float, encoder: str) -> int:
    """Não usa cpu_count() como teto. Chromium come RAM.

    Recalibrado: o divisor antigo de 3.5 GB/worker era um chute conservador
    (o próprio comentário dizia ~1.2 GB); medição real do Chrome do Remotion
    fica em ~2 GB com decode. E cores//2 desperdiçava o ganho documentado no
    remotion.config.ts (183s → 104s usando os cores) — agora deixa 2 threads
    livres para ffmpeg/SO e usa o resto.
    """
    cores = max(1, int(cores or 1))
    ram = float(ram_gb or 8)
    by_ram = max(1, int(ram / 2.0))
    by_cpu = max(1, cores - 2)
    cap = 6
    if encoder != "libx264" and ram >= 16:
        cap = 8
    if ram < 8 or cores <= 2:
        return 1
    return max(1, min(cap, by_ram, by_cpu, cores))


def _fingerprint(machine: dict[str, Any], ff_ver: str) -> str:
    gpus = machine.get("gpus") or []
    gpu = (gpus[0].get("name") if gpus else "") or ""
    drv = (gpus[0].get("driver") if gpus else "") or ""
    try:
        from app.update_check import current_version

        ver = current_version()
    except Exception:
        ver = "0"
    return f"{gpu}|{drv}|{ff_ver}|{ver}|{REMOTION_PIN}"


def load_profile() -> dict[str, Any] | None:
    try:
        raw = json.loads(PROFILE_PATH.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_profile(data: dict[str, Any]) -> dict[str, Any]:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return data


def render_mode() -> str:
    try:
        from app.settings_store import load_settings

        m = str(load_settings().get("renderMode") or "auto").strip().lower()
    except Exception:
        m = "auto"
    return m if m in ("auto", "turbo", "quality") else "auto"


def build_profile(*, force_bench: bool = False) -> dict[str, Any]:
    """Detecta hardware, testa encoders de verdade, opcionalmente faz bench curto."""
    _log("HARDWARE_DETECTION_START")
    from app.system_info import detect_machine

    machine = detect_machine(force=True, probe_encoders=False, quick=False)
    cores = int(machine.get("cores") or 1)
    ram = float(machine.get("ramGb") or 0)
    gpus = list(machine.get("gpus") or [])
    cpu = str(machine.get("cpu") or platform.processor() or "")
    vendor = _gpu_vendor(gpus)
    gpu_name = (gpus[0].get("name") if gpus else "") or ""
    _log(f"CPU: {cpu}")
    _log(f"GPU: {gpu_name or 'nenhuma'}")

    listed = _listed_encoders()
    ff_ver = _ff_version()
    validated: dict[str, bool] = {}
    errors: dict[str, str] = {}
    for name in _H264_ORDER:
        if name == "libx264":
            ok, err = probe_encoder(name)
            validated[name] = ok
            if not ok:
                errors[name] = err
            _log(f"{name.upper()}: {'AVAILABLE' if ok else 'NOT_AVAILABLE'}")
            continue
        if name not in listed:
            validated[name] = False
            _log(f"{name.upper()}: NOT_LISTED")
            continue
        _log(f"ENCODER_ATTEMPT {name}")
        ok, err = probe_encoder(name)
        validated[name] = ok
        if ok:
            _log(f"ENCODER_SUCCESS {name}")
            _log(f"{name.split('_')[-1].upper()}: AVAILABLE")
        else:
            errors[name] = err
            _log(f"ENCODER_FAILED {name} {err[:180]}")
            _log(f"{name.split('_')[-1].upper()}: NOT_AVAILABLE")

    mode = render_mode()
    chosen = "libx264"
    if mode != "quality":
        for name in _H264_ORDER:
            if validated.get(name):
                chosen = name
                break
    else:
        chosen = "libx264" if validated.get("libx264") else next(
            (n for n in _H264_ORDER if validated.get(n)), "libx264"
        )

    bench: dict[str, float] = {}
    prev = load_profile()
    fp = _fingerprint(machine, ff_ver)
    need_bench = force_bench or not prev or prev.get("fingerprint") != fp
    if need_bench:
        _log("BENCHMARK_START")
        for name in _H264_ORDER:
            if not validated.get(name):
                continue
            fps = _bench_encoder(name, 3.0)
            if fps is not None:
                bench[name] = fps
                _log(f"{name}: {fps} FPS")
        if bench and mode != "quality":
            # Bench curto (3s/720p) penaliza init da GPU. Só troca entre
            # hardware encoders; CPU ganha o default só se a GPU estiver quebrada.
            hw = [n for n in ("h264_nvenc", "h264_qsv", "h264_amf") if n in bench]
            if hw:
                best_hw = max(hw, key=lambda n: bench[n])
                if bench[best_hw] >= 8:
                    if best_hw != chosen:
                        _log(f"BENCHMARK_OVERRIDE {chosen} → {best_hw}")
                    chosen = best_hw
                elif bench.get("libx264", 0) > bench[best_hw]:
                    _log(f"BENCHMARK_OVERRIDE {best_hw} lento demais → libx264")
                    chosen = "libx264"
    elif prev:
        bench = dict(prev.get("benchmarkFps") or {})

    conc = _recommend_concurrency(cores, ram, chosen)
    _log(f"SELECTED_ENCODER: {chosen}")
    _log(f"SELECTED_CONCURRENCY: {conc}")

    profile = {
        "os": platform.system(),
        "cpu": cpu,
        "cores": cores,
        "ramGb": ram,
        "gpu": gpu_name,
        "gpuVendor": vendor,
        "gpus": gpus,
        "ffmpegVersion": ff_ver,
        "listedEncoders": sorted(listed),
        "nvenc": bool(validated.get("h264_nvenc")),
        "qsv": bool(validated.get("h264_qsv")),
        "amf": bool(validated.get("h264_amf")),
        "validated": validated,
        "errors": errors,
        "recommendedEncoder": chosen,
        "recommendedConcurrency": conc,
        "benchmarkFps": bench,
        "lastBenchmark": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if need_bench else (prev or {}).get("lastBenchmark"),
        "renderMode": mode,
        "remotionPin": REMOTION_PIN,
        "fingerprint": fp,
        "hardwareAcceleration": "if-possible" if chosen != "libx264" or vendor != "unknown" else "disabled",
    }
    return save_profile(profile)


def ensure_profile(*, force: bool = False) -> dict[str, Any]:
    prev = load_profile()
    if force or prev is None:
        return build_profile(force_bench=force)
    # Não usa detect_machine(quick=True): ele omite GPU e o fingerprint
    # nunca bate — re-probeava NVENC em todo job. Compara só o que é barato.
    try:
        from app.update_check import current_version

        ver = current_version()
    except Exception:
        ver = "0"
    if prev.get("remotionPin") != REMOTION_PIN:
        return build_profile(force_bench=True)
    stored_fp = str(prev.get("fingerprint") or "")
    if not stored_fp.endswith(f"|{ver}|{REMOTION_PIN}"):
        return build_profile(force_bench=False)
    try:
        ff_ver = _ff_version()
        if ff_ver and prev.get("ffmpegVersion") and prev.get("ffmpegVersion") != ff_ver:
            return build_profile(force_bench=True)
    except Exception:
        pass
    return prev


def encoder_args(name: str | None = None, *, mode: str | None = None) -> tuple[str, list[str]]:
    """(encoder, flags após -c:v) para o modo atual."""
    prof = ensure_profile()
    mode = (mode or prof.get("renderMode") or render_mode()).lower()
    enc = name or str(prof.get("recommendedEncoder") or "libx264")
    if mode == "quality":
        flags = _QUALITY_FLAGS.get(enc) or _QUALITY_FLAGS["libx264"]
        if enc != "libx264" and enc not in _QUALITY_FLAGS:
            flags = _ENCODER_FLAGS.get(enc) or _QUALITY_FLAGS["libx264"]
        return enc, list(flags)
    return enc, list(_ENCODER_FLAGS.get(enc) or _ENCODER_FLAGS["libx264"])


def remotion_flags() -> list[str]:
    """Flags extras do `remotion render`.

    4.0.482: só concurrency. Não passa --hardware-acceleration — NVENC
    no encoder interno do Remotion no Windows só existe a partir de 4.0.484,
    e mesmo lá o FFmpeg bundled do Remotion no Windows não traz NVENC.
    O encode GPU do ATIVAVID é encode_final (FFmpeg nosso).
    """
    prof = ensure_profile()
    conc = int(prof.get("recommendedConcurrency") or 2)
    return [f"--concurrency={conc}"]


def encode_with_fallback(
    build_cmd,
    *,
    label: str = "ffmpeg",
) -> subprocess.CompletedProcess:
    """Roda build_cmd(encoder, flags). Se GPU falhar, cai para libx264.

    build_cmd(name, extra) -> list[str] (comando ffmpeg completo).
    Stderr em arquivo, não em RAM: encode longo vomita log. Isso não é o
    deadlock clássico (Popen+PIPE+wait). subprocess.run(capture_output=True)
    usa communicate() e drena o pipe. Arquivo aqui é para não estourar
    memória e preservar o stderr se o worker matar o processo.
    """
    prof = ensure_profile()
    primary, flags = encoder_args()
    chain = [primary]
    if primary != "libx264":
        chain.append("libx264")
    last: subprocess.CompletedProcess | None = None
    last_err = ""
    for enc in chain:
        extra = flags if enc == primary else list(_ENCODER_FLAGS["libx264"] if render_mode() != "quality" else _QUALITY_FLAGS["libx264"])
        if enc == "libx264" and render_mode() == "quality":
            extra = list(_QUALITY_FLAGS["libx264"])
        cmd = build_cmd(enc, extra)
        _log(f"ENCODER_ATTEMPT {label} {enc}")
        out_fd = err_fd = None
        out_name = err_name = ""
        try:
            out_fd, out_name = tempfile.mkstemp(suffix=".out", prefix="ativavid_enc_")
            err_fd, err_name = tempfile.mkstemp(suffix=".err", prefix="ativavid_enc_")
            last = subprocess.run(
                cmd, stdout=out_fd, stderr=err_fd,
                **hide_console_kwargs(),
            )
        except OSError as e:
            last_err = str(e)
            _log(f"ENCODER_FAILED {enc} {e}")
            continue
        finally:
            for fd in (out_fd, err_fd):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            err_txt = ""
            out_txt = ""
            try:
                err_txt = Path(err_name).read_text(encoding="utf-8", errors="replace") if err_name else ""
            except OSError:
                pass
            try:
                out_txt = Path(out_name).read_text(encoding="utf-8", errors="replace") if out_name else ""
            except OSError:
                pass
            for p in (out_name, err_name):
                if p:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except OSError:
                        pass
            if last is not None:
                last.stdout = out_txt
                last.stderr = err_txt
        if last is not None and last.returncode == 0:
            if enc != primary:
                _log(f"ENCODER_FALLBACK {primary} → {enc}")
                _log("FALLBACK_TO_CPU libx264")
                _log(
                    "USER_FALLBACK_CPU A aceleração por GPU não pôde ser utilizada. "
                    "O vídeo continuará sendo processado pela CPU."
                )
            else:
                _log(f"ENCODER_SUCCESS {enc}")
            return last
        last_err = ((last.stderr if last else "") or last_err)[-800:]
        _log(f"ENCODER_FAILED {enc} exit={getattr(last, 'returncode', '?')}")
        if enc != "libx264":
            _log(f"ENCODER_FALLBACK {enc} → libx264")
    if last is None:
        raise RuntimeError(f"{label} falhou: {last_err}")
    return last


def public_profile() -> dict[str, Any]:
    """Resumo para a UI (sem stderr técnico)."""
    p = load_profile() or {}
    enc = p.get("recommendedEncoder") or "libx264"
    accel_on = enc != "libx264"
    bench = p.get("benchmarkFps") or {}
    fps = bench.get(enc)
    return {
        "gpu": p.get("gpu") or "",
        "gpuVendor": p.get("gpuVendor") or "unknown",
        "encoder": enc,
        "acceleration": "on" if accel_on else "off",
        "mode": p.get("renderMode") or "auto",
        "recommendedMode": "turbo" if accel_on else "auto",
        "concurrency": p.get("recommendedConcurrency"),
        "benchmarkFps": fps,
        "lastBenchmark": p.get("lastBenchmark"),
        "nvenc": bool(p.get("nvenc")),
        "qsv": bool(p.get("qsv")),
        "amf": bool(p.get("amf")),
        "friendly": (
            "Aceleração de hardware ativada"
            if accel_on
            else "Renderização pela CPU"
        ),
    }
