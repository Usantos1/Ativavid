"""Render a video from an EDL.

Implements the HEURISTICS render pipeline in the correct order:

  1. Per-segment extract with color grade + 30ms audio fades baked in
  2. Lossless -c copy concat into base.mp4
  3. If overlays or subtitles: single filter graph that overlays animations
     (with PTS shift so frame 0 lands at the overlay window start)
     and applies `subtitles` filter LAST → final.mp4

Optionally builds a master SRT from the per-source transcripts + EDL
output-timeline offsets, applies the proven force_style (2-word
UPPERCASE chunks, Helvetica 18 Bold, MarginV=35).

Usage:
    python helpers/render.py <edl.json> -o final.mp4
    python helpers/render.py <edl.json> -o preview.mp4 --preview
    python helpers/render.py <edl.json> -o final.mp4 --build-subtitles
    python helpers/render.py <edl.json> -o final.mp4 --no-subtitles
"""

from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import atexit
import contextlib
import functools
import json
import math
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ffprobe_util import first_record, parse_rate  # mesma pasta

try:
    from grade import get_preset, auto_grade_for_clip  # same directory
except Exception:
    def get_preset(name: str) -> str:
        return ""

    def auto_grade_for_clip(video, start=0.0, duration=None, verbose=False):  # type: ignore
        return "eq=contrast=1.03:saturation=0.98", {}


_ENCODER_CACHE: str | None = None

# Remotion OffthreadVideo seeks by keyframe. Segment concat used to leave
# 5–8s GOPs (one keyframe per take), which fails mid-clip under memory pressure
# with "No frame found at position …". Force ~1s GOPs on every encoder.
_SEEKABLE_GOP = ["-g", "30"]

_WIN_HIDE = 0
if sys.platform == "win32":
    _WIN_HIDE = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)


def _run(cmd, **kwargs):
    """subprocess.run that does not flash a CMD window on Windows."""
    if _WIN_HIDE and "creationflags" not in kwargs:
        kwargs["creationflags"] = _WIN_HIDE
    return subprocess.run(cmd, **kwargs)


def _run_ffmpeg(cmd: list[str], *, label: str = "ffmpeg") -> None:
    """Roda ffmpeg com stderr em arquivo (binário), não em PIPE de texto.

    O deadlock clássico é Popen(stdout=PIPE, stderr=PIPE) + wait() sem ler.
    subprocess.run(..., capture_output=True) usa communicate() e não trava
    por buffer cheio. O incidente real aqui foi outro: HDR/tonemap gera
    megabytes de log; stderr=PIPE + text mode no Windows chegou a [Errno 22]
    e o worker matou o filho com stderr vazio. Arquivo binário evita isso
    e guarda o log se o processo for morto.
    """
    import tempfile

    fd, err_name = tempfile.mkstemp(suffix=".fferr", prefix="ativavid_")
    err_path = Path(err_name)
    try:
        # Binary: ffmpeg escreve bytes; text mode no Windows → Errno 22.
        with os.fdopen(fd, "wb") as errf:
            proc = _run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=errf)
        if proc.returncode != 0:
            raise RuntimeError(
                f"{label} falhou (exit {proc.returncode}):\n{_ffmpeg_err_tail(err_path)}"
            )
    finally:
        try:
            err_path.unlink(missing_ok=True)
        except OSError:
            pass


def _ffmpeg_err_tail(err_path: Path) -> str:
    try:
        raw = err_path.read_bytes()
    except OSError:
        return "(sem stderr)"
    err = raw.decode("utf-8", errors="replace").strip()
    if not err:
        return "(sem stderr)"
    return "\n".join(err.splitlines()[-16:])


def _encoder_works(name: str, extra: list[str]) -> bool:
    """Real open-encoder probe — `-encoders` lists nvenc even when the driver is too old."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "color=c=black:s=1280x720:d=0.04",
        "-frames:v", "1", "-an",
        "-c:v", name, *extra,
        "-f", "null", "-",
    ]
    try:
        r = _run(
            cmd, capture_output=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pick_video_encoder() -> tuple[str, list[str]]:
    """Prefer a GPU encoder that actually opens; else libx264.

    Returns (name, extra_args_after_-c:v). Decisão centralizada em render_engine.
    """
    global _ENCODER_CACHE
    try:
        from app.render_engine import encoder_args

        name, extra = encoder_args()
        _ENCODER_CACHE = name
        return name, extra
    except Exception:
        pass
    if _ENCODER_CACHE is None:
        try:
            r = _run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
            blob = (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.SubprocessError):
            blob = ""
        candidates: list[tuple[str, list[str]]] = []
        if "h264_nvenc" in blob:
            candidates.append((
                "h264_nvenc",
                ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"],
            ))
        if "h264_qsv" in blob:
            candidates.append((
                "h264_qsv",
                ["-preset", "medium", "-global_quality", "23", "-pix_fmt", "nv12"],
            ))
        if "h264_amf" in blob:
            candidates.append((
                "h264_amf",
                ["-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24", "-pix_fmt", "yuv420p"],
            ))
        chosen = "libx264"
        for name, extra in candidates:
            if _encoder_works(name, extra):
                chosen = name
                break
        _ENCODER_CACHE = chosen
        if chosen == "libx264" and candidates:
            print(
                f"  note: GPU encoder indisponível ({candidates[0][0]}) — usando libx264",
                flush=True,
            )
    name = _ENCODER_CACHE or "libx264"
    if name == "h264_nvenc":
        return name, ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p", *_SEEKABLE_GOP]
    if name == "h264_qsv":
        return name, ["-preset", "medium", "-global_quality", "23", "-pix_fmt", "nv12", *_SEEKABLE_GOP]
    if name == "h264_amf":
        return name, [
            "-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "24",
            "-pix_fmt", "yuv420p", *_SEEKABLE_GOP,
        ]
    return "libx264", ["-g", "30", "-keyint_min", "15"]

# -------- Subtitle style (bold-overlay, proven at 1920×1080 and 1080×1920) --
#
# MarginV is NOT taste — it is a platform safe-zone rule.
# TikTok / IG Reels / Shorts UI (caption, username, music, right-rail actions)
# covers roughly the bottom ~25–30% of a 1080×1920 frame. Captions placed near
# the bottom edge get clipped or obscured by the UI. libass auto-scales the
# render canvas relative to PlayResY=288, so MarginV=90 lands the caption
# baseline roughly 30% up from the bottom on any aspect — clear of the UI on
# every major vertical-video platform. Do not drop this below ~75 without a
# specific reason.
SUB_FORCE_STYLE = (
    "FontName=Helvetica,FontSize=18,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H00000000,"
    "BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=90"
)

# -------- Helpers ------------------------------------------------------------


def run(cmd: list[str], quiet: bool = False) -> None:
    if not quiet:
        print(f"  $ {' '.join(str(c) for c in cmd[:6])}{' …' if len(cmd) > 6 else ''}")
    _run(cmd, check=True)


# -------- Duplicate-invocation guard -----------------------------------------
#
# Two agent sessions (or one session retrying after what LOOKS like a hang, but
# is actually just a slow render) can end up launching render.py on the SAME
# EDL/output pair at once. Nothing downstream notices: both invocations extract
# the same segments into the same clips_graded/ dir, both write the same
# base.mp4, and whichever finishes last silently "wins" — burning CPU/IO for
# the one that lost while looking to a human like the render is just slow.
# A pidfile next to the requested output makes the second invocation bail
# immediately with a clear reason instead of racing the first.


# Renders that hang (ffmpeg wait, driver stall, etc.) leave a live PID + lock
# forever and block every retry. After this age the lock is treated as hung
# and reclaimed (the old PID is asked to exit when possible).
_RENDER_LOCK_STALE_S = 45 * 60


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID is currently running (Windows + POSIX)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours to signal
    return True


def _pid_owns_render(pid: int, out_path: Path) -> bool:
    """True só se o PID vivo for um render.py deste cut (evita PID reusado)."""
    if not _pid_alive(pid):
        return False
    if os.name != "nt":
        return True
    try:
        import subprocess

        kw = {}
        try:
            from app.win_process import hide_console_kwargs  # type: ignore

            kw = hide_console_kwargs()
        except Exception:
            pass
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\").CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            **kw,
        )
        cmd = (r.stdout or "").strip().lower()
        if not cmd:
            return False
        if "render.py" not in cmd:
            return False
        # mesmo cut / mesma pasta edit
        needle = str(out_path).lower().replace("/", "\\")
        stem = out_path.stem.lower()  # cut
        return needle in cmd.replace("/", "\\") or f"\\{stem}.mp4" in cmd.replace("/", "\\")
    except Exception:
        # se não der pra inspecionar, assume dono (seguro: evita corrida)
        return True


def _terminate_pid(pid: int) -> None:
    """Best-effort kill of a hung render owner (never raises)."""
    if pid <= 0 or pid == os.getpid():
        return
    try:
        if os.name == "nt":
            import subprocess

            _run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        else:
            os.kill(pid, 9)
    except OSError:
        pass


def acquire_render_lock(out_path: Path) -> None:
    """Claim `<out_path>.lock`, or exit with a clear message if another live
    render.py already owns this output. A stale lock (dead PID or hung past
    ``_RENDER_LOCK_STALE_S``) is reclaimed automatically; the lock is released
    on interpreter exit either way.

    Creation is atomic (O_CREAT|O_EXCL) so two launches in the same second
    cannot both pass a non-atomic exists()+write race.
    """
    lock_path = out_path.with_name(out_path.name + ".lock")

    def _release() -> None:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                lock_path.unlink()
        except OSError:
            pass

    def _try_create() -> bool:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            fd = os.open(str(lock_path), flags, 0o644)
        except FileExistsError:
            return False
        try:
            os.write(fd, str(os.getpid()).encode("utf-8"))
        finally:
            os.close(fd)
        return True

    for _attempt in range(4):
        if _try_create():
            atexit.register(_release)
            return
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            old_pid = None
        try:
            age_s = max(0.0, time.time() - lock_path.stat().st_mtime)
        except OSError:
            age_s = 0.0
        owns = bool(
            old_pid
            and old_pid != os.getpid()
            and _pid_owns_render(old_pid, out_path)
        )
        if owns and age_s < _RENDER_LOCK_STALE_S:
            sys.exit(
                f"render.py já está rodando para {out_path.name} (pid {old_pid}) — "
                "recusando iniciar um segundo render duplicado. Cancele na Fila "
                "ou espere o corte atual terminar."
            )
        if owns:
            print(
                f"[warn] lock de {out_path.name} travado há {int(age_s // 60)} min "
                f"(pid {old_pid}) — encerrando e reclamando",
                flush=True,
            )
            _terminate_pid(old_pid)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        time.sleep(0.05)

    sys.exit(
        f"não consegui o lock de {out_path.name} — outro render ainda está disputando o arquivo"
    )


def resolve_grade_filter(grade_field: str | None) -> str:
    """The EDL's 'grade' field can be a preset name, a raw ffmpeg filter, or 'auto'.

    Returns the filter string to embed into the per-segment -vf chain.
    For 'auto', returns the sentinel "__AUTO__" which is resolved per-segment.
    """
    if not grade_field:
        return ""
    if grade_field == "auto":
        return "__AUTO__"
    # Preset names are short identifiers, filter strings contain '=' or ','.
    if re.fullmatch(r"[a-zA-Z0-9_\-]+", grade_field):
        try:
            return get_preset(grade_field)
        except KeyError:
            print(f"warning: unknown preset '{grade_field}', using as raw filter")
            return grade_field
    return grade_field


def resolve_path(maybe_path: str, base: Path) -> Path:
    """Resolve a path that may be absolute or relative to `base`."""
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return (base / p).resolve()


# extract_segment probes the same source ~6x per call and a J-cut EDL calls it
# twice per range, so a 30-cut render spawns hundreds of identical ffprobes
# (100-300ms each on Windows). The source never changes mid-run, so results are
# cached per (path, mtime, size); a file we can't stat falls through uncached.
def _memo_by_stat(fn):
    cache: dict[tuple, object] = {}

    @functools.wraps(fn)
    def wrapper(video: Path, *args, **kwargs):
        try:
            st = Path(video).stat()
        except OSError:
            return fn(video, *args, **kwargs)
        key = (str(video), st.st_mtime_ns, st.st_size,
               args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = fn(video, *args, **kwargs)
        return cache[key]

    return wrapper


@_memo_by_stat
def probe_duration(video: Path) -> float:
    r = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True,
    )
    return float((r.stdout or "").strip() or 0.0)


# -------- HDR → SDR tone mapping (HLG / PQ sources) --------------------------
#
# iPhone defaults to HLG HDR in Rec.2020 (and many mirrorless cameras ship PQ).
# If the source is HDR and we only downconvert bit depth (yuv420p10le → yuv420p)
# without tone-mapping, the output is 8-bit but still carries HLG/PQ transfer
# metadata. Players that honor the metadata (screen recorders, most social
# upload re-encodes) interpret 8-bit values in an HDR container and the result
# looks oversaturated / blown out. QuickTime on macOS can hide this locally —
# screen recording and uploaded renders cannot.
#
# Fix: detect HDR via color_transfer and prepend a zscale+tonemap chain to the
# vf graph so the output is clean Rec.709 SDR.

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}  # PQ (HDR10) and HLG

TONEMAP_CHAIN = (
    "zscale=t=linear:npl=100,"
    "format=gbrpf32le,"
    "zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,"
    "format=yuv420p"
)


@_memo_by_stat
def _color_tags(video: Path) -> dict[str, str]:
    """Read the source's color tags (empty strings when absent/unknown)."""
    try:
        out = _run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer,color_primaries,color_space,color_range",
             "-of", "default=noprint_wrappers=1", str(video)],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        # Sem as tags, `is_hdr_source` diz False e o TONEMAP e pulado: fonte
        # HDR sai lavada. O padrao continua o mesmo — mas agora com aviso, em
        # vez de imagem errada sem explicacao.
        print(f"  [warn] tags de cor de {Path(video).name}: {e} — "
              f"seguindo como SDR (sem tonemap)", flush=True)
        return {}
    tags = {}
    for line in out.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            tags[k.strip()] = "" if v in ("unknown", "N/A") else v
    return tags


