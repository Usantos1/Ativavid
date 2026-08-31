"""Serialize Remotion / npm pesado across parallel ATIVAVID workers.

Light phases (transcribe, cut, ffmpeg extracts) stay parallel via Worker
parallelJobs. Only the heavy Remotion/npm pass takes a slot here.

ATIVAVID_RENDER_SLOTS=1|2 controls how many heavy jobs may run together.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path


def remotion_concurrency() -> int:
    try:
        from app.render_engine import ensure_profile  # type: ignore

        n = int((ensure_profile() or {}).get("recommendedConcurrency") or 0)
        if n >= 1:
            return max(1, min(8, n))
    except Exception:
        pass
    cores = os.cpu_count() or 4
    ram_hint = 8
    try:
        from app.system_info import detect_machine  # type: ignore

        ram_hint = float((detect_machine(quick=True) or {}).get("ramGb") or 8)
    except Exception:
        pass
    # Não usa cpu_count como teto: Chromium come RAM (~2 GB/worker medido).
    # Mesma calibração de render_engine._recommend_concurrency.
    by_ram = max(1, int(ram_hint / 2.0))
    return max(1, min(6, max(1, cores - 2), by_ram, cores))


def remotion_slots() -> int:
    raw = (os.environ.get("ATIVAVID_RENDER_SLOTS") or "").strip()
    if raw.isdigit():
        return max(1, min(2, int(raw)))
    return 1


def offthread_cache_bytes() -> int:
    """Bigger cache when we are the sole Remotion (see Remotion troubleshooting)."""
    slots = remotion_slots()
    base = 1024 * 1024 * 1024  # 1 GiB
    if slots >= 2:
        return base // 2
    return base


def avg_keyframe_gap_sec(video: Path) -> float | None:
    """Average seconds between keyframes, or None if probe fails."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0",
                str(video),
            ],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    times: list[float] = []
    for line in (r.stdout or "").splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and "K" in parts[1]:
            try:
                times.append(float(parts[0]))
            except ValueError:
                pass
    if len(times) < 2:
        return 99.0 if times else None
    gaps = [times[i] - times[i - 1] for i in range(1, len(times))]
    return sum(gaps) / len(gaps)


def ensure_seekable_for_remotion(src: Path, dest: Path, fps: float = 30.0) -> None:
    """Copy cut into remotion/public, re-encoding if GOPs are too sparse for OffthreadVideo."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A validacao do canario (canary_run) economiza a copia de 160 MB
    # ligando public/cut.mp4 ao cut.mp4 por HARDLINK. Num "Tentar novamente"
    # o dest entao E o src: copy2 por cima do proprio inode da
    # "[WinError 32] arquivo em uso" (o video dele do Fusca morreu assim), e
    # o reencode escreveria por cima do arquivo que esta lendo.
    try:
        mesmo_arquivo = dest.exists() and os.path.samefile(src, dest)
    except OSError:
        mesmo_arquivo = False
    gap = avg_keyframe_gap_sec(src)
    if gap is not None and gap <= 1.5:
        if not mesmo_arquivo:
            shutil.copy2(src, dest)
        return
    if mesmo_arquivo:
        dest.unlink()
    g = max(12, int(round(fps)))
    print(
        f"  remotion: cut com keyframes esparsos"
        f"{f' (~{gap:.1f}s)' if gap is not None else ''} — reencode -g {g}",
        flush=True,
    )
    venc, vextra = "libx264", [
        "-preset", "veryfast", "-crf", "18",
        "-g", str(g), "-keyint_min", str(max(8, g // 2)),
        "-pix_fmt", "yuv420p",
    ]
    try:
        from app.render_engine import encoder_args  # type: ignore

        name, extra = encoder_args()
        if name != "libx264":
            venc, vextra = name, list(extra)
            # GOP denso para OffthreadVideo — sobrescreve -g do perfil
            cleaned: list[str] = []
            skip = False
            for tok in vextra:
                if skip:
                    skip = False
                    continue
                if tok in ("-g", "-keyint_min"):
                    skip = True
                    continue
                cleaned.append(tok)
            vextra = cleaned + ["-g", str(g), "-keyint_min", str(max(8, g // 2))]
    except Exception:
        pass
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(src),
        "-c:v", venc, *vextra,
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not dest.exists():
        print("  remotion: reencode falhou — copiando cut original", flush=True)
        shutil.copy2(src, dest)


def lock_dir() -> Path:
    raw = os.environ.get("ATIVAVID_REMOTION_LOCK", "").strip()
    if raw:
        p = Path(raw)
        return p.parent if p.suffix else p
    root = os.environ.get("ATIVAVID_PROJECTS", "").strip()
    if root:
        return Path(root) / ".ativavid"
    return Path.home() / "ATIVAVID" / ".ativavid"


def _try_lock_file(path: Path):
    """Acquire non-blocking exclusive lock; return open file handle or None."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            # Arquivo vazio: locking(1) → Errno 22 no Windows. Garante 1 byte.
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write(b"\0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()}\n".encode())
        fh.flush()
        return fh
    except OSError:
        try:
            fh.close()
        except OSError:
            pass
        return None


def _unlock_file(fh) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fh.close()
    except OSError:
        pass


@contextmanager
def remotion_slot(poll_s: float = 0.75):
    """Wait until one of N render slots is free (default 1)."""
    n = remotion_slots()
    base = lock_dir()
    base.mkdir(parents=True, exist_ok=True)
    # Keep legacy single lock name as slot 0 for older processes.
    candidates = [base / "remotion.lock"] + [base / f"remotion.lock.{i}" for i in range(1, n)]
    # If n==1 only use remotion.lock; if n==2 use .0 style via remotion.lock + .1
    if n >= 2:
        candidates = [base / f"remotion.lock.{i}" for i in range(n)]

    print(f"  remotion: aguardando slot (1 de {n})…", flush=True)
    fh = None
    while fh is None:
        for path in candidates:
            fh = _try_lock_file(path)
            if fh is not None:
                print(f"  remotion: slot adquirido ({path.name})", flush=True)
                break
        if fh is None:
            time.sleep(poll_s)
    try:
        yield
    finally:
        _unlock_file(fh)
