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
import hashlib
import json
import math
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


def _recolher_marcos_do_corte(proc) -> None:
    """As etapas do corte, que so o helper conhece.

    O corte e 30,8% do tempo de render (12,6h somadas em 172 jobs) e era
    uma caixa preta: `CUT` dizia o total e mais nada. O helper agora
    imprime `TIMING_CORTE <etapa>=<segundos>` e aqui as linhas viram
    fases do `timing.json`, com o prefixo `CUT_`.

    Se o helper nao imprimir nada — versao antiga, saida perdida — o
    total continua sendo gravado como antes; nada depende disto.
    """
    import re

    saida = ((getattr(proc, "stdout", "") or "")
             + (getattr(proc, "stderr", "") or ""))
    for m in re.finditer(r"TIMING_CORTE (\w+)=([0-9.]+)", saida):
        try:
            _TIMING[f"CUT_{m.group(1)}"] = round(float(m.group(2)), 3)
        except ValueError:
            pass


def _timing_mark(name: str, t0: float) -> float:
    dt = time.perf_counter() - t0
    _TIMING[name] = round(dt, 3)
    print(f"TIMING {name}={dt:.2f}s", flush=True)
    return dt


def write_timing(edit_dir: Path) -> dict:
    """Grava timing.json — medição, não otimização."""
    # As sub-fases do corte (`CUT_*`) estão DENTRO do `CUT`: somá-las no
    # total contaria o mesmo tempo duas vezes e faria as porcentagens
    # mentirem.
    total = sum(v for k, v in _TIMING.items() if not k.startswith("CUT_"))
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
    for campo in ("overlayEngine", "overlayEngineSkip",
                  "overlayUmaPassadaFalhou"):
        if _RENDER_META.get(campo):
            payload[campo] = _RENDER_META[campo]
    # Trilha pedida e nao entregue: ate 25/08 o video saia SEM musica em
    # silencio absoluto (caso real: creditos do ElevenLabs esgotados e nada
    # no card, no timing, em lugar nenhum).
    if _RENDER_META.get("musicaSkip"):
        payload["musicaSkip"] = _RENDER_META["musicaSkip"]
    if _RENDER_META.get("musicaFonte"):
        payload["musicaFonte"] = _RENDER_META["musicaFonte"]
    if _RENDER_META.get("nivelAjustado"):
        payload["nivelAjustado"] = _RENDER_META["nivelAjustado"]
    if _RENDER_META.get("musicaMotorRecusa"):
        payload["musicaMotorRecusa"] = _RENDER_META["musicaMotorRecusa"]
    if _RENDER_META.get("endCardSkip"):
        payload["endCardSkip"] = _RENDER_META["endCardSkip"]
    # Trecho que pedia tempo inexistente na fonte. Isto tem de chegar na
    # FICHA: o video sai "pronto" com pedaco mudo e travado, e sem uma nota
    # o usuario procura defeito na gravacao dele.
    if _RENDER_META.get("trechosForaDaFonte"):
        payload["trechosForaDaFonte"] = _RENDER_META["trechosForaDaFonte"]
    if _RENDER_META.get("fonteSemAcento"):
        payload["fonteSemAcento"] = _RENDER_META["fonteSemAcento"]
    if _RENDER_META.get("midiaDoEditorPerdida"):
        payload["midiaDoEditorPerdida"] = _RENDER_META["midiaDoEditorPerdida"]
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
    # A FOLGA SAI DA DURACAO, logo abaixo. As duas checagens medem a mesma
    # grandeza e discordavam: a duracao aceita 0,08s (2,4 quadros a 30fps)
    # e a contagem exigia igualdade exata.
    #
    # Custo dessa incoerencia, medido nos projetos do usuario: TODAS as 15
    # quedas do motor rapido foram `FRAMES N!=M` com 1 a 3 quadros de
    # diferenca, e cada queda refaz o video no Chrome — 3,3x mais lento
    # (143 ms/quadro contra 35,5). Nenhuma consertou nada; o video ja
    # estava certo.
    #
    # O que a guarda pega continua pego: overlay truncado ou de outro corte
    # difere por SEGUNDOS. E quem passar aqui por 3 quadros esbarra na
    # duracao logo em seguida.
    fps_tl = float(tl.get("fps") or edit_data.get("fps") or 30.0)
    folga_f = max(1, int(0.08 * fps_tl))
    if abs(got - expected) > folga_f:
        return f"FRAMES {got}!={expected} (folga {folga_f}f)"
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


def _uv_python(*args: str, cwd: Path | None = None, check: bool = True,
               timeout: float | None = None) -> subprocess.CompletedProcess:
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
            timeout=timeout,
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


def _helper(name: str, *args: str, check: bool = True,
            timeout: float | None = None) -> subprocess.CompletedProcess:
    return _uv_python(str(HELPERS / name), *args, check=check,
                      timeout=timeout)


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