def is_hdr_source(video: Path) -> bool:
    """Return True if the source uses a PQ or HLG transfer function."""
    return _color_tags(video).get("color_transfer", "") in HDR_TRANSFERS


# Wide-gamut SDR (BT.2020 primaries with an ordinary transfer) is NOT caught by
# is_hdr_source — phone/mirrorless cameras routinely write bt2020 primaries with
# color_transfer=unknown. Left unconverted, cut.mp4 inherits the bt2020 tags and
# every downstream decoder re-interprets them: Chrome (which Remotion composites
# through) darkens the image by roughly a 1.2 gamma and shifts hue, so the Phase-2
# render no longer matches the Phase-1 grade the user approved. Convert to Rec.709
# at extraction so exactly one interpretation exists from the grade onwards.
WIDE_GAMUT_PRIMARIES = {"bt2020"}
WIDE_GAMUT_MATRICES = {"bt2020nc", "bt2020_ncl", "bt2020c", "bt2020_cl"}


def wide_gamut_chain(video: Path) -> str:
    """Filter chain converting a wide-gamut SDR source to Rec.709, or ''.

    Returns '' for HDR sources (TONEMAP_CHAIN already lands on Rec.709) and for
    sources that are already Rec.709 or untagged.
    """
    if is_hdr_source(video):
        return ""
    tags = _color_tags(video)
    primaries = tags.get("color_primaries", "")
    matrix = tags.get("color_space", "")
    if primaries not in WIDE_GAMUT_PRIMARIES and matrix not in WIDE_GAMUT_MATRICES:
        return ""
    in_range = "pc" if tags.get("color_range", "") == "pc" else "tv"
    # itrc: bt2020-10 is the SDR BT.2020 transfer; it matches Rec.709's curve, so
    # this converts the gamut without altering the tone curve the grade was cut on.
    return (
        f"colorspace=ispace={matrix or 'bt2020nc'}:iprimaries={primaries or 'bt2020'}"
        f":itrc=bt2020-10:irange={in_range}"
        ":space=bt709:primaries=bt709:trc=bt709:range=tv"
    )


@_memo_by_stat
def is_portrait_source(video: Path) -> bool:
    """Return True if the video DISPLAYS as portrait (height > width).

    Phone/mirrorless footage is often stored landscape (e.g. 3840×2160) with a
    ±90° display-matrix rotation, which ffmpeg auto-applies on decode. Reading
    only the raw stream dims would call such a clip landscape and scale it to
    the wrong size, so we swap dims when the rotation is ±90°/±270°.
    """
    try:
        out = _run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, check=True,
        )
        # first_record: com stream group o ffprobe repete o bloco e o
        # split(",") cru pegava valor colado do segundo. Caia no except
        # e respondia False em silencio.
        parts = first_record(out.stdout).split(",")
        w, h = int(parts[0]), int(parts[1])
    except Exception:
        return False

    rot = 0
    try:
        r = _run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream_side_data=rotation",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True,
        )
        vals = [v for v in r.stdout.split() if v.lstrip("-").isdigit()]
        if vals:
            rot = int(vals[0])
    except Exception as e:  # noqa: BLE001
        # Sem rotacao lida, a escala pode sair pelo lado errado numa fonte
        # girada — o prep fica deitado ou cortado. `vals` vazio NAO e falha
        # (video sem rotacao e o caso comum), por isso o aviso mora aqui.
        print(f"  [warn] rotacao de {Path(video).name}: {e} — assumindo 0", flush=True)
    if abs(rot) % 180 == 90:
        w, h = h, w
    return h > w


@_memo_by_stat
def source_fps(video: Path) -> float:
    """Return the source's video frame rate (frames per second).

    Reads r_frame_rate ("30000/1001") and evaluates the fraction. Returns 0.0
    if it can't be determined, so callers fall back to the safe default.
    """
    try:
        out = _run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        )
        return parse_rate(first_record(out.stdout), default=0.0)
    except Exception:
        return 0.0


def shortform_target_fps(video: Path) -> str:
    """Short-form render fps as a string for ffmpeg `-r`.

    Rule: sources shot at 30fps or higher render at 30 (keeps motion natural and
    matches Instagram/TikTok/Shorts capture); slower sources keep the 24 standard.
    """
    return "30" if source_fps(video) >= 29.5 else "24"


