"""Windows process helpers — hide console windows for child tools."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Windows CreateProcess fails if any single env value exceeds ~32767 chars.
# Leave headroom for PYTHONPATH and other vars in the same block.
_PATH_SOFT_CAP = 24000


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


def _norm_path_key(p: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(p.strip().strip('"')))
    except Exception:
        return p.strip().lower()


def dedupe_path(path_value: str, *, prefer: list[str] | None = None) -> str:
    """Unique PATH entries, prefer list first, soft-capped for Windows."""
    ordered: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        for part in str(raw or "").split(os.pathsep):
            p = part.strip().strip('"')
            if not p:
                continue
            key = _norm_path_key(p)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(p)

    for p in prefer or []:
        add(p)
    add(path_value)

    merged = os.pathsep.join(ordered)
    if len(merged) <= _PATH_SOFT_CAP:
        return merged
    # Drop from the end (lowest priority) until under cap.
    while ordered and len(os.pathsep.join(ordered)) > _PATH_SOFT_CAP:
        ordered.pop()
    return os.pathsep.join(ordered)


def refresh_path_env(env: dict | None = None) -> dict:
    """Merge Machine+User PATH from the registry into env (idempotent).

    GUI apps started via wscript often miss tools installed by winget (uv,
    ffmpeg, node) that an interactive PowerShell already sees.

    Must NOT grow PATH on every call — that used to blow past Windows' 32767
    char env limit and kill every child process.
    """
    out = dict(env or os.environ)
    if sys.platform != "win32":
        return out

    prefer: list[str] = []
    home = Path.home()
    extras = [
        Path(r"C:\Program Files\nodejs"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs",
        home / ".local" / "bin",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "uv",
        Path(r"C:\ffmpeg\bin"),
        home / "ATIVAVID" / "ffmpeg",
    ]
    for p in extras:
        try:
            if p.is_dir():
                prefer.append(str(p.resolve()))
        except OSError:
            pass

    chunks: list[str] = []
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
                        chunks.append(str(val))
            except OSError:
                continue
    except Exception:
        chunks = []

    chunks.append(out.get("PATH", "") or "")
    try:
        raw = os.path.expandvars(os.pathsep.join(chunks))
    except Exception:
        raw = os.pathsep.join(chunks)

    merged = dedupe_path(raw, prefer=prefer)
    out["PATH"] = merged
    # Keep process PATH in sync, but never re-append duplicates.
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
    # Always pass a sanitized env so PATH cannot explode in children.
    env = kwargs.pop("env", None)
    env = child_env(env)
    kwargs = {**kwargs, "env": env, **hide_console_kwargs()}
    try:
        return subprocess.run(cmd, **kwargs)
    except FileNotFoundError as e:
        missing = getattr(e, "filename", None) or (cmd[0] if cmd else "?")
        raise FileNotFoundError(
            f"[WinError 2] Não achou: {missing!r} (cmd={cmd!r})"
        ) from e
    except OSError as e:
        # WinError 206 / env too long
        msg = str(e)
        if "32767" in msg or getattr(e, "winerror", None) == 206:
            raise OSError(
                f"PATH do Windows estourou o limite (32767). "
                f"Reinicie o ATIVAVID. Detalhe: {e}"
            ) from e
        raise


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
            # Put node dir first once (deduped) so child scripts find `node`.
            os.environ["PATH"] = dedupe_path(
                os.environ.get("PATH", ""), prefer=[str(d.resolve())]
            )
            return str(p.resolve())
    raise FileNotFoundError(
        "node.exe não encontrado. Instale: winget install OpenJS.NodeJS.LTS "
        "e reabra o ATIVAVID."
    )


def child_env(base: dict | None = None) -> dict:
    """Env for subprocesses: refreshed PATH, node first, under Windows length cap."""
    out = refresh_path_env(base)
    try:
        node = resolve_node_exe()
        node_dir = str(Path(node).resolve().parent)
        out["PATH"] = dedupe_path(out.get("PATH", ""), prefer=[node_dir])
    except FileNotFoundError:
        pass
    # Avoid npm choosing a broken script-shell; postinstall calls bare `node`.
    out.setdefault("PYTHONIOENCODING", "utf-8")
    out.setdefault("PYTHONUTF8", "1")
    return out


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
            node2 = d / "node.exe"
            return [str(node2.resolve()) if node2.exists() else node, str(cand)]
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


# Só estes seguram arquivo dentro de edit/remotion. python.exe NUNCA entra:
# a linha de comando do próprio run_fast cita a pasta do projeto, então
# incluí-lo fazia o pipeline se matar sozinho (visto em produção: jobs
# morrendo mudos com exit -1 em toda reprocessada).
_HOLDER_NAMES = frozenset({
    "node.exe", "ffmpeg.exe", "ffprobe.exe", "esbuild.exe",
    "chrome.exe", "chrome-headless-shell.exe",
})


def _is_path_needle(raw: str) -> bool:
    """Só caminho absoluto vira alvo. Um token curto ("remotion", nome da
    pasta do projeto) casa com processos que nada têm a ver com a pasta —
    inclusive os de OUTROS jobs rodando em paralelo."""
    s = str(raw or "").strip()
    if len(s) < 8:
        return False
    return bool(re.match(r"^[a-zA-Z]:[\\/]", s)) or s.startswith("\\\\") or s.startswith("/")


def _protected_pids(rows: list[dict]) -> set[int]:
    """Eu, meus ancestrais e todos os meus descendentes. Matar qualquer um
    deles é suicídio do pipeline que está pedindo a limpeza."""
    by_pid = {int(r["pid"]): int(r.get("ppid") or 0) for r in rows if r.get("pid") is not None}
    me = os.getpid()
    safe = {me}
    cur = me
    for _ in range(24):  # ancestrais
        parent = by_pid.get(cur)
        if not parent or parent in safe:
            break
        safe.add(parent)
        cur = parent
    # Descendentes saem SÓ de mim: propagar a partir dos ancestrais faria o
    # pid 1 (ou o explorer) adotar a máquina inteira e a limpeza nunca mataria
    # ninguém — inclusive quem de fato segura a pasta.
    mine = {me}
    for _ in range(24):
        grew = False
        for pid, ppid in by_pid.items():
            if ppid in mine and pid not in mine:
                mine.add(pid)
                grew = True
        if not grew:
            break
    return safe | mine


def select_kill_targets(rows: list[dict], needles: list[str]) -> list[int]:
    """Quem realmente segura a pasta: processo da allowlist, citando um
    caminho absoluto alvo, e fora da minha própria árvore."""
    needles_l = [n.lower() for n in needles if _is_path_needle(n)]
    if not needles_l:
        return []
    safe = _protected_pids(rows)
    out: list[int] = []
    for r in rows:
        try:
            pid = int(r["pid"])
        except (KeyError, TypeError, ValueError):
            continue
        if pid in safe:
            continue
        if str(r.get("name") or "").lower() not in _HOLDER_NAMES:
            continue
        cmd = str(r.get("cmd") or "").lower().replace("/", "\\")
        if not cmd:
            continue
        if any(n.replace("/", "\\") in cmd for n in needles_l):
            out.append(pid)
    return out


def _list_processes() -> list[dict]:
    ps = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
        "ConvertTo-Json -Compress -Depth 2"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True, text=True, timeout=45, **hide_console_kwargs(),
    )
    try:
        data = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [
        {
            "pid": row.get("ProcessId"),
            "ppid": row.get("ParentProcessId"),
            "name": row.get("Name"),
            "cmd": row.get("CommandLine"),
        }
        for row in data
        if isinstance(row, dict)
    ]


def kill_processes_holding_path(path: Path | str, *, extra_needles: list[str] | None = None) -> list[int]:
    """Mata node/ffmpeg que seguram arquivos DENTRO de `path` (para o rmtree
    de edit/remotion não falhar com EPERM).

    Regras que existem por causa de um bug real: nunca mata processo da
    própria árvore, nunca aceita apelido curto como alvo e só encosta em
    processos que de fato abrem arquivo lá dentro."""
    if sys.platform != "win32":
        return []
    target = str(Path(path).resolve())
    needles = [target, target.replace("\\", "/")]
    for n in extra_needles or []:
        if n and str(n) not in needles:
            needles.append(str(n))
    if not any(_is_path_needle(n) for n in needles):
        return []

    killed: list[int] = []
    try:
        targets = select_kill_targets(_list_processes(), needles)
        if not targets:
            return []
        subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                "Stop-Process -Id " + ",".join(str(p) for p in targets)
                + " -Force -ErrorAction SilentlyContinue",
            ],
            capture_output=True, text=True, timeout=45, **hide_console_kwargs(),
        )
        killed = targets
    except Exception:
        return killed
    return killed
