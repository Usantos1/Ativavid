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
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "helpers"
# Windows + stdout em pipe = cp1252; prints com "→" derrubam o job.
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from ffprobe_util import first_record, parse_rate  # noqa: E402
import _utf8  # noqa: F401

SHORTFORM = REPO / "assets" / "shortform"
LONGFORM = REPO / "assets" / "longform"
DEFAULT_PRESET = (
    (Path.home() / "ATIVAVID" / "default-style.json")
    if (Path.home() / "ATIVAVID" / "default-style.json").exists()
    else REPO / "assets" / "preview" / "default-style.json"
)

LEAD_S = 0.05
TRAIL_S = 0.12
MIN_SILENCE_DROP = 0.40  # keep speech regions; gaps longer than this are cuts
ZOOM_CYCLE = [1.14, 1.2, 1.12, 1.22, 1.16, 1.1, 1.18]


def _acquire_edit_lock(edit_dir: Path) -> None:
    """Um run_fast por pasta edit/ — evita dois Workers (venv + Python do sistema)."""
    edit_dir.mkdir(parents=True, exist_ok=True)
    lock_path = edit_dir / ".run_fast.lock"
    stale_s = 90 * 60

    def _release() -> None:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                lock_path.unlink()
        except OSError:
            pass

    def _alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes

            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    for _ in range(5):
        try:
            fd = os.open(str(lock_path), flags, 0o644)
            try:
                os.write(fd, str(os.getpid()).encode("utf-8"))
            finally:
                os.close(fd)
            atexit.register(_release)
            return
        except FileExistsError:
            try:
                old = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                old = 0
            try:
                age = max(0.0, time.time() - lock_path.stat().st_mtime)
            except OSError:
                age = 0.0
            if old and old != os.getpid() and _alive(old) and age < stale_s:
                raise RuntimeError(
                    f"run_fast já está editando esta pasta (pid {old}). "
                    "Cancele na Fila ou espere terminar — dois processos no mesmo "
                    "projeto corrompem cut.mp4."
                )
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(0.05)
    raise RuntimeError(f"não consegui o lock de {lock_path}")


class NeedsReview(Exception):
    """Material problem — stop and surface to the user."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


_TIMING: dict[str, float] = {}
_RENDER_META: dict = {}


def _timing_mark(name: str, t0: float) -> float:
    dt = time.perf_counter() - t0
    _TIMING[name] = round(dt, 3)
    print(f"TIMING {name}={dt:.2f}s", flush=True)
    return dt


def write_timing(edit_dir: Path) -> dict:
    """Grava timing.json — medição, não otimização."""
    total = sum(_TIMING.values())
    stages = {
        k: {"sec": v, "pct": round(100.0 * v / total, 1) if total else 0.0}
        for k, v in _TIMING.items()
    }
    render_keys = ("CUT", "REMOTION_GATE", "REMOTION_BUNDLE", "REMOTION_RENDER", "FINAL_ENCODE")
    render_sec = round(sum(_TIMING.get(k, 0.0) for k in render_keys), 3)
    payload = {
        "stages": stages,
        "totalSec": round(total, 3),
        "wholeJobSec": round(total, 3),
        "renderSectionSec": render_sec,
        "otherSec": round(total - render_sec, 3),
    }
    try:
        from app.render_path import classify_render_path  # type: ignore

        ed_path = edit_dir / "remotion" / "public" / "edit-data.json"
        if ed_path.exists():
            ed = json.loads(ed_path.read_text(encoding="utf-8-sig"))
            edl = None
            edl_path = edit_dir / "edl.json"
            if edl_path.exists():
                edl = json.loads(edl_path.read_text(encoding="utf-8-sig"))
            cls = classify_render_path(ed, public=ed_path.parent, edl=edl)
            payload["renderPath"] = cls["path"]
            payload["renderPathReasons"] = cls["reasons"]
            payload["onlySimpleZoomCuts"] = cls.get("onlySimpleZoomCuts")
            payload["onlyZoomFamily"] = cls.get("onlyZoomFamily")
            payload["zoomEngine"] = cls.get("zoomEngine") or "remotion"
            if _RENDER_META.get("zoomEngine"):
                payload["zoomEngine"] = _RENDER_META["zoomEngine"]
            if _RENDER_META.get("renderPath") == "OVERLAY":
                payload["renderPath"] = "OVERLAY"
            if _RENDER_META.get("fallbackReasons"):
                payload["renderPath"] = "FULL"
                extra = list(_RENDER_META["fallbackReasons"])
                payload["renderPathReasons"] = extra + list(cls.get("reasons") or [])
                payload["zoomEngine"] = "remotion"
                payload["fallback"] = extra
            payload["fallbackUsed"] = bool(_RENDER_META.get("fallbackReasons"))
            payload["renderEngine"] = payload.get("renderPath") or "FULL"
            if _RENDER_META.get("fallbackReason"):
                payload["fallbackReason"] = _RENDER_META["fallbackReason"]
            if _RENDER_META.get("overlaySec") is not None:
                payload["overlaySec"] = _RENDER_META["overlaySec"]
            if _RENDER_META.get("composeSec") is not None:
                payload["composeSec"] = _RENDER_META["composeSec"]
            print(
                f"RENDER_PATH {payload['renderPath']} zoomEngine={payload.get('zoomEngine')} "
                f"reasons={','.join(payload['renderPathReasons'])}",
                flush=True,
            )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] classify render path: {e}", flush=True)
    # Por que o caminho rapido nao foi usado. Sem isto, "FULL" no timing.json
    # nao distingue "o video precisa do Remotion" de "outro job estava com a
    # vaga" -- e a segunda hipotese custa 2,4x. Fica FORA do bloco acima de
    # proposito: aquele depende do edit-data.json existir, e este dado e sobre
    # a decisao, nao sobre a classificacao.
    if _RENDER_META.get("overlaySkip"):
        payload["overlaySkip"] = _RENDER_META["overlaySkip"]
    # Qual motor desenhou o overlay, e o motivo quando o proprio ficou de fora.
    # O motor proprio desenha sem abrir o Chrome e e 3,3x mais rapido; ele se
    # desliga sozinho quando encontra recurso de template que nao suporta, e ate
    # aqui isso so aparecia num print do pipeline -- que nao e guardado.
    for campo in ("overlayEngine", "overlayEngineSkip"):
        if _RENDER_META.get(campo):
            payload[campo] = _RENDER_META[campo]
    try:
        (edit_dir / "timing.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass
    print(
        "TIMING_SUMMARY "
        + " ".join(f"{k}={v['sec']:.1f}s({v['pct']}%)" for k, v in stages.items())
        + f" total={payload['totalSec']:.1f}s",
        flush=True,
    )
    return payload


def _canary_validate_overlay(
    final: Path, edit_data: dict, ov_result: dict | None,
) -> str | None:
    """None se o OVERLAY passou; senão o motivo para pausar o canary."""
    from app.overlay_compose import (
        count_frames, garantir_true_peak, video_info,
    )
    from app.timeline import timeline_from_edit_data

    if not final.exists() or final.stat().st_size < 10_000:
        return "FINAL_INVALID"
    tl = timeline_from_edit_data(edit_data)
    expected = int(tl["durationInFrames"])
    got = int(count_frames(final) or 0)
    if got != expected:
        return f"FRAMES {got}!={expected}"
    info = video_info(final)
    exp_sec = float(tl["durationSec"])
    got_sec = float(info.get("duration") or 0)
    if abs(got_sec - exp_sec) > 0.08:
        return f"DURATION {got_sec}!={exp_sec}"
    # Conserta o pico ANTES de julgar por ele. Pico alto e defeito de AUDIO;
    # devolver o video inteiro para o Remotion por causa dele custava, no
    # projeto do usuario, 1657s para entregar -0,9 dBTP no fim — a queda nem
    # consertava o que a motivou. Dos 23 jobs que cairam na semana, 8
    # seguiram fora do limite depois de refeitos (12,6h de maquina).
    au = garantir_true_peak(final)
    _RENDER_META["LUFS"] = au.get("integratedLufs")
    _RENDER_META["truePeak"] = au.get("truePeakDb")
    tp = au.get("truePeakDb")
    if tp is not None and float(tp) > -0.99:
        return f"TRUE_PEAK {tp}>-1.0"
    if ov_result and ov_result.get("tempCleanupDone") is False:
        return "TEMP_CLEANUP_FAILED"
    alpha = (ov_result or {}).get("alpha") or {}
    if alpha:
        if alpha.get("ok") is False or alpha.get("hasAlpha") is False or alpha.get("opaque"):
            return "ALPHA_INVALID"
    return None


def _canary_job_report(edit_dir: Path, *, duration: float, fps: float, final: Path) -> dict:
    """Métricas do motor automático — o cliente não vê FULL/OVERLAY."""
    from app.overlay_compose import count_frames, video_info
    from app.timeline import timeline_from_edit_data

    ed_path = edit_dir / "remotion" / "public" / "edit-data.json"
    edit_data = {}
    if ed_path.exists():
        try:
            edit_data = json.loads(ed_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            edit_data = {}
    tl = timeline_from_edit_data(edit_data) if edit_data else {
        "durationInFrames": 0, "durationSec": float(duration or 0), "fps": float(fps or 30),
    }
    info = video_info(final) if final.exists() else {}
    encoder = ""
    gpu = ""
    try:
        from app.render_engine import public_profile

        pub = public_profile() or {}
        encoder = str(pub.get("encoder") or "")
        gpu = str(pub.get("gpu") or "")
    except Exception:
        encoder = ""
        gpu = ""
    whole = round(sum(_TIMING.values()), 3)
    gain = None
    raw_base = (os.environ.get("ATIVAVID_CANARY_FULL_BASELINE_SEC") or "").strip()
    if raw_base:
        try:
            base = float(raw_base)
            if base > 0 and whole > 0:
                gain = round(base - whole, 3)
        except ValueError:
            gain = None
    engine = _RENDER_META.get("renderPath") or "FULL"
    if _RENDER_META.get("fallbackReasons"):
        engine = "FULL"
    remotion_sec = _RENDER_META.get("overlaySec")
    if remotion_sec is None:
        remotion_sec = _TIMING.get("REMOTION_RENDER")
    report = {
        "renderEngine": engine,
        "renderPath": engine,
        "fallbackUsed": bool(_RENDER_META.get("fallbackReasons")),
        "fallbackReason": _RENDER_META.get("fallbackReason"),
        "wholeJobSec": whole,
        "cutSec": _TIMING.get("CUT"),
        "remotionSec": remotion_sec,
        "overlaySec": _RENDER_META.get("overlaySec"),
        "composeSec": _RENDER_META.get("composeSec") or _TIMING.get("FINAL_ENCODE"),
        "expectedFrames": tl.get("durationInFrames"),
        "cutFrames": _RENDER_META.get("cutFrames"),
        "overlayFrames": _RENDER_META.get("overlayFrames"),
        "finalFrames": info.get("frames") or (count_frames(final) if final.exists() else None),
        "expectedDuration": tl.get("durationSec"),
        "finalDuration": info.get("duration"),
        "integratedLUFS": _RENDER_META.get("LUFS"),
        "truePeak": _RENDER_META.get("truePeak"),
        "tempPeakBytes": _RENDER_META.get("tempPeakBytes"),
        "encoder": encoder,
        "gpu": gpu,
        "tempCleanupDone": _RENDER_META.get("tempCleanupDone"),
        "TEMP_CLEANUP_DONE": _RENDER_META.get("tempCleanupDone"),
        "overlayGainVsEstimatedFull": gain,
        "canaryAttempt": None,
        "canaryLimit": 5,
    }
    try:
        from app.overlay_path import overlay_rollout

        rollout = overlay_rollout()
    except Exception:
        rollout = "off"
    report["overlayRollout"] = rollout
    try:
        from app.overlay_canary import load_state, record_canary_job

        st = load_state()
        report["canaryAttempt"] = st.get("canaryAttempt")
        report["canaryLimit"] = st.get("canaryLimit") or 5
    except Exception:
        st = None
        record_canary_job = None  # type: ignore
    if report.get("integratedLUFS") is None and (
        rollout in ("canary", "default") or report["renderPath"] == "OVERLAY"
    ):
        try:
            from app.overlay_compose import ebur128_summary

            au = ebur128_summary(final)
            report["integratedLUFS"] = au.get("integratedLufs")
            report["truePeak"] = au.get("truePeakDb")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] canary audio: {e}", flush=True)
    if record_canary_job:
        try:
            record_canary_job({
                "project": edit_dir.parent.name,
                **{k: report.get(k) for k in (
                    "renderPath", "fallbackUsed", "wholeJobSec", "cutSec",
                    "overlaySec", "composeSec", "expectedFrames", "finalFrames",
                    "integratedLUFS", "truePeak",
                )},
            })
        except Exception:
            pass
    print(
        f"CANARY_JOB path={report['renderPath']} fallback={report['fallbackUsed']} "
        f"frames={report['expectedFrames']}/{report['finalFrames']} "
        f"whole={report['wholeJobSec']}",
        flush=True,
    )
    try:
        from app.render_telemetry import emit

        emit(edit_dir, report)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] render telemetry: {e}", flush=True)
    return report


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
    try:
        from app.win_process import hide_console_kwargs, resolve_python_cmd  # type: ignore
        hide = hide_console_kwargs()
        cmd = [*resolve_python_cmd(REPO), *args]
    except Exception:
        hide = {}
        cmd = ["uv", "run", "python", *args]
    env = os.environ.copy()
    # helpers import _utf8 from the helpers dir
    py_parts = [str(HELPERS), str(REPO)]
    for p in (env.get("PYTHONPATH") or "").split(os.pathsep):
        p = p.strip()
        if p and p not in py_parts:
            py_parts.append(p)
    env["PYTHONPATH"] = os.pathsep.join(py_parts)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        from app.win_process import child_env  # type: ignore
        env = child_env(env)
    except Exception:
        pass
    try:
        from app.ffmpeg_tools import ensure_ffmpeg_on_path  # type: ignore
        vend = ensure_ffmpeg_on_path()
        if vend:
            env["PATH"] = str(vend) + os.pathsep + env.get("PATH", "")
    except Exception:
        pass
    try:
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
    except FileNotFoundError as e:
        raise RuntimeError(
            f"WinError 2 — não achou o executável ({cmd[0]!r}). "
            "Reinstale o ATIVAVID ou: winget install astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS\n"
            f"detalhe: {e}"
        ) from e
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"cmd failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}"
        )
    return proc


# Marcadores que o helper de transcricao imprime e que PRECISAM aparecer no
# log do job. `_uv_python` roda com `capture_output=True`, entao sem este eco
# eles morrem no subprocesso -- e o usuario nunca ve o cache agindo nem a
# guarda descartando texto inventado.
_MARCADORES_TRANSCRICAO = (
    "TRANSCRIPTION ENGINE",
    "TRANSCRIPTION CACHE HIT",
    "PRIMEIRO_USO",
    "Preparando transcri",
    "WHISPER_GUARDA",
    "WHISPER_COMPONENTE_CUDA",
    "WHISPER_ACELERACAO_FALHOU",
    "ELEVENLABS_FALHOU",
    "Whisper backend:",
    # Revisao textual do Gemini sobre o transcript local. As tres linhas sao
    # o unico sinal que sai dela, e as tres tem de aparecer: a que diz que
    # deu certo, a que diz que foi pulada por politica e a que diz que caiu
    # para o Whisper puro. Revisao que falha em silencio vira suspeita de
    # regressao de qualidade sem nada no log para conferir.
    "REVISAO_GEMINI",
    "REVISAO_GEMINI_PULADA",
    "REVISAO_GEMINI_FALHOU",
)


def _ecoar_transcricao(proc: subprocess.CompletedProcess | None) -> None:
    """Repassa so as linhas de marcador. O resto da saida do helper e ruido."""
    if proc is None:
        return
    for fluxo in (getattr(proc, "stdout", "") or "", getattr(proc, "stderr", "") or ""):
        for linha in fluxo.splitlines():
            if any(linha.startswith(m) or m in linha
                   for m in _MARCADORES_TRANSCRICAO):
                print(linha.rstrip(), flush=True)


@lru_cache(maxsize=1)
def _backend_transcricao() -> str:
    """Qual motor transcreve neste job. Decidido em `app/transcricao/modo`.

    Em cache: os tres pontos de chamada tem de usar o MESMO motor no mesmo
    job, senao o transcript da fonte e o do cut sairiam de motores diferentes
    -- com tempos de palavra que nao conversam.
    """
    try:
        from app.transcricao.modo import backend_para_o_pipeline

        escolhido = backend_para_o_pipeline()
    except Exception as e:  # noqa: BLE001
        print(f"TRANSCRICAO_MODO_FALHOU {type(e).__name__}: {str(e)[:120]}",
              flush=True)
        escolhido = "elevenlabs"
    print(f"TRANSCRICAO_BACKEND {escolhido}", flush=True)
    return escolhido


def _helper(name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return _uv_python(str(HELPERS / name), *args, check=check)


def _ffprobe_exe() -> str:
    try:
        from app.ffmpeg_tools import ffprobe_bin  # type: ignore
        return ffprobe_bin()
    except Exception:
        return "ffprobe"


def _ffmpeg_exe() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin  # type: ignore
        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _run_tool(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run with Windows hide + npm/npx via cmd.exe (avoids WinError 2)."""
    try:
        from app.win_process import run_hidden  # type: ignore
        return run_hidden(argv, **kwargs)
    except ImportError:
        return subprocess.run(argv, **kwargs)