def _auto_extract_jobs() -> int:
    """Parallel extraction slots when --jobs isn't given.

    The app exports the performance profile's choice as ATIVAVID_EXTRACT_JOBS
    (Econômico=1, Balanceado≈cores/3, Desempenho≈cores/2); honoring it here is
    what makes the profile actually change extraction. Standalone runs keep the
    historical cores/3 heuristic, capped at 4.
    """
    try:
        n = int(os.environ.get("ATIVAVID_EXTRACT_JOBS", "0"))
        if n > 0:
            return n
    except ValueError:
        pass
    return max(1, min(4, (os.cpu_count() or 4) // 3))


# -------- Per-segment extraction (Rule 2 + Rule 3) --------------------------


_PREP_VER = "2"   # v2: o prep passou a descartar quadro antes do tonemap


def _fps_cedo(source: Path) -> str:
    """fps a por na FRENTE da cadeia, ou "" quando nao ha quadro a descartar.

    Vale para os dois lugares que montam uma cadeia short-form: o prep e o
    extract de cada segmento. Nos dois o alvo e sempre 30 ou 24 — nunca os 60
    da fonte — e nos dois o `-r` da saida so joga o quadro fora DEPOIS de
    escalar, tonemapar, graduar e (no extract) aplicar o zoom nele. Posto na
    frente, o quadro descartado nao custa nada.

    De quebra a escolha do quadro fica REGULAR: o `-r` da saida pega os
    primeiros quadros em sequencia e os exibe espacados, o que da meia
    velocidade no comeco de cada segmento (medido: 0,1,2,3,5,7,9... contra
    0,2,4,6,8...).
    """
    # Interruptor, no mesmo estilo do ATIVAVID_PREP_SOURCE=0: serve para o
    # A/B da medicao e como escape se a maquina de alguem reagir mal. O nome
    # antigo continua valendo — foi publicado no CHANGELOG da v2.32.
    if (os.environ.get("ATIVAVID_FPS_CEDO", "").strip() == "0"
            or os.environ.get("ATIVAVID_PREP_FPS", "").strip() == "0"):
        return ""
    alvo = shortform_target_fps(source)
    try:
        fonte = source_fps(source)
    except Exception:  # noqa: BLE001 - sonda falhou: melhor nao mexer
        return ""
    return alvo if fonte > float(alvo) + 0.5 else ""


def _prep_key(source: Path, scale: str, grade_filter: str) -> str:
    """Assinatura do que foi embutido no arquivo preparado."""
    st = source.stat()
    blob = "|".join([
        _PREP_VER, str(st.st_size), str(int(st.st_mtime)),
        scale, TONEMAP_CHAIN, grade_filter or "", _fps_cedo(source),
    ])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def prepare_sources_parallel(
    nomes: set[str], resolve, scale_for, grade_filter: str,
) -> dict[str, "Path | None"]:
    """Prepara VARIAS fontes ao mesmo tempo (2 por vez).

    Um x2 real do usuario tinha duas fontes 4K60 HDR e o prep sequencial
    dominava o CUT (~370s de 565s). O tonemap de UMA instancia nao satura os
    4 nucleos, entao duas instancias se sobrepoem de verdade. Mais de 2 por
    vez briga com o proprio ffmpeg e com o NVENC — nao vale.
    """
    from concurrent.futures import ThreadPoolExecutor

    out: dict[str, Path | None] = {}
    if not nomes:
        return out

    sozinho = len(nomes) == 1

    def _um(nome: str) -> tuple[str, Path | None]:
        sp = resolve(nome)
        try:
            return nome, prepared_source(sp, scale_for(sp), grade_filter,
                                         permitir_nvdec=sozinho)
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] fonte preparada de {nome}: {e}", flush=True)
            return nome, None

    if len(nomes) == 1:
        n, v = _um(next(iter(nomes)))
        return {n: v}
    with ThreadPoolExecutor(max_workers=2) as pool:
        for n, v in pool.map(_um, sorted(nomes)):
            out[n] = v
    return out


_NVDEC_LOCK = Path(tempfile.gettempdir()) / "ativavid-nvdec.lock"
_NVDEC_STALE_S = 60 * 20        # prep travado nao pode bloquear para sempre


@contextlib.contextmanager
def _reservar_nvdec():
    """Cede o NVDEC a UM prep por vez na maquina inteira.

    Rende True para quem pegou e False para quem nao pegou — quem nao pegou
    decodifica na CPU em vez de esperar (medido: dois NVDEC juntos custam
    98,7s contra 89,8s de um GPU + um CPU).

    A criacao e atomica (O_CREAT|O_EXCL); lock de PID morto ou velho demais e
    tomado, senao um prep que morreu no meio deixaria a GPU inutilizada.
    """
    fd = None
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            fd = os.open(str(_NVDEC_LOCK), flags, 0o644)
        except FileExistsError:
            velho = None
            try:
                dono = int(_NVDEC_LOCK.read_text(encoding="utf-8").split()[0])
                idade = time.time() - _NVDEC_LOCK.stat().st_mtime
                velho = (not _pid_alive(dono)) or idade > _NVDEC_STALE_S
            except (OSError, ValueError, IndexError):
                velho = True
            if not velho:
                yield False
                return
            try:
                _NVDEC_LOCK.unlink()
                fd = os.open(str(_NVDEC_LOCK), flags, 0o644)
            except OSError:
                yield False
                return
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        fd = None
        yield True
    except OSError:
        # Sem poder criar o arquivo, seguir sem NVDEC e o seguro.
        yield False
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            if (_NVDEC_LOCK.exists()
                    and _NVDEC_LOCK.read_text(encoding="utf-8").strip() == str(os.getpid())):
                _NVDEC_LOCK.unlink()
        except OSError:
            pass


def prepared_source(
    source: Path, scale: str, grade_filter: str, *, quiet: bool = False,
    permitir_nvdec: bool = True,
) -> Path | None:
    """Fonte com escala + tonemap + grade já aplicados, gerada UMA vez.

    O tonemap HDR é o passo mais caro do corte: um pipeline float32 que hoje
    roda de novo em cada segmento e em cada reprocessamento. Aplicando-o uma
    única vez sobre a fonte inteira, os segmentos passam a sair de um H.264
    8-bit barato.

    A cor é idêntica porque a ordem dos filtros (escala → tonemap → grade) é
    exatamente a mesma — só muda QUANDO são aplicados. Medido no projeto do
    usuário: 1ª execução empata com o caminho atual (297,6 s vs 294,4 s) e as
    reexecuções caem de 294,4 s para 29,7 s (9,9x).

    Devolve None quando não se aplica (fonte SDR, sem tonemap a economizar) ou
    quando algo falha — nesses casos o corte segue pelo caminho de sempre.
    """
    if os.environ.get("ATIVAVID_PREP_SOURCE", "").strip() == "0":
        return None
    if not is_hdr_source(source):
        return None  # sem tonemap, não há o que economizar
    prep = source.with_suffix(source.suffix + ".prep.mp4")
    keyf = source.with_suffix(source.suffix + ".prepkey")
    want = _prep_key(source, scale, grade_filter)
    if prep.exists() and keyf.exists():
        try:
            if keyf.read_text(encoding="utf-8").strip() == want:
                print(f"PREPARED_SOURCE HIT {source.name}", flush=True)
                return prep
        except OSError:
            pass
    print(f"PREPARED_SOURCE MISS {source.name}", flush=True)
    # Nome de temporário POR PROCESSO: dois renders construindo a mesma fonte
    # ao mesmo tempo escreveriam no mesmo arquivo e um promoveria o que o
    # outro estava escrevendo. Com pid no nome, cada um tem o seu e a
    # promoção atômica (replace) apenas escolhe um vencedor válido.
    tmp = prep.with_suffix(f".tmp{os.getpid()}.mp4")
    # `fps` na FRENTE: descartado antes de escalar e tonemapar, o quadro nao
    # custa nada. Depois do tonemap o trabalho caro ja foi feito.
    vf = ",".join([x for x in (
        (f"fps={_fps_cedo(source)}" if _fps_cedo(source) else ""),
        scale, TONEMAP_CHAIN, grade_filter) if x])
    # Qualidade alta de propósito: este arquivo é um INTERMEDIÁRIO e o corte
    # ainda será reencodado depois. A cq 19 a perda de geração medida foi
    # PSNR 35,5 dB; a cq 14 fica visualmente transparente e o arquivo é
    # temporário (some com o projeto).
    venc, _ = pick_video_encoder()
    if venc == "libx264":
        vextra = ["-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p"]
    elif "nvenc" in venc:
        vextra = ["-preset", "p4", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p"]
    else:
        vextra = ["-crf", "14", "-pix_fmt", "yuv420p"]
    def _cmd(hwaccel: bool) -> list[str]:
        # NVDEC no decode do 4K HEVC 10-bit: medido bit-IDENTICO (PSNR inf)
        # e ~15% mais rapido que decodificar na CPU. So o decode — o tonemap
        # continua na CPU, que e quem garante a cor.
        hw = ["-hwaccel", "cuda"] if hwaccel else []
        return [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *hw, "-i", str(source), "-vf", vf,
            "-c:v", venc, *vextra, "-g", "30", "-keyint_min", "15",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "copy", "-movflags", "+faststart", str(tmp),
        ]

    if not quiet:
        print(f"  preparando fonte (tonemap uma vez): {source.name}", flush=True)
    try:
        # A reserva vale para a MAQUINA: `permitir_nvdec` so conhece as fontes
        # deste job, e com parallelJobs=2 dois processos se veem sozinhos.
        with _reservar_nvdec() as tenho_gpu:
            try:
                if not (permitir_nvdec and tenho_gpu):
                    # Medido: DUAS instancias NVDEC+NVENC saturam o motor de
                    # video (98,7s contra 89,8s de um GPU + um CPU, e 89,1s do
                    # sequencial). Quem nao pegou vai de CPU, sem esperar.
                    raise RuntimeError("nvdec ocupado ou desligado")
                _run_ffmpeg(_cmd(True), label="prepared source (nvdec)")
            except Exception:  # noqa: BLE001 - sem NVDEC (ou concorrente): CPU
                tmp.unlink(missing_ok=True)
                _run_ffmpeg(_cmd(False), label="prepared source")
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] fonte preparada falhou ({e}) — seguindo pelo caminho normal", flush=True)
        tmp.unlink(missing_ok=True)
        return None
    # só aceita se a duração bater com a fonte (guarda contra arquivo truncado)
    try:
        if abs(probe_duration(tmp) - probe_duration(source)) > 0.5:
            print("  [warn] fonte preparada com duração diferente — descartada", flush=True)
            tmp.unlink(missing_ok=True)
            return None
    except Exception:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return None
    try:
        tmp.replace(prep)
        keyf.write_text(want, encoding="utf-8")
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return prep


def extract_segment(
    source: Path,
    seg_start: float,
    duration: float,
    grade_filter: str,
    out_path: Path,
    preview: bool = False,
    draft: bool = False,
    keep_resolution: bool = False,
    gain_db: float = 0.0,
    gain_windows: list | None = None,
    bleep_windows: list | None = None,
    streams: str = "av",
    zoom: dict | None = None,
    prepared: Path | None = None,
) -> None:
    """Extract a cut range as its own MP4 with grade + 30ms audio fades baked in.

    `streams` selects what lands in the file: "av" (default), "v" (video only) or
    "a" (audio only, PCM when the path ends in .wav). The split exists for the
    J-cut assembly, where a take's picture and its sound come from DIFFERENT
    ranges — trimming an already-extracted segment instead would leave the 30ms
    fade stranded mid-audio and turn the new end into a hard chop.

    `-ss` before `-i` for fast accurate seeking. Scale to 1080p from 4K.
    Portrait sources (height > width) are scaled by height to preserve orientation.

    Quality ladder:
      - final (default): 1080p libx264 fast CRF 20
      - preview:         1080p libx264 medium CRF 22 (evaluable for QC)
      - draft:           720p libx264 ultrafast CRF 28 (cut-point check only)
      - keep_resolution: source resolution + source fps (LONGFORM / 16:9 YouTube).
        Skips scaling and does not force 24 fps. Draft/preview still down-scale.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Fonte preparada: escala, tonemap e grade já estão embutidos nela, então
    # este segmento só precisa cortar (e aplicar zoom). Sem isto o tonemap
    # rodaria de novo por segmento.
    prepped = prepared is not None and prepared.exists()
    if prepped:
        source = prepared
        grade_filter = ""

    portrait = is_portrait_source(source)
    if draft:
        scale = "scale=-2:1280" if portrait else "scale=1280:-2"
    elif keep_resolution:
        scale = ""  # keep native resolution (longform)
    else:
        scale = "scale=-2:1920" if portrait else "scale=1920:-2"

    if prepped:
        # A fonte preparada já está na altura de entrega. Zera SÓ a escala:
        # mexer em keep_resolution também soltaria o fps da fonte (medido:
        # saía 60fps/1696 frames em vez de 30fps/851).
        scale = ""

    vf_parts: list[str] = []
    # Quadro fora ANTES de tudo. `-r` la embaixo tambem entrega 30fps, mas so
    # depois de escalar, graduar e dar zoom em cada um dos 60 quadros da fonte
    # — metade desse trabalho ia direto para o lixo. Numa fonte HDR o prep ja
    # resolveu isto (o arquivo preparado chega a 30fps e `_fps_cedo` devolve
    # ""), mas a fonte SDR 50/60fps nao passa pelo prep e pagava tudo.
    cedo = "" if keep_resolution or streams == "a" else _fps_cedo(source)
    if cedo:
        vf_parts.append(f"fps={cedo}")
    # Downscale FIRST, before any HDR tonemap / wide-gamut colour conversion.
    # TONEMAP_CHAIN runs a full-precision float pipeline (zscale linear-light +
    # gbrpf32le, i.e. 32-bit float, full chroma resolution, no subsampling) —
    # on a 4K portrait HLG source that's ~4x the pixels a 1080p-equivalent
    # output actually needs, and it dominates extraction time (measured: a
    # single 56s 4K HLG take split into 3 ranges took 14+ minutes with
    # tonemap-before-scale). Scaling in the source's native (gamma) domain
    # first, then tonemapping the already-small frame, is the standard cheap
    # trade-off — quality delta is invisible at short-form delivery res.
    if scale:
        vf_parts.append(scale)
    if is_hdr_source(source):
        vf_parts.append(TONEMAP_CHAIN)
    else:
        wide = wide_gamut_chain(source)
        if wide:
            vf_parts.append(wide)
    if grade_filter:
        # Force 8-bit BEFORE the grade. `colorlevels` — the backbone of the LOG
        # presets — is broken on 9–14 bit RGB: on a 10-bit source it collapses the
        # whole frame to a constant TV black (measured YAVG=64/1023, YBITDEPTH=1 on
        # an iPhone Apple Log ProRes). It is correct at 8-bit and at 16-bit, so a
        # 10-bit source silently renders black while an 8-bit one renders fine.
        # The output is `-pix_fmt yuv420p` regardless, so this costs nothing, and it
        # makes the render match the 8-bit frame the user approved in the
        # `grade.py --candidates` montage.
        vf_parts.append("format=yuv420p")
        vf_parts.append(grade_filter)
    # Zoom no mesmo encode do extract — nunca cut.mp4 → zoomed.mp4.
    # `zoom_vf` anda por `t`, não por `n`, então o descarte de quadro acima
    # não mexe na geometria do push-in — só faz ele rodar 30x em vez de 60x.
    if zoom and streams != "a" and not keep_resolution:
        fps_s = shortform_target_fps(source)
        n_frames = max(1, int(round(float(duration) * float(fps_s))))
        try:
            from app.ffmpeg_zoom import zoom_vf
        except ImportError:
            _repo = Path(__file__).resolve().parent.parent
            if str(_repo) not in sys.path:
                sys.path.insert(0, str(_repo))
            from app.ffmpeg_zoom import zoom_vf
        vf_parts.append(zoom_vf(zoom, n_frames=n_frames, fps=float(fps_s)))
    vf = ",".join(vf_parts)

    # Per-segment level match (whisper/mumble rescue). Applied BEFORE the fades
    # so the edges still land at true silence. A boosted segment gets a limiter
    # so a loud syllable inside a quiet take cannot clip after the gain.
    af_parts: list[str] = []
    # Windowed level match, applied BEFORE the flat range gain. A range holding two
    # speakers cannot be rescued by `gain_db`: the quiet one needs +7dB while the
    # close-mic one is already fine, and boosting the whole range just pushes the
    # good voice up with it. `gain_windows` lifts only the marked spans — times are
    # in SOURCE seconds and get rebased to the segment here, so a window survives a
    # re-render even if the range's start moves. Volume has timeline support, so
    # `enable=` is evaluated per frame.
    boosted = False
    for w in gain_windows or []:
        w_db = float(w.get("db", 0.0) or 0.0)
        if abs(w_db) <= 0.05:
            continue
        a = max(0.0, float(w["start"]) - seg_start)
        b = min(duration, float(w["end"]) - seg_start)
        if b - a <= 0.01:
            continue  # window falls outside this segment
        af_parts.append(f"volume={w_db:+.2f}dB:enable='between(t,{a:.3f},{b:.3f})'")
        boosted = boosted or w_db > 0
    if abs(gain_db) > 0.05:
        af_parts.append(f"volume={gain_db:+.2f}dB")
        boosted = boosted or gain_db > 0
    if boosted:
        af_parts.append("alimiter=level_in=1:level_out=1:limit=0.95")

    # Censor bleeps — a 1kHz tone REPLACING the audio inside each window. The
    # speech is muted and the tone gated by the SAME expression, so the swap is
    # sample-exact and no fragment of the word survives underneath it. Times are
    # in SOURCE seconds, like gain_windows. `sine` is a source filter, so the tone
    # is generated inside the filtergraph and needs no extra input file. Gating
    # uses volume's `eval=frame` expression rather than `enable=`, because enable
    # can only mute an existing signal — it cannot un-mute the tone.
    bleeps: list[tuple[float, float]] = []
    for w in bleep_windows or []:
        a = max(0.0, float(w["start"]) - seg_start)
        b = min(duration, float(w["end"]) - seg_start)
        if b - a > 0.005:
            bleeps.append((a, b))

    # 30ms audio fades at both edges (Rule 3) — prevent pops
    fade_out_start = max(0.0, duration - 0.03)
    fades = (f"afade=t=in:st=0:d=0.03,"
             f"afade=t=out:st={fade_out_start:.3f}:d=0.03")
    af = ",".join(af_parts + [fades])

    filter_complex = ""
    if bleeps and streams != "v":
        gate = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in bleeps)
        # Amplitude is peak-linear: 0.30 ≈ -10.5 dBFS peak / -13.5 dBFS RMS, which
        # sits just above conversational speech so the tone actually masks the word.
        # Built with `aevalsrc`, NOT `sine` — ffmpeg's sine source emits at 0.125
        # amplitude (-18 dBFS), so a level set against it is ~18 dB quieter than it
        # reads and the bleep is inaudible under the speech it is meant to cover.
        amp = float((bleep_windows or [{}])[0].get("level", 0.30) or 0.30)
        osc = f"{amp:.3f}*sin(2*PI*1000*t)"
        speech = ",".join(af_parts + [f"volume=volume='if({gate},0,1)':eval=frame"])
        parts = [
            f"[0:a]{speech}[sp]",
            f"aevalsrc=exprs={osc}|{osc}:s=48000:d={duration:.6f}:c=stereo,"
            f"volume=volume='if({gate},1,0)':eval=frame[bp]",
            f"[sp][bp]amix=inputs=2:duration=first:normalize=0,{fades}[aout]",
        ]
        if streams != "a" and vf:
            # -vf and -filter_complex cannot both drive the same output, so the
            # video chain moves into the graph too when a segment carries both.
            parts.insert(0, f"[0:v]{vf}[vout]")
        filter_complex = ";".join(parts)

    if draft:
        preset, crf = "ultrafast", "28"
        venc, vextra = "libx264", ["-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "15"]
    elif preview:
        preset, crf = "medium", "22"
        venc, vextra = "libx264", ["-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "15"]
    else:
        preset, crf = "fast", "20"
        venc, vextra = pick_video_encoder()
        if venc == "libx264":
            vextra = ["-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "15"]

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seg_start:.6f}",
        "-i", str(source),
        "-t", f"{duration:.6f}",
    ]
    if filter_complex:
        cmd += ["-filter_complex", filter_complex]
    if streams != "a":
        if vf and not filter_complex:
            cmd += ["-vf", vf]
        elif filter_complex:
            cmd += ["-map", "[vout]" if vf else "0:v"]
        cmd += ["-c:v", venc, *vextra]
        # Every path above lands on Rec.709 (tonemap for HDR, wide_gamut_chain for
        # BT.2020 SDR, passthrough for the rest), so tag it explicitly. Without this
        # the segments can inherit the source's tags and downstream decoders
        # (Chrome/Remotion in Phase 2) silently re-interpret the graded image.
        cmd += ["-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-color_range", "tv"]
        if not keep_resolution:
            # short-form fps: 30 if the source is 30fps+ (natural motion, matches
            # IG/TikTok/Shorts capture), else the 24 standard; longform keeps source.
            cmd += ["-r", shortform_target_fps(source)]
            if zoom:
                cmd += ["-fps_mode", "cfr"]
    else:
        cmd += ["-vn"]

    if streams != "v":
        cmd += ["-map", "[aout]"] if filter_complex else ["-af", af]
        if out_path.suffix.lower() == ".wav":
            # PCM for the J-cut mix — the segments get summed, so no point
            # compounding AAC generations before the single final encode.
            cmd += ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        cmd += ["-an"]

    if out_path.suffix.lower() in (".mp4", ".mov"):
        cmd += ["-movflags", "+faststart"]
    cmd += [str(out_path)]
    try:
        _run_ffmpeg(cmd, label=f"ffmpeg extract ({out_path.name})")
    except RuntimeError:
        raise


def snap_ranges_to_frames(edl: dict, fps: int) -> int:
    """Round every range's DURATION up to a whole number of frames.

    ffmpeg encodes a segment's video as whole frames but keeps its audio at the
    exact requested length, so a range whose duration is not a frame multiple
    produces a clip whose audio is a few ms shorter than its picture. Across a
    28-cut edit that summed to +0.44s of video over audio here, and cut.mp4 came
    out with an audio track LONGER than its video. Remotion then stretches that
    audio across the composition and the voice slides progressively out of sync —
    barely visible at the start, half a second adrift by the end.

    Snapping UP only ever extends a range into its trailing pad (≤1 frame), so it
    cannot clip a word. Returns how many ranges were changed.
    """
    changed = 0
    for r in edl.get("ranges", []):
        dur = r["end"] - r["start"]
        # Round the frame count to 4 decimals BEFORE ceiling. `end` is persisted to
        # 6 decimals, so a duration that is already a whole number of frames comes
        # back as e.g. 1.866667 → 1.866667*30 = 56.00001, which a bare ceil() turns
        # into 57. That made the snap non-idempotent: every re-render of the same
        # EDL grew the affected ranges by one more frame, and since this function
        # rewrites edl.json the drift persisted.
        frames = math.ceil(round(dur * fps, 4))
        snapped = r["start"] + frames / fps
        if abs(snapped - r["end"]) > 1e-6:
            r["end"] = round(snapped, 6)
            changed += 1
    return changed


def extract_all_segments(
    edl: dict,
    edit_dir: Path,
    preview: bool,
    draft: bool = False,
    keep_resolution: bool = False,
    jobs: int = 0,
) -> list[Path]:
    """Extract every EDL range into edit_dir/clips_graded/seg_NN.mp4.
    Returns the ordered list of segment paths.

    Segments are independent, so they encode in PARALLEL (`jobs` ffmpeg
    processes; 0 = auto ≈ cores/3, capped at 4 — each libx264 already uses
    several threads). Order is preserved by the seg_NN filenames.

    If the EDL `grade` is "auto", analyze each segment range with
    `auto_grade_for_clip` and apply a per-segment subtle correction.
    Otherwise, apply the same preset/raw filter to every segment.
    """
    resolved = resolve_grade_filter(edl.get("grade"))
    is_auto = resolved == "__AUTO__"
    clips_dir = edit_dir / (
        "clips_draft" if draft else ("clips_preview" if preview else "clips_graded")
    )
    clips_dir.mkdir(parents=True, exist_ok=True)

    ranges = edl["ranges"]
    sources = edl["sources"]

    # mirror of the J-cut path — see the note there on why ALL of them go
    for stale in list(clips_dir.glob("seg_*.mp4")) + list(clips_dir.glob("seg_*.wav")):
        stale.unlink(missing_ok=True)

    if jobs <= 0:
        jobs = _auto_extract_jobs()
    print(f"extracting {len(ranges)} segment(s) → {clips_dir.name}/  ({jobs} parallel)")

    # Uma fonte preparada por arquivo, montada ANTES do laço paralelo: se cada
    # thread chamasse por conta própria, N threads tonemapariam a mesma fonte
    # ao mesmo tempo.
    prep_by_src: dict[str, Path | None] = {}
    if not (draft or preview or keep_resolution) and not is_auto:
        prep_by_src = prepare_sources_parallel(
            {r["source"] for r in ranges},
            lambda n: resolve_path(sources[n], edit_dir),
            lambda sp: "scale=-2:1920" if is_portrait_source(sp) else "scale=1920:-2",
            resolved)
        _hits = [k for k, v in prep_by_src.items() if v]
        if _hits:
            print(f"  fonte preparada em uso: {', '.join(_hits)}", flush=True)
    try:
        from app.ffmpeg_zoom import zoom_enabled, zoom_for_index
    except ImportError:
        zoom_enabled = lambda _edl: False  # noqa: E731
        zoom_for_index = lambda _edl, _i: None  # noqa: E731
    if zoom_enabled(edl):
        print("  zoom FFmpeg no extract (crop/scale, sem zoompan)", flush=True)
    if is_auto:
        print("  (auto-grade per segment: analyzing each range)")

    def work(i: int, r: dict) -> Path:
        src_name = r["source"]
        src_path = resolve_path(sources[src_name], edit_dir)
        start = float(r["start"])
        end = float(r["end"])
        duration = end - start
        out_path = clips_dir / f"seg_{i:02d}_{src_name}.mp4"

        if is_auto:
            seg_filter, _stats = auto_grade_for_clip(src_path, start=start, duration=duration, verbose=False)
        else:
            seg_filter = resolved

        gain_db = float(r.get("gain_db", 0.0) or 0.0)
        gain_windows = r.get("gain_windows") or []
        bleep_windows = r.get("bleep_windows") or []

        note = r.get("beat") or r.get("note") or ""
        grade_note = f"  grade: {seg_filter or '(none)'}" if is_auto else ""
        gain_note = f"  gain: {gain_db:+.1f}dB" if abs(gain_db) > 0.05 else ""
        if gain_windows:
            gain_note += f"  +{len(gain_windows)} janela(s)"
        if bleep_windows:
            gain_note += f"  {len(bleep_windows)} apito(s)"
        print(f"  [{i:02d}] {src_name}  {start:7.2f}-{end:7.2f}  ({duration:5.2f}s)  {note}{grade_note}{gain_note}", flush=True)
        extract_segment(
            src_path, start, duration, seg_filter, out_path,
            preview=preview, draft=draft, keep_resolution=keep_resolution,
            gain_db=gain_db, gain_windows=gain_windows,
            bleep_windows=bleep_windows,
            zoom=zoom_for_index(edl, i),
            prepared=prep_by_src.get(src_name),
        )
        return out_path

    if jobs == 1 or len(ranges) == 1:
        return [work(i, r) for i, r in enumerate(ranges)]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        return list(ex.map(work, range(len(ranges)), ranges))


# -------- Lossless concat ----------------------------------------------------


def concat_segments(segment_paths: list[Path], out_path: Path, edit_dir: Path) -> None:
    """Lossless concat via the concat demuxer. No re-encode.

    Known artefact, measured 2026-08-20 on a real cut: the demuxer offsets each
    segment by the PREVIOUS segment's *container* duration, which is the max of
    its streams. `snap_ranges_to_frames` rounds the video up to whole frames but
    `extract_segment` keeps the audio at the exact requested length, so a segment
    whose audio runs longer than its video pushes the next one late — leaving a
    hole in the video timeline. On that cut: 2422 steps of exactly 1 frame and a
    single step of 3, right before a 1-frame trailing segment. Result: 2424
    frames occupying 2426 slots.

    Downstream both compose paths normalise with `fps=` before padding, so the
    hole no longer costs a full Remotion re-render (it used to: `FRAMES a!=b`).
    Fixing it HERE would mean trimming each segment's audio to its video length,
    which changes what the J-cut assembly gets — not done, not measured.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = edit_dir / "_concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"concat → {out_path.name}")
    _run_ffmpeg(cmd, label=f"ffmpeg concat ({out_path.name})")
    concat_list.unlink(missing_ok=True)


# -------- J-cut assembly (Phase-1 default cleanup) ---------------------------
#
# A straight concat leaves a beat of silence at every junction: the outgoing take
# keeps its trailing pad and the incoming one starts with its own. Measured on a
# real 3-take edit that was 130ms and 140ms — small on paper, clearly a pause in
# the room.
#
# The J-cut removes it by OVERLAPPING instead of butting: the outgoing take's audio
# runs to its natural end while the incoming take's audio starts `lead` frames
# earlier, on its own track, and the two are summed. The incoming take's PICTURE
# starts where the outgoing audio ends, skipping `lead` frames of its own head —
# so the voice arrives before the face. Sync inside each take is preserved by
# construction:  video_in = audio_in + lead  and  video_offset = audio_offset + lead.
#
# Getting the seam tighter is done by trimming the OUTGOING take's tail, not by
# raising the lead: a bigger lead also pushes the picture deeper into the incoming
# take's speech, which reads as entering mid-word.
#
# The tail trim is MEASURED, never blind. Cutting a fixed 2 frames off every take
# would eventually decapitate a word on footage whose take ends tight — so the trim
# is capped by the silence actually present at the end of that range, keeping 10ms.

JCUT_LEAD_FRAMES = 5
JCUT_TAIL_TRIM_FRAMES = 2


def jcut_settings(edl: dict, fps: int) -> dict | None:
    """Resolve J-cut config. On by default; `"jcut": false` in the EDL disables it.

    Returns None when there is nothing to overlap (single range) or when disabled.
    """
    cfg = edl.get("jcut", True)
    if cfg is False or cfg == "off" or cfg == "none":
        return None
    if len(edl.get("ranges", [])) < 2:
        return None
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "lead_frames": max(0, int(cfg.get("lead_frames", JCUT_LEAD_FRAMES))),
        "tail_trim_frames": max(0, int(cfg.get("tail_trim_frames", JCUT_TAIL_TRIM_FRAMES))),
        "fps": fps,
    }


