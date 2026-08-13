"""Serialize Remotion renders across parallel ATIVAVID workers.

Two Remotion processes each set concurrency=N cores and fight over RAM for the
OffthreadVideo frame cache — that surfaces as:
  Compositor error: No frame found at position …
Phase-1 ffmpeg jobs can stay parallel; only the Remotion pass takes the lock.
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
    cores = os.cpu_count() or 4
    # When the lock is held we are the only Remotion — use all cores.
    # Cap at 8: beyond that decode/layout rarely scales and RAM pressure rises.
    return max(1, min(8, cores))


def offthread_cache_bytes() -> int:
    """Bigger cache when we are the sole Remotion (see Remotion troubleshooting)."""
    return 1024 * 1024 * 1024  # 1 GiB


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
    gap = avg_keyframe_gap_sec(src)
    if gap is not None and gap <= 1.5:
        shutil.copy2(src, dest)
        return
    g = max(12, int(round(fps)))
    print(
        f"  remotion: cut com keyframes esparsos"
        f"{f' (~{gap:.1f}s)' if gap is not None else ''} — reencode -g {g}",
        flush=True,
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-g", str(g), "-keyint_min", str(max(8, g // 2)),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not dest.exists():
        print("  remotion: reencode falhou — copiando cut original", flush=True)
        shutil.copy2(src, dest)


def lock_path() -> Path:
    raw = os.environ.get("ATIVAVID_REMOTION_LOCK", "").strip()
    if raw:
        return Path(raw)
    root = os.environ.get("ATIVAVID_PROJECTS", "").strip()
    if root:
        return Path(root) / ".ativavid" / "remotion.lock"
    return Path.home() / "ATIVAVID" / ".ativavid" / "remotion.lock"


@contextmanager
def remotion_slot(poll_s: float = 0.75):
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    print(f"  remotion: aguardando slot ({path.name})…", flush=True)
    try:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(poll_s)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    time.sleep(poll_s)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()}\n".encode())
        fh.flush()
        print("  remotion: slot adquirido", flush=True)
        yield
    finally:
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
        fh.close()
