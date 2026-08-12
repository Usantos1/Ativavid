#!/usr/bin/env python3
"""Smoke test for the skill itself. No API keys, no user projects, no network.

Why this exists: 28 helpers and, until now, zero tests. The cost showed up
twice in one afternoon — a "→" in a startup banner killed the preview server
before it bound its port, and 8 helpers (render.py among them) could not print
their own --help when stdout was a pipe. Both are trivial to catch and both
reached the user instead, as "it just doesn't work".

What it checks, in order of how often it has actually caught something:

  1. cp1252 stdout — every helper answers --help with output redirected, the
     way an agent or a log file calls it. This is THE regression that keeps
     happening, because it never reproduces in an interactive console.
  2. syntax — every .py compiles, every .js parses (needs node; skipped if not).
  3. the preview server — boots on a free port and serves its routes,
     including the /p/<pasta>/ scoping and its refusal of paths outside
     --projects-root.
  4. the Remotion template — present, and its integrity hashes agree with
     check_template_integrity.py.

It writes only inside a temp dir it makes and removes.

    python helpers/selftest.py [-v]

Exit code is the number of failures, so it composes with anything.
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
HELPERS = SKILL / "helpers"
PREVIEW = SKILL / "assets" / "preview"
PY = sys.executable

VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv
_results: list[tuple[str, str, str]] = []   # (status, name, detail)


def record(ok: bool | None, name: str, detail: str = "") -> None:
    """ok=True pass, False fail, None skip. A skip is NOT a pass — it prints."""
    status = "PASS" if ok else ("SKIP" if ok is None else "FAIL")
    _results.append((status, name, detail))
    if VERBOSE or status != "PASS":
        line = f"  [{status}] {name}"
        print(f"{line}\n         {detail}" if detail else line, flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def get(url: str, timeout: float = 8.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return 0, b""


# ---------------------------------------------------------------- 1. cp1252
def check_redirected_stdout() -> None:
    """Every helper must print its --help with a cp1252 stdout.

    PYTHONIOENCODING is FORCED rather than merely scrubbed, and that distinction
    is the difference between a test and a coin flip. Scrubbing only exposes the
    bug when the ambient console happens to be cp1252 — and the console codepage
    changes under you (a PowerShell or ffmpeg call is enough). Caught in the act:
    this check went green against a render.py with the fix deliberately removed,
    purely because the codepage had flipped to UTF-8 mid-session.

    Forcing it reproduces the hostile condition every run, on any machine. A
    helper that calls reconfigure() at import still passes, because reconfigure
    overrides the encoding the stream was created with — which is exactly the
    property being tested.
    """
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env["PYTHONIOENCODING"] = "cp1252"
    for f in sorted(HELPERS.glob("*.py")):
        if f.name.startswith("_") or f.name == Path(__file__).name:
            continue
        try:
            r = subprocess.run([PY, str(f), "--help"], capture_output=True, env=env,
                               timeout=90, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            record(False, f"--help {f.name}", "travou (>90s)")
            continue
        if r.returncode == 0:
            record(True, f"--help {f.name}")
        elif "UnicodeEncodeError" in (r.stderr or ""):
            record(False, f"--help {f.name}",
                   "UnicodeEncodeError com stdout redirecionado — falta `import _utf8`")
        else:
            last = (r.stderr or "").strip().splitlines()
            record(False, f"--help {f.name}", last[-1][:110] if last else f"rc={r.returncode}")


# ------------------------------------------------------- 1b. leitura em UTF-8
def check_reads_are_utf8() -> None:
    """No text read may rely on the locale encoding.

    This is the READ half of the cp1252 problem, and it is worse than the write
    half because it does not raise: `Path.read_text()` with no encoding decodes
    a UTF-8 file as cp1252, so "Doce para café" silently becomes "Doce para
    cafÃ©" and JSON parses happily. Everything downstream — the project name in
    the UI, the beats in edl.json, the transcript that becomes the subtitles,
    the correction note the user typed — is Portuguese, so this corrupts
    exactly the content that matters, with no error anywhere.

    Static, not behavioural: reproducing it needs a cp1252 locale, and the whole
    point is that catching it must not depend on the ambient locale.

    AST rather than grep, and that is not fussiness — the grep version flagged
    this very docstring for containing the words `read_text()`. A check that
    cries wolf on prose gets ignored, which is the same as not having it.
    """
    import ast
    offenders = []
    for f in sorted(HELPERS.glob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), str(f))
        except SyntaxError:
            continue  # already reported by the syntax check
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "read_text"
                    and not any(k.arg == "encoding" for k in node.keywords)):
                offenders.append(f"{f.name}:{node.lineno}")
    record(not offenders, "toda leitura de texto declara encoding",
           ", ".join(offenders[:8]) + (f" (+{len(offenders) - 8})" if len(offenders) > 8 else ""))

    # and prove the failure mode is what the check claims, so the check cannot
    # quietly become a rule nobody remembers the reason for
    tmp = Path(tempfile.mkdtemp(prefix="ativavid-enc-"))
    try:
        p = tmp / "state.json"
        original = "Doce para café — Adoçar seu dia"
        p.write_text(json.dumps({"project": original}, ensure_ascii=False), encoding="utf-8")
        mangled = json.loads(p.read_bytes().decode("cp1252"))["project"]
        clean = json.loads(p.read_text(encoding="utf-8"))["project"]
        record(clean == original and mangled != original,
               "cp1252 corrompe em silencio (premissa da checagem acima)",
               f"cp1252 leu {mangled!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 2. syntax
def check_syntax() -> None:
    bad = []
    for f in sorted(HELPERS.glob("*.py")):
        try:
            compile(f.read_text(encoding="utf-8"), str(f), "exec")
        except SyntaxError as e:
            bad.append(f"{f.name}:{e.lineno}")
    record(not bad, "sintaxe python (helpers/*.py)", ", ".join(bad))

    node = shutil.which("node")
    js = sorted(PREVIEW.glob("*.js"))
    if not node:
        record(None, "sintaxe js (assets/preview/*.js)", "node nao encontrado no PATH")
    elif not js:
        record(None, "sintaxe js (assets/preview/*.js)", "nenhum .js")
    else:
        bad = []
        for f in js:
            r = subprocess.run([node, "--check", str(f)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                bad.append(f.name)
        record(not bad, f"sintaxe js ({len(js)} arquivos)", ", ".join(bad))


# ---------------------------------------------------------------- 3. server
def check_preview_server() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ativavid-selftest-"))
    proc = None
    try:
        # two projects, so the /p/ prefix has something to be WRONG about: if
        # scoping silently fell back to the server's own root the caption would
        # come back as the other project's and this would still 200
        for name, legenda in (("Alfa", "sou o alfa"), ("Bravo ção", "sou o bravo")):
            edit = tmp / name / "edit"
            edit.mkdir(parents=True)
            (edit / "state.json").write_text(
                json.dumps({"project": name, "phase": 1, "video": "cut.mp4"}),
                encoding="utf-8")
            (edit / "legenda.txt").write_text(legenda, encoding="utf-8")

        port = free_port()
        proc = subprocess.Popen(
            [PY, str(HELPERS / "preview_server.py"),
             "--root", str(tmp / "Alfa" / "edit"),
             "--projects-root", str(tmp), "--port", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace")

        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            if get(f"{base}/api/state", timeout=1)[0] == 200:
                break
            if proc.poll() is not None:
                out = (proc.stdout.read() if proc.stdout else "") or ""
                record(False, "servidor sobe", out.strip().splitlines()[-1][:140]
                       if out.strip() else f"morreu com rc={proc.returncode}")
                return
            time.sleep(0.25)
        else:
            record(False, "servidor sobe", "nao respondeu em 15s")
            return
        record(True, "servidor sobe")

        for path, want in (("/", 200), ("/fase1", 200), ("/estilo", 200), ("/fase2", 200),
                           ("/painel", 200), ("/api/state", 200), ("/api/projects", 200),
                           ("/media/legenda.txt", 200), ("/api/cover", 404),
                           ("/rota/que/nao/existe", 404)):
            code, _ = get(base + path)
            record(code == want, f"rota {path}", f"esperava {want}, veio {code}")

        # the scoping itself: right project, not just any 200
        code, body = get(f"{base}/p/Bravo%20%C3%A7%C3%A3o/media/legenda.txt")
        txt = body.decode("utf-8", "replace").strip()
        record(code == 200 and txt == "sou o bravo", "/p/<pasta>/ serve o projeto certo",
               f"HTTP {code}, corpo {txt!r}")

        code, body = get(f"{base}/p/Bravo%20%C3%A7%C3%A3o/api/state")
        try:
            proj = json.loads(body).get("state", {}).get("project")
        except Exception:
            proj = None
        record(proj == "Bravo ção", "/p/<pasta>/api/state escopado", f"veio {proj!r}")

        code, _ = get(f"{base}/p/Alfa/media/../../../../secret.txt")
        record(code != 200, "recusa caminho fora do edit dir", f"HTTP {code}")

        code, body = get(f"{base}/api/projects")
        try:
            n = len(json.loads(body).get("projects", []))
        except Exception:
            n = -1
        record(n == 2, "painel enxerga os 2 projetos", f"achou {n}")
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 4. template
def check_template() -> None:
    src = SKILL / "assets" / "shortform" / "src"
    if not src.is_dir():
        record(False, "template shortform existe", f"{src} nao encontrado")
        return
    tsx = sorted(src.glob("*.tsx"))
    record(bool(tsx), "template shortform existe", f"{len(tsx)} arquivos .tsx")

    checker = HELPERS / "check_template_integrity.py"
    if not checker.exists():
        record(None, "integridade do template", "check_template_integrity.py ausente")
        return
    tmp = Path(tempfile.mkdtemp(prefix="ativavid-tpl-"))
    try:
        # a pristine copy must pass its own integrity check; if it does not, the
        # hashes shipped with the skill are stale and EVERY project will be told
        # its template was tampered with
        shutil.copytree(src, tmp / "src")
        r = subprocess.run([PY, str(checker), str(tmp)], capture_output=True,
                           text=True, timeout=60, encoding="utf-8", errors="replace")
        record(r.returncode == 0, "integridade do template (copia intacta)",
               (r.stdout + r.stderr).strip().splitlines()[-1][:120]
               if r.returncode else "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("ATIVAVID selftest\n")
    for title, fn in (("1. stdout redirecionado (cp1252)", check_redirected_stdout),
                      ("1b. leitura de texto em UTF-8", check_reads_are_utf8),
                      ("2. sintaxe", check_syntax),
                      ("3. servidor de preview", check_preview_server),
                      ("4. template remotion", check_template)):
        print(title, flush=True)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — a broken check is a failure, not a crash
            record(False, title, f"{type(e).__name__}: {e}")
        print(flush=True)

    ok = sum(1 for s, _, _ in _results if s == "PASS")
    skip = sum(1 for s, _, _ in _results if s == "SKIP")
    fail = [(n, d) for s, n, d in _results if s == "FAIL"]
    print(f"{ok} passou · {len(fail)} falhou · {skip} pulado")
    for n, d in fail:
        print(f"  FALHOU  {n}" + (f" — {d}" if d else ""))
    return len(fail)


if __name__ == "__main__":
    sys.exit(main())