@_memo_by_stat
def _full_silence_edges(source: Path,
                        noise_db: int = -35) -> tuple[list[float], list[float], float]:
    """silencedetect over the WHOLE source, once, at the J-cut's own params.

    plan_jcut queries one range at a time, which used to spawn one serial
    ffmpeg decode per range over the same file. The full-file scan costs one
    audio decode and every range projects its answer from it. Phase-1's
    speech_regions map is NOT reused here on purpose: it detects at
    -33dB/d=0.10 while the tail trim needs -35dB/d=0.02.
    """
    r = _run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d=0.02", "-f", "null", "-"],
        capture_output=True, text=True)
    starts: list[float] = []
    ends: list[float] = []
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            try:
                starts.append(float(line.rsplit("silence_start:", 1)[1].split()[0]))
            except (ValueError, IndexError):
                pass
        elif "silence_end:" in line:
            try:
                ends.append(float(line.rsplit("silence_end:", 1)[1].split()[0]))
            except (ValueError, IndexError):
                pass
    try:
        src_dur = probe_duration(source)
    except Exception:
        src_dur = 0.0
    return starts, ends, src_dur


def _silence_edges(source: Path, start: float, end: float,
                   noise_db: int = -35) -> tuple[list[float], list[float], float]:
    """Return (silence_starts, silence_ends, clip_dur) relative to the extract.

    Projected from the cached full-file scan: silences are clamped to the
    window and shifted to extract-relative time. A silence still running at
    the window's end yields a start with no matching end — the same shape the
    old per-range detector produced.
    """
    dur = max(0.0, end - start)
    if dur <= 0.02:
        return [], [], dur
    abs_starts, abs_ends, src_dur = _full_silence_edges(source, noise_db=noise_db)
    # silencedetect alternates start/end; a file that ends in silence has one
    # unmatched start, whose silence runs to EOF.
    eof = src_dur if src_dur > 0 else end
    intervals = [
        (s, abs_ends[i] if i < len(abs_ends) else eof)
        for i, s in enumerate(abs_starts)
    ]
    starts: list[float] = []
    ends: list[float] = []
    for a, b in intervals:
        lo, hi = max(a, start), min(b, end)
        if hi - lo < 0.02:  # same d=0.02 floor the per-range detector applied
            continue
        starts.append(lo - start)
        if b <= end - 1e-6:  # speech resumed inside the window → end event
            ends.append(hi - start)
    return starts, ends, dur