def _preview_edits(edit_dir: Path) -> dict:
    """O arquivo que a tela grava ao salvar. {} quando nao existe/ilegivel."""
    try:
        d = json.loads((edit_dir / "preview_edits.json")
                       .read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def midia_do_editor(edit_dir: Path, public: Path, edit_data: dict) -> None:
    """Imagem, clipe e efeito sonoro que o USUARIO poe na mao no editor.

    Roda depois do b-roll de proposito: em "limpa" o automatico e
    descartado, mas o que foi pedido na mao fica. Arquivo que nao esta em
    public/ nao entra e sai avisado — sumir calado foi o defeito que este
    caminho tinha.
    """
    ed = (_preview_edits(edit_dir).get("editData") or {})
    if not isinstance(ed, dict):
        return

    def _repor(rel: str) -> bool:
        """True se o arquivo esta (ou voltou a estar) em public/.

        O render refaz public/ do zero, e a midia escolhida na tela morava
        so la. A copia de fora (`<edit>/midia/`) e a que sobrevive.
        """
        destino = public / rel
        if destino.exists():
            return True
        guardado = edit_dir / "midia" / rel
        if not guardado.is_file():
            return False
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(guardado, destino)
            return True
        except OSError:
            return False
    inseridos, perdidos = 0, []
    inserts = list(edit_data.get("inserts") or [])
    # Ja aplicado? Esta funcao roda no render completo E no "Aplicar
    # alteracoes"; sem esta marca, aplicar duas vezes poria a mesma imagem
    # duas vezes no video.
    ja = {(str(x.get("src") or ""), round(float(x.get("start") or 0), 2))
          for x in inserts if isinstance(x, dict)}
    for it in (ed.get("newInserts") or []):
        if not isinstance(it, dict):
            continue
        src = str(it.get("src") or "").replace("\\", "/").lstrip("/")
        if not src or ".." in src.split("/"):
            continue
        if not _repor(src):
            perdidos.append(src)
            continue
        try:
            ini = float(it.get("start"))
            fim = float(it.get("end"))
        except (TypeError, ValueError):
            continue
        if fim - ini < 0.2:
            fim = ini + 2.5
        if (src, round(ini, 2)) in ja:
            continue
        geo = {}
        for chave, lim in (("x", 1.0), ("y", 1.0), ("size", 1.0),
                           ("w", 1.0), ("h", 1.0)):
            if it.get(chave) is None:
                continue
            try:
                v = float(it[chave])
            except (TypeError, ValueError):
                continue
            piso = 0.02 if chave in ("x", "y") else 0.05
            geo[chave] = min(lim, max(piso, v))
        inserts.append({"src": src, "start": round(ini, 3),
                        "end": round(fim, 3),
                        "credit": str(it.get("credit") or ""),
                        **geo,
                        # `manual`: o corte nao pode descartar isto como
                        # descarta o b-roll automatico do estilo limpa
                        "manual": True})
        inseridos += 1
    if inseridos:
        edit_data["inserts"] = inserts

    emojis = list(edit_data.get("emojis") or [])
    ja_emoji = {(str(x.get("char") or ""), round(float(x.get("atSec") or 0), 2))
                for x in emojis if isinstance(x, dict)}
    n_emoji = 0
    for it in (ed.get("emojis") or []):
        if not isinstance(it, dict):
            continue
        ch = str(it.get("char") or "").strip()
        if not ch:
            continue
        try:
            em = max(0.0, float(it.get("atSec")))
        except (TypeError, ValueError):
            continue
        def _f(k, padrao):
            try:
                return float(it.get(k, padrao))
            except (TypeError, ValueError):
                return padrao
        if (ch[:8], round(em, 2)) in ja_emoji:
            continue
        emojis.append({
            "char": ch[:8], "atSec": round(em, 3),
            "durSec": round(max(0.2, _f("durSec", 1.6)), 3),
            "x": min(1.0, max(0.0, _f("x", 0.5))),
            "y": min(1.0, max(0.0, _f("y", 0.34))),
            "size": min(0.8, max(0.05, _f("size", 0.22))),
        })
        n_emoji += 1
    if n_emoji:
        edit_data["emojis"] = emojis

    sons = list(edit_data.get("sfxManual") or [])
    ja_som = {(str(x.get("src") or ""), round(float(x.get("atSec") or 0), 2))
              for x in sons if isinstance(x, dict)}
    n_som = 0
    for it in (ed.get("sfxManual") or []):
        if not isinstance(it, dict):
            continue
        nome = str(it.get("src") or "").replace("\\", "/").split("/")[-1]
        if not nome or not _repor(f"sfx/{nome}"):
            if nome:
                perdidos.append(f"sfx/{nome}")
            continue
        try:
            em = float(it.get("atSec"))
        except (TypeError, ValueError):
            continue
        vol = it.get("volume")
        try:
            vol = float(vol) if vol is not None else 0.5
        except (TypeError, ValueError):
            vol = 0.5
        if (nome, round(max(0.0, em), 2)) in ja_som:
            continue
        sons.append({"src": nome, "atSec": round(max(0.0, em), 3),
                     "volume": max(0.0, min(1.5, vol))})
        n_som += 1
    if n_som:
        edit_data["sfxManual"] = sons
    if inseridos or n_som or n_emoji:
        print(f"[editor] mídia posta na mão: {inseridos} insert(s), "
              f"{n_som} efeito(s), {n_emoji} emoji(s)", flush=True)
    if perdidos:
        # Ficha, nao so log: o usuario pediu e nao veio.
        _RENDER_META["midiaDoEditorPerdida"] = perdidos[:6]
        print(f"[editor] ATENCAO: não achei em public/ — {', '.join(perdidos[:6])}",
              flush=True)


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


# Equilibrio de niveis entre os trechos do corte.
#
# O voice_levels acha as passagens que estao >= 5 dB abaixo da mediana da
# PROPRIA fonte e sugere ganho para elas. Quem esta so um pouco abaixo (-3,
# -4 dB) nao e tocado — e ai o reforco dos vizinhos CRIA o desnivel: com
# +7 dB nos outros, o trecho intocado passa a soar 6-8 dB abaixo do resto.
# Medido em 27/08: 6 de 10 videos com um trecho assim, e os marcados eram
# justamente os de ganho 0 (fala cobrindo 100% do trecho — nao e artefato
# de medida).
_DESNIVEL_AVISA_DB = 5.0   # so mexe quando a diferenca e audivel
_FOLGA_DB = 1.5            # mesma folga do suggest_gain: nao encosta na mediana
_TETO_GANHO_DB = 12.0      # teto de sempre: acima disso sobe o ruido da sala


def _nivel_do_trecho(fases: list[dict], ini: float, fim: float) -> float | None:
    """Nivel do trecho = media dos niveis das frases, pesada pelo tempo que
    cada uma ocupa dentro dele."""
    soma = peso = 0.0
    for f in fases:
        a = max(ini, float(f.get("start") or 0))
        b = min(fim, float(f.get("end") or 0))
        if b <= a:
            continue
        lvl = f.get("level_db")
        if lvl is None:
            continue
        soma += float(lvl) * (b - a)
        peso += (b - a)
    return soma / peso if peso > 0 else None


def _equilibrar_ganhos(ranges: list[dict], vozes: dict) -> int:
    """Da ganho de complemento aos trechos que ficariam abaixo dos demais.

    `vozes` e {chave da fonte: analise de voz DAQUELA fonte}. O agrupamento
    por fonte nao e detalhe: com varios takes, os tempos de cada um comecam
    do zero, entao medir um trecho do take 2 contra as frases do take 1
    compara pedacos de gravacoes diferentes que so por acaso caem no mesmo
    minuto — e o ganho ia parar no trecho errado (ate +10,5 dB).

    Devolve quantos trechos foram ajustados. So SOBE volume, nunca abaixa —
    abaixar mexeria no que ja foi aprovado de ouvido.
    """
    ajustados = 0
    for chave, voz in (vozes or {}).items():
        grupo = [r for r in ranges if str(r.get("source") or "") == str(chave)]
        ajustados += _equilibrar_grupo(grupo, voz)
    return ajustados


def _equilibrar_grupo(ranges: list[dict], voice: dict) -> int:
    """Nivela os trechos de UMA fonte contra a voz dessa mesma fonte."""
    fases = [f for f in (voice.get("phrases") or [])
             if f.get("level_db") is not None]
    if not fases or len(ranges) < 3:
        return 0
    depois = []
    for r in ranges:
        lvl = _nivel_do_trecho(fases, float(r.get("start") or 0),
                              float(r.get("end") or 0))
        depois.append(None if lvl is None
                      else lvl + float(r.get("gain_db") or 0))
    validos = sorted(x for x in depois if x is not None)
    if len(validos) < 3:
        return 0
    mediana = validos[len(validos) // 2]
    ajustados = 0
    for r, pos in zip(ranges, depois):
        if pos is None or pos > mediana - _DESNIVEL_AVISA_DB:
            continue
        atual = float(r.get("gain_db") or 0)
        extra = min(mediana - _FOLGA_DB - pos, _TETO_GANHO_DB - atual)
        if extra < 0.5:
            continue
        r["gain_db"] = round(atual + extra, 1)
        ajustados += 1
        print(f"[nivel] trecho {r.get('beat') or ''} {atual:.1f} -> "
              f"{r['gain_db']:.1f} dB (estava {mediana - pos:.1f} dB abaixo "
              "dos outros)", flush=True)
    return ajustados


def transcript_text(edit_dir: Path, stem: str) -> str:
    p = edit_dir / "transcripts" / f"{stem}.json"
    if not p.exists():
        return ""
    data = json.loads(p.read_text(encoding="utf-8"))
    return (data.get("text") or "").strip()


def _nivel_do_audio(src: Path) -> tuple[float, float]:
    """(volume medio, pico) em dB. (0, 0) quando nao da para medir."""
    try:
        r = subprocess.run(
            [_ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(src),
             "-vn", "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return (0.0, 0.0)
    txt = r.stderr or ""
    m = re.search(r"mean_volume:\s*(-?[\d.]+)", txt)
    pk = re.search(r"max_volume:\s*(-?[\d.]+)", txt)
    return (float(m.group(1)) if m else 0.0,
            float(pk.group(1)) if pk else 0.0)


def motivo_da_transcricao_ruim(src: Path, texto: str,
                               duracao: float | None = None) -> str:
    """Por que a transcricao saiu vazia — na lingua do usuario.

    "Transcricao ruim ou vazia — confira o audio" nao diz o que conferir.
    Caso real (29/08): tres jobs pararam com essa frase e as causas eram
    DIFERENTES — dois videos com o audio quase mudo (media -42 e -53 dB,
    quando fala normal fica perto de -20) e um de 3 segundos com uma
    palavra so. Medir custa um ffmpeg de segundos e troca "confira o
    audio" por uma instrucao.
    """
    try:
        dur = float(duracao) if duracao else _ffprobe_duration(src)
    except Exception:  # noqa: BLE001
        dur = 0.0
    media, pico = _nivel_do_audio(src)
    if media and media <= -40.0:
        return (f"o áudio está quase mudo (volume médio {media:.0f} dB, "
                f"pico {pico:.0f} dB — fala normal fica perto de -20 dB). "
                "Confira se o microfone gravou.")
    if dur and dur < 6.0:
        return (f"o vídeo tem só {dur:.0f}s e quase nenhuma fala"
                + (f" (\"{texto.strip()[:40]}\")" if texto.strip() else "")
                + " — curto demais para virar um corte.")
    if not texto.strip():
        return ("não foi reconhecida nenhuma fala no áudio. Se o vídeo tem "
                "voz, veja se ela não está abafada ou em outro idioma.")
    return (f"a transcrição saiu quebrada (\"{texto.strip()[:60]}\") — "
            "confira o áudio do vídeo.")


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
        # O `result.json` guarda o CAMINHO do final e nao acompanhava o
        # rename: 10 projetos do usuario ficaram apontando para um arquivo
        # que nao existe mais, e a publicacao no Instagram le esse campo.
        try:
            rp = edit_dir / "result.json"
            rd = json.loads(rp.read_text(encoding="utf-8-sig"))
            if isinstance(rd, dict) and rd.get("final"):
                rd["final"] = str(dest)
                rp.write_text(json.dumps(rd, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        except (OSError, json.JSONDecodeError, TypeError):
            pass
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

    # Hashtags FIXAS da marca mandam (pedido 26/08): o dono define a lista
    # e ela sai EXATAMENTE assim — posicionamento e estrategia dele, nao
    # heuristica nossa. Sem lista, o palpite automatico continua.
    fixas = [t if t.startswith("#") else "#" + t
             for t in re.split(r"[\s,;]+", str(preset.get("postHashtags") or "").strip())
             if t.strip("#").strip()]
    rodape = str(preset.get("postRodape") or "").strip()
    if rodape:
        lines.append("")
        lines.append(rodape)
    if fixas:
        lines.append("")
        lines.append(" ".join(fixas[:12]))
        return "\n".join(lines).strip() + "\n"
    if rodape:
        return "\n".join(lines).strip() + "\n"

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


# A IA as vezes RECUSA em vez de escrever, e a recusa passa em qualquer
# checagem de tamanho: nos projetos do usuario, dois `legenda.txt` sao
# "Sou apenas um modelo de linguagem. Nao posso ajudar com isso." por
# inteiro — a legenda que ele copia para o Instagram. Um deles virou ate o
# titulo do cartao.
_RECUSA_DA_IA = re.compile(
    r"(modelo de linguagem|sou (apenas )?uma? (ia|intelig)"
    r"|n[ãa]o posso (ajudar|fazer|criar|gerar)"
    r"|n[ãa]o consigo ajudar"
    r"|al[ée]m das minhas (habilidades|habiliades|capacidades)"
    r"|as an ai|i'm sorry|i cannot|i can't help)",
    re.I,
)


def _parece_recusa(texto: str) -> bool:
    """A IA disse que nao vai escrever, em vez de escrever.

    So vale para texto CURTO: uma legenda de verdade pode mencionar "IA"
    falando do produto ("nossa IA acha o defeito"), e barrar isso seria
    jogar fora legenda boa. Recusa nao passa de um paragrafo.
    """
    t = (texto or "").strip()
    return len(t) <= 320 and bool(_RECUSA_DA_IA.search(t))


def _llm_polish_legenda(draft: str, *, spoken: str, preset: dict) -> str | None:
    """Optional short IG caption via sessão IA. Soft-fail → keep draft."""
    try:
        from app.llm_session import chat  # type: ignore
    except Exception:
        return None
    copy = preset.get("endCardCopy") or {}
    seo = str(preset.get("postSeo") or "").strip()
    rodape = str(preset.get("postRodape") or "").strip()
    fixas = [t if t.startswith("#") else "#" + t
             for t in re.split(r"[\s,;]+", str(preset.get("postHashtags") or "").strip())
             if t.strip("#").strip()][:12]
    system = (
        "Você escreve legendas curtas de Reels/TikTok em português do Brasil.\n"
        "Responda SOMENTE com o texto final da legenda (sem markdown, sem aspas).\n"
        "Regras: 1ª linha = gancho; 2–4 linhas no máximo no corpo; NÃO cole a "
        "transcrição inteira; corrija erros óbvios de ASR; preserve o CTA da "
        "marca se houver."
        + ("\nSEO LOCAL (obrigatório): o corpo DEVE conter UMA frase natural "
           "que conecte o assunto do vídeo ao serviço e à cidade dos dados "
           "abaixo — escrita como alguém pesquisaria no Google (ex.: 'troca "
           "de tela em Campinas é aqui na loja'). Escolha o serviço MAIS "
           "ligado ao vídeo; não liste palavras-chave, não soe anúncio, não "
           "repita a frase do gancho."
           if seo else "")
        + ("\nNÃO escreva rodapé/assinatura da loja nem hashtags — eles são "
           "adicionados automaticamente depois. Escreva SÓ o gancho e o corpo "
           "ligados a ESTE vídeo."
           if (fixas or rodape) else
           "\nNo máximo 4 hashtags de nicho (evite #viral #fyp).")
    )
    user = (
        f"CTA marca: {(copy.get('line1') or '').strip()} | {(copy.get('line2') or '').strip()}\n"
        + (f"SEO local (cidade e termos): {seo}\n" if seo else "")
        + (f"Hashtags obrigatórias: {' '.join(fixas)}\n" if fixas else "")
        + f"Rascunho atual:\n{draft}\n\n"
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
    # Recusa passa em tamanho (60 caracteres) e em hashtags (nenhuma), e
    # sobrescreveria o rascunho do EDL, que estava certo.
    if _parece_recusa(text):
        print("[legenda] a IA recusou — fica o rascunho do corte", flush=True)
        return None
    # teto de hashtags acompanha a lista fixa do dono (que pode passar de 6)
    if text.count("#") > max(6, len(fixas) + 2):
        return None
    if fixas or rodape:
        # A IA escreve SO a parte variavel; rodape e hashtags sao montados
        # AQUI, deterministicamente (estrategia do dono, nao palpite):
        # corpo -> rodape fixo -> hashtags. Linhas de hashtag e copias do
        # rodape que a IA teimou em escrever caem fora antes.
        corpo = re.sub(r"(?:\n\s*#[^\n]*)+\s*$", "", text.rstrip()).rstrip()
        if rodape and rodape in corpo:
            corpo = corpo.replace(rodape, "").rstrip()
        partes = [corpo]
        if rodape:
            partes.append(rodape)
        if fixas:
            partes.append(" ".join(fixas))
        text = "\n\n".join(pt for pt in partes if pt)
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


# Etiqueta (prefixo "rotulo--" no nome do arquivo) -> clima. As faixas
# colhidas dos projetos ganharam o tipo do video que as gerou; um MP3 solto
# sem prefixo cai no rodizio geral. Ingles e portugues porque o contentType
# interno e em ingles e o usuario renomeia em portugues.
_TRILHA_CLIMA = {
    "viral": "agitado", "humor": "agitado", "sales": "agitado",
    "ad": "agitado", "venda": "agitado", "anuncio": "agitado",
    "padrao": "agitado", "agitado": "agitado",
    "review": "medio", "informational": "medio", "resenha": "medio",
    "informativo": "medio", "medio": "medio",
    "educational": "calmo", "institutional": "calmo",
    "educacional": "calmo", "institucional": "calmo",
    "longform": "calmo", "calmo": "calmo",
}
_TRILHA_ROTULO_PT = {
    "sales": "venda", "ad": "anuncio", "review": "resenha",
    "informational": "informativo", "educational": "educacional",
    "institutional": "institucional", "": "padrao",
}


def _arquivar_trilha(trilha: Path, ct: str, raiz_projetos: Path,
                     origem: str) -> str:
    """Guarda na Biblioteca a trilha que ACABOU de ser gerada.

    Musica gerada e ativo pago (em credito ou em tempo de GPU) e antes ela
    morria dentro da pasta do projeto: as 139 primeiras faixas so viraram
    biblioteca porque foram garimpadas na mao em 26/08. Agora toda trilha
    nova entra sozinha, com a etiqueta do tipo do video ("viral--...") que
    o proprio plano B usa para escolher pelo clima — a biblioteca cresce a
    cada video e o acervo do plano B fica mais rico com o uso.

    Nao arquiva o que ja veio da biblioteca nem o reaproveitado (seria a
    mesma musica de novo). Falha aqui nunca derruba o render.
    """
    try:
        from app.broll_library import library_root
        pasta = library_root(raiz_projetos) / "Trilhas"
        pasta.mkdir(parents=True, exist_ok=True)
        rotulo = _TRILHA_ROTULO_PT.get(ct, ct or "padrao").lower()
        carimbo = time.strftime("%Y%m%d-%H%M%S")
        dest = pasta / f"{rotulo}--{origem}-{carimbo}.mp3"
        shutil.copy2(trilha, dest)
        print(f"[7/9] trilha arquivada na Biblioteca: {dest.name}",
              flush=True)
        return dest.name
    except (OSError, ValueError) as e:  # noqa: BLE001
        print(f"[7/9] nao deu para arquivar a trilha: {e}", flush=True)
        return ""


def _preferencia_motor_musica() -> str:
    """auto (nuvem primeiro) | local (IA local primeiro) | nuvem (só ela)."""
    try:
        from app.settings_store import load_settings
        v = str(load_settings().get("musicEngine") or "auto").lower().strip()
    except Exception:
        return "auto"
    return v if v in ("auto", "local", "nuvem") else "auto"


def _motor_musica_dir(raiz_projetos: Path) -> str:
    """Pasta do venv MotorMusica, irma da Biblioteca real (resolve o
    junction dos Projetos do mesmo jeito que a biblioteca de trilhas)."""
    try:
        from app.broll_library import library_root
        return str(library_root(raiz_projetos).parent / "MotorMusica")
    except Exception:
        return ""


# Teto de tempo para o motor local. O launcher ja tem o dele (240s), mas
# se ELE travar o render fica preso para sempre: o [7/9] espera a chamada
# sincrona sem prazo. Render real de 27/08 mostrou MUSIC_WAIT=124s — nao
# pode virar infinito.
_MOTOR_TETO_S = 300
# Quando a maquina esta apertada o launcher recusa (codigo 6). No fio
# ANTECIPADO vale esperar e tentar de novo: a fase que come RAM (transcricao,
# corte) acaba, a memoria volta e a musica ainda sai em paralelo, sem
# segurar o render. No caminho sincrono nao ha o que esperar.
_MOTOR_RECUSADO = 6
# Espera CURTA e muitas voltas: com 45s de intervalo o motor so comecava
# depois que a memoria ja tinha liberado ha tempo, e o render esperava 2,5
# min pela musica (medido em 27/08). Com 12s ele pega a folga assim que a
# transcricao solta a RAM — mesma cobertura (~2 min), musica pronta antes.
_MOTOR_TENTATIVAS = 10
_MOTOR_ESPERA_S = 12
# Esperar a VEZ (outro video compondo) compensa mais que esperar folga de
# memoria: uma composicao leva ~90s, entao com dois videos em paralelo o
# segundo so precisa de paciencia. Medido em 28/08 nos 10 ultimos renders:
# metade das trilhas caiu para a biblioteca, e a fila do motor e a
# explicacao mais provavel.
_MOTOR_NA_FILA = 7        # codigo do launcher para "outro esta compondo"
# 18 voltas x 12s = 216s, DENTRO dos 240s que o render espera pelo fio
# antecipado (music_thread.join(timeout=240)). Com 22 voltas a espera
# passava do prazo: o render desistia com o fio ainda tentando, caia no
# caminho sincrono (uma tentativa so) e a trilha vinha da biblioteca
# mesmo com o motor prestes a liberar.
_MOTOR_TENTATIVAS_FILA = 18
# MEDIDO em 30/08, antes de "otimizar" esta espera: dos 138 jobs com
# `MUSIC_WAIT`, 106 esperam ~0s e 16 esperam mais de 30s. Desses 16, DEZ
# terminam com "motor: MusicGen local" — ou seja, a espera esta compondo
# musica de verdade, nao desperdicando. Encurtar o teto trocaria trilha de
# IA por trilha da biblioteca nesses casos.
#
# O custo total e 27 minutos somados em 138 jobs (12s de media). O ganho
# real estaria em SOBREPOR a fila do motor com o render do overlay (a
# composicao do Overlay nao usa a trilha; ela entra so no compose), nao em
# cortar o tempo de espera. Fica registrado para nao se mexer aqui pelo
# motivo errado.


def _tentar_musicgen(destino: Path, vibe: str, length_sec: int,
                     raiz_projetos: Path, tentativas: int = 1) -> bool:
    """Plano B da trilha: o motor LOCAL compoe a musica DESTE video, com o
    mesmo vibe que o ElevenLabs receberia. So roda onde o venv MotorMusica
    existe (launcher sai com 3 na hora em maquina sem ele); medido em
    26/08 na RTX 3050: 30s compostos em 67s, pico 1,9GB de VRAM."""
    for volta in range(max(1, tentativas, _MOTOR_TENTATIVAS_FILA)):
        try:
            proc = _helper("musicgen_local.py", vibe, "-o", str(destino),
                           "--length-sec", str(int(length_sec)),
                           "--motor", _motor_musica_dir(raiz_projetos),
                           check=False, timeout=_MOTOR_TETO_S)
        except subprocess.TimeoutExpired:
            print(f"[7/9] motor local passou de {_MOTOR_TETO_S}s — seguindo "
                  "sem ele", flush=True)
            return False
        if destino.exists() and destino.stat().st_size > 1000:
            _RENDER_META.pop("musicaMotorRecusa", None)
            return True
        codigo = proc.returncode
        if codigo not in (_MOTOR_RECUSADO, _MOTOR_NA_FILA):
            _RENDER_META["musicaMotorRecusa"] = (
                "o motor local não está instalado" if codigo == 3 else
                "o motor passou do tempo" if codigo == 5 else
                f"o motor falhou (código {codigo})")
            return False
        teto = (max(tentativas, _MOTOR_TENTATIVAS_FILA)
                if codigo == _MOTOR_NA_FILA else tentativas)
        if volta >= teto - 1:
            _RENDER_META["musicaMotorRecusa"] = (
                "outro vídeo ocupou o motor até o fim da espera"
                if codigo == _MOTOR_NA_FILA
                else "a máquina não tinha folga de memória")
            return False
        time.sleep(_MOTOR_ESPERA_S)
    return False


def _trilha_etiqueta(nome: str) -> str:
    return nome.split("--", 1)[0].lower() if "--" in nome else ""


def _trilha_da_biblioteca(destino: Path, dur_s: float, ct: str = "",
                          raiz_projetos: Path | None = None) -> str | None:
    """Plano B da trilha quando a IA falha: musicas do PROPRIO usuario.

    A geracao por IA morre de dois jeitos reais — creditos esgotados (caso
    de 26/08: 346k creditos do ElevenLabs queimados e o plano so renova em
    08/09) e rede fora — e nos dois o video saia MUDO de musica. Aqui o
    usuario deixa MP3s royalty-free em ATIVAVID/Biblioteca/Trilhas UMA vez
    e o pipeline rodizia entre eles (.rodizio.txt guarda a ultima usada,
    senao todo video sairia com a mesma musica). A faixa e loopada/aparada
    para a duracao do video com fade de entrada e saida. Retorna o nome da
    faixa usada, ou None (pasta vazia / ffmpeg falhou) — e o chamador
    mantem o aviso de "sem trilha".
    """
    # A pasta REAL vem do library_root do app — o mesmo que a tela
    # Biblioteca usa. Caso real (26/08): os Projetos do usuario sao um
    # junction C:\Users\...\ATIVAVID\Projetos -> E:\ATIVAVID\Projetos, e o
    # Path.home() apontava para a biblioteca do C: enquanto o app usa a do
    # E: — 139 trilhas invisiveis. A raiz dos projetos resolve o junction;
    # home fica de reserva.
    try:
        from app.broll_library import library_root
        pasta = library_root(raiz_projetos) / "Trilhas"
    except Exception:
        pasta = Path.home() / "ATIVAVID" / "Biblioteca" / "Trilhas"
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        faixas = sorted(
            f for f in pasta.iterdir()
            if f.is_file() and f.stat().st_size > 50_000
            and f.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac",
                                     ".ogg", ".flac"})
    except OSError:
        return None
    if not faixas:
        return None
    # Escolha por CLIMA, em tres degraus: (1) faixas do MESMO tipo do video
    # (um video viral pega uma trilha nascida de video viral — phonk pesado,
    # nao piano calmo); (2) faixas do mesmo clima (agitado/medio/calmo);
    # (3) qualquer uma. O rodizio roda DENTRO do degrau escolhido.
    rotulo = _TRILHA_ROTULO_PT.get(ct, ct or "padrao").lower()
    clima = _TRILHA_CLIMA.get(rotulo, "agitado")
    mesmas = [f for f in faixas if _trilha_etiqueta(f.name) == rotulo]
    parecidas = [f for f in faixas
                 if _TRILHA_CLIMA.get(_trilha_etiqueta(f.name)) == clima]
    escolhidas = mesmas or parecidas or faixas
    marca = pasta / ".rodizio.txt"
    try:
        ultima = marca.read_text(encoding="utf-8").strip()
    except OSError:
        ultima = ""
    nomes = [f.name for f in escolhidas]
    idx = (nomes.index(ultima) + 1) % len(escolhidas) \
        if ultima in nomes else 0
    escolha = escolhidas[idx]
    alvo = max(4.0, float(dur_s) + 2.0)
    proc = subprocess.run(
        [_ffmpeg_exe(), "-y", "-stream_loop", "-1", "-i", str(escolha),
         "-t", f"{alvo:.2f}", "-vn",
         "-af", ("afade=t=in:st=0:d=0.6,"
                 f"afade=t=out:st={max(0.5, alvo - 1.8):.2f}:d=1.6"),
         "-c:a", "libmp3lame", "-q:a", "4", str(destino)],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not destino.exists() \
            or destino.stat().st_size < 1000:
        destino.unlink(missing_ok=True)
        return None
    try:
        marca.write_text(escolha.name, encoding="utf-8")
    except OSError:
        pass
    return escolha.name


# Sobra de silencio e take baixo: os DOIS defeitos que o verify_cut acha de
# verdade nos videos reais. Medido em 27/08 nos 10 ultimos: 6 de 10 com
# pausa sobrando (0,4-0,7s cada) e 6 de 10 com um trecho mais baixo que o
# resto. Estouro de emenda e clipping: zero. O diagnostico existia desde
# sempre — e era jogado fora ao fim do render, entao ninguem podia agir.
_SILENCIO_MIN_S = 0.4      # abaixo disso e respiracao, nao pausa morta
_SILENCIO_AVISA_S = 0.8    # so avisa quando o total incomoda de verdade
_NIVEL_AVISA_DB = -6.0     # queda que o ouvido pega (o flag interno e -4)


def _gravar_diagnostico_do_corte(edit_dir: Path, vdata: dict) -> None:
    """Guarda em verificacao.json o que o verify_cut achou.

    Sem isto o dado morre no fim do render: 158 projetos entregues e
    nenhum guardou uma linha do que a verificacao viu (varredura 27/08).
    """
    if not vdata:
        # Verificacao sem resposta (verify_cut falhou/ilegivel): o arquivo do
        # render ANTERIOR nao pode sobreviver — a ficha passaria a descrever
        # defeitos de um corte que nao existe mais.
        (edit_dir / "verificacao.json").unlink(missing_ok=True)
        return
    sil = [(float(x.get("start") or 0), float(x.get("end") or 0))
           for x in (vdata.get("silences") or [])]
    sil = [(a, b) for a, b in sil if b - a >= _SILENCIO_MIN_S]
    # MESMA guarda do verify_cut: trecho com RMS <= -90 dB e silencio digital
    # (b-roll mudo, take sem audio), nao voz baixa — sem isto o card acusava
    # "voz 77 dB mais baixa" em trecho que o proprio verificador marcou "ok".
    # E delta nao-finito (silencio absoluto -> -inf) e descartado: ele chegava
    # inteiro no JSON e o `int()` da nota derrubava o /api/jobs, deixando a
    # Fila em branco a cada atualizacao.
    baixos = []
    for x in (vdata.get("range_levels") or []):
        try:
            delta = float(x.get("delta_db"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(delta) or delta > _NIVEL_AVISA_DB:
            continue
        # Silencio COMPROVADO sai (mesma guarda do verify_cut: rms <= -90 e
        # trecho mudo, b-roll ou take sem audio — nao voz baixa). Sem rms
        # gravado, o aviso fica: calar por falta de dado esconderia defeito
        # de verdade.
        rms = x.get("rms_db")
        if rms is not None:
            try:
                r = float(rms)
            except (TypeError, ValueError):
                r = 0.0
            if not math.isfinite(r) or r <= -90:
                continue
        baixos.append(x)
    pops = [j for j in (vdata.get("junctions") or [])
            if any(t in str(j.get("verdict") or "")
                   for t in ("POP", "HOT"))]
    dados = {
        "flags": vdata.get("flags"),
        "silenciosSobrando": [{"inicio": round(a, 2), "fim": round(b, 2)}
                              for a, b in sil],
        "silencioTotalS": round(sum(b - a for a, b in sil), 2),
        "takesBaixos": [{"trecho": int(x.get("index") or 0),
                         "quedaDb": round(float(x.get("delta_db") or 0), 1)}
                        for x in baixos],
        "emendasEstouradas": len(pops),
        "picoDb": vdata.get("peak_db"),
    }
    try:
        (edit_dir / "verificacao.json").write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


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
            # CENTRO da tela: abertura em que a manchete e a unica coisa na
            # tela (pedido do usuario, 29/08). Cada motor centraliza com a
            # altura que ele mesmo mediu — mandar um `paddingTop` calculado
            # aqui erraria, porque o numero de linhas e o tamanho da fonte so
            # sao conhecidos na hora de desenhar.
            "centro": str(preset.get("headlinePos") or "").lower().strip()
                      in ("centro", "center", "meio"),
            "style": headline if hook_enabled else "outline",
            "lines": hook if hook_enabled else ["", ""],
            "accent": accent,
            "logo": None,
            "sign": None,
        },
        "videoLayout": _layout_valido(edit_style_norm),
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
    # Quem consome a cor da LEGENDA e quem consome a da ENFASE estao em
    # `app/caption_styles.py`. Escrito aqui a mao, um estilo novo guardava a
    # cor no preset e o render nunca a recebia — o seletor da tela mentia.
    from app.caption_styles import USAM_COR_DA_ENFASE, USAM_COR_DA_LEGENDA
    if ca and captions in USAM_COR_DA_LEGENDA:
        ed["captions"]["accent"] = ca
    ea = preset.get("emphasisAccent")
    if ea and captions in USAM_COR_DA_ENFASE:
        ed["captions"]["emphasisAccent"] = ea
    circ = preset.get("circleAccent")
    if circ and captions == "stacked":
        ed["captions"]["circleAccent"] = circ
    # "marca-texto": a enfase pinta o fundo em vez de circular (pedido do
    # usuario, 26/08). Mesmas cues, mesmo tempo, mesmo scratch — so a tinta.
    if str(preset.get("emphasisStyle") or "").lower() == "marker"             and captions == "stacked":
        ed["captions"]["emphasisStyle"] = "marker"
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


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


def _palavras_do_video(public: Path) -> list[tuple[str, float, float]]:
    """Palavras com tempo NO VIDEO JA CORTADO (caption-cues.json).

    E o unico relogio que serve para posicionar b-roll: a transcricao da
    fonte fala do arquivo original, e o corte ja mudou tudo de lugar.
    """
    f = public / "caption-cues.json"
    if not f.is_file():
        return []
    try:
        dados = json.loads(f.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    cues = dados if isinstance(dados, list) else (dados.get("cues") or [])
    fora: list[tuple[str, float, float]] = []
    for c in cues:
        for linha in (c.get("lines") or []):
            for w in linha:
                txt = _sem_acento(str(w.get("text") or "")).strip(" .,!?;:—-")
                try:
                    ini = float(w.get("fromMs") or 0) / 1000.0
                    fim = float(w.get("toMs") or 0) / 1000.0
                except (TypeError, ValueError):
                    continue
                if txt and fim > ini:
                    fora.append((txt, ini, fim))
    return fora


def _palavras_do_take(nome: str) -> list[str]:
    """O que o arquivo diz que o take MOSTRA.

    "humor--cavalo-patada.mp4" -> ["cavalo", "patada"]. A categoria (antes
    do `--`) fica de fora: ela diz o PAPEL do take, nao o conteudo, e
    casar "humor" com a palavra "humor" da fala seria coincidencia.
    """
    import re
    base = nome.rsplit(".", 1)[0]
    if "--" in base:
        base = base.split("--", 1)[1]
    partes = re.split(r"[^0-9A-Za-zÀ-ÿ]+", base)
    return [_sem_acento(x) for x in partes if len(x) >= 4]


def _momento_do_take(nome: str, palavras: list[tuple[str, float, float]],
                     depois_de: float) -> float | None:
    """Quando a palavra que o take ilustra e dita (segundo do video).

    Pedido do usuario: "quando der uma patada, usar um take de cavalo dando
    patada". Antes o b-roll usava as 3 palavras mais frequentes do texto
    INTEIRO e espalhava os inserts em fatias iguais — o take caia em
    qualquer lugar menos no momento da piada.
    """
    chaves = _palavras_do_take(nome)
    if not chaves:
        return None
    for txt, ini, fim in palavras:
        if fim < depois_de:
            continue
        for k in chaves:
            if txt == k or (len(k) >= 5 and (txt.startswith(k) or k.startswith(txt))
                            and abs(len(txt) - len(k)) <= 3):
                return fim
    return None


def _aparar_fora_da_fonte(ranges: list[dict],
                          duracoes: dict[str, float]) -> list[dict]:
    """Tira do corte o que pede tempo que o arquivo NAO tem.

    Isto nunca da erro: o ffmpeg, pedido a partir de um instante que nao
    existe, entrega silencio e quadro congelado, e o video sai "pronto".
    Caso real (29/08, job de 3 partes do usuario): `Parte 1.mov` tem 6,1s e
    o EDL trazia 12 trechos dessa fonte indo ate 137,5s — tempos da
    `parte 2`. O video saiu com 28s, 23,4s deles mudos e travados, e so a
    ficha de qualidade estranhou.

    A causa daquele caso foi consertada (o casamento de take por nome), mas
    a familia do defeito e maior do que ela: qualquer engano de relogio
    entre takes cai aqui. Um trecho fora da fonte nunca e conteudo — e
    sempre erro de conta. Entao ele e aparado, ou removido se nao sobrar
    nada, e o motivo vai para o log e para a ficha.
    """
    if not ranges or not duracoes:
        return ranges
    fora: list[dict] = []
    limpos: list[dict] = []
    for r in ranges:
        dur = duracoes.get(str(r.get("source") or ""))
        if not dur:
            limpos.append(r)
            continue
        try:
            ini, fim = float(r["start"]), float(r["end"])
        except (KeyError, TypeError, ValueError):
            limpos.append(r)
            continue
        if fim <= dur + 0.05:
            limpos.append(r)
            continue
        novo_fim = min(fim, dur)
        if novo_fim - ini < 0.30:
            fora.append({"fonte": r.get("source"), "de": round(ini, 2),
                         "ate": round(fim, 2), "acao": "removido"})
            continue
        fora.append({"fonte": r.get("source"), "de": round(ini, 2),
                     "ate": round(fim, 2), "acao": f"aparado em {novo_fim:.2f}"})
        limpos.append(dict(r, end=round(novo_fim, 3)))
    if fora:
        _RENDER_META["trechosForaDaFonte"] = fora[:8]
        for f in fora[:5]:
            print(f"[corte] fora da fonte: {f['fonte']} {f['de']}-{f['ate']}s "
                  f"({f['acao']})", flush=True)
        print(f"[corte] {len(fora)} trecho(s) pediam tempo que a fonte nao "
              f"tem — o video sairia mudo e travado neles", flush=True)
    return limpos


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
    if edit_style in _QUADRO_CHEIO and not explicit:
        edit_data["inserts"] = []
        print("[broll] estilo limpa + b-roll no padrão — sem inserts automáticos", flush=True)
        return edit_data
    if edit_style in _QUADRO_CHEIO:
        print(f"[broll] estilo limpa, mas b-roll={mode} pedido — inserts ligados", flush=True)
    # 1) biblioteca local
    try:
        from app.broll_library import pick_for_query  # type: ignore
        from auto_broll import keywords_from_text  # type: ignore

        kws = keywords_from_text(transcript, limit=3)
        query = " ".join(kws) if kws else "produto"
        # A biblioteca REAL vem da raiz dos projetos, nunca do Path.home():
        # os Projetos do usuario sao um junction C:\...\ATIVAVID\Projetos ->
        # E:\ATIVAVID\Projetos, e no C: sobrou uma pasta Biblioteca VAZIA.
        # O b-roll lia essa pasta morta — as fotos e os takes dele estavam
        # todos no E: e nunca eram achados (mesmo defeito que a 3.03
        # consertou na trilha; aqui tinha ficado).
        # public = <Projetos>/<projeto>/edit/remotion/public
        raiz_projetos = public.parents[3] if len(public.parents) > 3 else None
        from auto_broll import _mode_count  # type: ignore
        # Pede MAIS candidatos do que vai usar: quem entra e quem casa com
        # um momento da fala, nao quem aparece primeiro na pasta.
        quantos = max(1, _mode_count(mode))
        local = pick_for_query(query, projects_root=raiz_projetos,
                               limit=max(8, quantos * 3))
        if local:
            # pilula estica endSec para o vídeo inteiro — para o espaço de b-roll
            # vale a janela clássica de gancho, nunca a persistência da barra.
            hook_end = min(4.0, float((edit_data.get("hook") or {}).get("endSec") or 3.0))
            end_card = float((edit_data.get("endCard") or {}).get("lastSec") or 2.5)
            inserts = []
            pexels_dir = public / "pexels"
            pexels_dir.mkdir(parents=True, exist_ok=True)
            usable = max(0.0, duration - hook_end - end_card - 0.4)
            palavras = _palavras_do_video(public)
            # 1o passo: quem casa com uma palavra dita entra NAQUELE momento;
            # o resto (ou tudo, se nao houver legenda) volta para as fatias
            # iguais de antes.
            escolhidos: list[tuple[dict, float | None]] = []
            usados = hook_end + 0.3
            for it in local:
                if len(escolhidos) >= quantos:
                    break
                quando = _momento_do_take(it.get("name") or "", palavras,
                                          usados) if palavras else None
                if quando is None:
                    continue
                escolhidos.append((it, quando + 0.08))
                usados = quando + 2.6      # dois takes colados viram ruido
            if len(escolhidos) < quantos:
                for it in local:
                    if len(escolhidos) >= quantos:
                        break
                    if any(x is it for x, _ in escolhidos):
                        continue
                    escolhidos.append((it, None))
            sem_momento = [1 for _, q in escolhidos if q is None]
            slot = usable / max(1, len(sem_momento) or len(escolhidos))
            if palavras and any(q is not None for _, q in escolhidos):
                casados = sum(1 for _, q in escolhidos if q is not None)
                print(f"[broll] {casados} take(s) no momento da fala",
                      flush=True)
            i_livre = 0
            for it, quando in escolhidos:
                src_path = Path(it["path"])
                if not src_path.exists():
                    continue
                ext = src_path.suffix.lower()
                # O TAKE de video entra igual a foto. Antes o codigo exigia
                # `kind == "image"` e o clipe da biblioteca era descartado
                # calado — o usuario guardava take de reacao/humor e nada
                # aparecia no video. Quem desenha e o InsertCard, que agora
                # escolhe Img ou OffthreadVideo pela extensao.
                if ext not in (".jpg", ".jpeg", ".png", ".webp",
                               ".mp4", ".mov", ".webm"):
                    continue
                video = ext in (".mp4", ".mov", ".webm")
                name = f"lib-{src_path.stem[:30]}{ext}"
                shutil.copy2(src_path, pexels_dir / name)
                if quando is None:
                    start = hook_end + 0.3 + i_livre * slot
                    i_livre += 1
                else:
                    start = max(hook_end + 0.3, quando)
                # take de video respira mais que uma foto: a acao precisa
                # acontecer (uma patada em 1,0s nao le)
                teto = 2.5 if video else 1.6
                end = min(duration - end_card - 0.2,
                          start + min(teto, max(1.0, slot * 0.55)))
                if end <= start + 0.6:
                    continue
                inserts.append({"src": f"pexels/{name}", "start": round(start, 3),
                                "end": round(end, 3), "local": True,
                                "kind": "video" if video else "image",
                                "noMomento": quando is not None})
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


def _legenda_comeca_depois(public: Path, segundos: float) -> int:
    """Tira da legenda o que cai ANTES de `segundos`.

    Abertura em que a manchete e a unica coisa na tela: nesses primeiros
    segundos a legenda repetiria, palavra por palavra, o que a manchete ja
    esta dizendo em corpo grande. Cortar aqui — e nao no motor — faz os
    DOIS (Remotion e o proprio) obedecerem, porque os dois leem este mesmo
    arquivo.

    Uma cue que atravessa a fronteira nao e jogada fora: ela comeca no
    limite, e as palavras que ficaram atras saem dela.
    """
    if segundos <= 0:
        return 0
    f = public / "caption-cues.json"
    if not f.is_file():
        return 0
    try:
        dados = json.loads(f.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return 0
    cues = dados if isinstance(dados, list) else (dados.get("cues") or [])
    ms = segundos * 1000.0
    fora: list[dict] = []
    tirados = 0
    for c in cues:
        try:
            fim = float(c.get("endMs") or 0)
            ini = float(c.get("startMs") or 0)
        except (TypeError, ValueError):
            fora.append(c)
            continue
        if fim <= ms:
            tirados += 1
            continue
        if ini < ms:
            linhas = []
            for linha in (c.get("lines") or []):
                palavras = [w for w in linha
                            if float(w.get("toMs") or 0) > ms]
                if palavras:
                    linhas.append(palavras)
            if not linhas:
                tirados += 1
                continue
            c = dict(c, startMs=ms, lines=linhas)
            # `lineStyles`/`lineBoost`/`lineEmph` andam junto com as linhas
            for chave in ("lineStyles", "lineBoost", "lineEmph"):
                v = c.get(chave)
                if isinstance(v, list) and len(v) > len(linhas):
                    c[chave] = v[-len(linhas):]
            tirados += 1
        fora.append(c)
    if tirados:
        f.write_text(json.dumps(fora, ensure_ascii=False), encoding="utf-8")
        print(f"[legenda] comeca em {segundos:.1f}s (a manchete fica sozinha "
              f"antes disso) — {tirados} trecho(s) ajustado(s)", flush=True)
    return tirados


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


# Layouts de video: a lista mora em app/video_layouts.py. Repetida aqui, um
# id novo que esquecesse UMA das copias simplesmente nao acontecia no video,
# calado — foi assim que o "degrade" passou meses sem sair no motor rapido.
def _layout_valido(nome: object) -> str:
    from app.video_layouts import normalizar
    return normalizar(nome)


def _layout_pede_remotion(nome: object) -> bool:
    """Divide a tela ou transforma o video -> caminho lento."""
    from app.video_layouts import DIVIDEM, transforma_o_video
    return str(nome or "").lower() in DIVIDEM or transforma_o_video(nome)


def _quadro_cheio() -> frozenset:
    from app.video_layouts import QUADRO_CHEIO
    return QUADRO_CHEIO


_QUADRO_CHEIO = _quadro_cheio()

_ACENTOS_PT = "ÁÃÂÀÉÊÍÓÔÕÚÇáãâàéêíóôõúç!?"


def _acentos_que_faltam(arquivo: Path) -> str:
    """Letras do portugues que a fonte nao desenha DE VERDADE.

    Fonte de demonstracao nao deixa a letra faltando: ela MAPEIA o acento
    para um carimbo ("DEMO"). Por isso comparar com o glifo de ausente
    (.notdef) nao acha nada — a assinatura e outra: varios caracteres
    DIFERENTES saem com o desenho identico.

    Caso real (29/08): a Integral CF demo escrevia "N[DEMO]O MORRE[DEMO]"
    onde devia sair "NAO MORRE!" — e isso so apareceria no video pronto,
    na frente do cliente dele.
    """
    try:
        from PIL import ImageFont

        f = ImageFont.truetype(str(arquivo), 64)

        def _desenho(ch: str) -> tuple:
            # `bytes(mask)`, nao `mask.tobytes()`: o objeto do Pillow nao tem
            # esse metodo, e o try/except abaixo engolia o AttributeError —
            # a checagem dizia "nenhum acento faltando" para uma fonte que
            # carimbava DEMO em todos eles.
            m = f.getmask(ch)
            return (m.size, bytes(m))

        ausente = _desenho("")
        grupos: dict[tuple, list[str]] = {}
        for c in _ACENTOS_PT:
            grupos.setdefault(_desenho(c), []).append(c)
        faltam: list[str] = []
        for desenho, chars in grupos.items():
            # o proprio .notdef, ou um carimbo que serve a varias letras
            if desenho == ausente or len(chars) >= 3:
                faltam.extend(chars)
        return "".join(c for c in _ACENTOS_PT if c in faltam)
    except Exception:  # noqa: BLE001 - checagem nunca derruba o render
        return ""


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
    faltam = _acentos_que_faltam(src)
    if faltam:
        _RENDER_META["fonteSemAcento"] = {"arquivo": src.name, "faltam": faltam}
        print(f"[fonte] ATENCAO: {src.name} nao tem {faltam} — nessas letras "
              f"a fonte desenha o simbolo dela (fonte de demonstracao costuma "
              f"carimbar 'DEMO')", flush=True)


# Tempero por video. O vibe fixo por tipo dava sempre a MESMA "banda":
# 5 trilhas seguidas do mesmo clima saiam com timbre irmao (o usuario
# ouviu e apontou em 27/08). Cada video sorteia um instrumento em
# destaque, uma textura e um empurrao no andamento — o clima nao muda,
# so a roupa.
#
# O sorteio e DETERMINISTICO pela semente (nome da pasta do projeto):
# refazer a Fase 2 do mesmo video devolve o mesmo pedido, senao o
# reaproveitamento da trilha quebraria e cada refazer geraria musica nova
# — exatamente o ralo que queimou 346k creditos em 26/08.
_MUSIC_TEMPEROS = {
    "agitado": ["distorted electric guitar riffs", "brass stabs",
                "gritty analog synth lead", "hand percussion and claps",
                "deep sub bass and trap hats", "funk guitar skank"],
    "medio": ["warm electric piano", "muted trumpet", "clean electric guitar",
              "vibraphone", "nylon guitar", "soft rhodes and shaker"],
    "calmo": ["felt piano", "soft cello pad", "acoustic guitar arpeggio",
              "music box bells", "warm analog pad", "gentle marimba"],
}
_MUSIC_TEXTURAS = ["airy and spacious mix", "warm tape-saturated mix",
                   "dry punchy mix", "lush reverb", "lo-fi vinyl texture",
                   "clean modern mix"]


def _temperar_vibe(base: str, semente: str, clima: str) -> str:
    """Acrescenta instrumento, textura e ajuste de bpm ao pedido base."""
    if not semente:
        return base
    h = hashlib.md5(semente.encode("utf-8", "ignore")).digest()
    opcoes = _MUSIC_TEMPEROS.get(clima) or _MUSIC_TEMPEROS["agitado"]
    instrumento = opcoes[h[0] % len(opcoes)]
    textura = _MUSIC_TEXTURAS[h[1] % len(_MUSIC_TEXTURAS)]
    desvio = (h[2] % 13) - 6  # -6..+6 bpm
    saida = base
    if desvio:
        # o bpm do texto base vira o bpm temperado ("124 bpm" -> "130 bpm")
        m = re.search(r"(\d{2,3})\s*bpm", saida)
        if m:
            novo = max(70, min(150, int(m.group(1)) + desvio))
            saida = saida[:m.start()] + f"{novo} bpm" + saida[m.end():]
    return f"{saida}, featuring {instrumento}, {textura}"


def _music_vibe_for(preset: dict, is_longform: bool,
                    semente: str = "") -> str:
    if is_longform:
        return _temperar_vibe(
            "calm cinematic instrumental bed, soft piano and pads, 90 bpm, "
            "no vocals", semente, "calmo")
    try:
        from app.content_type import normalize_content_type

        ct = normalize_content_type(preset.get("contentType")) or ""
    except Exception:
        ct = str(preset.get("contentType") or "").strip().lower()
    base = _MUSIC_VIBES.get(ct, _MUSIC_DEFAULT)
    rotulo = _TRILHA_ROTULO_PT.get(ct, ct or "padrao").lower()
    return _temperar_vibe(base, semente, _TRILHA_CLIMA.get(rotulo, "agitado"))


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


def _sfx_do_usuario(dest: Path, edit_dir: Path) -> None:
    """Efeito que o usuario poe na Biblioteca entra no lugar do do app.

    A vaga e a categoria do arquivo ("whoosh--meu.mp3" troca o whoosh).
    Roda no scaffold porque e ali que a pasta `public/sfx` do projeto
    nasce — e os DOIS motores tocam o som a partir dela.
    """
    try:
        from app.broll_library import aplicar_sfx_do_usuario
        raiz = edit_dir.parent.parent
        trocados = aplicar_sfx_do_usuario(dest / "public", raiz)
        if trocados:
            print(f"[scaffold] efeitos do usuario: {', '.join(trocados)}",
                  flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] efeitos do usuario: {str(e)[:80]}", flush=True)


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
        _sfx_do_usuario(dest, edit_dir)
        return dest

    if dest.exists():
        _clear_dir_windows(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("node_modules"))

    _sfx_do_usuario(dest, edit_dir)

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
        # Instalacao NOVA sem a marca preenchida travava TODOS os primeiros
        # jobs no REVISAR (caso real, cliente em trial 26/08: 5 de 5) —
        # pessimo primeiro contato. O video sai SEM o card final e a ficha
        # avisa onde preencher; quem ja tem marca nem passa por aqui.
        elems = dict(elems)
        elems["endCard"] = False
        preset = dict(preset)
        preset["elements"] = elems
        _RENDER_META["endCardSkip"] = (
            "sem texto da marca — preencha em Estilos para o card voltar")
        print("[marca] card final desligado: endCardCopy vazio", flush=True)

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
    elif intent_mode in ("complete", "intact"):
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
    # Analise de voz de CADA fonte, pela chave do range: o nivelamento
    # precisa medir cada take contra ele mesmo (ver _equilibrar_ganhos).
    vozes_por_fonte: dict[str, dict] = {}
    duracoes_por_fonte: dict[str, float] = {}
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
                raise NeedsReview(
                    "bad_transcript",
                    motivo_da_transcricao_ruim(src, spoken_i, dur_i))
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
        vozes_por_fonte[key] = voice_i
        duracoes_por_fonte[key] = dur_i
        if idx == 0:
            grade_field = g
            regions = regions_i
            voice = voice_i
            dur = dur_i
            spoken = spoken_i
            source_key = key

        if len(sources) > 1:
            if intent_mode == "intact":
                # Sem cortes com varios takes: cada take entra inteiro, na ordem.
                all_ranges.append({
                    "source": key,
                    "start": 0.0,
                    "end": round(dur_i, 3),
                    "beat": "HOOK" if idx == 0 else f"B{idx}",
                    "quote": "",
                    "reason": "sem cortes",
                    "gain_db": 0.0,
                })
                continue
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
    elif str(preset.get("editingIntent") or "").lower() == "intact" and len(sources) == 1:
        # Sem cortes: o video INTEIRO, zero tesoura. So legendas, titulo,
        # cor e trilha. Pedido direto do usuario (24-25/08): "quero o mais
        # original possivel" — o minimo que existia (Video completo) ainda
        # tira silencio e repeticao.
        print("[intacto] sem cortes — o video inteiro", flush=True)
        set_stage(edit_dir, "planning", "Mantendo o video inteiro…", 38)
        ranges = [{
            "source": source_key,
            "start": 0.0,
            "end": round(float(dur), 3),
            "beat": "HOOK",
            "quote": "",
            "reason": "sem cortes",
            "gain_db": 0.0,
        }]
        llm_meta = {"ok": True, "backend": "sem_cortes"}
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
        # O caminho de varias fontes decide o corte sem IA (juncao dos takes)
        # e por isso nunca teve titulo: 18 de 18 jobs sairam com as primeiras
        # palavras da fala como nome. Pede-se SO a headline — o corte nao muda,
        # e falha vira o comportamento antigo, nunca um render caido.
        try:
            sys.path.insert(0, str(HELPERS))
            from llm_cut_plan import headline_apenas  # type: ignore

            hl = headline_apenas(cut_spoken_join, preset)
            if hl.get("headline"):
                llm_meta["headline"] = hl["headline"]
                llm_meta["headlineAlts"] = hl.get("headlineAlts") or []
                llm_meta["headlineBackend"] = hl.get("backend")
        except Exception as e:  # noqa: BLE001
            print(f"[multi] headline avulsa indisponivel: {str(e)[:80]}", flush=True)

    if not ranges:
        raise NeedsReview("no_speech", "nenhum trecho de fala para cortar")

    # Nivelamento: DEPOIS de todos os ranges decididos (plano da IA,
    # heuristica ou juncao de takes) e antes do corte. Fica fora do `else`
    # de proposito — vale para todo caminho —, e por isso mesmo NAO pode
    # levar junto nada do bloco de varias fontes: na 3.18 este `if` engoliu
    # o bloco do multi-take por indentacao e todo render de fonte unica
    # passou a sobrescrever llm_meta (o guard_ranges voltava a mexer no
    # corte que o usuario salvou no preview) e a repedir a headline.
    if ranges and intent_mode not in ("intact",):
        _n_eq = _equilibrar_ganhos(ranges, vozes_por_fonte)
        if _n_eq:
            _RENDER_META["nivelAjustado"] = _n_eq

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

    ranges = _aparar_fora_da_fonte(ranges, duracoes_por_fonte)
    if not ranges:
        raise NeedsReview(
            "no_speech",
            "todos os trechos pediam tempo que as fontes nao tem")

    if not allow_landscape and intent_mode not in ("complete", "intact"):
        total_keep = sum(max(0.0, float(r["end"]) - float(r["start"])) for r in ranges)
        if total_keep > max_dur:
            raise NeedsReview(
                "out_of_format",
                f"corte estimado {total_keep:.0f}s acima do limite {max_dur}s — reduza takes",
            )

    try:
        from app.corte_relatorio import gerar as _gerar_relatorio

        _gerar_relatorio(edit_dir, duration_s=dur, ranges=ranges,
                         stem=primary.stem, mode=intent_mode or "dynamic",
                         backend=llm_meta.get("backend"))
    except Exception as e:  # noqa: BLE001 - relatorio nunca derruba o render
        print(f"[relatorio] indisponivel: {str(e)[:80]}", flush=True)

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
            and not _layout_pede_remotion(preset.get("edit"))
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
    _music_via: dict = {}
    music_tmp = edit_dir / "_trilha_ai.mp3"
    music_tmp.unlink(missing_ok=True)
    music_vibe = _music_vibe_for(preset, is_longform,
                                 semente=edit_dir.parent.name)
    if elems.get("musicAI"):
        # O J-cut e o polimento só ENCURTAM a timeline, então a duração
        # planejada é >= a final e a trilha nunca sai curta (+2s de margem).
        planned_keep = sum(
            max(0.0, float(r.get("end") or 0) - float(r.get("start") or 0))
            for r in ranges
        )
        # REAPROVEITA a trilha do render anterior: cada geracao custa
        # creditos do ElevenLabs, e "refazer a Fase 2" gerava musica NOVA
        # toda vez — foi assim que 346k creditos do plano do usuario
        # evaporaram em dias (26/08: refazeres + Gerar 5 versoes, uma
        # trilha cobrada por rodada). So gera de novo se nao ha trilha, se
        # o corte ficou mais LONGO que ela, ou se o clima (vibe) mudou.
        trilha_antiga = edit_dir / "remotion" / "public" / "trilha.mp3"
        vibe_antigo = ""
        try:
            vibe_antigo = (trilha_antiga.with_suffix(".vibe.txt")
                           .read_text(encoding="utf-8").strip())
        except OSError:
            pass
        reuso = False
        if (trilha_antiga.is_file()
                and trilha_antiga.stat().st_size > 100_000
                and vibe_antigo == music_vibe.strip()):
            try:
                pr = subprocess.run(
                    [_ffprobe_exe(), "-v", "error", "-show_entries",
                     "format=duration", "-of", "csv=p=0",
                     str(trilha_antiga)],
                    capture_output=True, text=True, timeout=30)
                dur_antiga = float((pr.stdout or "0").strip() or 0)
            except (OSError, ValueError, subprocess.SubprocessError):
                dur_antiga = 0.0
            if dur_antiga + 0.5 >= planned_keep:
                shutil.copy2(trilha_antiga, music_tmp)
                reuso = True
                print(f"[7/9] soundtrack REAPROVEITADA do render anterior "
                      f"({dur_antiga:.0f}s >= {planned_keep:.0f}s) — sem "
                      "gasto de créditos", flush=True)
        if planned_keep >= 3 and not reuso:
            _pref_musica = _preferencia_motor_musica()

            def _music_worker() -> None:
                pronto = lambda: (music_tmp.exists()  # noqa: E731
                                  and music_tmp.stat().st_size > 1000)
                segundos = int(planned_keep) + 2

                def _nuvem() -> None:
                    _helper("elevenlabs_music.py", music_vibe,
                            "-o", str(music_tmp),
                            "--length-sec", str(segundos), check=False)

                def _local() -> None:
                    if _tentar_musicgen(music_tmp, music_vibe, segundos,
                                        edit_dir.parents[1],
                                        tentativas=_MOTOR_TENTATIVAS):
                        _music_via["motor"] = True
                        print("[7/9] trilha composta pelo MOTOR LOCAL "
                              "(MusicGen)", flush=True)

                # "local": a IA da propria maquina compoe primeiro — nao
                # gasta credito nenhum e a nuvem vira reserva. "nuvem": so
                # ElevenLabs. "auto" (padrao): nuvem primeiro, local de
                # reserva. Em todos, a biblioteca fecha a fila la no [7/9].
                if _pref_musica == "local":
                    _local()
                    if not pronto():
                        _nuvem()
                elif _pref_musica == "nuvem":
                    _nuvem()
                else:
                    _nuvem()
                    if not pronto():
                        _local()

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
        _recolher_marcos_do_corte(_helper("render.py", *render_args))
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
    _gravar_diagnostico_do_corte(edit_dir, vdata)

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
            # SEMPRE vazio, nao "vazio se nao existir". O arquivo descreve as
            # cues do `stacked`; em qualquer outro estilo ele nao tem dono.
            # Deixar o antigo no lugar fazia o motor proprio desenhar o
            # stacked POR CIMA do karaoke num projeto que ja tinha sido
            # renderizado em stacked e depois trocou de estilo (medido:
            # 2,557 de tinta contra o template, com as duas legendas na
            # tela).
            (public / "caption-cues.json").write_text("[]", encoding="utf-8")
        # ABERTURA SO COM A MANCHETE: o usuario escolheu que a legenda espera
        # a manchete sair. Roda depois das cues existirem, e vale para os dois
        # motores (ambos leem caption-cues.json).
        if str(preset.get("legendaAposHeadline") or "").lower() in (
                "1", "true", "sim", "yes") or preset.get("legendaAposHeadline") is True:
            try:
                _legenda_comeca_depois(
                    public, _hook_end_sec(
                        str(preset.get("headline") or "outline"), preset, duration))
            except Exception as e:  # noqa: BLE001 - legenda nunca derruba render
                print(f"[legenda] inicio nao ajustado: {str(e)[:70]}", flush=True)

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
        # Ultima rede do titulo. `headline_preservada` so reaproveita o que um
        # render anterior GRAVOU -- e projeto de antes da 2.62 nunca gravou
        # (o primeiro render caiu no KeyError 'viral'). Visto nos jobs reais
        # de 24/08: dois `manual_edl` sairam com titulo cru mesmo com a
        # preservacao no lugar, porque nao havia nada preservado. Pede-se so o
        # titulo, pela mesma rede do plano; `headline_apenas` nunca levanta.
        #
        # O modo LEVE tambem entra. A primeira versao o excluia alegando que a
        # tela promete "sem IA" -- leitura errada: a tela diz "Sem IA mexendo
        # NO CORTE", e o proprio comentario do modo diz "Headline e legenda da
        # Fase 2 seguem normais". O corte continua 100% heuristico; so o
        # titulo sai escrito. Um job real do usuario (24/08 17:10) saiu com
        # titulo cru por causa da exclusao.
        if not llm_meta.get("headline"):
            try:
                from llm_cut_plan import headline_apenas  # type: ignore

                hl_av = headline_apenas(cut_spoken, preset)
                if hl_av.get("headline"):
                    llm_meta = dict(llm_meta)
                    llm_meta["headline"] = hl_av["headline"]
                    llm_meta["headlineAlts"] = hl_av.get("headlineAlts") or []
                    llm_meta["headlineBackend"] = hl_av.get("backend")
                    # Grava o avulso na memoria do projeto. Sem isto o proximo
                    # reprocesso chamaria a IA de novo -- e o titulo poderia
                    # MUDAR entre reprocessos, que e justamente o que a
                    # preservacao existe para impedir. Visto na validacao de
                    # 24/08: o titulo saiu certo e o headline_ia.json ficou
                    # vazio.
                    llm_meta = headline_preservada(edit_dir, llm_meta)
            except Exception as e:  # noqa: BLE001
                print(f"[ia] ultima rede do titulo indisponivel: {str(e)[:80]}",
                      flush=True)
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
    midia_do_editor(edit_dir, public, edit_data)
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
            if _music_via.get("motor"):
                _RENDER_META["musicaFonte"] = "motor: MusicGen local"
        else:
            # Antecipada falhou (rede/planned<3s) — chamada síncrona antiga.
            _mproc = _helper(
                "elevenlabs_music.py", music_vibe,
                "-o", str(trilha),
                "--length-sec", str(int(duration) + 2),
                check=False,
            )
            if not trilha.exists():
                _mtxt = ((_mproc.stderr or "") + (_mproc.stdout or ""))
                if "insufficient_credits" in _mtxt or "payment_required" in _mtxt:
                    _RENDER_META["musicaSkip"] = (
                        "créditos do ElevenLabs esgotados — renove o plano")
                else:
                    _RENDER_META["musicaSkip"] = (
                        "geração falhou: " + _mtxt.strip()[-140:]
                        if _mtxt.strip() else "geração falhou (sem detalhe)")
                if (_preferencia_motor_musica() != "nuvem"
                        and _tentar_musicgen(trilha, music_vibe,
                                             int(duration) + 2,
                                             edit_dir.parents[1])):
                    _RENDER_META.pop("musicaSkip", None)
                    _RENDER_META["musicaFonte"] = "motor: MusicGen local"
                    print("[7/9] trilha composta pelo MOTOR LOCAL "
                          "(MusicGen)", flush=True)
                try:
                    from app.content_type import normalize_content_type
                    _ct_bib = "longform" if is_longform else (
                        normalize_content_type(preset.get("contentType"))
                        or "")
                except Exception:
                    _ct_bib = ""
                if not trilha.exists():
                    _nome_bib = _trilha_da_biblioteca(
                        trilha, float(duration), _ct_bib,
                        raiz_projetos=edit_dir.parents[1])
                else:
                    _nome_bib = None
                if _nome_bib:
                    _RENDER_META.pop("musicaSkip", None)
                    _RENDER_META["musicaFonte"] = _nome_bib
                    print(f"[7/9] trilha da BIBLIOTECA: {_nome_bib}",
                          flush=True)
                elif not trilha.exists():
                    # so quando NADA salvou a trilha — com o motor tendo
                    # composto, o musicaSkip ja foi removido e nao ha o
                    # que anexar (KeyError, pego em revisao 26/08)
                    _RENDER_META["musicaSkip"] += (
                        " · plano B: deixe MP3s em "
                        "ATIVAVID/Biblioteca/Trilhas")
        if trilha.exists():
            try:
                trilha.with_suffix(".vibe.txt").write_text(
                    music_vibe.strip(), encoding="utf-8")
            except OSError:
                pass
            # Trilha NOVA (nao reaproveitada e nao vinda da biblioteca) vai
            # para o acervo com a etiqueta do clima deste video.
            _fonte_atual = str(_RENDER_META.get("musicaFonte") or "")
            if not reuso and not (_fonte_atual
                                  and not _fonte_atual.startswith("motor:")):
                try:
                    from app.content_type import normalize_content_type
                    _ct_arq = "longform" if is_longform else (
                        normalize_content_type(preset.get("contentType"))
                        or "")
                except Exception:
                    _ct_arq = ""
                _arquivar_trilha(
                    trilha, _ct_arq, edit_dir.parents[1],
                    "mg" if _fonte_atual.startswith("motor:") else "ia")
            edit_data["soundtrack"]["enabled"] = True
            (public / "edit-data.json").write_text(
                json.dumps(edit_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            music = False
            _RENDER_META.setdefault(
                "musicaSkip", "geração falhou (sem detalhe)")
            print(f"[7/9] SEM trilha: {_RENDER_META['musicaSkip']}",
                  flush=True)
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
                        _RENDER_META["overlayUmaPassadaFalhou"] = (
                            (ov_result or {}).get("onePassFail"))
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
                        # Prazo por quadro. O padrao do Remotion (30s) mata o
                        # render inteiro quando UM quadro demora — e demorar e
                        # normal aqui: a maquina do usuario edita video com o
                        # Chrome e o Cursor abertos, e o quadro pede decode de
                        # 4K HDR. Visto em 29/08: render de 3,5min morreu em
                        # "delayRender ... nao liberado apos 28000ms" buscando
                        # UM quadro do cut.mp4, com a maquina ocupada. Teto
                        # alto nao atrasa render saudavel: ele so muda quanto
                        # tempo se espera antes de desistir.
                        "--timeout=120000",
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

            _au_final = garantir_true_peak(final)
            # A medicao de DEPOIS do conserto tem de ir para a ficha. Sem
            # isto ela guardava o pico que o caminho rapido mediu ANTES de
            # cair: o job de 27/08 ficou registrado em -0,7 dBTP com o
            # arquivo entregue em -1,3. Uma varredura nos proprios dados
            # concluiu "14 videos estourados" que nao existiam — a ficha
            # tem de dizer o que foi ENTREGUE, nao o que se tentou.
            if _au_final.get("truePeakDb") is not None:
                _RENDER_META["truePeak"] = _au_final.get("truePeakDb")
            if _au_final.get("integratedLufs") is not None:
                _RENDER_META["LUFS"] = _au_final.get("integratedLufs")
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
            mode=intent_mode or "dynamic",
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
