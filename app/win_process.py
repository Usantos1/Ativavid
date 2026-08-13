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


def wrap_win_cmdline(argv: list[str]) -> list[str]:
    """On Windows, launch .cmd/.bat via cmd.exe so CREATE_NO_WINDOW works.

    `npx.cmd` / `npm.cmd` with CREATE_NO_WINDOW raise WinError 2 (file not found)
    because CreateProcess cannot run batch files directly.
    """
    if sys.platform != "win32" or not argv:
        return list(argv)
    exe = Path(str(argv[0])).name.lower()
    if exe.endswith((".cmd", ".bat")) or exe in {"npm", "npx"}:
        return ["cmd.exe", "/d", "/c", *argv]
    return list(argv)


def run_hidden(argv: list[str], **kwargs):
    """subprocess.run with no console flash; wraps npm/npx on Windows."""
    cmd = wrap_win_cmdline(list(argv))
    kwargs = {**kwargs, **hide_console_kwargs()}
    try:
        return subprocess.run(cmd, **kwargs)
    except FileNotFoundError as e:
        missing = getattr(e, "filename", None) or (cmd[0] if cmd else "?")
        raise FileNotFoundError(
            f"[WinError 2] Não achou: {missing!r} (cmd={cmd!r})"
        ) from e


def _node_candidate_dirs() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    pf = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    pf86 = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    home = Path.home()
    return [
        pf / "nodejs",
        pf86 / "nodejs",
        local / "Programs" / "nodejs",
        local / "Programs" / "node",
        home / "scoop" / "apps" / "nodejs" / "current",
        home / "AppData" / "Roaming" / "nvm",
        Path(r"C:\nodejs"),
    ]


def resolve_node_exe() -> str:
    """Absolute path to node.exe — GUI PATH often misses winget installs."""
    refresh_path_env()
    found = shutil.which("node") or shutil.which("node.exe")
    if found and Path(found).exists():
        return str(Path(found).resolve())
    for d in _node_candidate_dirs():
        p = d / "node.exe"
        if p.exists():
            # Put node dir first so child tools can find peers
            try:
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass
            return str(p.resolve())
    raise FileNotFoundError(
        "node.exe não encontrado. Instale: winget install OpenJS.NodeJS.LTS "
        "e reabra o ATIVAVID."
    )


def resolve_npm_argv() -> list[str]:
    """npm as [node, npm-cli.js] — evita npm.cmd (WinError 2 / 'não é reconhecido')."""
    node = resolve_node_exe()
    node_dir = Path(node).resolve().parent
    npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if npm_cli.exists():
        return [node, str(npm_cli)]
    # nvm / portable layouts
    for d in _node_candidate_dirs():
        cand = d / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if cand.exists():
            return [resolve_node_exe() if (d / "node.exe").exists() else node, str(cand)]
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm:
        return [npm]
    raise FileNotFoundError(
        "npm não encontrado junto do Node. Reinstale: winget install OpenJS.NodeJS.LTS"
    )


def resolve_remotion_argv(remotion_dir: Path, *args: str) -> list[str]:
    """Remotion CLI via node + local package — sem npx.cmd no PATH."""
    node = resolve_node_exe()
    root = Path(remotion_dir)
    candidates = [
        root / "node_modules" / "@remotion" / "cli" / "remotion-cli.js",
        root / "node_modules" / "@remotion" / "cli" / "dist" / "remotion-cli.js",
        root / "node_modules" / "remotion" / "cli.js",
    ]
    for cli in candidates:
        if cli.exists():
            return [node, str(cli), *args]
    # Último recurso: npx-cli.js do Node (ainda sem .cmd)
    node_dir = Path(node).resolve().parent
    npx_cli = node_dir / "node_modules" / "npm" / "bin" / "npx-cli.js"
    if npx_cli.exists():
        return [node, str(npx_cli), "--no-install", "remotion", *args]
    raise FileNotFoundError(
        f"CLI Remotion ausente em {root / 'node_modules'} "
        "(rode npm install no scaffold) e npx também não achou."
    )


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