def trailing_silence(source: Path, start: float, end: float,
                     noise_db: int = -35) -> float:
    """Seconds of silence at the END of a source range. 0.0 if it ends in speech.

    This is what bounds the tail trim: we only ever remove what is already silent.
    """
    starts, ends, dur = _silence_edges(source, start, end, noise_db=noise_db)
    if not starts:
        return 0.0
    last = starts[-1]
    # the range ends in silence only if no speech resumed after `last`
    if any(e > last + 1e-6 and e < dur - 0.02 for e in ends):
        return 0.0
    return max(0.0, dur - last)


def leading_silence(source: Path, start: float, end: float,
                    noise_db: int = -35) -> float:
    """Seconds of silence at the START of a source range. 0.0 if it starts in speech."""
    starts, ends, dur = _silence_edges(source, start, end, noise_db=noise_db)
    if dur <= 0.02:
        return 0.0
    # Silence that begins at (or before) t=0 of the extract.
    head_starts = [s for s in starts if s <= 0.04]
    if not head_starts:
        # No silence_start near 0 — maybe the clip opens already mid-silence
        # without a detect event; if first silence_end is early, use that.
        if ends and ends[0] < min(0.55, dur * 0.5) and (not starts or starts[0] > ends[0]):
            return max(0.0, ends[0])
        return 0.0
    # First silence block from the head: ends at first silence_end after 0.
    for e in ends:
        if e > 0.01:
            return max(0.0, min(e, dur))
    return max(0.0, dur)


