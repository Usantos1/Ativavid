"""Windows process helpers — hide console windows for child tools."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


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


def refresh_path_env(env: dict | None = None) -> dict:
    """Merge Machine+User PATH from the registry into env.

    GUI apps started via wscript often miss tools installed by winget (uv,
    ffmpeg, node) that an interactive PowerShell already sees.
    """
    out = dict(env or os.environ)
    if sys.platform != "win32":
        return out
    parts: list[str] = []
    try:
        import winreg

        for hive, sub in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    val, _ = winreg.QueryValueEx(key, "Path")
                    if val:
                        parts.append(str(val))
            except OSError:
                continue
    except Exception:
        return out

    home = Path.home()
    extras = [
        home / ".local" / "bin",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "uv",
        Path(r"C:\Program Files\nodejs"),
        Path(r"C:\ffmpeg\bin"),
    ]
    for p in extras:
        try:
            if p.is_dir():
                parts.insert(0, str(p))
        except OSError:
            pass

    merged = os.pathsep.join([*parts, out.get("PATH", "")])
    try:
        merged = os.path.expandvars(merged)
    except Exception:
        pass
    out["PATH"] = merged
    os.environ["PATH"] = merged
    return out


def resolve_python_cmd(repo: Path | None = None) -> list[str]:
    """Argv prefix to run Python after install — prefer .venv, never require `uv` on PATH.

    Installed app starts via `.venv\\Scripts\\pythonw.exe`. Jobs used to call
    `uv run …`, which fails with WinError 2 on PCs where uv is missing from the
    GUI process PATH (even when APIs are configured).
    """
    refresh_path_env()
    root = Path(repo) if repo else Path(__file__).resolve().parent.parent
    scripts = root / ".venv" / "Scripts"
    for name in ("python.exe", "pythonw.exe"):
        p = scripts / name
        if p.exists():
            if name == "pythonw.exe":
                alt = scripts / "python.exe"
                if alt.exists():
                    return [str(alt)]
            return [str(p)]

    exe = Path(sys.executable) if sys.executable else None
    if exe and exe.exists():
        if exe.name.lower() == "pythonw.exe":
            alt = exe.with_name("python.exe")
            if alt.exists():
                return [str(alt)]
        return [str(exe)]

    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "python"]
    py = shutil.which("python") or shutil.which("py")
    if py:
        return [py]
    return ["python"]
