"""Windows process helpers — hide console windows for child tools."""
from __future__ import annotations

import subprocess
import sys


def hide_console_kwargs() -> dict:
    """Extra kwargs for subprocess so ffmpeg/uv/npm/powershell don't flash a CMD box.

    CREATE_NO_WINDOW alone is usually enough; STARTUPINFO SW_HIDE covers edge
    cases (some console tools still allocate a window briefly).
    """
    if sys.platform != "win32":
        return {}
    kwargs: dict = {}
    no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if no_win:
        kwargs["creationflags"] = no_win
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
    except Exception:
        pass
    return kwargs