def polish_edl_edges(edl: dict, edit_dir: Path) -> None:
    """In-place: clamp ranges to source duration; strip dead air at head/tail.

    Fixes leftover silence / false-start pads on the first and last takes —
    including single-range edits that never enter the J-cut path.
    """
    sources = edl.get("sources") or {}
    ranges = edl.get("ranges") or []
    n = len(ranges)
    for i, r in enumerate(ranges):
        key = r.get("source")
        if key not in sources:
            continue
        try:
            src = resolve_path(sources[key], edit_dir)
        except Exception:
            continue
        start, end = float(r["start"]), float(r["end"])
        try:
            src_dur = probe_duration(src)
        except Exception:
            src_dur = None
        if src_dur and src_dur > 0:
            end = min(end, src_dur)
            start = max(0.0, min(start, max(0.0, end - 0.08)))

        if i == 0 and end - start > 0.25:
            head = leading_silence(src, start, end)
            if head > 0.06:
                start = min(end - 0.12, start + head - 0.040)

        if i == n - 1 and end - start > 0.25:
            avail = trailing_silence(src, start, end)
            if avail > 0.06:
                end = max(start + 0.12, end - (avail - 0.040))

        if end - start >= 0.12:
            r["start"] = round(start, 3)
            r["end"] = round(end, 3)


def plan_jcut(edl: dict, edit_dir: Path, cfg: dict) -> list[dict]:
    """Work out each take's video range, audio range and output offsets."""
    fps = cfg["fps"]
    ranges = edl["ranges"]
    sources = edl["sources"]
    n = len(ranges)

    srcs: list[Path] = []
    tail_frames: list[int] = []
    silence_ms: list[int | None] = []
    for i, r in enumerate(ranges):
        src = resolve_path(sources[r["source"]], edit_dir)
        srcs.append(src)
        start, end = float(r["start"]), float(r["end"])

        # Mid-take only: head/tail of the whole cut were already polished on the EDL.
        avail = trailing_silence(src, start, end) if i < n - 1 else None
        silence_ms.append(round(avail * 1000) if avail is not None else None)
        tf = 0
        if avail is not None and cfg["tail_trim_frames"]:
            budget = max(0.0, avail - 0.010)          # keep 10ms of room tone
            tf = min(cfg["tail_trim_frames"], int(budget * fps))
        tail_frames.append(tf)

    repo = Path(__file__).resolve().parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from app.timeline_map import layout_jcut_spans

    layout = layout_jcut_spans(
        ranges,
        fps=fps,
        lead_frames=cfg["lead_frames"],
        tail_frames=tail_frames,
    )
    plan: list[dict] = []
    for i, (r, span) in enumerate(zip(ranges, layout)):
        plan.append({
            "i": i, "src": srcs[i], "range": r,
            "a_in": span["a_in"], "a_out": span["a_out"], "a_off": span["a_off"],
            "v_in": span["v_in"], "v_out": span["v_out"], "v_off": span["v_off"],
            "tail_frames": span["tailFrames"],
            "silence_avail_ms": silence_ms[i],
        })
    return plan


def assemble_jcut(plan: list[dict], out_path: Path, edit_dir: Path) -> None:
    """Concat the video track, sum the offset audio tracks, mux them together."""
    work = edit_dir / "clips_graded"
    vlist = edit_dir / "_concat_jcut.txt"
    vlist.write_text("".join(f"file '{p['video_path'].resolve()}'\n" for p in plan), encoding="utf-8")

    video_only = work / "_jcut_video.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vlist),
         "-c", "copy", str(video_only)], quiet=True)
    vlist.unlink(missing_ok=True)

    inputs: list[str] = []
    labels = ""
    refs = ""
    for k, p in enumerate(plan):
        inputs += ["-i", str(p["audio_path"])]
        # delay in SAMPLES: adelay's integer-millisecond form leaves the mix a
        # fraction short of the video, and a downstream -shortest then amputates
        # whole frames of picture.
        smp = int(round(p["a_off"] * 48000))
        labels += f"[{k}:a]adelay={smp}S|{smp}S[d{k}];"
        refs += f"[d{k}]"

    audio_only = work / "_jcut_audio.wav"
    run(["ffmpeg", "-y", *inputs, "-filter_complex",
         f"{labels}{refs}amix=inputs={len(plan)}:normalize=0:duration=longest,"
         f"alimiter=limit=0.95[a]", "-map", "[a]", "-c:a", "pcm_s16le",
         str(audio_only)], quiet=True)

    total = sum(p["v_out"] - p["v_in"] for p in plan)
    # NO -shortest here: a sub-millisecond audio shortfall would truncate video.
    run(["ffmpeg", "-y", "-i", str(video_only), "-i", str(audio_only),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-t", f"{total:.6f}", "-movflags", "+faststart", str(out_path)], quiet=True)
    video_only.unlink(missing_ok=True)
    audio_only.unlink(missing_ok=True)


def extract_and_assemble_jcut(
    edl: dict, edit_dir: Path, cfg: dict, preview: bool, draft: bool,
    keep_resolution: bool, jobs: int, base_path: Path,
) -> list[dict]:
    """Extract every take's picture and sound separately, then overlap-assemble."""
    resolved = resolve_grade_filter(edl.get("grade"))
    is_auto = resolved == "__AUTO__"
    clips_dir = edit_dir / (
        "clips_draft" if draft else ("clips_preview" if preview else "clips_graded"))
    clips_dir.mkdir(parents=True, exist_ok=True)

    plan = plan_jcut(edl, edit_dir, cfg)
    if jobs <= 0:
        jobs = _auto_extract_jobs()

    # Fonte preparada (tonemap + grade uma vez só) — mesma ideia do caminho
    # sem J-cut. Montada aqui, antes do laço paralelo.
    prep_by_src: dict[str, Path | None] = {}
    if not (draft or preview or keep_resolution) and not is_auto:
        prep_by_src = prepare_sources_parallel(
            {r["source"] for r in edl["ranges"]},
            lambda n: resolve_path(edl["sources"][n], edit_dir),
            lambda sp: "scale=-2:1920" if is_portrait_source(sp) else "scale=1920:-2",
            resolved)
        _hits = [k for k, v in prep_by_src.items() if v]
        if _hits:
            print(f"  fonte preparada em uso: {', '.join(_hits)}", flush=True)

    # Render incremental: um re-render que só mudou parte do corte reaproveita
    # os segmentos idênticos da extração anterior (casados por CHAVE de
    # conteúdo — fonte+mtime+range+grade+zoom+flags — nunca por nome).
    # A extração é determinística por chave, então o arquivo é byte-equivalente.
    encoder_env = os.environ.get("ATIVAVID_ENCODER") or ""

    def _seg_key(kind: str, src: Path, a: float, b: float, extra: list) -> str:
        try:
            st = src.stat()
            ident = f"{src}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            ident = str(src)
        return json.dumps(
            [kind, ident, round(a, 6), round(b, 6), extra],
            sort_keys=True, default=str,
        )

    try:
        from app.ffmpeg_zoom import zoom_for_index as _zoom_key_fn
    except ImportError:
        _zoom_key_fn = lambda _edl, _i: None  # noqa: E731

    # Sobra de um crash entre o rename para .keep e a restauração — só lixo.
    for orphan in clips_dir.glob("seg_*.keep"):
        orphan.unlink(missing_ok=True)

    old_by_key: dict[str, Path] = {}
    for sidecar in clips_dir.glob("seg_*.segkey"):
        media = sidecar.with_suffix("")
        if media.exists():
            try:
                old_by_key[sidecar.read_text(encoding="utf-8")] = media
            except OSError:
                pass

    keep: list[tuple[Path, Path]] = []  # (temp, destino final)
    reuse_hits = 0
    for p in plan:
        i, r = p["i"], p["range"]
        vkey = _seg_key(
            "v", p["src"], p["v_in"], p["v_out"],
            # `prep` entra na chave: o segmento sai de um arquivo diferente
            # quando a fonte preparada existe, então não pode reusar o antigo.
            [str(edl.get("grade") or ""), _zoom_key_fn(edl, i),
             preview, draft, keep_resolution, encoder_env,
             bool(prep_by_src.get(r["source"]))],
        )
        akey = _seg_key(
            "a", p["src"], p["a_in"], p["a_out"],
            [float(r.get("gain_db", 0.0) or 0.0), r.get("gain_windows") or [],
             r.get("bleep_windows") or [], preview, draft,
             bool(prep_by_src.get(r["source"]))],
        )
        p["_vkey"], p["_akey"] = vkey, akey
        vpath = clips_dir / f"seg_{i:02d}_{r['source']}_v.mp4"
        apath = clips_dir / f"seg_{i:02d}_{r['source']}_a.wav"
        for key, dest, flag in ((vkey, vpath, "reuse_v"), (akey, apath, "reuse_a")):
            srcf = old_by_key.pop(key, None)
            if srcf is not None:
                tmp = clips_dir / (dest.name + ".keep")
                try:
                    os.replace(srcf, tmp)
                except OSError:
                    continue
                keep.append((tmp, dest))
                p[flag] = True
                reuse_hits += 1

    # Clear EVERY old segment, not just the other mode's. Two ways this folder goes
    # stale and both are invisible downstream, because segments.json is built by
    # globbing it: the butt-join mode writes seg_NN_*.mp4 next to the J-cut's
    # seg_NN_*_v.mp4 (a bare glob sums both), and a re-render with FEWER ranges
    # leaves the higher-numbered segments of the previous cut behind. Measured: a
    # 3-range EDL over a stale 4th segment gave segments.json 9.23s for a 7.57s
    # video — it renders without error and every overlay lands wrong.
    # (Os reusados já foram movidos para *.keep e voltam com o nome NOVO abaixo,
    # então o invariante "a pasta contém exatamente o plano atual" se mantém.)
    for stale in (
        list(clips_dir.glob("seg_*.mp4")) + list(clips_dir.glob("seg_*.wav"))
        + list(clips_dir.glob("seg_*.segkey"))
    ):
        stale.unlink(missing_ok=True)
    for tmp, dest in keep:
        os.replace(tmp, dest)
    if reuse_hits:
        print(f"  reuso: {reuse_hits}/{2 * len(plan)} segmentos aproveitados da extração anterior",
              flush=True)

    lead_ms = round(cfg["lead_frames"] / cfg["fps"] * 1000)
    print(f"J-cut: áudio entra {cfg['lead_frames']}f ({lead_ms}ms) antes da imagem"
          f"  ({len(plan)} takes, {jobs} paralelos)")
    try:
        from app.ffmpeg_zoom import zoom_enabled, zoom_for_index
    except ImportError:
        zoom_enabled = lambda _edl: False  # noqa: E731
        zoom_for_index = lambda _edl, _i: None  # noqa: E731
    if zoom_enabled(edl):
        print("  zoom FFmpeg no extract de vídeo (crop/scale, sem zoompan)", flush=True)

    def work(p: dict) -> dict:
        i, r = p["i"], p["range"]
        seg_filter = (auto_grade_for_clip(p["src"], start=p["v_in"],
                                          duration=p["v_out"] - p["v_in"],
                                          verbose=False)[0]
                      if is_auto else resolved)
        gain_db = float(r.get("gain_db", 0.0) or 0.0)
        gain_windows = r.get("gain_windows") or []
        bleep_windows = r.get("bleep_windows") or []
        vpath = clips_dir / f"seg_{i:02d}_{r['source']}_v.mp4"
        apath = clips_dir / f"seg_{i:02d}_{r['source']}_a.wav"
        if not p.get("reuse_v"):
            extract_segment(p["src"], p["v_in"], p["v_out"] - p["v_in"], seg_filter,
                            vpath, preview=preview, draft=draft,
                            keep_resolution=keep_resolution, streams="v",
                            zoom=zoom_for_index(edl, i),
                            prepared=prep_by_src.get(r["source"]))
        if not p.get("reuse_a"):
            extract_segment(p["src"], p["a_in"], p["a_out"] - p["a_in"], "",
                            apath, preview=preview, draft=draft,
                            keep_resolution=keep_resolution, gain_db=gain_db,
                            gain_windows=gain_windows, bleep_windows=bleep_windows,
                            streams="a",
                            prepared=prep_by_src.get(r["source"]))
        p["video_path"], p["audio_path"] = vpath, apath

        tail_note = ""
        if p["tail_frames"]:
            tail_note = (f"  cauda -{p['tail_frames']}f"
                         f" (de {p['silence_avail_ms']}ms de silêncio)")
        elif p["silence_avail_ms"] is not None:
            tail_note = f"  cauda 0f (só {p['silence_avail_ms']}ms de silêncio)"
        gain_note = f"  gain: {gain_db:+.1f}dB" if abs(gain_db) > 0.05 else ""
        if gain_windows:
            gain_note += f"  +{len(gain_windows)} janela(s)"
        if bleep_windows:
            gain_note += f"  {len(bleep_windows)} apito(s)"
        reuse_note = ""
        if p.get("reuse_v") or p.get("reuse_a"):
            reuse_note = "  reuso:" + ("v" if p.get("reuse_v") else "") + \
                ("a" if p.get("reuse_a") else "")
        print(f"  [{i:02d}] {r['source']}  v {p['v_in']:7.2f}-{p['v_out']:7.2f}"
              f"  a {p['a_in']:7.2f}-{p['a_out']:7.2f}"
              f"  {r.get('beat') or ''}{tail_note}{gain_note}{reuse_note}", flush=True)
        return p

    if jobs == 1 or len(plan) == 1:
        plan = [work(p) for p in plan]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            plan = list(ex.map(work, plan))

    # Sidecars de chave só depois da extração bem-sucedida: um crash no meio
    # nunca deixa chave apontando para arquivo incompleto.
    for p in plan:
        for flag_key, media in (("_vkey", p["video_path"]), ("_akey", p["audio_path"])):
            try:
                Path(str(media) + ".segkey").write_text(p[flag_key], encoding="utf-8")
            except OSError:
                pass

    assemble_jcut(plan, base_path, edit_dir)
    return plan


# -------- Master SRT (Rule 5) ------------------------------------------------


PUNCT_BREAK = set(".,!?;:")


def _srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_in_range(transcript: dict, t_start: float, t_end: float) -> list[dict]:
    out: list[dict] = []
    for w in transcript.get("words", []):
        if w.get("type") != "word":
            continue
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        if we <= t_start or ws >= t_end:
            continue
        out.append(w)
    return out


def build_master_srt(edl: dict, edit_dir: Path, out_path: Path) -> None:
    """Build an output-timeline SRT from per-source transcripts.

    - 2-word chunks (break on any punctuation in between)
    - UPPERCASE text
    - Output times computed as word.start - segment_start + segment_offset
    """
    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]

    entries: list[tuple[float, float, str]] = []
    seg_offset = 0.0

    for r in edl["ranges"]:
        src_name = r["source"]
        seg_start = float(r["start"])
        seg_end = float(r["end"])
        seg_duration = seg_end - seg_start

        tr_path = transcripts_dir / f"{src_name}.json"
        if not tr_path.exists():
            print(f"  no transcript for {src_name}, skipping captions for this segment")
            seg_offset += seg_duration
            continue

        transcript = json.loads(tr_path.read_text(encoding="utf-8"))
        words_in_seg = _words_in_range(transcript, seg_start, seg_end)

        # Group into 2-word chunks, break on punctuation
        chunks: list[list[dict]] = []
        current: list[dict] = []
        for w in words_in_seg:
            text = (w.get("text") or "").strip()
            if not text:
                continue
            current.append(w)
            # Break if the current text ends in punctuation or we hit 2 words
            ends_in_punct = bool(text) and text[-1] in PUNCT_BREAK
            if len(current) >= 2 or ends_in_punct:
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)

        for chunk in chunks:
            local_start = max(seg_start, chunk[0].get("start", seg_start))
            local_end = min(seg_end, chunk[-1].get("end", seg_end))
            out_start = max(0.0, local_start - seg_start) + seg_offset
            out_end = max(0.0, local_end - seg_start) + seg_offset
            if out_end <= out_start:
                out_end = out_start + 0.4
            text = " ".join((w.get("text") or "").strip() for w in chunk)
            text = re.sub(r"\s+", " ", text).strip()
            # Strip trailing punctuation for cleaner uppercase look
            text = text.rstrip(",;:")
            text = text.upper()
            entries.append((out_start, out_end, text))

        seg_offset += seg_duration

    # Sort and write as SRT
    entries.sort(key=lambda e: e[0])
    lines: list[str] = []
    for i, (a, b, t) in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(a)} --> {_srt_timestamp(b)}")
        lines.append(t)
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"master SRT → {out_path.name} ({len(entries)} cues)")