def _ffprobe_duration(path: Path) -> float:
    out = _run_tool(
        [
            _ffprobe_exe(), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nokey=1:noprint_wrappers=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out or 0.0)


def _ffprobe_fps(path: Path) -> float:
    out = _run_tool(
        [
            _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=nokey=1:noprint_wrappers=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    # Com stream group (material de camera) o ffprobe repete o bloco e a
    # saida vem com o valor duas vezes. Ler isso como um valor so derrubava
    # o video em producao.
    return parse_rate(first_record(out), default=30.0)


def _ffprobe_wh(path: Path) -> tuple[int, int]:
    cmd = [
        _ffprobe_exe(),
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
    r = _run_tool(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or f"exit {r.returncode}"
        low = err.lower()
        # Cópia interrompida do celular: o MP4/MOV grava o índice (moov) no
        # fim — sem ele o arquivo é irrecuperável e "tentar de novo" nunca
        # resolve. Mensagem tem que mandar recopiar a origem.
        if "moov atom" in low or "invalid data found" in low or "end of file" in low:
            raise NeedsReview(
                "arquivo_corrompido",
                f"{path.name}: {err[:200]}",
            )
        raise RuntimeError(
            f"ffprobe falhou ao ler o vídeo ({path.name}): {err}\n"
            "Confira se o arquivo abre no player e se o FFmpeg está instalado."
        )
    parts = [p for p in first_record(r.stdout).split(",") if p.strip()]
    if len(parts) < 2:
        raise RuntimeError(f"ffprobe não retornou width/height para {path.name}: {r.stdout!r}")
    return int(parts[0]), int(parts[1])


def _ffprobe_rotation(path: Path) -> int:
    """Display-matrix rotation in degrees (0 if none). Phone clips often store
    landscape pixels with ±90 so the *display* is vertical — render.py already
    accounts for this; the format gate must too."""
    try:
        r = _run_tool(
            [
                _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
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
        r = _run_tool(
            [
                _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
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
    # nb_frames from the container index is exact for the ffmpeg-written MP4s
    # this is called on; -count_frames decodes the whole file and is kept only
    # as the fallback for containers that don't carry the count.
    out = _run_tool(
        [
            _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    out = first_record(out)
    if out not in ("", "N/A"):
        try:
            n = int(out)
            if n > 0:
                return n
        except ValueError:
            pass
    out = _run_tool(
        [
            _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries", "stream=nb_read_frames",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    return int(first_record(out) or 0)


def load_preset(path: Path | None, raw: str | None) -> dict:
    if raw:
        return json.loads(raw)
    p = path or DEFAULT_PRESET
    if not p.exists():
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from app.style_defaults import load_shipped_style

        return load_shipped_style()
    return json.loads(p.read_text(encoding="utf-8-sig"))


def resolve_color_grade(color: dict, preset: dict) -> str:
    """LOG/HLG/PQ → grade do detector; Rec.709 → look de marca do preset.

    colorGrade no preset: nome de preset (marca, neutral_punch, none, …),
    filtro ffmpeg cru, ou "auto" (render analisa por segmento).
    """
    detected = str(color.get("grade") or "").strip()
    profile = str(color.get("profile") or "").strip().lower()
    house = str(preset.get("colorGrade") or "marca").strip() or "marca"
    if house.lower() in ("none", "off", "false", "0"):
        house = ""

    # Detector achou expansão LOG — isso tem prioridade (sem ela o flat fica morto).
    logish = profile not in ("", "rec709", "bt709", "normal", "srgb")
    if detected and (logish or detected in ("apple_log", "auto") or "colorlevels" in detected):
        print(
            f"[color] profile={profile or '?'} confidence={color.get('confidence')} "
            f"-> LOG grade={detected!r}",
            flush=True,
        )
        return detected

    if not house:
        print(f"[color] profile={profile or 'rec709'} -> sem look (colorGrade=none)", flush=True)
        return ""

    print(
        f"[color] profile={profile or 'rec709'} confidence={color.get('confidence')} "
        f"-> look de marca={house!r}",
        flush=True,
    )
    return house


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


# Knobs que definem O CORTE (não o visual): se algum mudou, o usuário está
# pedindo um plano novo e o reuso do EDL manual não se aplica.
_CUT_STYLE_KEYS = ("rhythm", "intensity", "editingIntent", "contentType", "speechClean")


def load_manual_edl_ranges(edit_dir: Path, source_key: str, preset: dict) -> list[dict] | None:
    """Reprocesso respeita o corte que o usuário já aplicou no editor.

    Sem isto, um requeue por mudança de headline/estilo replaneja com a IA e
    DESFAZ os cortes manuais (visto em produção: EDL truncado pelo usuário
    voltou ao plano cheio). Reusa o edl.json quando (a) houve edição manual
    antes (preview_edits.applied.json OU corrections.json com edl mexido/
    aplicado — o caminho de quick apply não passa por preview_edits) e
    (b) os knobs de corte não mudaram — mudar ritmo/intensidade/tipo é
    pedido explícito de replanejar."""
    manual = (edit_dir / "preview_edits.applied.json").exists()
    if not manual:
        try:
            corr = json.loads((edit_dir / "corrections.json").read_text(encoding="utf-8-sig"))
            dirty = corr.get("dirty") or {}
            pending = corr.get("pending") or {}
            manual = bool(
                dirty.get("edl")
                or pending.get("edl")
                or corr.get("appliedAt")
            )
        except (OSError, json.JSONDecodeError, AttributeError):
            manual = False
    if not manual:
        return None
    edl_p = edit_dir / "edl.json"
    if not edl_p.exists():
        return None
    try:
        data = json.loads(edl_p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    # Os knobs que geraram ESTE corte moram no proprio edl.json. A versao
    # anterior lia o `preset-used.json` como se fosse a rodada passada — mas o
    # worker o reescreve com o preset ATUAL antes de lancar o run_fast
    # (local_server.py), entao a comparacao era do preset com ele mesmo e a
    # guarda nunca disparava: mudar ritmo/intensidade/tipo e reprocessar
    # mantinha o corte velho calado.
    #
    # EDL sem `cutStyle` e de antes deste campo existir: mantem o corte, que e
    # o comportamento que o usuario ja conhece. Recortar sozinho um projeto
    # antigo seria pior do que nao replanejar.
    congelado = data.get("cutStyle") if isinstance(data, dict) else None
    if isinstance(congelado, dict) and congelado:
        for key in _CUT_STYLE_KEYS:
            if str(congelado.get(key) or "") != str(preset.get(key) or ""):
                mudou = [k for k in _CUT_STYLE_KEYS
                         if str(congelado.get(k) or "") != str(preset.get(k) or "")]
                print(f"[edits] replanejando o corte — mudou: {', '.join(mudou)}",
                      flush=True)
                return None
    raw = data.get("ranges") if isinstance(data, dict) else None
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        src = str(r.get("source") or source_key)
        if src != source_key:
            return None  # multi-take fica fora do reuso
        try:
            start, end = float(r["start"]), float(r["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end - start < 0.05:
            continue
        item = {
            "source": src,
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
    return out or None


def build_edl_ranges(
    source_key: str,
    regions: list[tuple[float, float]],
    voice: dict,
    quote: str,
    source_dur: float | None = None,
    preserve_hook: bool = False,
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

    # Drop leading micro "false starts" only when the job does not protect the hook.
    if not preserve_hook:
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


_WIN_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def headline_delivery_text(edit_data: dict | None, llm_meta: dict | None = None) -> str:
    """Texto da headline na tela — o nome que o cliente vê no arquivo final."""
    hook = (edit_data or {}).get("hook") or {}
    if hook.get("enabled") is not False:
        lines = hook.get("lines") or hook.get("text") or []
        if isinstance(lines, str):
            lines = [lines]
        text = " ".join(str(x).strip() for x in lines if str(x or "").strip())
        if text:
            return text
    for src in (
        (llm_meta or {}).get("headline"),
        (edit_data or {}).get("aiHeadline"),
        (edit_data or {}).get("headline") if isinstance((edit_data or {}).get("headline"), str) else "",
    ):
        text = str(src or "").strip()
        if text and text.lower() not in ("outline", "realce", "card", "misto", "nenhuma"):
            return text
    return ""


def safe_delivery_filename(text: str) -> str:
    s = _WIN_BAD_NAME.sub("", text or "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    if not s or s.upper() in _WIN_RESERVED:
        return "final.mp4"
    return f"{s[:80].rstrip(' .')}.mp4"


def promote_final_headline(
    edit_dir: Path,
    final: Path,
    edit_data: dict | None,
    llm_meta: dict | None = None,
) -> Path:
    """Renomeia final.mp4 para a headline. Se não houver texto, mantém final.mp4."""
    if not final or not final.is_file():
        return final
    dest_name = safe_delivery_filename(headline_delivery_text(edit_data, llm_meta))
    dest = edit_dir / dest_name
    if dest.resolve() == final.resolve():
        return final
    prev_name = ""
    state_p = edit_dir / "state.json"
    if state_p.exists():
        try:
            prev_name = str(json.loads(state_p.read_text(encoding="utf-8")).get("finalVideo") or "")
        except (OSError, json.JSONDecodeError, TypeError):
            prev_name = ""
    try:
        if dest.exists():
            dest.unlink()
        final.replace(dest)
        if prev_name and prev_name not in {dest.name, final.name, "cut.mp4", "base.mp4"}:
            leftover = edit_dir / prev_name
            if leftover.is_file():
                leftover.unlink()
        print(f"[final] {dest.name}", flush=True)
        return dest
    except OSError as e:
        print(f"[warn] rename final: {e}", flush=True)
        return final


def _grab_frame(video: Path, dest: Path, t: float | None = None) -> bool:
    cmd = [_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"]
    if t and t > 0:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", str(video), "-frames:v", "1", "-q:v", "2", str(dest)]
    try:
        _run_tool(cmd, capture_output=True, timeout=40)
    except Exception:
        return False
    return dest.exists() and dest.stat().st_size > 400


def _jpeg_is_dark(jpg: Path) -> bool:
    try:
        from PIL import Image

        im = Image.open(jpg).convert("L").resize((24, 24))
        return (sum(im.getdata()) / 576.0) < 16
    except Exception:
        pass
    try:
        raw = _run_tool(
            [
                _ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                "-i", str(jpg), "-vf", "scale=16:16,format=gray",
                "-f", "rawvideo", "-",
            ],
            capture_output=True, timeout=15,
        )
        data = raw.stdout or b""
        if len(data) >= 16:
            return (sum(data[:256]) / max(1, len(data[:256]))) < 16
    except Exception:
        return False
    return False


def _second_keyframe_time(path: Path) -> float:
    """pts do 2º keyframe do vídeo (0.0 se não houver um nos primeiros ~15s)."""
    try:
        proc = _run_tool(
            [
                _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
                "-read_intervals", "%+15",
                "-show_entries", "packet=pts_time,flags",
                "-of", "csv=p=0", str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.strip().split(",")
            if len(parts) >= 2 and "K" in parts[1]:
                try:
                    t = float(parts[0])
                except ValueError:
                    continue
                if t > 0.01:
                    return t
    except Exception:
        pass
    return 0.0


def _seal_cover_head_splice(final: Path, cover: Path, edit_dir: Path) -> bool:
    """Carimba a capa no frame 0 re-encodando SÓ o primeiro GOP.

    A cauda entra por -c copy a partir do 2º keyframe e o áudio original é
    reaproveitado intacto. O resultado só substitui o final se a contagem de
    frames, a duração E um decode completo sem erros baterem — qualquer falha
    devolve False e o chamador cai no re-encode total (comportamento antigo).
    """
    kf = _second_keyframe_time(final)
    if not (0.1 < kf < 15.0):
        return False
    head = edit_dir / "_seal_head.mp4"
    tail = edit_dir / "_seal_tail.mp4"
    joined = edit_dir / "_seal_join.mp4"
    lst = edit_dir / "_seal_concat.txt"
    work = edit_dir / "_final_cover.mp4"
    tmp = [head, tail, joined, lst, work]
    try:
        want_frames = _count_frames(final)
        want_dur = _ffprobe_duration(final)
        r1 = _run_tool(
            [
                _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(final), "-i", str(cover),
                "-filter_complex", "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]",
                "-map", "[v]", "-an", "-t", f"{kf:.6f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", str(head),
            ],
            capture_output=True, timeout=120,
        )
        r2 = _run_tool(
            [
                _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{kf:.6f}", "-i", str(final),
                "-map", "0:v", "-c:v", "copy", "-an", str(tail),
            ],
            capture_output=True, timeout=60,
        )
        if r1.returncode != 0 or r2.returncode != 0:
            return False
        lst.write_text(
            f"file '{head.resolve()}'\nfile '{tail.resolve()}'\n", encoding="utf-8"
        )
        r3 = _run_tool(
            [
                _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(lst),
                "-c", "copy", str(joined),
            ],
            capture_output=True, timeout=60,
        )
        if r3.returncode != 0 or not joined.is_file():
            return False
        r4 = _run_tool(
            [
                _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(joined), "-i", str(final),
                "-map", "0:v", "-map", "1:a?",
                "-c", "copy", "-movflags", "+faststart", str(work),
            ],
            capture_output=True, timeout=60,
        )
        if r4.returncode != 0 or not work.is_file() or work.stat().st_size < 1000:
            return False
        got_frames = _count_frames(work)
        got_dur = _ffprobe_duration(work)
        if want_frames and got_frames != want_frames:
            print(
                f"[warn] cover splice: frames {got_frames} != {want_frames} — re-encode total",
                flush=True,
            )
            return False
        if want_dur and abs(got_dur - want_dur) > 0.05:
            print(
                f"[warn] cover splice: duração {got_dur:.3f}s != {want_dur:.3f}s — re-encode total",
                flush=True,
            )
            return False
        # A emenda mistura extradata de encoders diferentes; um decode completo
        # sem erros é o que garante que players não vão quebrar depois do corte.
        chk = _run_tool(
            [
                _ffmpeg_exe(), "-v", "error", "-i", str(work), "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=300,
        )
        if chk.returncode != 0 or (chk.stderr or "").strip():
            print("[warn] cover splice: decode com erros — re-encode total", flush=True)
            return False
        work.replace(final)
        return True
    except Exception as e:
        print(f"[warn] cover splice: {e}", flush=True)
        return False
    finally:
        for p in tmp:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def headline_preservada(edit_dir: Path, llm_meta: dict) -> dict:
    """A headline da IA sobrevive ao reprocesso.

    Ela só chega em `llm_meta` quando o planejador roda. Reaproveitar o corte
    — reaplicar do editor, `manual_edl`, modo leve, várias fontes — pula o
    planejador de propósito, e aí o título caía para `hook_lines_from_text`,
    que é literalmente as primeiras palavras da fala.

    Medido nos 147 projetos do usuário: 37 tinham plano ok e nenhuma headline
    (13/13 dos `manual_edl`, 4/4 dos `preview_edits`, 2/2 do modo leve). Num
    vídeo reprocessado três vezes o título foi de "Chip e carregador potente
    na loja" para "Meu filho, você tem chip aí nessa loja?".

    Guarda num arquivo PRÓPRIO em vez de reler o `edit-data.json`: depois de um
    reprocesso ruim o edit-data já carrega a fala crua no hook, e reler dali
    perpetuaria o erro em vez de corrigi-lo.

    Grava ANTES de reler — se fosse ao contrário, um plano novo seria
    sobrescrito pelo antigo e a headline nunca mais mudaria.
    """
    caminho = edit_dir / "headline_ia.json"
    nova = str((llm_meta or {}).get("headline") or "").strip()
    if nova:
        try:
            caminho.write_text(json.dumps(
                {"headline": nova, "backend": (llm_meta or {}).get("backend")},
                ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return llm_meta
    try:
        guardada = str(json.loads(
            caminho.read_text(encoding="utf-8-sig")).get("headline") or "").strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        return llm_meta
    if not guardada:
        return llm_meta
    print(f"[ia] headline reaproveitada do render anterior: {guardada[:60]!r}",
          flush=True)
    fora = dict(llm_meta or {})
    fora["headline"] = guardada
    return fora


def seal_delivery_cover(edit_dir: Path, final: Path) -> Path:
    """Capa = primeiro frame com imagem. Grava cover.jpg, thumb e embute no MP4.

    Instagram/Reels usam o frame 0. Se ele for preto, carimbamos a capa nele
    e anexamos o JPEG no arquivo para a capa ir junto na hora de postar.
    """
    if not final or not final.is_file():
        return final
    cover = edit_dir / "cover.jpg"
    thumb = edit_dir / "thumb.jpg"
    probe = edit_dir / "_cover_try.jpg"
    chosen_t = 0.0
    if _grab_frame(final, probe, None) and _jpeg_is_dark(probe):
        for t in (0.12, 0.28, 0.5, 0.8):
            if _grab_frame(final, probe, t) and not _jpeg_is_dark(probe):
                chosen_t = t
                break
    if not (probe.exists() and probe.stat().st_size > 400):
        return final
    try:
        shutil.copy2(probe, cover)
        probe.unlink(missing_ok=True)
    except OSError:
        return final
    try:
        _run_tool(
            [
                _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(cover), "-vf", "scale=360:-2", "-q:v", "3", str(thumb),
            ],
            capture_output=True, timeout=20,
        )
    except Exception:
        pass

    work = edit_dir / "_final_cover.mp4"
    if chosen_t > 0 and not _seal_cover_head_splice(final, cover, edit_dir):
        # Fallback: re-encode total (comportamento antigo).
        try:
            proc = _run_tool(
                [
                    _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(final), "-i", str(cover),
                    "-filter_complex",
                    "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]",
                    "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", str(work),
                ],
                capture_output=True, timeout=180,
            )
            if proc.returncode == 0 and work.is_file() and work.stat().st_size > 1000:
                work.replace(final)
            elif work.exists():
                work.unlink(missing_ok=True)
        except Exception as e:
            print(f"[warn] cover frame0: {e}", flush=True)
            try:
                work.unlink(missing_ok=True)
            except OSError:
                pass

    tagged = edit_dir / "_final_tagged.mp4"
    try:
        proc = _run_tool(
            [
                _ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(final), "-i", str(cover),
                "-map", "0", "-map", "1",
                "-c", "copy", "-c:v:1", "mjpeg",
                "-disposition:v:1", "attached_pic",
                "-movflags", "+faststart", str(tagged),
            ],
            capture_output=True, timeout=60,
        )
        if proc.returncode == 0 and tagged.is_file() and tagged.stat().st_size > 1000:
            tagged.replace(final)
        elif tagged.exists():
            tagged.unlink(missing_ok=True)
    except Exception as e:
        print(f"[warn] cover attach: {e}", flush=True)
        try:
            tagged.unlink(missing_ok=True)
        except OSError:
            pass
    print(f"[cover] {cover.name} frame={chosen_t:.2f}s", flush=True)
    return final


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
    print(f"[legenda] {'IA' if polished else 'EDL'} -> {path.name} ({len(body)} chars)", flush=True)
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
        # Sub-frame audio drift after loudnorm / J-cut / voice-master can leave
        # the concat a few frames shorter or longer than sum(seg_*_v). Absorb
        # into the last segment so Phase 2 still ships; only huge gaps fail.
        drift = abs(t - real)
        # ~1s @30fps — enough for typical loudnorm -shortest drift on long cuts
        soft = max(30, int(round(fps * 1.0)))
        if drift > soft:
            raise RuntimeError(f"segments sum {t}f != cut.mp4 {real}f")
        print(
            f"[warn] segments sum {t}f vs cut.mp4 {real}f (Δ{real - t}f) — "
            f"ajustando último segmento",
            flush=True,
        )
        cum[-1] = real
        if len(cum) >= 2 and cum[-1] <= cum[-2]:
            # cut shorter than all-but-last: pull frames from earlier segments
            need = cum[-2] - real + 1
            for i in range(len(cum) - 2, 0, -1):
                room = cum[i] - cum[i - 1] - 1
                if room <= 0:
                    continue
                take = min(room, need)
                for j in range(i, len(cum) - 1):
                    cum[j] -= take
                need -= take
                if need <= 0:
                    break
            cum[-1] = real
            if cum[-1] <= cum[-2]:
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
    from app.timeline import canonical_duration_in_frames

    n = canonical_duration_in_frames(edit_data["durationSec"], edit_data["fps"])
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


def compute_camera(preset: dict, n_segs: int) -> dict:
    """Mesmos zooms/pushIn que o Remotion receberia — usado no extract FFmpeg."""
    elems = dict(preset.get("elements") or {})
    intensity = (preset.get("intensity") or "medio").lower()
    if intensity == "sutil":
        elems["zoomAuto"] = bool(elems.get("zoomAuto"))
        zoom_scale = 0.5
    elif intensity == "forte":
        elems["zoomAuto"] = True
        zoom_scale = 1.15
    else:
        zoom_scale = 1.0
    n_segs = max(1, int(n_segs))
    zooms = (ZOOM_CYCLE * ((n_segs // len(ZOOM_CYCLE)) + 1))[:n_segs]
    zooms = [round(1.0 + (z - 1.0) * zoom_scale, 3) for z in zooms]
    if not elems.get("zoomCuts", True) or intensity == "sutil":
        if intensity == "sutil":
            zooms = [round(1.0 + (z - 1.0) * 0.35, 3) for z in zooms]
        if not elems.get("zoomCuts", True):
            zooms = [1.0] * n_segs
    return {
        "zooms": zooms,
        "pushIn": (0.04 if elems.get("zoomAuto", True) else 0.0) * zoom_scale,
        "targetX": 0.5,
        "targetY": 0.4,
    }


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
    cam = compute_camera(preset, n_segs)
    zooms = cam["zooms"]

    hook_enabled = headline != "nenhuma"
    cap_enabled = captions != "nenhuma"
    edit_style_norm = str(preset.get("edit") or "limpa").lower().strip()
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
            "pushIn": cam["pushIn"],
            "targetX": cam["targetX"],
            "targetY": cam["targetY"],
        },
        "hook": {
            "enabled": hook_enabled,
            # "pilula" é barra de contexto, não momento de abertura — fica o
            # vídeo inteiro. Para os demais, "headlineDuration" do preset:
            # curta (janela clássica), media (dobro, teto 8s) ou inteira.
            "endSec": _hook_end_sec(headline, preset, duration),
            "animation": (
                str(preset.get("headlineAnimation") or "padrao").lower()
                if str(preset.get("headlineAnimation") or "").lower() in ("pop", "deslizar")
                else "padrao"
            ),
            "style": headline if hook_enabled else "outline",
            "lines": hook if hook_enabled else ["", ""],
            "accent": accent,
            "logo": None,
            "sign": None,
        },
        "videoLayout": (
            edit_style_norm
            if edit_style_norm in ("limpa", "split", "split2", "moldura", "barra", "desfocado", "degrade")
            else "limpa"
        ),
        "captions": {
            "enabled": cap_enabled,
            "style": captions if cap_enabled else "karaoke",
            "fontSize": 76,
            "maxWords": 3,
            "safeWidth": 720,
            "paddingBottom": 420,
            "windows": [],
        },  # posição/tamanho do preset entram logo abaixo (_apply_caption_geometry)
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
    if ca and captions in ("karaoke", "simples", "serifada", "classica", "bloco", "recorte"):
        ed["captions"]["accent"] = ca
    ea = preset.get("emphasisAccent")
    if ea and captions in ("stacked", "scatter", "impacto"):
        ed["captions"]["emphasisAccent"] = ea
    circ = preset.get("circleAccent")
    if circ and captions == "stacked":
        ed["captions"]["circleAccent"] = circ
    _apply_caption_geometry(ed, preset)
    _apply_brand_fonts(ed, preset)

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

    Quem decide é o `brollMode`, não o layout. O layout `limpa` (quadro cheio,
    o PADRÃO) segue sem inserts enquanto o b-roll está no valor padrão — é o
    talking-head limpo da skill. Mas escolher "Sempre" ou "Raro" é um pedido
    explícito de imagens, e antes isso era engolido em silêncio só porque o
    layout era o padrão: o usuário ligava b-roll e nada aparecia.
    """
    edit_style = (preset.get("edit") or "limpa").lower().strip()
    mode = (preset.get("brollMode") or "quando_necessario").lower().strip()
    if mode in ("off", "nenhum", "none", "desligado"):
        edit_data["inserts"] = []
        print("[broll] desligado no estilo", flush=True)
        return edit_data
    explicit = mode not in ("quando_necessario", "", "auto")
    if edit_style in ("limpa", "clean", "limpo", "moldura", "barra", "desfocado", "degrade") and not explicit:
        edit_data["inserts"] = []
        print("[broll] estilo limpa + b-roll no padrão — sem inserts automáticos", flush=True)
        return edit_data
    if edit_style in ("limpa", "clean", "limpo", "moldura", "barra", "desfocado", "degrade"):
        print(f"[broll] estilo limpa, mas b-roll={mode} pedido — inserts ligados", flush=True)
    # 1) biblioteca local
    try:
        from app.broll_library import pick_for_query  # type: ignore
        from auto_broll import keywords_from_text  # type: ignore

        kws = keywords_from_text(transcript, limit=3)
        query = " ".join(kws) if kws else "produto"
        local = pick_for_query(query, limit=2)
        if local:
            # pilula estica endSec para o vídeo inteiro — para o espaço de b-roll
            # vale a janela clássica de gancho, nunca a persistência da barra.
            hook_end = min(4.0, float((edit_data.get("hook") or {}).get("endSec") or 3.0))
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

        hook_end = min(4.0, float((edit_data.get("hook") or {}).get("endSec") or 3.0))
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


def encode_final(
    edit_dir: Path,
    with_music: bool,
    duration: float,
    duration_in_frames: int | None = None,
    dest: Path | None = None,
) -> Path:
    """Reencode color-convert do render Remotion → final.mp4.

    Não é remux: há reencode de vídeo (NVENC/QSV/AMF/libx264) + loudnorm.
    Audio MUST come from the Remotion render ([0:a]): it already mixes voice +
    caption click/scratch + whoosh/flash SFX + soundtrack (when enabled in
    edit-data). Mixing cut.mp4 + trilha here used to strip every ASMR layer.
    ``with_music`` is kept for call-site compatibility / logging only.
    """
    render = edit_dir / "remotion" / "out" / "render.mp4"
    final = Path(dest) if dest is not None else edit_dir / "final.mp4"
    _ = with_music  # soundtrack already baked in Remotion when enabled

    vid_chain = (
        "[0:v]scale=in_range=full:out_range=limited,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]"
    )
    # TP=-1.5, nao -1.0: o limite de entrega E -1,0, e este loudnorm e de UMA
    # passagem (modo dinamico, menos preciso que as duas do compose). Mirando
    # no proprio limite, os finais do caminho completo sairam em -0,8 e -0,9 —
    # os 2 unicos fora de especificacao entre os 40 finais medidos, os dois
    # deste caminho. `I` segue -14 LUFS: o volume nao muda, so o teto de pico.
    fc = f"{vid_chain};[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[out]"

    def _cmd(enc: str, extra: list[str]) -> list[str]:
        return [
            _ffmpeg_exe(), "-y", "-hide_banner", "-nostats",
            "-i", str(render),
            "-filter_complex", fc,
            "-map", "[vid]", "-map", "[out]",
            "-c:v", enc, *extra,
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            *(["-frames:v", str(int(duration_in_frames))] if duration_in_frames else []),
            "-t", f"{duration:.6f}", "-movflags", "+faststart",
            str(final),
        ]

    t0 = time.perf_counter()
    # Se o Remotion já entregou yuv420p/tv/bt709 (render com --color-space=
    # bt709, medido: sai idêntico ao que a cadeia de conversão produzia), o
    # reencode de vídeo não tem trabalho — copia o stream e processa só o
    # áudio. Falha na cópia cai no reencode antigo.
    proc = None
    try:
        tags = _run_tool(
            [
                _ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt,color_range,color_space",
                "-of", "csv=p=0", str(render),
            ],
            capture_output=True, text=True, timeout=30,
        ).stdout
        tags = first_record(tags).split(",")
        if tags[:3] == ["yuv420p", "tv", "bt709"]:
            print("[final_encode] video ja em bt709/tv -> stream copy", flush=True)
            proc = _run_tool(
                [
                    _ffmpeg_exe(), "-y", "-hide_banner", "-nostats",
                    "-i", str(render),
                    "-filter_complex", "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[out]",
                    "-map", "0:v", "-c:v", "copy",
                    "-map", "[out]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{duration:.6f}", "-movflags", "+faststart",
                    str(final),
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0:
                print("[warn] stream copy falhou — reencode normal", flush=True)
                proc = None
    except Exception:
        proc = None
    if proc is None:
        try:
            from app.render_engine import encode_with_fallback, public_profile  # type: ignore

            pub = public_profile()
            print(
                f"EXPORT_INFO gpu={pub.get('gpu') or '-'} encoder={pub.get('encoder')} "
                f"mode={pub.get('mode')} accel={pub.get('acceleration')}",
                flush=True,
            )
            proc = encode_with_fallback(_cmd, label="final_encode")
        except Exception:
            proc = _run_tool(
                _cmd("libx264", ["-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p"]),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
    if proc.returncode != 0:
        raise RuntimeError(f"final_encode failed:\n{(proc.stderr or '')[-3000:]}")
    elapsed = max(0.001, time.perf_counter() - t0)
    ratio = (float(duration) / elapsed) if duration else 0.0
    print(
        f"FINAL_ENCODE_DONE elapsed={elapsed:.1f}s duration={duration:.1f}s "
        f"renderSpeedRatio={ratio:.2f}x",
        flush=True,
    )
    print("[final_encode] audio Remotion (voz+SFX+trilha) -> final.mp4", flush=True)
    return final


def remux_final(edit_dir: Path, with_music: bool, duration: float) -> Path:
    """Alias legado — a etapa reencoda; use encode_final."""
    return encode_final(edit_dir, with_music, duration)


def _npm_cmd() -> list[str]:
    """Argv prefix for npm (node + npm-cli.js on Windows)."""
    try:
        from app.win_process import resolve_npm_argv  # type: ignore
        return resolve_npm_argv()
    except Exception:
        if os.name == "nt":
            return [shutil.which("npm.cmd") or "npm.cmd"]
        return [shutil.which("npm") or "npm"]


def _remotion_cmd(remotion_dir: Path, *args: str) -> list[str]:
    """Argv for Remotion CLI without npx.cmd."""
    try:
        from app.win_process import resolve_remotion_argv  # type: ignore
        return resolve_remotion_argv(remotion_dir, *args)
    except Exception:
        npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
        return [npx, "remotion", *args]




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


def _clear_dir_windows(dest: Path) -> None:
    """Apaga pasta remotion mesmo com lock residual (retry + kill + rename)."""
    import time

    if not dest.exists():
        return
    # NUNCA passe apelido curto aqui (o nome da pasta, "remotion", o id do
    # job): o matcher é por substring da linha de comando, então um apelido
    # casava com o próprio run_fast — que cita a pasta do projeto nos
    # argumentos — e com os jobs vizinhos rodando em paralelo. O pipeline se
    # matava sozinho a cada reprocessada, mudo, com exit -1.
    try:
        from app.win_process import kill_processes_holding_path  # type: ignore

        kill_processes_holding_path(dest)
    except Exception:
        pass

    for attempt in range(7):
        shutil.rmtree(dest, ignore_errors=True)
        if not dest.exists():
            return
        time.sleep(0.35 * (attempt + 1))
        if attempt in (1, 3):
            try:
                from app.win_process import kill_processes_holding_path  # type: ignore

                kill_processes_holding_path(dest)
            except Exception:
                pass

    # Último recurso: renomeia e deixa lixo pra limpar depois
    junk = dest.with_name(f"remotion_old_{int(time.time())}")
    try:
        dest.rename(junk)
        shutil.rmtree(junk, ignore_errors=True)
    except OSError:
        pass
    if dest.exists():
        raise RuntimeError(
            f"Não deu para limpar {dest} (arquivo em uso). "
            "Cancele a edição desse projeto na Fila, espere 5s e tente de novo."
        )


_CAP_SIZE_SCALE = {"p": 0.85, "m": 1.0, "g": 1.18}
# paddingBottom por posição (quadro de 1920): "baixo" mantém o default de cada
# estilo; centro/alto sobem o bloco. Os offsets de stacked/scatter são frações
# próprias de cada componente, mapeadas para a MESMA altura visual.
_CAP_POS_PADDING = {"centro": 900, "alto": 1330}
_CAP_POS_STACKED = {"baixo": 0.156, "centro": -0.02, "alto": -0.28}
_CAP_POS_SCATTER = {"baixo": 0.72, "centro": 0.5, "alto": 0.3}


def _apply_caption_geometry(ed: dict, preset: dict) -> None:
    """Traduz captionPosition/captionSize nos knobs que cada estilo já lê.

    karaoke lê fontSize/paddingBottom; stacked lê fontScale/stackedOffsetY;
    scatter lê scatterFontSize/scatterOffsetY; os estáticos e o impacto leem
    position/sizeScale (SimpleCaptions/ImpactCaptions).
    """
    cap = ed.get("captions") or {}
    pos = str(preset.get("captionPosition") or "baixo").lower()
    size = str(preset.get("captionSize") or "m").lower()
    scale = _CAP_SIZE_SCALE.get(size, 1.0)
    if scale != 1.0:
        cap["fontSize"] = round(76 * scale)
        cap["fontScale"] = round(scale, 3)
        cap["scatterFontSize"] = round(72 * scale)
        cap["sizeScale"] = round(scale, 3)
    if pos in _CAP_POS_PADDING:
        cap["paddingBottom"] = _CAP_POS_PADDING[pos]
        cap["stackedOffsetY"] = _CAP_POS_STACKED[pos]
        cap["scatterOffsetY"] = _CAP_POS_SCATTER[pos]
    cap["position"] = pos
    ed["captions"] = cap


# IDs do catálogo de fontes do template (assets/shortform/src/fonts.ts).
# Valor fora do catálogo é descartado — o template ignoraria e a UI mentiria.
_FONT_IDS = {"poppins", "inter", "montserrat", "playfair", "lora", "anton", "bebas", "archivo", "arquivo"}


def _hook_end_sec(headline: str, preset: dict, duration: float) -> float:
    """Janela da headline. pilula/inteira = vídeo todo; media = dobro (teto
    8s); curta (default) = fórmula clássica. O espaço do b-roll continua
    usando a janela clássica (clamp min(4.0,…) nos pontos de leitura)."""
    if not duration:
        return 4.0
    dur_pref = str(preset.get("headlineDuration") or "curta").lower().strip()
    if headline == "pilula" or dur_pref in ("inteira", "sempre", "full"):
        return round(duration, 3)
    base = min(4.0, max(1.5, duration * 0.25))
    if dur_pref in ("media", "média", "longa"):
        return round(min(8.0, max(base * 2, 3.0), duration), 3)
    return round(base, 3)


def _apply_brand_fonts(ed: dict, preset: dict) -> None:
    """captionFont/headlineFont do preset → fontFamily no edit-data."""
    cf = str(preset.get("captionFont") or "").strip().lower()
    hf = str(preset.get("headlineFont") or "").strip().lower()
    if cf in _FONT_IDS:
        ed.setdefault("captions", {})["fontFamily"] = cf
    if hf in _FONT_IDS:
        ed.setdefault("hook", {})["fontFamily"] = hf


_MUSIC_VIBES = {
    # A trilha acompanha o TIPO do conteúdo — um vibe fixo dava a mesma música
    # para humor, venda e tutorial (contradizia a própria doc da skill).
    "humor": (
        "playful upbeat brazilian funk-pop instrumental, bouncy percussion, "
        "quirky synth stabs, 124 bpm, fun mischievous mood, no vocals"
    ),
    "sales": (
        "energetic modern pop instrumental, driving beat, bright synths and "
        "claps, 126 bpm, confident urgent mood, no vocals"
    ),
    "ad": (
        "punchy commercial pop instrumental, big drums, rising energy with a "
        "clear final hit, 128 bpm, bold persuasive mood, no vocals"
    ),
    "viral": (
        "hard-hitting brazilian phonk instrumental, heavy 808s, aggressive "
        "cowbell groove, 130 bpm, hype viral energy, no vocals"
    ),
    "educational": (
        "minimal lofi hip-hop instrumental, warm keys and soft beat, 92 bpm, "
        "focused calm mood, no vocals"
    ),
    "review": (
        "modern chillhop instrumental, crisp drums, warm electric piano, "
        "104 bpm, curious upbeat mood, no vocals"
    ),
    "institutional": (
        "elegant corporate instrumental, soft piano, warm pads and light "
        "percussion, 100 bpm, trustworthy inspiring mood, no vocals"
    ),
    "informational": (
        "clean minimal electronic instrumental, light pulse, airy pads, "
        "106 bpm, clear neutral mood, no vocals"
    ),
}
_MUSIC_DEFAULT = (
    "upbeat modern brazilian pop instrumental, light guitars and soft drums, "
    "120 bpm, warm confident mood, no vocals"
)


def _attach_brand_font_file(ed: dict, public) -> None:
    """Fonte própria da marca (id "arquivo"): copia o .ttf/.otf de
    ~/ATIVAVID/Fontes para public/fonts/ e aponta ed["brandFontFile"].
    Sem arquivo na pasta, o id cai fora com aviso — nunca quebra o render.
    É o caminho para fontes licenciadas do usuário (ex.: Integral) sem o
    app redistribuí-las."""
    from pathlib import Path as _P

    uses = [k for k in ("captions", "hook")
            if str((ed.get(k) or {}).get("fontFamily") or "") == "arquivo"]
    if not uses:
        return
    fonts_dir = _P.home() / "ATIVAVID" / "Fontes"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    cand = sorted(
        [f for f in fonts_dir.iterdir()
         if f.is_file() and f.suffix.lower() in (".ttf", ".otf", ".woff2", ".woff")],
        key=lambda f: f.name.lower(),
    )
    if not cand:
        print(f"[warn] fonte da marca: nenhum .ttf/.otf em {fonts_dir} — usando padrão", flush=True)
        for k in uses:
            ed[k].pop("fontFamily", None)
        return
    src = cand[0]
    dest_dir = _P(public) / "fonts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"brand{src.suffix.lower()}"
    shutil.copy2(src, dest)
    ed["brandFontFile"] = f"fonts/{dest.name}"
    print(f"[fonte] {src.name} → {dest.name} (fonte da marca)", flush=True)


def _music_vibe_for(preset: dict, is_longform: bool) -> str:
    if is_longform:
        return "calm cinematic instrumental bed, soft piano and pads, 90 bpm, no vocals"
    try:
        from app.content_type import normalize_content_type

        ct = normalize_content_type(preset.get("contentType")) or ""
    except Exception:
        ct = str(preset.get("contentType") or "").strip().lower()
    return _MUSIC_VIBES.get(ct, _MUSIC_DEFAULT)


def _sync_template_src(template: Path, dest: Path) -> None:
    """Copia o src/ do template embarcado por cima do scaffold reusado.

    CustomGraphics.tsx é o ÚNICO arquivo editável pelo usuário (Hard Rule 11)
    e só entra se estiver faltando — nunca sobrescreve customização.
    """
    src_dir = template / "src"
    dst_dir = dest / "src"
    if not src_dir.is_dir():
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    synced = 0
    for f in src_dir.iterdir():
        if not f.is_file():
            continue
        target = dst_dir / f.name
        if f.name == "CustomGraphics.tsx" and target.exists():
            continue
        if not target.exists() or target.read_bytes() != f.read_bytes():
            shutil.copy2(f, target)
            synced += 1
    if synced:
        print(f"[scaffold] template src sincronizado ({synced} arquivo(s))", flush=True)


def scaffold_remotion(edit_dir: Path, *, track: str = "shortform") -> Path:
    dest = edit_dir / "remotion"
    src = LONGFORM if track == "longform" else SHORTFORM
    if not src.exists():
        raise RuntimeError(f"template missing: {src}")

    # Reusa scaffold saudável — apagar node_modules a cada retry custa minutos
    # e no Windows estourava o pipe do worker ([Errno 22]).
    cli_ok = (dest / "node_modules" / "@remotion" / "cli").is_dir() or (
        dest / "node_modules" / "remotion"
    ).is_dir()
    if dest.exists() and cli_ok:
        print("[scaffold] reusando Remotion existente", flush=True)
        # O template embarcado ganha estilos novos entre versões; o src/ do
        # scaffold é imutável (fora CustomGraphics) e fica para trás — aí o
        # projeto antigo falha a checagem de integridade ou renderiza o estilo
        # errado em silêncio. Sincronizar é barato (poucos KB).
        try:
            _sync_template_src(src, dest)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] sync template src: {e}", flush=True)
        try:
            _seed_remotion_chrome(dest)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] seed chrome: {e}", flush=True)
        return dest

    if dest.exists():
        _clear_dir_windows(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("node_modules"))

    try:
        pkg_path = dest / "package.json"
        pkg = json.loads(pkg_path.read_text(encoding="utf-8-sig"))
        deps = pkg.setdefault("dependencies", {})
        for k in list(deps):
            if k == "remotion" or k.startswith("@remotion/"):
                deps[k] = "4.0.482"
        pkg["overrides"] = {
            "remotion": "4.0.482",
            "@remotion/cli": "4.0.482",
            "@remotion/google-fonts": "4.0.482",
            "@remotion/layout-utils": "4.0.482",
        }
        pkg_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] não deu para pinanar package.json: {e}", flush=True)

    linked = False
    try:
        from remotion_gate import remotion_slot  # type: ignore
        slot_cm = remotion_slot
    except Exception:
        from contextlib import nullcontext

        slot_cm = nullcontext
    try:
        from app.remotion_cache import attach_node_modules  # type: ignore

        with slot_cm():
            linked = attach_node_modules(dest, track, src / "package.json")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] remotion-cache: {e}", flush=True)
        linked = False

    if not linked:
        try:
            from app.win_process import child_env, resolve_npm_argv  # type: ignore
            npm_argv = resolve_npm_argv()
            env = child_env()
        except Exception as e:
            raise RuntimeError(
                f"Node/npm não encontrado no PATH do app. "
                f"Instale: winget install OpenJS.NodeJS.LTS — detalhe: {e}"
            ) from e
        print("[scaffold] npm install (fallback no job)…", flush=True)
        with slot_cm():
            try:
                proc = _run_tool(
                    [*npm_argv, "install", "--no-fund", "--no-audit", "--save-exact"],
                    cwd=dest,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    env=env,
                )
            except FileNotFoundError as e:
                raise RuntimeError(
                    f"Node/npm não encontrado no PATH do app. "
                    f"Instale: winget install OpenJS.NodeJS.LTS — detalhe: {e}"
                ) from e
            except OSError as e:
                raise RuntimeError(f"Falha ao iniciar npm install: {e}") from e
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "")[-3000:]
            raise RuntimeError(f"npm install failed:\n{err}")
    # Reaproveita Chrome Headless já baixado em outro projeto (evita download 110MB falho)
    try:
        _seed_remotion_chrome(dest)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] seed chrome: {e}", flush=True)
    return dest


def _seed_remotion_chrome(dest: Path) -> None:
    """Copia chrome-headless-shell de outro projeto ATIVAVID, se existir."""
    target = dest / "node_modules" / ".remotion" / "chrome-headless-shell"
    exe = target / "win64" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    if exe.exists():
        return
    roots = []
    try:
        roots.append(dest.resolve().parents[2])  # .../Projetos/<job>/edit/remotion → Projetos
    except IndexError:
        pass
    home_proj = Path.home() / "ATIVAVID" / "Projetos"
    e_proj = Path(r"E:\ATIVAVID\Projetos")
    for r in (home_proj, e_proj):
        if r.exists() and r not in roots:
            roots.append(r)
    donor = None
    for root in roots:
        for cand in root.glob("*/edit/remotion/node_modules/.remotion/chrome-headless-shell"):
            dex = cand / "win64" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
            if dex.exists() and cand.resolve() != target.resolve():
                donor = cand
                break
        if donor:
            break
    if not donor:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(donor, target)
    print(f"[scaffold] chrome headless reaproveitado de {donor}", flush=True)


def run(
    source: Path,
    edit_dir: Path,
    preset: dict,
    language: str = "pt",
    skip_phase2: bool = False,
    also: list[Path] | None = None,
) -> dict:
    """Run the full pipeline. Returns a result dict; raises NeedsReview on gates.

    `also`: extra takes no mesmo projeto — um EDL / um cut / um final.
    """
    _TIMING.clear()
    _RENDER_META.clear()
    _t_job = time.perf_counter()
    # Fase-a-fase: sem estas marcas o timing.json não enxergava a metade
    # inicial do job (transcrição/IA/legendas caíam todas em OTHER) e a ETA
    # da Fila chutava. Medição, não otimização.
    _t_phase = time.perf_counter()
    try:
        from app.win_process import refresh_path_env  # type: ignore
        refresh_path_env()
    except Exception:
        pass
    try:
        from app.ffmpeg_tools import ensure_ffmpeg_on_path  # type: ignore
        ensure_ffmpeg_on_path()
    except Exception:
        pass

    sources: list[Path] = [source.resolve()]
    for a in also or []:
        p = Path(a).resolve()
        if p.exists() and p not in sources:
            sources.append(p)

    edit_dir = edit_dir.resolve()
    edit_dir.mkdir(parents=True, exist_ok=True)

    status: dict = {"status": "processing", "phase": 1, "edit_dir": str(edit_dir)}

    # --- brand gate ---
    from app.brand_kits import fill_end_card_copy

    preset = fill_end_card_copy(preset)
    elems = preset.get("elements") or {}
    copy = preset.get("endCardCopy") or {}
    if elems.get("endCard", True) and not (
        (copy.get("line1") or "").strip() or (copy.get("line2") or "").strip()
    ):
        raise NeedsReview("missing_brand_copy", "endCardCopy.line1/line2 empty in preset")

    export_id = str(preset.get("exportPreset") or preset.get("videoGoal") or "reels").lower()
    allow_landscape = export_id in ("youtube", "longform", "horizontal", "16:9", "16x9")
    try:
        from app.editing_intent import load as load_intent, merge_into_preset

        _intent = load_intent(edit_dir)
        if _intent:
            preset = merge_into_preset(preset, _intent)
    except Exception:
        _intent = None
    intent_mode = str((preset or {}).get("editingIntent") or "").lower()
    if intent_mode == "clips":
        max_dur = 7200  # podcast/aula: o job mãe só analisa e divide
    elif allow_landscape:
        max_dur = 1800
    elif intent_mode == "complete":
        max_dur = 1800
    elif intent_mode == "dynamic":
        max_dur = 600
    else:
        max_dur = 180
    is_longform = bool(allow_landscape)
    status["format"] = "youtube" if allow_landscape else "reels"

    sources_map: dict[str, str] = {}
    all_ranges: list[dict] = []
    spoken_parts: list[str] = []
    grade_field = ""
    primary = sources[0]
    used_keys: set[str] = set()
    regions = []
    voice: dict = {}
    dur = 0.0
    spoken = ""
    source_key = "SRC"

    print(f"[1/9] transcribe {len(sources)} take(s)", flush=True)
    set_stage(
        edit_dir,
        "transcribing",
        f"Transcrevendo {len(sources)} take(s)…" if len(sources) > 1 else "Transcrevendo o áudio…",
        12,
    )

    for idx, src in enumerate(sources):
        w, h = _display_wh(src)
        dur_i = _ffprobe_duration(src)
        min_dur = 3.0 if idx == 0 else 0.4
        if dur_i < min_dur or dur_i > max_dur:
            raise NeedsReview("out_of_format", f"{src.name}: duration {dur_i:.1f}s outside window")
        if idx == 0 and w > h * 1.15 and not allow_landscape:
            raise NeedsReview(
                "out_of_format",
                f"{src.name} displays as landscape {w}x{h}; use exportPreset=youtube no estilo para 16:9",
            )

        stem = src.stem
        base_key = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:28] or f"SRC{idx}"
        key = base_key
        n = 2
        while key in used_keys:
            key = f"{base_key}_{n}"
            n += 1
        used_keys.add(key)
        sources_map[key] = str(src)

        set_stage(edit_dir, "transcribing", f"Transcrevendo {src.name} ({idx + 1}/{len(sources)})…", 12 + idx)
        # As quatro análises do take são independentes entre si — transcrição
        # é rede, regiões/voz/cor são CPU. Em paralelo, a fase custa o tempo
        # da mais lenta (quase sempre a transcrição), não a soma das quatro.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as _an_ex:
            # `--backend elevenlabs` explícito, não o `auto` que estava aqui.
            # O `auto` só escolhe o Scribe para fonte acima de 5 min, e NENHUMA
            # fonte do usuário chega perto disso: das 149 medidas no disco dele,
            # a mais longa tem 2,8 min. Resultado, 149 de 149 foram para o Groq
            # — o plano pago de Scribe nunca foi usado no vídeo curto, que é
            # todo o trabalho dele.
            #
            # Não é só qualidade. O Groq gratuito responde 429 sob carga e o
            # cliente espera 5,10,20,40,60,60s por tentativa: e é isso que a
            # fase ANALYZE mostra. Medido por período nos projetos dele, o
            # custo por segundo de fonte foi de 2,27 na manhã de 20/08 (lote
            # grande, muito 429) contra 0,12 na tarde do MESMO dia — 19x de
            # espalhamento sem nada mudar no código.
            #
            # Quem não tem chave do ElevenLabs não é afetado: `transcribe_one`
            # desce para o Groq sozinho quando a chave falta, e agora também
            # quando o Scribe falha em execução.
            _f_tr = _an_ex.submit(
                _helper, "transcribe.py", str(src),
                "--edit-dir", str(edit_dir), "--language", language,
                "--backend", _backend_transcricao(),
            )
            _f_sr = _an_ex.submit(_helper, "speech_regions.py", str(src))
            _f_vl = _an_ex.submit(
                _helper, "voice_levels.py", str(src),
                "--edit-dir", str(edit_dir), "--json",
            )
            _f_color = _an_ex.submit(_helper, "detect_color.py", str(src), "--json")
            _ecoar_transcricao(_f_tr.result())
            sr = _f_sr.result()
            vl = _f_vl.result()
            _color_proc = _f_color.result()
        stem_tr = edit_dir / "transcripts" / f"{stem}.json"
        key_tr = edit_dir / "transcripts" / f"{key}.json"
        if stem_tr.exists() and stem != key and not key_tr.exists():
            try:
                shutil.copy2(stem_tr, key_tr)
            except OSError:
                pass

        spoken_i = transcript_text(edit_dir, stem) or transcript_text(edit_dir, key)
        if transcript_looks_bad(spoken_i):
            if idx == 0:
                raise NeedsReview("bad_transcript", f"{src.name}: {spoken_i[:200] or '(empty)'}")
            print(f"[warn] {src.name}: sem fala — take extra, seguindo", flush=True)
            spoken_i = ""
        spoken_parts.append(spoken_i)

        set_stage(edit_dir, "analyzing", f"Analisando {src.name}…", 22)
        regions_i = parse_speech_regions(sr.stdout)
        voice_i = json.loads(vl.stdout)
        low_phrases = [p for p in voice_i.get("phrases") or [] if p.get("flag") == "LOW"]
        if low_phrases:
            print(f"[warn] {src.name}: {len(low_phrases)} under-level phrase(s)", flush=True)

        color = json.loads(_color_proc.stdout)
        if color.get("confidence") == "low":
            print(f"[warn] {src.name}: color confidence low (profile={color.get('profile')})", flush=True)
        g = resolve_color_grade(color, preset)
        if idx == 0:
            grade_field = g
            regions = regions_i
            voice = voice_i
            dur = dur_i
            spoken = spoken_i
            source_key = key

        if len(sources) > 1:
            try:
                all_ranges.extend(build_edl_ranges(
                    key, regions_i, voice_i, spoken_i, source_dur=dur_i,
                    preserve_hook=bool(preset.get("preserveHook")),
                ))
            except NeedsReview:
                if idx == 0:
                    raise
                all_ranges.append({
                    "source": key,
                    "start": 0.0,
                    "end": round(dur_i, 3),
                    "beat": "CTA",
                    "quote": "",
                    "reason": "take extra sem fala",
                })

    _helper("pack_transcripts.py", "--edit-dir", str(edit_dir))
    cut_spoken_join = "\n".join(spoken_parts).strip()

    _timing_mark("ANALYZE", _t_phase)  # probes + transcrição + regiões/voz/cor
    _t_phase = time.perf_counter()

    if intent_mode == "clips":
        # Job mãe: só divide. O Worker materializa um projeto por clipe
        # (preview_edits.json com os ranges) e cada filho roda como job comum.
        print("[clips] dividindo o vídeo em clipes independentes", flush=True)
        set_stage(edit_dir, "planning", "Separando os clipes…", 45)
        packed_p = edit_dir / "takes_packed.md"
        try:
            packed = packed_p.read_text(encoding="utf-8-sig") if packed_p.exists() else spoken
        except OSError:
            packed = spoken
        try:
            from app.llm_session import chat as _clips_chat
            from app.podcast_clips import plan_clips

            clips = plan_clips(
                edit_dir, packed=packed, duration=dur,
                regions=regions, chat_fn=_clips_chat,
            )
        except Exception as e:  # noqa: BLE001
            raise NeedsReview("clips_plan_failed", str(e)[:300])
        _timing_mark("PLAN", _t_phase)
        set_stage(edit_dir, "exporting", f"Criando {len(clips)} clipes na Fila…", 96)
        status["status"] = "clips_planned"
        status["clips"] = len(clips)
        print(f"[clips] {len(clips)} clipes planejados", flush=True)
        return status

    print("[2b/9] montando corte", flush=True)
    set_stage(edit_dir, "planning", "Montando o corte…", 35)
    llm_meta: dict = {"ok": False}
    ranges: list[dict] | None = None

    ranges = load_preview_edit_ranges(edit_dir, source_key)
    if ranges:
        llm_meta = {"ok": True, "backend": "preview_edits"}
        # Clipe de podcast: o preview_edits do filho carrega a headline do
        # clipe — vira o hook em vez do fallback de primeiras palavras.
        try:
            pe_applied = edit_dir / "preview_edits.applied.json"
            if pe_applied.exists():
                pe_data = json.loads(pe_applied.read_text(encoding="utf-8-sig"))
                pe_hl = str(pe_data.get("headline") or "").strip()
                if pe_hl:
                    llm_meta["headline"] = pe_hl[:80]
        except (OSError, json.JSONDecodeError):
            pass
        print(f"[edits] corte do editor · {len(ranges)} takes", flush=True)
        set_stage(edit_dir, "planning", "Aplicando seus ajustes…", 38)
    elif len(sources) == 1 and (manual := load_manual_edl_ranges(edit_dir, source_key, preset)):
        ranges = manual
        llm_meta = {"ok": True, "backend": "manual_edl"}
        print(f"[edits] mantendo seu corte aplicado · {len(ranges)} takes", flush=True)
        set_stage(edit_dir, "planning", "Mantendo seus cortes…", 38)
    elif str(preset.get("editingIntent") or "").lower() == "light" and len(sources) == 1:
        # Edição leve: corte heurístico local (silêncio/erro), sem chamada de
        # IA — o modo mais rápido e previsível do app. Headline e legenda da
        # Fase 2 seguem normais.
        print("[leve] edição leve — corte heurístico, sem IA", flush=True)
        set_stage(edit_dir, "planning", "Cortando silêncios e erros…", 38)
        ranges = build_edl_ranges(
            source_key, regions, voice, spoken, source_dur=dur,
            preserve_hook=True,
        )
        llm_meta = {"ok": True, "backend": "heuristic_light"}
    elif len(sources) == 1:
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
            ranges = build_edl_ranges(
                source_key, regions, voice, spoken, source_dur=dur,
                preserve_hook=bool(preset.get("preserveHook")),
            )
    else:
        ranges = all_ranges
        llm_meta = {"ok": True, "backend": "multi_take_concat", "takes": len(sources)}
        print(f"[multi] {len(sources)} takes · {len(ranges)} ranges", flush=True)
        spoken = cut_spoken_join

    if not ranges:
        raise NeedsReview("no_speech", "nenhum trecho de fala para cortar")

    if llm_meta.get("backend") not in ("preview_edits", "manual_edl"):
        try:
            from app.editing_intent import guard_ranges

            ranges = guard_ranges(
                ranges,
                preset=preset,
                regions=regions,
                duration_s=dur,
                edit_dir=edit_dir,
                source_stem=primary.stem,
            )
        except Exception:
            pass

    for i, r in enumerate(ranges):
        if str(r.get("beat") or "").upper() in ("HOOK", "CTA", "KEEP"):
            continue
        r["beat"] = "HOOK" if i == 0 else ("CTA" if i == len(ranges) - 1 and len(ranges) > 2 else f"B{i}")

    if not allow_landscape and intent_mode != "complete":
        total_keep = sum(max(0.0, float(r["end"]) - float(r["start"])) for r in ranges)
        if total_keep > max_dur:
            raise NeedsReview(
                "out_of_format",
                f"corte estimado {total_keep:.0f}s acima do limite {max_dur}s — reduza takes",
            )

    edl = {
        "version": 1,
        "sources": sources_map,
        "grade": grade_field,
        "voice_master": True,
        "ranges": ranges,
        "llm": llm_meta,
        # Os knobs que DECIDIRAM este corte, congelados junto com ele. Sem isto
        # nao existe "antes" para comparar: a guarda de replanejamento lia o
        # `preset-used.json`, que o worker reescreve com o preset ATUAL logo
        # antes de rodar — ela comparava o preset com ele mesmo e nunca
        # disparava.
        "cutStyle": {k: str(preset.get(k) or "") for k in _CUT_STYLE_KEYS},
    }
    edl_path = edit_dir / "edl.json"
    edl_path.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")

    source = primary
    stem = source.stem

    zoom_baked = False
    if (not is_longform):
        try:
            from app.ffmpeg_zoom import attach_to_edl, experimental_on
        except Exception:
            attach_to_edl = None  # type: ignore
            experimental_on = lambda: False  # noqa: E731
        overlay_flag = False
        try:
            from app.overlay_path import overlay_on as overlay_experimental_on
            overlay_flag = overlay_experimental_on()
        except Exception:
            overlay_flag = False
        overlay_candidate = (
            not bool(elems.get("tracking"))
            and str(preset.get("edit") or "").lower() not in ("split", "split2", "moldura", "barra", "desfocado")
        )
        if attach_to_edl and (experimental_on() or (overlay_flag and overlay_candidate)):
            try:
                from app.brand_kits import export_preset_info  # type: ignore
                exp = export_preset_info(preset.get("exportPreset") or preset.get("videoGoal"))
            except Exception:
                exp = {"width": 1080, "height": 1920}
            cam_spec = compute_camera(preset, len(ranges))
            if attach_to_edl(
                edl, cam_spec,
                width=int(exp.get("width") or 1080),
                height=int(exp.get("height") or 1920),
            ):
                edl_path.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")
                zoom_baked = True
                print("FFMPEG_ZOOM extract=on", flush=True)

    # Antecipações: trilha IA (rede, 20-60s) e scaffold Remotion (disco) não
    # dependem do cut — rodam em paralelo com o render do corte e as legendas.
    import threading as _threading

    music_thread = None
    music_tmp = edit_dir / "_trilha_ai.mp3"
    music_tmp.unlink(missing_ok=True)
    music_vibe = _music_vibe_for(preset, is_longform)
    if elems.get("musicAI"):
        # O J-cut e o polimento só ENCURTAM a timeline, então a duração
        # planejada é >= a final e a trilha nunca sai curta (+2s de margem).
        planned_keep = sum(
            max(0.0, float(r.get("end") or 0) - float(r.get("start") or 0))
            for r in ranges
        )
        if planned_keep >= 3:
            def _music_worker() -> None:
                _helper(
                    "elevenlabs_music.py", music_vibe,
                    "-o", str(music_tmp),
                    "--length-sec", str(int(planned_keep) + 2),
                    check=False,
                )

            music_thread = _threading.Thread(
                target=_music_worker, daemon=True, name="music-ai")
            music_thread.start()
            print("[7/9] soundtrack antecipada (em paralelo)", flush=True)

    _scaffold_box: dict = {}

    def _scaffold_worker() -> None:
        try:
            _scaffold_box["remotion"] = scaffold_remotion(
                edit_dir, track="longform" if is_longform else "shortform")
        except Exception as e:  # noqa: BLE001
            _scaffold_box["error"] = e

    scaffold_thread = _threading.Thread(
        target=_scaffold_worker, daemon=True, name="scaffold")
    scaffold_thread.start()

    _timing_mark("PLAN", _t_phase)  # plano LLM + EDL + zoom + antecipações
    print("[3/9] render cut.mp4")
    set_stage(edit_dir, "cutting", "Criando a edição…", 48)
    cut_path = edit_dir / "cut.mp4"
    render_args = [str(edl_path), "-o", str(cut_path), "--no-subtitles", "--voice-master"]
    if is_longform:
        render_args.append("--keep-resolution")
    _t_cut = time.perf_counter()
    try:
        _helper("render.py", *render_args)
    except RuntimeError:
        if not zoom_baked:
            raise
        print("FFMPEG_ZOOM_FAILED", flush=True)
        edl.pop("ffmpegZoom", None)
        edl_path.write_text(json.dumps(edl, indent=2, ensure_ascii=False), encoding="utf-8")
        zoom_baked = False
        _RENDER_META["zoomEngine"] = "remotion"
        _RENDER_META["fallbackReasons"] = ["FFMPEG_ZOOM_FAILED", "FALLBACK_FULL_REMOTION"]
        print("FALLBACK_FULL_REMOTION", flush=True)
        _helper("render.py", *render_args)
    if zoom_baked:
        _RENDER_META["zoomEngine"] = "ffmpeg"
    _timing_mark("CUT", _t_cut)
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
        # Não deixar as antecipações órfãs: o scaffold parcial seria refeito,
        # mas esperar aqui mantém o estado em disco consistente.
        scaffold_thread.join(timeout=120)
        if music_thread is not None:
            music_thread.join(timeout=240)
        status["status"] = "cut_ready"
        return status

    # --- Phase 2 ---
    track = "longform" if is_longform else "shortform"
    print(f"[4/9] scaffold Remotion ({track})")
    set_stage(edit_dir, "visuals", "Preparando legendas e visual…", 62)
    _t_bundle = time.perf_counter()
    scaffold_thread.join(timeout=300)
    remotion = _scaffold_box.get("remotion")
    if remotion is None:
        # Thread falhou ou estourou o tempo — tentativa síncrona (a antiga).
        err = _scaffold_box.get("error")
        if err:
            print(f"[warn] scaffold antecipado falhou: {err} — refazendo", flush=True)
        remotion = scaffold_remotion(edit_dir, track=track)
    _timing_mark("REMOTION_BUNDLE", _t_bundle)
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
    _t_gate = time.perf_counter()
    ensure_seekable_for_remotion(cut_path, public / "cut.mp4", fps=fps_for_gop)
    _timing_mark("REMOTION_GATE", _t_gate)

    print("[5/9] captions from cut")
    _t_phase = time.perf_counter()
    if is_longform:
        # Longform gera .srt/chapters do transcript do corte — precisa transcrever.
        _ecoar_transcricao(_helper(
            "transcribe.py", str(cut_path), "--edit-dir", str(edit_dir),
            "--language", language, "--backend", _backend_transcricao()))
        cut_spoken = transcript_text(edit_dir, "cut") or spoken
    else:
        # Shortform: as palavras da fonte já foram transcritas na fase 1 e o
        # remap pelo EDL não custa rede. Transcrever o corte de novo virou
        # fallback (abaixo). cut_spoken é refinado após gerar as legendas.
        cut_spoken = spoken

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
    try:
        edl_after = json.loads(edl_path.read_text(encoding="utf-8-sig"))
    except Exception:
        edl_after = edl
    from app.timeline import planned_edit_duration_sec

    planned = planned_edit_duration_sec(edl_after)
    if planned:
        print(
            f"TIMELINE_DURATION edit_data_will_use_cut={duration:.6f}s "
            f"edl_planned={planned:.6f}s (informational; Remotion uses edit-data)",
            flush=True,
        )

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
        caps_path = public / "captions.json"
        # ATIVAVID_TRANSCRIBE_CUT=1 força o comportamento antigo (sempre
        # transcrever o corte) — válvula de escape do rollout do remap-first.
        force_cut_tr = os.environ.get("ATIVAVID_TRANSCRIBE_CUT") == "1"

        def _write_caps_from_edl() -> None:
            _helper(
                "captions_for_remotion.py",
                str(edl_path),
                "-o", str(caps_path),
                "--max-sec", f"{duration:.6f}",
            )

        def _write_caps_from_cut() -> None:
            _helper(
                "captions_for_remotion.py",
                "--transcript", str(cut_tr),
                "-o", str(caps_path),
                "--max-sec", f"{duration:.6f}",
            )

        def _caps_data() -> list:
            try:
                return json.loads(caps_path.read_text(encoding="utf-8")) if caps_path.exists() else []
            except Exception:
                return []

        def _coverage_ok() -> bool:
            try:
                sys.path.insert(0, str(HELPERS))
                from captions_for_remotion import captions_coverage_ok  # type: ignore

                data = _caps_data()
                if not data:
                    return False
                return duration <= 1 or captions_coverage_ok(data, duration)
            except Exception as e:  # noqa: BLE001
                print(f"[warn] caption coverage check: {e}", flush=True)
                return True

        # Remap-first: reusa o transcript da fonte (fase 1) remapeado pelo EDL —
        # zero rede. Transcrever o corte é o fallback quando o remap não cobre.
        edl_ok = False
        if edl_path.exists() and not force_cut_tr:
            _write_caps_from_edl()
            edl_ok = _coverage_ok()
            if not edl_ok:
                print("[warn] remap via EDL cobre pouco — transcrevendo o corte", flush=True)

        if edl_ok:
            # cut_spoken deve refletir só as palavras que FICARAM no corte
            # (b-roll, gancho, legenda do post e score dependem disso).
            joined = " ".join(
                str(c.get("text") or "").strip() for c in _caps_data() if c.get("text")
            ).strip()
            if joined:
                cut_spoken = joined
        else:
            _ecoar_transcricao(_helper(
            "transcribe.py", str(cut_path), "--edit-dir", str(edit_dir),
            "--language", language, "--backend", _backend_transcricao()))
            cut_spoken = transcript_text(edit_dir, "cut") or spoken
            # Groq/Whisper often stretches OR truncates word times vs the real
            # cut — either breaks full-video karaoke. Prefer EDL remap then.
            timing_issue = None
            if cut_tr.exists() and duration > 0:
                try:
                    sys.path.insert(0, str(HELPERS))
                    from captions_for_remotion import transcript_timing_issue  # type: ignore

                    timing_issue = transcript_timing_issue(cut_tr, duration)
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] caption mode check: {e}", flush=True)
            if timing_issue in ("overrun", "underrun", "empty") and edl_path.exists():
                print(
                    f"[warn] transcript do cut ({timing_issue}) — "
                    "legendas via EDL (fonte)",
                    flush=True,
                )
                _write_caps_from_edl()
            else:
                _write_caps_from_cut()
            if not _coverage_ok():
                data = _caps_data()
                last = max((c.get("endMs") or 0) for c in data) / 1000 if data else 0
                print(
                    f"[warn] cobertura de legendas fraca "
                    f"(última palavra {last:.1f}s / cut {duration:.1f}s)",
                    flush=True,
                )

        try:
            from app.caption_fixes import apply_caption_fixes, load_stored_fixes

            fixes = list(load_stored_fixes(edit_dir))
            for name in ("preview_edits.json", "preview_edits.applied.json"):
                p = edit_dir / name
                if not p.exists():
                    continue
                data = json.loads(p.read_text(encoding="utf-8-sig"))
                if isinstance(data.get("captionFixes"), list):
                    fixes.extend(data["captionFixes"])
                    break
            if fixes:
                apply_caption_fixes(edit_dir, fixes)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] captionFixes: {e}", flush=True)

        if (preset.get("elements") or {}).get("emojiCaptions"):
            try:
                from app.caption_emoji import apply_to_captions_file

                n_emoji = apply_to_captions_file(caps_path)
                if n_emoji:
                    print(f"[emoji] {n_emoji} emoji(s) nas legendas", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[warn] emoji captions: {e}", flush=True)

        cap_style = preset.get("captions") or "karaoke"
        if cap_style == "stacked":
            # Prefer captions.json timings (already clamped / EDL-mapped) over a
            # stretched cut.json so stacked cues stay in sync with the audio.
            brand_emph = str(preset.get("emphasisWords") or "").strip()
            _helper(
                "caption_style.py",
                "--captions", str(public / "captions.json"),
                "-o", str(public / "caption-cues.json"),
                "--lang", language,
                "--max-sec", f"{duration:.6f}",
                *(["--emphasis", brand_emph] if brand_emph else []),
            )
        else:
            cues = public / "caption-cues.json"
            if not cues.exists():
                cues.write_text("[]", encoding="utf-8")

    _timing_mark("CAPTIONS", _t_phase)
    _t_phase = time.perf_counter()
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
        from app.caption_fixes import apply_replacements_to_text, load_stored_fixes

        _text_fixes = load_stored_fixes(edit_dir)
        cut_spoken = apply_replacements_to_text(cut_spoken, _text_fixes)
        hook = hook_lines_from_text(cut_spoken)
        llm_meta = headline_preservada(edit_dir, llm_meta)
        if llm_meta.get("headline"):
            preset = dict(preset)
            preset["aiHeadline"] = apply_replacements_to_text(str(llm_meta["headline"]), _text_fixes)
        # 3 opções de headline para o seletor do editor: a escolhida + as
        # alternativas da IA (ângulos diferentes), todas com as correções de
        # texto do usuário aplicadas. Arquivo é só dado — não muda o render.
        try:
            opts = []
            for cand in [llm_meta.get("headline"), *(llm_meta.get("headlineAlts") or [])]:
                t = apply_replacements_to_text(str(cand or "").strip(), _text_fixes)
                if t and t not in opts:
                    opts.append(t[:80])
            if opts:
                (edit_dir / "headline_options.json").write_text(
                    json.dumps({"options": opts[:3]}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception as e:  # noqa: BLE001
            print(f"[warn] headline options: {e}", flush=True)
        edit_data = build_edit_data(cut_path, preset, hook, duration, fps)
        if str(preset.get("headline") or "") == "pergunta" and (edit_data.get("hook") or {}).get("enabled"):
            # Duas fases: lines = PERGUNTA (com ? garantido), answerLines =
            # RESPOSTA, e a virada mira o fim do primeiro corte — onde a fala
            # começa a responder.
            hk = edit_data["hook"]
            q = apply_replacements_to_text(
                str(llm_meta.get("headlineQuestion") or "").strip(), _text_fixes)
            if q:
                if not q.endswith("?"):
                    q += "?"
                qw = q.split()
                qm = max(1, len(qw) // 2)
                hk["lines"] = [" ".join(qw[:qm]), " ".join(qw[qm:]) or qw[-1]]
            elif hk.get("lines"):
                ls = [str(x) for x in hk["lines"]]
                if ls and not ls[-1].strip().endswith("?"):
                    ls[-1] = ls[-1].rstrip(".!…") + "?"
                hk["lines"] = ls
            ans = apply_replacements_to_text(
                str(llm_meta.get("headlineAnswer") or "").strip(), _text_fixes)
            if not ans:
                alts = llm_meta.get("headlineAlts") or []
                ans = str(alts[0]).strip() if alts else "A resposta está no vídeo"
            aw = ans.split()
            am = max(1, len(aw) // 2)
            hk["answerLines"] = (
                [" ".join(aw[:am]), " ".join(aw[am:])] if len(aw) > 3 else [ans]
            )
            first_len = 0.0
            try:
                r0 = (edl_ranges or [])[0]
                first_len = max(0.0, float(r0.get("end") or 0) - float(r0.get("start") or 0))
            except (IndexError, TypeError, ValueError, AttributeError):
                first_len = 0.0
            answer_at = max(1.5, min(first_len or 2.5, 6.0, duration * 0.4))
            hk["answerAtSec"] = round(answer_at, 3)
            hk["endSec"] = round(
                min(duration, max(float(hk.get("endSec") or 4.0), answer_at + 3.0)), 3)
        if (preset.get("elements") or {}).get("listCounter"):
            try:
                from app.list_counter import detect_list_markers

                _lc_words = json.loads(caps_path.read_text(encoding="utf-8-sig"))
                _lc = detect_list_markers(_lc_words if isinstance(_lc_words, list) else [])
                if _lc:
                    edit_data["listMarkers"] = _lc
                    print(f"[lista] {len(_lc)} marcadores: "
                          + ", ".join(f"{m['n']}º@{m['atSec']:.1f}s" for m in _lc), flush=True)
                else:
                    print("[lista] contador ligado, mas sem enumeração na fala", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[warn] contador de lista: {e}", flush=True)
        edit_data = _attach_auto_broll(edit_data, public, preset, cut_spoken, duration)
        if zoom_baked:
            from app.ffmpeg_zoom import flatten_remotion_camera

            flatten_remotion_camera(edit_data)
            print("FFMPEG_ZOOM remotion_camera=identity (bake no cut)", flush=True)
        try:
            from app.overlay_path import experimental_on as _ov_on
            if _ov_on() and not zoom_baked:
                print("OVERLAY_FLAG zoom não bakeado — FULL se o classificador exigir", flush=True)
        except Exception:
            pass
    from app.timeline import timeline_from_edit_data

    _tl = timeline_from_edit_data(edit_data)
    print(
        f"CANONICAL_DURATION frames={_tl['durationInFrames']} "
        f"sec={_tl['durationSec']:.6f} sourceDurationSec={_tl['sourceDurationSec']:.6f} "
        f"fps={_tl['fps']:g}",
        flush=True,
    )
    _attach_brand_font_file(edit_data, public)
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

    _timing_mark("SEGMENTS", _t_phase)  # segments.json + broll + proxy + track
    _t_phase = time.perf_counter()
    music = bool(elems.get("musicAI"))
    if music:
        print("[7/9] soundtrack")
        trilha = public / "trilha.mp3"
        if music_thread is not None:
            music_thread.join(timeout=240)
        if music_tmp.exists() and music_tmp.stat().st_size > 1000:
            os.replace(music_tmp, trilha)
        else:
            # Antecipada falhou (rede/planned<3s) — chamada síncrona antiga.
            _helper(
                "elevenlabs_music.py", music_vibe,
                "-o", str(trilha),
                "--length-sec", str(int(duration) + 2),
                check=False,
            )
        if trilha.exists():
            edit_data["soundtrack"]["enabled"] = True
            (public / "edit-data.json").write_text(
                json.dumps(edit_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            music = False
    else:
        music_tmp.unlink(missing_ok=True)
        print("[7/9] soundtrack skipped")

    _timing_mark("MUSIC_WAIT", _t_phase)  # espera da trilha antecipada (0s ideal)
    print("[8/9] Remotion render")
    set_stage(edit_dir, "waiting_render", "Aguardando slot Remotion…", 82)
    _helper("check_template_integrity.py", str(remotion), "--track", track)

    overlay_final = False
    if is_longform:
        _RENDER_META["overlaySkip"] = "longform"
    if (not is_longform):
        try:
            from app.overlay_path import overlay_on, try_overlay_final
        except Exception:
            overlay_on = lambda: False  # noqa: E731
            try_overlay_final = None  # type: ignore
        if not (overlay_on() and try_overlay_final):
            _RENDER_META["overlaySkip"] = "desligado"
        if overlay_on() and try_overlay_final:
            from app.render_path import classify_render_path

            cls = classify_render_path(
                edit_data, public=public, edl=edl, ffmpeg_zoom=zoom_baked,
            )
            if cls["path"] == "FULL":
                print(
                    f"OVERLAY_SKIP ineligible reasons={cls.get('fullReasons')}",
                    flush=True,
                )
                _RENDER_META["overlaySkip"] = (
                    "recurso:" + ",".join(cls.get("fullReasons") or ["?"]))
            else:
                from app.overlay_canary import (
                    begin_overlay_attempt,
                    close_canary_if_done,
                    pause_canary,
                    release_overlay_slot,
                    try_acquire_overlay_slot,
                )

                # Espera a vaga (padrao 180s) em vez de desistir na hora. A
                # vaga fica ocupada por 26% do job, e cair custa +294s contra
                # ~75s de espera media. So depois do teto e que vai para o
                # caminho lento.
                slot = try_acquire_overlay_slot()
                if slot is None:
                    print("OVERLAY_SKIP slot busy — FULL", flush=True)
                    _RENDER_META["overlaySkip"] = "vaga_ocupada_apos_espera"
                else:
                    print("OVERLAY_SLOT acquired", flush=True)
                    from app.overlay_path import overlay_rollout as _ov_roll
                    if _ov_roll() == "canary":
                        begin_overlay_attempt()
                    try:
                        print(f"OVERLAY_PATH reasons={cls.get('overlayReasons')}", flush=True)
                        set_stage(edit_dir, "rendering", "Renderizando overlay…", 85)
                        _t_ov = time.perf_counter()
                        ov_result = try_overlay_final(
                            edit_dir=edit_dir,
                            remotion=remotion,
                            cut=cut_path,
                            edit_data=edit_data,
                            duration=duration,
                            dest=edit_dir / "final.mp4",
                        )
                        _timing_mark("REMOTION_RENDER", _t_ov)
                        bad = _canary_validate_overlay(
                            edit_dir / "final.mp4", edit_data, ov_result,
                        )
                        if bad:
                            raise RuntimeError(bad)
                        _RENDER_META["renderPath"] = "OVERLAY"
                        _RENDER_META["overlayEngine"] = (ov_result or {}).get("engine")
                        _RENDER_META["overlayEngineSkip"] = (ov_result or {}).get("engineSkip")
                        _RENDER_META["overlaySec"] = (ov_result or {}).get("remotionSec")
                        _RENDER_META["composeSec"] = (ov_result or {}).get("composeSec")
                        _RENDER_META["timeline"] = (ov_result or {}).get("timeline")
                        _RENDER_META["tempPeakBytes"] = (ov_result or {}).get("tempPeakBytes")
                        _RENDER_META["cutFrames"] = (ov_result or {}).get("cutFrames")
                        _RENDER_META["overlayFrames"] = (ov_result or {}).get("overlayFrames")
                        _RENDER_META["tempCleanupDone"] = (ov_result or {}).get("tempCleanupDone")
                        overlay_final = True
                    except Exception as e:  # noqa: BLE001
                        print(f"OVERLAY_FAILED {e}", flush=True)
                        _RENDER_META["fallbackReason"] = str(e)
                        _RENDER_META["fallbackReasons"] = (
                            list(_RENDER_META.get("fallbackReasons") or [])
                            + ["OVERLAY_FAILED", "FALLBACK_FULL_REMOTION"]
                        )
                        print("FALLBACK_FULL_REMOTION", flush=True)
                        pause_canary(str(e))
                        overlay_final = False
                    finally:
                        release_overlay_slot(slot)
                        print("OVERLAY_SLOT released", flush=True)
                        close_canary_if_done()

    if overlay_final:
        print("[9/9] overlay já escreveu final.mp4", flush=True)
        _t_enc = time.perf_counter()
        final = edit_dir / "final.mp4"
        _timing_mark("FINAL_ENCODE", _t_enc)
    else:
        (remotion / "out").mkdir(exist_ok=True)
        comp_id = "Longform" if is_longform else "Reels"
        conc = remotion_concurrency()
        cache_b = offthread_cache_bytes()
        extra_flags: list[str] = []
        try:
            from app.render_engine import remotion_flags  # type: ignore

            extra_flags = remotion_flags()
            conc_flag = next((f for f in extra_flags if f.startswith("--concurrency=")), None)
            if conc_flag:
                extra_flags = [f for f in extra_flags if not f.startswith("--concurrency=")]
                conc = int(conc_flag.split("=", 1)[1])
        except Exception:
            extra_flags = []
        print(f"REMOTION_RENDER_START concurrency={conc} flags={extra_flags}", flush=True)
        _t_rend = time.perf_counter()
        with remotion_slot():
            set_stage(edit_dir, "rendering", "Renderizando o vídeo final…", 85)

            def _do_render(flags: list[str]):
                return _run_tool(
                    _remotion_cmd(
                        remotion,
                        "render",
                        comp_id,
                        "out/render.mp4",
                        f"--concurrency={conc}",
                        f"--offthreadvideo-cache-size-in-bytes={cache_b}",
                        # Sai yuv420p/tv/bt709 direto (medido) — o encode_final
                        # detecta e copia o stream em vez de reencodar o vídeo.
                        "--color-space=bt709",
                        *flags,
                    ),
                    cwd=remotion,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                )
            try:
                rend = _do_render(extra_flags)
            except FileNotFoundError as e:
                raise RuntimeError(
                    f"Node/Remotion não encontrado ao renderizar. "
                    f"Instale: winget install OpenJS.NodeJS.LTS — detalhe: {e}"
                ) from e
        _timing_mark("REMOTION_RENDER", _t_rend)
        if rend.returncode != 0:
            raise RuntimeError(
                f"remotion render failed:\n{rend.stderr[-4000:]}\n{rend.stdout[-2000:]}"
            )
        print("REMOTION_RENDER_DONE", flush=True)

        print("[9/9] encode final + legenda")
        set_stage(edit_dir, "exporting", "Finalizando exportação…", 95)
        _t_enc = time.perf_counter()
        from app.timeline import timeline_from_edit_data as _tl_fn

        _enc_tl = _tl_fn(edit_data)
        final = encode_final(
            edit_dir, music, _enc_tl["durationSec"],
            duration_in_frames=_enc_tl["durationInFrames"],
        )
        _timing_mark("FINAL_ENCODE", _t_enc)
        # O caminho completo pede `loudnorm ... TP=-1` numa passagem so, e o
        # loudnorm entrega uns 0,1 a 0,2 dB ACIMA do que se pede: 18 dos 61
        # jobs completos da semana sairam acima de -1,0 dBTP (o pior, -0,3) e
        # foram publicados assim. Aqui ele passa pela mesma conferencia que o
        # caminho rapido — que ja usa duas passagens com folga.
        try:
            from app.overlay_compose import garantir_true_peak

            garantir_true_peak(final)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] true peak: {e}", flush=True)
    other = time.perf_counter() - _t_job - sum(_TIMING.values())
    if other > 0.05:
        _TIMING["OTHER"] = round(other, 3)
    write_timing(edit_dir)
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
        silences = list((vdata or {}).get("silences") or [])
        low_levels = sum(
            1 for row in ((vdata or {}).get("range_levels") or [])
            if str(row.get("verdict") or "") == "LOW-LEVEL"
        )
        score = score_structural(
            duration=duration,
            ranges=edl_ranges,
            has_hook_beat=any(str(r.get("beat") or "").upper() == "HOOK" for r in edl_ranges),
            has_cta=any(str(r.get("beat") or "").upper() == "CTA" for r in edl_ranges),
            silence_flags=len(silences) + low_levels,
            transcript_ok=not transcript_looks_bad(cut_spoken),
            spoken=cut_spoken or "",
        )
        (edit_dir / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        score = None
        print(f"[warn] score: {e}", flush=True)

    final = promote_final_headline(edit_dir, final, edit_data, llm_meta)
    final = seal_delivery_cover(edit_dir, final)
    try:
        from app.delivery_pack import ensure_delivery_pack

        packed = ensure_delivery_pack(edit_dir, final=final)
        if packed:
            print(f"[pack] {packed}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] delivery pack: {e}", flush=True)
    set_stage(edit_dir, "done", "Pronto", 100)
    # Rebatiza o fingerprint das corrections para o estado recém-gerado
    # (captions/edl/cut agora são a mesma verdade). Sem isto um projeto com
    # edições antigas guardava um "relógio" defasado e o quick apply passava
    # a falhar para sempre com "OLD map Nf vs cut.mp4 Mf".
    try:
        from app.apply_execute import _clear_dirty

        if (edit_dir / "corrections.json").exists():
            _clear_dirty(edit_dir)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] corrections clock: {e}", flush=True)
    _write_preview_state(
        edit_dir, source.name, phase=3, message="Pronto",
        fps=int(fps), style=style_blob,
        final_name=final.name,
    )
    canary = {}
    try:
        canary = _canary_job_report(edit_dir, duration=duration, fps=fps, final=final)
        (edit_dir / "canary.json").write_text(
            json.dumps(canary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] canary report: {e}", flush=True)
    (edit_dir / "result.json").write_text(
        json.dumps({
            "status": "done",
            "final": str(final),
            "legenda": str(legenda),
            "durationSec": duration,
            "fps": fps,
            "score": score,
            "llm": llm_meta,
            "canary": canary,
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
    # `deliveryPack` NAO e desta funcao: quem grava e o `ensure_delivery_pack`,
    # que roda logo antes. Montar o state do zero apagava o ponteiro para a
    # pasta de entrega, e o "Abrir pasta" perdia o caminho — medido: 13
    # projetos do usuario com `publicar/` criada e sem ponteiro. Ele so
    # sobrevivia quando um apply posterior o regravava.
    anterior = edit_dir / "state.json"
    if anterior.exists():
        try:
            velho = json.loads(anterior.read_text(encoding="utf-8-sig"))
            if isinstance(velho, dict) and velho.get("deliveryPack"):
                state["deliveryPack"] = velho["deliveryPack"]
        except (OSError, json.JSONDecodeError):
            pass
    anterior.write_text(json.dumps(state, indent=2), encoding="utf-8")


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
    ap.add_argument(
        "--also",
        type=Path,
        action="append",
        default=[],
        help="takes extras no mesmo projeto (repetível) — um final só",
    )
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

    try:
        _acquire_edit_lock(args.edit_dir.resolve())
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        if args.json:
            print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    preset = load_preset(args.preset, args.preset_json)
    try:
        result = run(
            args.source,
            args.edit_dir,
            preset,
            language=args.language,
            skip_phase2=args.skip_phase2,
            also=list(args.also or []),
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
