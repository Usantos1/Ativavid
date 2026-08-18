"""Move pasta de projeto para a Lixeira. Nunca apaga de vez."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

__all__ = ["RecycleError", "is_safe_project_dir", "send_to_recycle_bin"]


class RecycleError(RuntimeError):
    pass


def is_safe_project_dir(proj: Path, projects_root: Path) -> bool:
    """Só pastas que o app criou debaixo da raiz de projetos."""
    try:
        target = Path(proj).resolve()
        root = Path(projects_root).resolve()
    except OSError:
        return False
    if not target.is_dir():
        return False
    if target == root:
        return False
    return root in target.parents


def send_to_recycle_bin(
    path: Path,
    *,
    runner: Callable[[Path], None] | None = None,
) -> None:
    """Envia arquivo ou pasta para a Lixeira do Windows.

    `runner` é injetável nos testes — não chama PowerShell.
    """
    target = Path(path).resolve()
    if not target.exists():
        raise RecycleError("pasta não encontrada")
    if runner is not None:
        runner(target)
        return
    if sys.platform != "win32":
        raise RecycleError("Lixeira só no Windows")
    quoted = str(target).replace("'", "''")
    if target.is_dir():
        verb = (
            "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory("
            f"'{quoted}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
        )
    else:
        verb = (
            "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
            f"'{quoted}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
        )
    ps = "Add-Type -AssemblyName Microsoft.VisualBasic; " + verb
    try:
        from app.win_process import hide_console_kwargs

        extra = hide_console_kwargs()
    except Exception:
        extra = {}
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
            **extra,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecycleError(str(exc)[:200]) from exc
    if r.returncode != 0 or target.exists():
        err = (r.stderr or r.stdout or "falhou ao mover para a Lixeira").strip()
        raise RecycleError(err[:200])