# -------- Loudness normalization (social-ready audio) -----------------------


# Social-media standard: -14 LUFS integrated, -1 dBTP peak, LRA 11 LU.
# Matches YouTube / Instagram / TikTok / X / LinkedIn normalization targets.
LOUDNORM_I = -14.0
LOUDNORM_TP = -1.0
LOUDNORM_LRA = 11.0


def measure_loudness(video_path: Path, pre_chain: str = "") -> dict[str, str] | None:
    """Run ffmpeg loudnorm first pass and parse the JSON measurement.

    `pre_chain` (e.g. the voice-master chain) is applied before the meter, so
    the measurement matches what the fused apply pass will normalize.

    Returns a dict with measured_i, measured_tp, measured_lra, measured_thresh,
    target_offset, or None if measurement failed.
    """
    filter_str = (
        (f"{pre_chain}," if pre_chain else "")
        + f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}:print_format=json"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(video_path),
        "-af", filter_str,
        "-vn", "-f", "null", "-",
    ]
    proc = _run(cmd, capture_output=True, text=True)
    # loudnorm prints the JSON to stderr at the end of the run
    stderr = proc.stderr

    # Find the JSON block — loudnorm output contains a `{ ... }` block
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stderr[start : end + 1])
    except json.JSONDecodeError:
        return None
    needed = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not needed.issubset(data.keys()):
        return None
    return data


# -------- Voice EQ + mastering (spoken-word broadcast chain) ----------------

# A conservative broadcast chain for a single spoken voice. Applied BEFORE
# loudnorm so the normalizer measures the already-mastered signal.
#   1. highpass 90 Hz .......... kill rumble / HVAC / handling / plosive thump
#   2. afftdn .................. tame room / store hiss (keeps speech)
#   3. -2.5 dB @ 200 Hz (Q1.1) .. reduce boxiness / mud
#   4. acompressor ............. even out dynamics, bring the voice forward
#   5. +2.5 dB @ 3.2 kHz (Q1.6) . presence / intelligibility
#   6. high-shelf +2.5 dB @ 9 kHz . air (slightly softer so denoise isn't harsh)
#   7. deesser ................. tame sibilance the presence boost exaggerates
#   8. alimiter ................ safety ceiling before loudnorm
# Every value is a starting point — tune per voice/room if the material asks.
VOICE_MASTER_CHAIN = (
    "highpass=f=90,"
    "afftdn=nr=13:nf=-38:tn=1,"
    "equalizer=f=200:t=q:w=1.1:g=-2.5,"
    "acompressor=threshold=-20dB:ratio=3:attack=12:release=200:makeup=3:knee=6,"
    "equalizer=f=3200:t=q:w=1.6:g=2.5,"
    "treble=g=2.5:f=9000,"
    "deesser=i=0.35,"
    "alimiter=level_in=1:level_out=1:limit=0.95"
)


def apply_voice_master(input_path: Path, output_path: Path) -> None:
    """Run the spoken-word EQ + mastering chain, video copied untouched.

    Runs before loudnorm; loudnorm then normalizes the mastered signal to the
    social target. Audio re-encoded to AAC 192k/48k, video stream copied.
    """
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(input_path),
        "-c:v", "copy",
        "-af", VOICE_MASTER_CHAIN,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(output_path),
    ]
    print(f"  voice master: EQ + compression + de-ess → {output_path.name}")
    _run_ffmpeg(cmd, label=f"ffmpeg voice-master ({output_path.name})")


def apply_loudnorm_two_pass(
    input_path: Path,
    output_path: Path,
    preview: bool = False,
    pre_chain: str = "",
) -> bool:
    """Run two-pass loudnorm on input_path, write normalized copy to output_path.

    `pre_chain` fuses an upstream filter chain (voice master) into the same
    encode: the measurement pass meters through it and the apply pass runs it
    before loudnorm — one AAC encode instead of two files and two encodes.

    Returns True on success, False if measurement failed (caller should fall
    back to copying the input unchanged).

    In preview mode, skips the measurement pass and uses a one-pass approximation
    for speed. Final mode always does the proper two-pass.
    """
    pre = f"{pre_chain}," if pre_chain else ""
    if preview:
        # One-pass approximation — faster, slightly less accurate.
        filter_str = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-nostats",
            "-i", str(input_path),
            "-c:v", "copy",
            # apad: if loudnorm audio ends a few ms early, -shortest must NOT
            # amputate video frames (that caused "segments sum Nf != cut.mp4 Mf").
            "-af", f"{pre}{filter_str},apad",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]
        print(f"  loudnorm (1-pass preview) → {output_path.name}")
        _run_ffmpeg(cmd, label=f"ffmpeg loudnorm-preview ({output_path.name})")
        return True

    # Full two-pass
    print(f"  loudnorm pass 1: measuring {input_path.name}")
    measurement = measure_loudness(input_path, pre_chain=pre_chain)
    if measurement is None:
        print("  loudnorm measurement failed — falling back to 1-pass")
        return apply_loudnorm_two_pass(
            input_path, output_path, preview=True, pre_chain=pre_chain)

    print(f"    measured: I={measurement['input_i']} LUFS  "
          f"TP={measurement['input_tp']}  LRA={measurement['input_lra']}")

    filter_str = (
        f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}"
        f":measured_I={measurement['input_i']}"
        f":measured_TP={measurement['input_tp']}"
        f":measured_LRA={measurement['input_lra']}"
        f":measured_thresh={measurement['input_thresh']}"
        f":offset={measurement['target_offset']}"
        f":linear=true"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(input_path),
        "-c:v", "copy",
        "-af", f"{pre}{filter_str},apad",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        # With apad, audio never ends first — -shortest stops on video end,
        # so we keep every picture frame and still clip any audio overrun.
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    print(f"  loudnorm pass 2: normalizing → {output_path.name}")
    _run_ffmpeg(cmd, label=f"ffmpeg loudnorm ({output_path.name})")
    return True


# -------- Final compositing (Rule 1 + Rule 4) -------------------------------


def build_final_composite(
    base_path: Path,
    overlays: list[dict],
    subtitles_path: Path | None,
    out_path: Path,
    edit_dir: Path,
) -> None:
    """Final pass: base → overlays (PTS-shifted) → subtitles LAST → out.

    If there are no overlays and no subtitles, just copy base to out.
    """
    has_overlays = bool(overlays)
    has_subs = subtitles_path is not None and subtitles_path.exists()

    if not has_overlays and not has_subs:
        # Nothing to draw — a remux here rewrites the whole file for identical
        # bytes, so just move it. base.mp4 has no consumers after this point
        # (it only appears in skip-lists) and is rebuilt fresh on every run.
        os.replace(base_path, out_path)
        return

    inputs: list[str] = ["-i", str(base_path)]
    for ov in overlays:
        ov_path = resolve_path(ov["file"], edit_dir)
        inputs += ["-i", str(ov_path)]

    filter_parts: list[str] = []
    # PTS-shift every overlay so its frame 0 lands at start_in_output
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS+{t}/TB[a{idx}]")

    # Chain overlays on top of base
    current = "[0:v]"
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        dur = float(ov["duration"])
        end = t + dur
        next_label = f"[v{idx}]"
        filter_parts.append(
            f"{current}[a{idx}]overlay=enable='between(t,{t:.3f},{end:.3f})'{next_label}"
        )
        current = next_label

    # Subtitles LAST — Rule 1
    if has_subs:
        subs_abs = str(subtitles_path.resolve()).replace(":", r"\:").replace("'", r"\'")
        filter_parts.append(
            f"{current}subtitles='{subs_abs}':force_style='{SUB_FORCE_STYLE}'[outv]"
        )
        out_label = "[outv]"
    else:
        # Rename the last overlay output to [outv] for consistency
        if has_overlays:
            filter_parts.append(f"{current}null[outv]")
            out_label = "[outv]"
        else:
            out_label = "[0:v]"

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", out_label,
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        # keep the Rec.709 tags the segments carry — this pass re-encodes video
        "-colorspace", "bt709", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-color_range", "tv",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"compositing → {out_path.name}")
    print(f"  overlays: {len(overlays)}, subtitles: {'yes' if has_subs else 'no'}")
    _run_ffmpeg(cmd, label=f"ffmpeg composite ({out_path.name})")


# -------- Main ---------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a video from an EDL")
    ap.add_argument("edl", type=Path, help="Path to edl.json")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output video path")
    ap.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: 1080p, medium, CRF 22 — evaluable for QC, faster than final.",
    )
    ap.add_argument(
        "--draft",
        action="store_true",
        help="Draft mode: 720p, ultrafast, CRF 28 — cut-point verification only.",
    )
    ap.add_argument(
        "--build-subtitles",
        action="store_true",
        help="Build master.srt from transcripts + EDL offsets before compositing",
    )
    ap.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip subtitles even if the EDL references one",
    )
    ap.add_argument(
        "--no-loudnorm",
        action="store_true",
        help="Skip audio loudness normalization. Default is on (-14 LUFS, -1 dBTP, LRA 11).",
    )
    ap.add_argument(
        "--voice-master",
        action="store_true",
        help="Apply spoken-word EQ + mastering (highpass, mud cut, compression, "
             "presence + air, de-ess, limiter) before loudnorm. Also enabled by "
             'EDL field "voice_master": true.',
    )
    ap.add_argument(
        "--keep-resolution",
        action="store_true",
        help="LONGFORM (16:9 YouTube): keep the source resolution and fps instead of "
             "forcing 1080p @ 24. Grade/voice-master/loudnorm still apply.",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Parallel segment extractions (0 = auto ≈ cores/3, capped at 4).",
    )
    ap.add_argument(
        "--no-jcut",
        action="store_true",
        help="Butt-join the takes instead of overlapping them. The J-cut is the "
             "default Phase-1 cleanup: the next take's audio starts a few frames "
             "before its picture, which removes the pause at every junction. Also "
             'disabled by EDL field "jcut": false.',
    )
    ap.add_argument(
        "--no-polish",
        action="store_true",
        help="Não mexer nos ranges (proto/benchmark: compara o mesmo EDL).",
    )
    ap.add_argument(
        "--jcut-lead",
        type=int,
        default=None,
        help=f"Frames the audio leads the picture (default {JCUT_LEAD_FRAMES}).",
    )
    ap.add_argument(
        "--jcut-tail-trim",
        type=int,
        default=None,
        help=f"Max frames trimmed off each outgoing take's tail (default "
             f"{JCUT_TAIL_TRIM_FRAMES}). Capped by the silence actually there.",
    )
    args = ap.parse_args()

    edl_path = args.edl.resolve()
    if not edl_path.exists():
        sys.exit(f"edl not found: {edl_path}")

    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edit_dir = edl_path.parent
    out_path = args.output.resolve()
    acquire_render_lock(out_path)

    # Strip measurable dead air at the first head / last tail, and clamp past EOF.
    if not args.no_polish:
        before = [(float(r["start"]), float(r["end"])) for r in edl.get("ranges") or []]
        polish_edl_edges(edl, edit_dir)
        after = [(float(r["start"]), float(r["end"])) for r in edl.get("ranges") or []]
        if before != after:
            edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
            print("  polished head/tail silence on EDL ranges", flush=True)

    # Frame-align every range BEFORE extraction, and persist it: the EDL, the
    # preview timeline and segments.json must all describe the same cut as the
    # rendered file, or anything that has to land on a cut lands beside it.
    first_src = next(iter(edl.get("sources", {}).values()), None)
    target_fps = int(shortform_target_fps(Path(first_src))) if (first_src and not args.keep_resolution) else 30
    snapped = snap_ranges_to_frames(edl, target_fps)
    if snapped:
        edl["total_duration_s"] = round(sum(r["end"] - r["start"] for r in edl["ranges"]), 3)
        edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  frame-aligned {snapped} range(s) to {target_fps}fps → edl.json updated")

    if args.draft:
        base_name = "base_draft.mp4"
    elif args.preview:
        base_name = "base_preview.mp4"
    else:
        base_name = "base.mp4"
    base_path = edit_dir / base_name

    jcut = None if args.no_jcut else jcut_settings(edl, target_fps)
    if jcut:
        if args.jcut_lead is not None:
            jcut["lead_frames"] = max(0, args.jcut_lead)
        if args.jcut_tail_trim is not None:
            jcut["tail_trim_frames"] = max(0, args.jcut_tail_trim)

    if jcut:
        # 1+2. Picture and sound extracted from different ranges, then overlapped.
        plan = extract_and_assemble_jcut(
            edl, edit_dir, jcut, preview=args.preview, draft=args.draft,
            keep_resolution=args.keep_resolution, jobs=args.jobs,
            base_path=base_path,
        )
        # Persist the real output timeline: everything downstream (preview
        # timeline, segments.json, Phase-2 overlays) indexes off these, and the
        # J-cut timeline is SHORTER than the sum of the ranges.
        edl["jcut_timeline"] = [
            {"beat": p["range"].get("beat"), "source": p["range"]["source"],
             "video_start_in_output": round(p["v_off"], 6),
             "video_duration": round(p["v_out"] - p["v_in"], 6),
             "audio_start_in_output": round(p["a_off"], 6),
             "audio_duration": round(p["a_out"] - p["a_in"], 6),
             "tail_trim_frames": p["tail_frames"]}
            for p in plan
        ]
        edl["total_duration_s"] = round(
            sum(p["v_out"] - p["v_in"] for p in plan), 3)
        edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  timeline J-cut: {edl['total_duration_s']}s → edl.json atualizado")
    else:
        # 1. Extract per-segment (auto-grade per range if EDL grade is "auto")
        segment_paths = extract_all_segments(
            edl, edit_dir, preview=args.preview, draft=args.draft,
            keep_resolution=args.keep_resolution, jobs=args.jobs,
        )
        # 2. Concat → base
        concat_segments(segment_paths, base_path, edit_dir)
        # Drop any J-cut timeline from a PREVIOUS render — and persist that, or the
        # stale block outlives the render it described and everything downstream
        # (verify_cut, the preview lanes, Phase-2 offsets) keeps trusting it.
        if edl.pop("jcut_timeline", None) is not None:
            edl["total_duration_s"] = round(
                sum(r["end"] - r["start"] for r in edl["ranges"]), 3)
            edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2), encoding="utf-8")
            print("  J-cut desligado → jcut_timeline removido do edl.json")

    # 3. Subtitles: build if requested, resolve final path
    subs_path: Path | None = None
    if not args.no_subtitles:
        if args.build_subtitles:
            subs_path = edit_dir / "master.srt"
            build_master_srt(edl, edit_dir, subs_path)
        elif edl.get("subtitles"):
            subs_path = resolve_path(edl["subtitles"], edit_dir)
            if not subs_path.exists():
                print(f"warning: subtitles path in EDL does not exist: {subs_path}")
                subs_path = None

    # 4. Composite (overlays + subtitles LAST) → intermediate (pre-loudnorm) path
    overlays = edl.get("overlays") or []
    voice_master = args.voice_master or bool(edl.get("voice_master"))

    if args.no_loudnorm and not voice_master:
        # Composite directly to final output
        build_final_composite(base_path, overlays, subs_path, out_path, edit_dir)
    else:
        # Composite to a temp file, then voice master + loudnorm in ONE encode.
        tmp_composite = out_path.with_suffix(".prenorm.mp4")
        build_final_composite(base_path, overlays, subs_path, tmp_composite, edit_dir)
        temps = [tmp_composite]

        if args.no_loudnorm:
            # Voice master requested but loudnorm skipped: master alone is final.
            print("voice mastering → EQ + compression + de-ess (spoken word)")
            apply_voice_master(tmp_composite, out_path)
        else:
            # Fusing the chains avoids writing a .voiced.mp4 intermediate AND
            # re-encoding its AAC a second time in the loudnorm pass.
            if voice_master:
                print("voice mastering + loudness normalization (fused, one encode)")
            else:
                print("loudness normalization → social-ready (-14 LUFS / -1 dBTP / LRA 11)")
            apply_loudnorm_two_pass(
                tmp_composite, out_path, preview=args.draft,
                pre_chain=VOICE_MASTER_CHAIN if voice_master else "")

        for t in temps:
            t.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\ndone: {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
