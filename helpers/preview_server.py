"""ATIVAVID preview server — serves the standard editing interface + session media.

The interface app (assets/preview/) is IMMUTABLE and lives in the skill repo;
per-session it is fed by data only:
  - <edit>/state.json          written by the skill (phase, files, message)
  - <edit>/edl.json            the cut (segments shown/trimmed on the timeline)
  - <edit>/cut.mp4             current render (played + scrubbed)
  - <edit>/preview_edits.json  WRITTEN BY THE UI when the user saves timeline
                               adjustments — the skill reads, validates, applies
                               and re-renders.
  - <edit>/corrections.json    dirty flags + headline do operador; a UI grava
                               headline/captions/EDL nas fontes de verdade
                               (edit-data.json, captions.json, edl.json)
  - <edit>/preview_style.json  WRITTEN BY THE UI at the Fase 1 → Fase 2 gate:
                               editing style, caption style, edit elements.

Routes:
  /                     the app (from <skill>/assets/preview/)
  /assets/<file>        app files (css/js/logo)
  /media/<path>         files under --root (the edit dir) — Range supported
  /gen/waveform.json    min/max audio peaks of cut.mp4 (auto-(re)generated)
  /gen/thumbs/<n>.jpg   timeline filmstrip thumbs (auto-generated, 1 per 2s)
  /api/state    GET     state.json + mtimes (UI polls this to hot-reload)
  /api/save     POST    body → <edit>/preview_edits.json (atomic), or
                        <edit>/preview_style.json when body.type=="style-setup"
  /api/corrections POST persist headline/legenda/EDL; op=apply dispara o executor
  /api/apply-plan GET   plano testável: reuseCut vs rebuildCut
  /api/apply-status GET progresso amigável do Apply
  /api/open-folder POST opens Explorer at finalVideo (falls back to the edit
                        dir) — local machine only, mirrors "reveal in Finder"
  /api/open-final  POST opens the delivered mp4 in the OS player (startfile)
  /api/cover       POST {t} → JPEG do frame na agulha em cover.jpg + thumb.jpg
                        (não remuxa o MP4; a capa do arquivo continua no render)
  /api/default-style POST body → <skill>/assets/preview/default-style.json —
                        the ONE exception to "assets/preview is data-fed, not
                        written": a shared "house style" data file, read by
                        every project's defaultStyle(), not app.js itself
  /api/images/search GET ?q= — Pexels results as JSON (thumb + id + credit),
                        nothing downloaded yet; the UI shows these as a picker
  /api/images/pick  POST {url, credit} → downloads into
                        <edit>/remotion/public/pexels/ and returns the local
                        path, so an insert can point at it
  /painel           GET  cross-project dashboard (every sibling project's phase,
                        delivery health and pending requests)
  /api/projects     GET  the data behind /painel
  /p/<pasta>/…      ANY  the SAME editor, scoped to any project under
                        --projects-root: the prefix rebinds `root` for one
                        request, so /p/Foo/api/state and /p/Foo/media/x read
                        Foo. One server serves every project; the dashboard's
                        `editor` button links here.

Usage:
    uv run helpers/preview_server.py --root <videos_dir>/edit [--port 4820]
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import array
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

# The image picker reuses pexels_search.py's own search/download/slugify
# rather than reimplementing the API call — same helper the skill runs from
# the CLI, so a fix there fixes both. Imported lazily-ish (module lives
# beside this one) and tolerated missing: requests is a dependency of the
# helper, not of serving a preview, so a bad install should degrade the
# picker, not stop the whole server from booting.
try:
    import pexels_search
except Exception:  # noqa: BLE001 — missing deps must not break the server
    pexels_search = None

# Repo root on path so we can reuse the Windows "no CMD flash" helper.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
try:
    from app.win_process import hide_console_kwargs
except Exception:  # noqa: BLE001 — helpers can run outside the app package
    def hide_console_kwargs() -> dict:  # type: ignore[misc]
        return {}


def _run(cmd, **kwargs):
    """subprocess.run without flashing a CMD window on Windows."""
    kwargs = {**hide_console_kwargs(), **kwargs}
    return subprocess.run(cmd, **kwargs)


APP_DIR = _REPO / "assets" / "preview"
STUDIO_DIR = APP_DIR.parent / "studio"

# A running server holds the Python it was STARTED with, while the browser is
# always handed the current app.js — so after the skill is updated the UI grows
# a button whose route does not exist yet, and clicking it 404s into a blank
# tab. It looks like a broken feature; it is a stale process. Remember the
# file's mtime at boot and compare later, so the panel can say so out loud
# instead of leaving you to guess.
SERVER_MTIME_AT_BOOT = Path(__file__).stat().st_mtime
PEAKS_PER_SEC = 40
THUMB_EVERY_S = 2.0
THUMB_HEIGHT = 90

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".srt": "text/plain; charset=utf-8",
}

_thumb_lock = threading.Lock()

# Um refazimento de copia leve por projeto de cada vez: o editor
# pergunta pela copia a cada abertura, e sem isto cada pergunta
# abriria um ffmpeg novo no mesmo arquivo.
_PROXY_LOCK = threading.Lock()
_PROXY_REFAZENDO: set[str] = set()
_thumb_state: dict[str, float] = {}  # video path -> mtime generated


def probe_duration(path: Path) -> float:
    out = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def gen_waveform(video: Path, out_json: Path) -> None:
    """Decode audio to mono s16 and store min/max peak pairs per bucket (0-100)."""
    rate = 8000
    raw = _run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn",
         "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    per_bucket = max(1, rate // PEAKS_PER_SEC)
    mins: list[int] = []
    maxs: list[int] = []
    for i in range(0, len(samples), per_bucket):
        chunk = samples[i:i + per_bucket]
        if not chunk:
            continue
        mins.append(round(min(chunk) / 32768 * 100))
        maxs.append(round(max(chunk) / 32768 * 100))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "peaksPerSec": PEAKS_PER_SEC,
        "duration": len(samples) / rate,
        "min": mins,
        "max": maxs,
        "srcMtime": video.stat().st_mtime,
    }), encoding="utf-8")
    tmp.replace(out_json)


def gen_thumbs(video: Path, out_dir: Path) -> None:
    """Filmstrip thumbs: one small jpg every THUMB_EVERY_S seconds."""
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    _run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps=1/{THUMB_EVERY_S},scale=-2:{THUMB_HEIGHT}",
         "-q:v", "6", str(out_dir / "%04d.jpg")],
        check=False, capture_output=True,
    )
    (out_dir / "meta.json").write_text(json.dumps({
        "everySec": THUMB_EVERY_S,
        "count": len(list(out_dir.glob("*.jpg"))),
        "srcMtime": video.stat().st_mtime,
    }), encoding="utf-8")


def _bring_window_to_front(want_title_start: str, timeout_s: float = 2.0) -> bool:
    """Force the just-opened Explorer window to the foreground.

    Spawning explorer.exe from this server DOES open the window — it just
    opens BEHIND whatever the user is looking at (Claude Code, the browser),
    because Windows blocks a background process from stealing focus; a plain
    SetForegroundWindow from here is silently downgraded to a taskbar flash.
    The documented workaround is AttachThreadInput: temporarily join the
    input queue of whichever thread currently owns the foreground window, so
    this process is treated as if IT were already in the foreground chain,
    then the real SetForegroundWindow call is honoured instead of ignored.
    Polls briefly since the window may not exist yet the instant explorer.exe
    returns (it can still be handing off to the shell process).
    """
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        found = []

        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.startswith(want_title_start):
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        if found:
            hwnd = found[0]
            fg_hwnd = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.AttachThreadInput(target_thread, fg_thread, True)
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE — undoes a minimized state
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
            user32.AttachThreadInput(target_thread, fg_thread, False)
            return True
        time.sleep(0.1)
    return False


# ffprobe costs ~40ms per file and the dashboard probes every delivery on
# every refresh — cache on (path, mtime, size) so a re-scan is instant and a
# re-rendered file still gets re-probed.
_dur_cache: dict[tuple[str, float, int], float | None] = {}


def esquentar_painel(roots) -> None:
    """Mede as duracoes do painel em segundo plano, no arranque.

    `/api/projects` faz um `ffprobe` por projeto: com os 187 do usuario a
    primeira chamada custa **31,5s** e a segunda 0,2s. O cache ja existia;
    quem pagava os 31 segundos era sempre quem abriu a tela.

    So leitura. Falhar aqui nao muda nada — a rota mede na hora.
    """
    def _trabalho() -> None:
        try:
            for proot in roots or ():
                proot = Path(proot)
                if not proot.is_dir():
                    continue
                for edit in sorted(proot.glob("*/edit")):
                    for mp4 in edit.glob("*.mp4"):
                        if mp4.name in ("cut.mp4", "base.mp4",
                                        "cut_proxy.mp4", "final_proxy.mp4"):
                            continue
                        probe_duration_cached(mp4)
        except Exception:  # noqa: BLE001 — conforto, nunca derruba o app
            pass

    threading.Thread(target=_trabalho, daemon=True,
                     name="painel-esquentar").start()


def probe_duration_cached(p: Path) -> float | None:
    try:
        st = p.stat()
    except OSError:
        return None
    key = (str(p), st.st_mtime, st.st_size)
    if key not in _dur_cache:
        d = probe_duration(p)
        # probe_duration returns 0.0 both for "unreadable" and "empty"; for the
        # dashboard the distinction matters (a truncated MP4 must read as
        # BROKEN, not as a 0-second video), so collapse 0 to None.
        _dur_cache[key] = d if d > 0 else None
    return _dur_cache[key]


_proc_cache: dict[str, object] = {"at": 0.0, "lines": []}


def running_ativavid_processes() -> list[str]:
    """Command lines of every live preview_server / watch_edits process.

    The dashboard uses this to say which projects currently have something
    attached to them. That question caused real damage: a watcher left armed
    on a finished project applied a style change nobody was expecting, and
    nothing on screen had said the project was still being watched.

    Cached for a few seconds — the WMI query costs ~300ms and a scan asks once
    for every project. Any failure degrades to "unknown", never to a wrong
    claim that a project is idle.
    """
    now = time.time()
    if now - float(_proc_cache["at"]) < 5.0:
        return list(_proc_cache["lines"])  # type: ignore[arg-type]
    lines: list[str] = []
    try:
        out = _run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'preview_server|watch_edits' } | "
             "ForEach-Object { $_.CommandLine }"],
            # stdin=DEVNULL is the fix, not decoration: the server usually runs
            # detached (Start-Process, hidden, handles redirected), and a child
            # that inherits a dead stdin can come back with stdout None. The
            # same query run from a normal shell always worked, which is what
            # made this look like a query bug instead of a handle bug.
            # encoding/errors are the actual fix. PowerShell emits the project
            # paths, which here contain "Amanhã", "LUMINÁRIA", "café" — the
            # default decode raised UnicodeDecodeError inside subprocess's
            # reader THREAD, which killed the thread and left stdout as None.
            # That None was the AttributeError that 500'd the whole dashboard,
            # three layers away from the real cause.
            capture_output=True, text=True, timeout=8, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
        )
        # `or ""`: observed None here on Windows when the server itself was
        # launched detached with redirected handles. Root cause unproven, so
        # this guards the symptom rather than claiming a fix — and the except
        # below is deliberately broad for the same reason: "which processes are
        # attached" is a nice-to-have, and it must never be able to take the
        # whole dashboard down with it (it did: HTTP 500 on /api/projects).
        if out.returncode == 0:
            lines = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    except Exception as e:
        # Degrade, but not in silence: a broad except that swallows the reason
        # turns "feature is off" into an unsolvable mystery. Logged once.
        if not _proc_cache.get("warned"):
            print(f"[processos] deteccao indisponivel: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            _proc_cache["warned"] = True
        lines = []
    _proc_cache["at"] = now
    _proc_cache["lines"] = lines
    return list(lines)


_TEMPLATE_EDITABLE = {"CustomGraphics.tsx"}


def template_state(edit: Path) -> str:
    """'ok' | 'stale' | 'none' — does this project's src/ match the shipped template?

    Same comparison check_template_integrity.py makes, surfaced per project so a
    whole shelf of projects can be seen at once. It matters because the template
    is SHARED: improving it (a new caption style, an end card) instantly leaves
    every already-scaffolded project behind, and the only sign today is a failed
    integrity check at render time — one project at a time, after the wait.

    CustomGraphics.tsx is excluded: it is the one file a project is meant to own.
    """
    src = edit / "remotion" / "src"
    if not src.is_dir():
        return "none"
    for track in ("shortform", "longform"):
        tsrc = APP_DIR.parent / track / "src"
        if not tsrc.is_dir():
            continue
        shipped = {p.name for p in tsrc.glob("*.ts*")} - _TEMPLATE_EDITABLE
        local = {p.name for p in src.glob("*.ts*")} - _TEMPLATE_EDITABLE
        if not shipped or not (shipped & local):
            continue
        if shipped - local:            # a file the template has and this project lacks
            return "stale"
        for name in shipped:
            try:
                if (tsrc / name).read_bytes() != (src / name).read_bytes():
                    return "stale"
            except OSError:
                return "stale"
        return "ok"
    return "none"


def _pedido_e_novo(pedido: Path, delivery: dict | None, edit: Path) -> bool:
    """O pedido salvo e mais novo que o video entregue?

    Sem essa comparacao, "existe o arquivo" marcava como pendente coisa ja
    aplicada: dos 12 projetos do usuario que o painel acusava, 10 tinham o
    pedido mais VELHO que a entrega — sobra, nao trabalho perdido.
    """
    try:
        if not pedido.is_file():
            return False
        nome = (delivery or {}).get("name")
        if not nome:
            return True          # sem entrega, o pedido esta mesmo pendente
        alvo = edit / str(nome)
        if not alvo.is_file():
            return True
        return pedido.stat().st_mtime > alvo.stat().st_mtime
    except OSError:
        return False


def describe_pending(edit: Path) -> dict | None:
    """One-line summary of whatever request is sitting unapplied in a project.

    The dashboard used to say only THAT something was pending, which still
    meant opening the file to learn anything. The interesting part is cheap to
    extract and is exactly what decides whether it matters.
    """
    style_p, edits_p = edit / "preview_style.json", edit / "preview_edits.json"
    for p, kind in ((style_p, "style"), (edits_p, "edits")):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"kind": kind, "savedAt": None, "summary": "arquivo ilegível"}
        saved = d.get("savedAt")
        if kind == "style":
            bits = [d.get("editName") or d.get("edit"),
                    f"headline {d.get('headlineName') or d.get('headline')}",
                    f"legenda {d.get('captionsName') or d.get('captions')}"]
            if d.get("note"):
                bits.append(f"obs: {d['note']}")
            return {"kind": "style", "savedAt": saved,
                    "summary": " · ".join(b for b in bits if b)}
        parts = []
        if d.get("notes"):
            parts.append(f"{len(d['notes'])} marcação(ões)")
        if d.get("edl"):
            e = d["edl"]
            if e.get("removed"):
                parts.append(f"{len(e['removed'])} take(s) removido(s)")
            if e.get("changes"):
                parts.append(f"{len(e['changes'])} corte(s) ajustado(s)")
        if d.get("captionFixes"):
            parts.append(f"{len(d['captionFixes'])} legenda(s) corrigida(s)")
        if d.get("editData", {}).get("newInserts"):
            parts.append(f"{len(d['editData']['newInserts'])} imagem(ns) nova(s)")
        return {"kind": "edits", "savedAt": saved,
                "summary": " · ".join(parts) or "ajustes salvos"}
    return None


class Handler(BaseHTTPRequestHandler):
    root: Path  # set on the class by main()
    projects_roots: list[Path] = []
    scoped = False  # per-request: is this a /p/<pasta>/ view of ANOTHER project?
    scope_miss = False  # per-request: /p/<pasta>/ nomeou um projeto inexistente
    # callable(edit_dir) -> nome do card do hub, ou None; o desktop_server
    # empresta o dele (o preview nao enxerga o banco de jobs)
    titulo_do_card = None
    protocol_version = "HTTP/1.1"

    # ---- helpers ----
    def _hdr(self, code: int, ctype: str, length: int | None = None,
             extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self._hdr(code, "application/json; charset=utf-8", len(body))
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except OSError as e:
            if getattr(e, "winerror", None) in (10053, 10054):
                return
            if getattr(e, "errno", None) in (32, 104):
                return
            raise

    def _send_file(self, path: Path) -> None:
        """Static file with HTTP Range support (video scrubbing needs it)."""
        if not path.is_file():
            self._json({"error": f"not found: {path.name}"}, 404)
            return
        size = path.stat().st_size
        ctype = MIME.get(path.suffix.lower(), "application/octet-stream")
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                code = 206
        length = end - start + 1
        extra = {"Content-Range": f"bytes {start}-{end}/{size}"} if code == 206 else None
        self._hdr(code, ctype, length, extra)
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                except OSError as e:
                    # Windows: WinError 10053/10054 when WebView cancela o stream
                    if getattr(e, "winerror", None) in (10053, 10054):
                        return
                    if getattr(e, "errno", None) in (32, 104):
                        return
                    raise
                remaining -= len(chunk)

    def _safe(self, base: Path, rel: str) -> Path | None:
        rel = unquote(str(rel or "")).lstrip("/").replace("\\", "/")
        if not rel or ".." in Path(rel).parts:
            return None
        p = (base / rel).resolve()
        root = base.resolve()
        try:
            p.relative_to(root)
        except ValueError:
            return None
        return p

    def _refazer_proxy_atrasado(self, cut: Path) -> None:
        """Manda refazer a copia leve deste projeto, uma vez.

        A copia atrasada e ignorada (a sessao usa o video cheio), mas sem
        ninguem refaze-la o projeto fica pesado para sempre: 46 dos 186
        projetos do usuario chegaram assim. Aqui o conserto acontece onde
        importa — no projeto que ele abriu — e a PROXIMA abertura ja e
        leve.

        `_PROXY_REFAZENDO` evita a enxurrada: o editor pergunta pela copia
        a cada abertura, e sem o registro cada pergunta abriria um ffmpeg.
        """
        chave = str(self.root)
        with _PROXY_LOCK:
            if chave in _PROXY_REFAZENDO:
                return
            _PROXY_REFAZENDO.add(chave)

        def _solta() -> None:
            with _PROXY_LOCK:
                _PROXY_REFAZENDO.discard(chave)

        try:
            from make_proxy import refazer_em_fundo  # type: ignore

            t = refazer_em_fundo(cut, self.root)
        except Exception:  # noqa: BLE001 — copia e conforto, nunca o produto
            t = None
        if t is None:
            _solta()
            return
        threading.Thread(target=lambda: (t.join(), _solta()),
                         daemon=True, name="proxy-solta").start()

    def _proxy_util(self) -> Path | None:
        """O `cut_proxy.mp4`, mas so enquanto ele for o corte de agora.

        O proxy e uma copia leve do corte, e o corte muda: cada "Aplicar
        alteracoes" refaz o `cut.mp4`. Medido nos projetos do usuario, **46
        de 186 tem o proxy mais velho que o corte** — um deles por 3,7
        dias. Servir esse arquivo faria o editor tocar um video que nao e o
        corte atual, com trechos que ja nao existem: pior que lento.

        Velho e o mesmo que nao existir. Quem pergunta ja sabe cair no
        arquivo cheio.
        """
        px = self.root / "cut_proxy.mp4"
        cut = self.root / "cut.mp4"
        if not px.is_file():
            return None
        try:
            if cut.is_file() and px.stat().st_mtime < cut.stat().st_mtime:
                self._refazer_proxy_atrasado(cut)
                return None
        except OSError:
            return None
        return px

    def _proxy_final_util(self) -> Path | None:
        """O `final_proxy.mp4`, enquanto ele for do video entregue de agora.

        Mesma doenca do proxy do corte: refazer a Fase 2 troca o arquivo
        entregue, e servir a copia velha faria a aba Visual mostrar um
        video que ja nao existe — pior que lento. Velho e o mesmo que nao
        existir; quem pergunta ja sabe cair no arquivo cheio.
        """
        px = self.root / "final_proxy.mp4"
        # Com o state.json na mao a escolha e o nome DECLARADO; sem ele a
        # busca cai no "mp4 mais novo", que numa pasta com sobra de apply
        # (`cut.apply.tmp.mp4`) pode apontar para um arquivo de trabalho —
        # e a copia ficaria eternamente "atrasada", refazendo sem parar.
        estado: dict = {}
        try:
            estado = json.loads(
                (self.root / "state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            estado = {}
        try:
            rel = self._resolve_final_video(estado if isinstance(estado, dict) else {})
        except Exception:  # noqa: BLE001
            rel = None
        final = self._safe(self.root, rel) if rel else None
        if final is None or not final.is_file():
            return None
        if not px.is_file():
            self._refazer_proxy_final(final)
            return None
        try:
            if px.stat().st_mtime < final.stat().st_mtime:
                self._refazer_proxy_final(final)
                return None
        except OSError:
            return None
        return px

    def _refazer_proxy_final(self, final: Path) -> None:
        """Manda fazer a copia leve do final, uma vez por projeto.

        Os 186 projetos que ja existem nao tem essa copia: ela nasce aqui,
        na primeira vez que ele abre a aba Visual. Enquanto nao fica pronta
        o editor toca o arquivo cheio, como antes.
        """
        chave = str(self.root) + "|final"
        with _PROXY_LOCK:
            if chave in _PROXY_REFAZENDO:
                return
            _PROXY_REFAZENDO.add(chave)

        def _solta() -> None:
            with _PROXY_LOCK:
                _PROXY_REFAZENDO.discard(chave)

        try:
            from make_proxy import proxy_do_final  # type: ignore

            t = proxy_do_final(final, self.root)
        except Exception:  # noqa: BLE001 — copia e conforto, nunca o produto
            t = None
        if t is None:
            _solta()
            return
        threading.Thread(target=lambda: (t.join(), _solta()),
                         daemon=True, name="proxy-final-solta").start()

    def _current_video(self) -> Path | None:
        state_p = self.root / "state.json"
        rel = "cut.mp4"
        if state_p.exists():
            try:
                rel = json.loads(state_p.read_text(encoding="utf-8")).get("video") or rel
            except json.JSONDecodeError:
                pass
        p = self._safe(self.root, rel)
        return p if p and p.exists() else None

    # ---- routes ----
    def _scope(self, path: str) -> str:
        """Serve the editor for ANY scanned project, at /p/<pasta>/….

        The alternative was spawning a second server per project — a port and a
        process each, and this user has already had 21 orphans pointing at
        folders that no longer existed. A path prefix costs neither: it rebinds
        `root` for the length of ONE request (an instance attribute shadowing
        the class one), so every route below reads the right project without
        knowing this exists. No prefix → the server's own root, unchanged.
        """
        self.root = type(self).root          # reset: keep-alive reuses instances
        self.scoped = False
        self.scope_miss = False
        m = re.match(r"/p/([^/]+)(/.*)?$", path)
        if not m:
            return path
        folder = unquote(m.group(1))
        for proot in self.projects_roots:
            edit = self._project_edit_dir(str(proot / folder / "edit"))
            if edit:
                self.root, self.scoped = edit, True
                return m.group(2) or "/"
        # Unknown project. Falling through to the server's own root was fine
        # for a GET — a stale bookmark shows SOMETHING rather than a dead page.
        # It is not fine for a write: /p/ProjetoApagado/api/save would land in
        # whichever project this server was started on, under a URL naming a
        # different one, and the UI would confirm "salvo". Renaming a folder is
        # enough to trigger it. So: remember the miss, and let do_POST refuse.
        self.scope_miss = True
        return m.group(2) or "/"

    def do_HEAD(self) -> None:  # noqa: N802
        """Existe o arquivo? Sem corpo.

        O editor pergunta assim se o projeto tem a copia leve do corte
        (`cut_proxy.mp4`, 13 a 22x menor que o `cut.mp4`) antes de decidir
        o que tocar na linha do tempo. Sem esta funcao o servidor responde
        **501 Unsupported method**, a pergunta vira "nao tem", e o editor
        toca o arquivo cheio — 4K HDR — em 186 projetos que TEM a copia.

        So arquivo. HEAD numa rota de API responde 405: rodar o trabalho de
        um GET para jogar a resposta fora seria pior que nao atender.
        """
        path = urlparse(self.path).path
        alvo = None
        if path.startswith("/media/"):
            alvo = self._safe(self.root, path[len("/media/"):])
            # A mesma regra do GET, senao a pergunta e a resposta discordam.
            if alvo is not None and alvo.name == "cut_proxy.mp4" and not self._proxy_util():
                self._sem_corpo(404)
                return
            if (alvo is not None and alvo.name == "final_proxy.mp4"
                    and not self._proxy_final_util()):
                self._sem_corpo(404)
                return
        elif path.startswith("/assets/studio/"):
            alvo = self._safe(STUDIO_DIR, path[len("/assets/studio/"):])
        elif path.startswith("/assets/"):
            alvo = self._safe(APP_DIR, path[len("/assets/"):])
        else:
            self._sem_corpo(405)
            return
        if alvo is None or not alvo.is_file():
            self._sem_corpo(404)
            return
        self._sem_corpo(
            200,
            ctype=MIME.get(alvo.suffix.lower(), "application/octet-stream"),
            tamanho=alvo.stat().st_size,
        )

    def _sem_corpo(self, code: int, *, ctype: str | None = None,
                   tamanho: int | None = None) -> None:
        self.send_response(code)
        if ctype:
            self.send_header("Content-Type", ctype)
        if tamanho is not None:
            self.send_header("Content-Length", str(tamanho))
            # o mesmo Accept-Ranges do GET: quem pergunta por HEAD costuma
            # querer saber se da para pedir pedaco depois
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self._scope(self.path.split("?", 1)[0])
        # /p/<pasta> desconhecida não pode cair no dummy do hub (Estilo padrão /
        # loja-teste): o editor acharia que não há cut.mp4 e herdaria outra marca.
        if getattr(self, "scope_miss", False) and path.startswith("/api/"):
            self._json({"ok": False, "error": "projeto não encontrado"}, 404)
            return
        if path in ("/", "/index.html", "/fase1", "/estilo", "/fase2", "/estilo-padrao"):
            # the last SPA tab routes (app.js reads location.pathname) — a real
            # path, not a query string or hash. /estilo-padrao is the desktop
            # "house style" page (same index, HOUSE_STYLE mode in app.js).
            self._send_file(APP_DIR / "index.html")
        elif path.startswith("/assets/studio/"):
            p = self._safe(STUDIO_DIR, path[len("/assets/studio/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path.startswith("/assets/"):
            p = self._safe(APP_DIR, path[len("/assets/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path.startswith("/media/"):
            p = self._safe(self.root, path[len("/media/"):])
            # Proxy mais velho que o corte nao e proxy: entregar isso faria
            # o editor tocar um video que nao e o corte de agora.
            if p is not None and p.name == "cut_proxy.mp4" and not self._proxy_util():
                self._json({"error": "proxy desatualizado"}, 404)
                return
            if (p is not None and p.name == "final_proxy.mp4"
                    and not self._proxy_final_util()):
                self._json({"error": "proxy do final desatualizado"}, 404)
                return
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path == "/gen/waveform.json":
            self._waveform()
        elif path.startswith("/gen/thumbs/"):
            self._thumbs(path[len("/gen/thumbs/"):])
        elif path == "/api/health":
            self._health()
        elif path == "/api/brand-presets":
            self._brand_presets()
        elif path == "/api/events":
            self._events()
        elif path == "/api/state":
            self._state()
        elif path == "/api/intent":
            self._intent_get()
        elif path == "/api/versions":
            self._versions_get()
        elif path == "/api/apply-plan":
            self._apply_plan_get()
        elif path == "/api/apply-status":
            self._apply_status_get()
        elif path == "/api/corrections":
            self._corrections_get()
        elif path == "/painel":
            self._send_file(APP_DIR / "painel.html")
        elif path == "/api/projects":
            self._scan_projects()
        elif path == "/api/images/search":
            qs = parse_qs(urlparse(self.path).query)
            q = qs.get("q", [""])[0].strip()
            # 4.96: `source=freepik&kind=video` busca no banco da Freepik
            # (Magnific); sem os dois, e o Pexels de sempre.
            self._images_search(q, source=qs.get("source", [""])[0].strip().lower(),
                                kind=qs.get("kind", [""])[0].strip().lower())
        else:
            self._json({"error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        route = self._scope(self.path.split("?", 1)[0])
        if self.scope_miss:
            # never write into a project the URL did not ask for
            self._json({"ok": False, "error":
                        "Esse projeto não existe mais nesta pasta — nada foi salvo. "
                        "Volte ao painel e abra o projeto de novo."}, 404)
            return
        if route == "/api/library/trecho":
            self._salvar_trecho()
            return
        if route == "/api/open-folder":
            self._open_folder()
            return
        if route == "/api/open-final":
            self._open_final()
            return
        if route == "/api/project/action":
            self._project_action()
            return
        if route == "/api/default-style":
            self._save_default_style()
            return
        if route == "/api/images/pick":
            self._images_pick()
            return
        if route == "/api/cover":
            self._save_cover()
            return
        if route == "/api/append-cta":
            self._append_cta()
            return
        if route == "/api/intent":
            self._intent_post()
            return
        if route == "/api/restaurar-trecho":
            self._restaurar_trecho()
            return
        if route == "/api/versions":
            self._versions_post()
            return
        if route == "/api/corrections":
            self._corrections_post()
            return
        if route == "/api/style-export":
            self._style_export()
            return
        if route == "/api/apply-plan":
            self._apply_plan_get()
            return
        if route != "/api/save":
            self._json({"error": "unknown route"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        body["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # The style pick goes to its own file. It is a one-time setup decision,
        # not a correction, and sharing preview_edits.json would make one save
        # clobber the other (they are written at different moments, by different
        # screens, and the skill consumes+deletes them independently).
        name = "preview_style.json" if body.get("type") == "style-setup" else "preview_edits.json"
        # O MODO DE EDICAO e do job_intent.json, que o run_fast le a cada
        # render (merge_into_preset) e que e knob de replanejo (cutStyle).
        # Sem esta gravacao nao existia jeito NENHUM de tirar um projeto da
        # Edicao leve: o usuario trocava o estilo, mandava refazer, e o corte
        # heuristico saia identico — tres vezes no mesmo dia (24/08), 70,4s
        # nas tres. Gravar aqui e o que faz "Salvar e refazer" replanejar.
        modo = str(body.get("editingIntent") or "").strip().lower()
        if body.get("type") == "style-setup" and modo in (
                "light", "dynamic", "complete", "intact"):
            try:
                from app.editing_intent import load as _li, save as _si

                atual = _li(self.root) or {}
                if str(atual.get("editingIntent") or "") != modo:
                    atual["editingIntent"] = modo
                    _si(self.root, atual)
                    print(f"[estilo] modo de edição → {modo}", flush=True)
            except Exception as e:  # noqa: BLE001 - estilo salva mesmo assim
                print(f"[estilo] modo não gravado: {e}", flush=True)
        # MARCA do video. Mesma logica do modo de edicao acima: o
        # `job_intent.json` e lido a cada render, e e dele que saem as cores
        # e o texto do card final. Sem gravar aqui, trocar a marca na tela
        # mudava o editor e o video saia com a marca velha assim mesmo.
        marca = str(body.get("brandId") or "").strip()
        # O PRESET escolhido na linha de cima do editor (4.28). Ate entao
        # aquela linha trocava a MARCA, conceito que saiu do app na 4.19 —
        # quem decide cor, legenda e cartao final e o preset.
        preset_id = str(body.get("brandPresetId") or "").strip()
        if body.get("type") == "style-setup" and (marca or preset_id):
            try:
                from app.editing_intent import load as _lm, save as _sm

                atual = _lm(self.root) or {}
                mudou = False
                if marca and str(atual.get("brandId") or "") != marca:
                    atual["brandId"] = marca
                    mudou = True
                if preset_id and str(atual.get("brandPresetId") or "") != preset_id:
                    atual["brandPresetId"] = preset_id
                    mudou = True
                if mudou:
                    _sm(self.root, atual)
                    print(f"[estilo] preset do vídeo → {preset_id or marca}",
                          flush=True)
            except Exception as e:  # noqa: BLE001 - estilo salva mesmo assim
                print(f"[estilo] preset não gravado: {e}", flush=True)
        out = self.root / name
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out)
        # O VEREDITO do apply volta na resposta. Antes ele era descartado e a
        # resposta dizia "ok" sempre: a tela limpava a correcao, cantava
        # "Legenda corrigida" e a palavra continuava errada no video. Pior no
        # meio do caminho — o apply grava captions.json ANTES das cues, entao
        # um erro ali deixa os dois discordando, calado.
        #
        # `changed == 0` NAO e falha: no app o mesmo fix passa por aqui duas
        # vezes (no clique e ao salvar) e na segunda o texto ja esta no lugar.
        # Quem separa "ja aplicado" de "nao achei" e o apply_caption_fixes.
        cap_res: dict | None = None
        snap_err: str | None = None
        if name == "preview_edits.json" and body.get("captionFixes"):
            try:
                from app.caption_fixes import apply_caption_fixes

                cap_res = apply_caption_fixes(self.root, body.get("captionFixes"))
            except Exception as e:
                cap_res = {"ok": False, "changed": 0, "error": f"nao consegui gravar a legenda: {e}"}
        if name == "preview_edits.json" and body.get("edl"):
            try:
                from app.project_versions import snapshot

                snapshot(
                    self.root,
                    origin="save",
                    description="Antes de salvar nova revisão",
                    extra={"edl": body.get("edl"), "intent": body.get("intent")},
                )
            except Exception as e:
                # Nao derruba o salvamento — o preview_edits.json ja esta
                # gravado. Mas tambem nao some: este snapshot e o que permite
                # "voltar versao", e falhar calado deixa o usuario achando que
                # tem para onde voltar.
                print(f"[warn] snapshot de versao falhou: {e}", flush=True)
                snap_err = str(e)[:200]
        resp: dict = {"ok": True, "file": str(out)}
        if cap_res is not None:
            resp["captionFix"] = cap_res
        if snap_err:
            resp["snapshotError"] = snap_err
        self._json(resp)

    def _salvar_trecho(self) -> None:
        """Guarda um trecho do video na Biblioteca, como clipe de b-roll.

        O tempo chega no relogio do arquivo que ele esta VENDO (a tela
        converte com `draftToRendered`): assim o clipe e exatamente o que
        passou na frente dele.
        """
        # Le o corpo COMO AS OUTRAS rotas daqui: `self._read_json()` e do
        # handler do outro servidor, e o editor roda sob o `DesktopHandler`
        # — que herda este arquivo e nao tem aquele metodo. O teste ao vivo
        # devolveu "Failed to fetch" e o log, o AttributeError.
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"ok": False, "error": "JSON inválido"}, 400)
            return
        try:
            from app.broll_library import salvar_trecho
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": str(e)}, 500)
            return
        alvo = self.root / str(body.get("arquivo") or "cut.mp4")
        try:
            alvo = alvo.resolve()
            alvo.relative_to(self.root.resolve())
        except (OSError, ValueError):
            self._json({"ok": False, "error": "arquivo fora do projeto"}, 400)
            return
        try:
            out = salvar_trecho(
                alvo,
                inicio=float(body.get("inicio") or 0),
                fim=float(body.get("fim") or 0),
                categoria=str(body.get("categoria") or "reacao"),
                nome=str(body.get("nome") or ""),
                projects_root=self.root.parent.parent,
            )
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)
            return
        except (OSError, Exception) as e:  # noqa: BLE001
            self._json({"ok": False, "error": f"não deu para recortar: {e}"}, 500)
            return
        self._json(out)

    def _open_folder(self) -> None:
        """Reveal the exported file in Explorer — same idea as any NLE's
        "show in folder" on export. finalVideo when it exists (selects the
        file itself), else the edit dir (nothing delivered yet)."""
        state_p = self.root / "state.json"
        state: dict = {}
        if state_p.exists():
            try:
                state = json.loads(state_p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        try:
            from app.delivery_pack import folder_to_open

            packed = folder_to_open(self.root)
            if packed.is_dir() and packed != self.root:
                target = packed
                try:
                    if target.is_file():
                        subprocess.run(f'explorer /select,"{target}"')
                    else:
                        subprocess.run(["explorer", str(target)])
                except OSError as e:
                    self._json({"ok": False, "error": str(e)}, 500)
                    return
                self._json({"ok": True, "path": str(target)})
                return
        except Exception:
            pass
        # same stale-pointer resolution the Final tab uses — see _resolve_final_video
        rel = self._resolve_final_video(state)
        target = self._safe(self.root, rel) if rel else None
        if (not target or not target.exists()) and rel and self.root.name.lower() == "edit":
            parent_hit = self.root.parent / Path(unquote(rel)).name
            if parent_hit.exists():
                target = parent_hit
        if not target or not target.exists():
            target = self.root
        try:
            if target.is_file():
                # NOT a list: subprocess.list2cmdline would wrap the whole
                # "/select,<path>" token in one pair of quotes when the path
                # has a space (list2cmdline quotes an argv element as a
                # whole, unaware /select, is a prefix explorer.exe expects
                # OUTSIDE any quoting). Explorer then fails to recognize the
                # switch and silently opens its default location instead —
                # this is exactly what was firing on every click. A raw
                # command-line string bypasses that: on Windows, shell=False
                # with a str `args` is passed straight to CreateProcess with
                # no rewriting, so the quotes land only around the path.
                subprocess.run(f'explorer /select,"{target}"')
            else:
                subprocess.run(["explorer", str(target)])
        except OSError as e:
            self._json({"ok": False, "error": str(e)}, 500)
            return
        # Explorer titles a /select, window after the CONTAINING folder, not
        # the selected file — same name either way this resolves.
        want_title = target.parent.name if target.is_file() else target.name
        _bring_window_to_front(want_title)
        self._json({"ok": True, "path": str(target)})

    def _open_final(self) -> None:
        """Open the delivered file in the default player — same startfile
        the dashboard already uses for action=video."""
        state_p = self.root / "state.json"
        state: dict = {}
        if state_p.exists():
            try:
                state = json.loads(state_p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        rel = self._resolve_final_video(state)
        target = self._safe(self.root, rel) if rel else None
        if (not target or not target.is_file()) and rel and self.root.name.lower() == "edit":
            parent_hit = self.root.parent / Path(unquote(rel)).name
            if parent_hit.is_file():
                target = parent_hit
        if not target or not target.is_file():
            self._json({"ok": False, "error": "sem vídeo final"}, 404)
            return
        try:
            os.startfile(str(target))  # noqa: S606 — default player, user asked
        except OSError as e:
            self._json({"ok": False, "error": str(e)}, 500)
            return
        self._json({"ok": True, "path": str(target)})

    def _project_edit_dir(self, raw: str) -> Path | None:
        """Validate a path posted by /painel: it must be an <edit> dir that
        actually sits under one of the configured --projects-root folders.

        The dashboard hands back paths it got from the server, but the route is
        still reachable by anything on localhost — so re-derive trust here
        instead of trusting the round trip.
        """
        try:
            p = Path(raw).resolve()
        except (OSError, ValueError):
            return None
        if p.name != "edit" or not p.is_dir():
            return None
        for proot in self.projects_roots:
            try:
                p.relative_to(proot.resolve())
                return p
            except ValueError:
                continue
        return None

    def _project_action(self) -> None:
        """User-initiated actions from /painel. Every one of these is a click
        the person made on a row they are looking at — the dashboard itself
        still never acts on its own."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"ok": False, "error": "invalid JSON"}, 400)
            return
        edit = self._project_edit_dir(body.get("path") or "")
        if not edit:
            self._json({"ok": False, "error": "caminho fora das pastas configuradas"}, 400)
            return

        action = body.get("action")
        state: dict = {}
        sp = edit / "state.json"
        if sp.exists():
            try:
                state = json.loads(sp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {}
        resolved = self._resolve_final_video(state, edit)

        if action == "folder":
            target = (edit / resolved) if resolved else edit
            try:
                if target.is_file():
                    subprocess.run(f'explorer /select,"{target}"')
                else:
                    subprocess.run(["explorer", str(target)])
            except OSError as e:
                self._json({"ok": False, "error": str(e)}, 500)
                return
            _bring_window_to_front(target.parent.name if target.is_file() else target.name)
            self._json({"ok": True, "path": str(target)})
            return

        if action == "video":
            if not resolved:
                self._json({"ok": False, "error": "sem entrega ainda"}, 404)
                return
            target = edit / resolved
            try:
                os.startfile(str(target))  # noqa: S606 — default player, user asked
            except OSError as e:
                self._json({"ok": False, "error": str(e)}, 500)
                return
            self._json({"ok": True, "path": str(target)})
            return

        if action == "fixPointer":
            # the ONLY write this route can do, and only to the one key that is
            # provably wrong: finalVideo naming a file that is not on disk
            if not resolved:
                self._json({"ok": False, "error": "sem entrega para apontar"}, 404)
                return
            if not sp.exists():
                self._json({"ok": False, "error": "projeto sem state.json"}, 404)
                return
            before = state.get("finalVideo")
            if before == resolved:
                self._json({"ok": True, "unchanged": True, "finalVideo": resolved})
                return
            state["finalVideo"] = resolved
            tmp = sp.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(sp)
            self._json({"ok": True, "from": before, "finalVideo": resolved})
            return

        if action == "deleteProject":
            # To the RECYCLE BIN, never a hard delete. This is the only action
            # here that destroys work, and the whole project folder goes — the
            # sources, the renders, the transcripts. A wrong click has to stay
            # undoable, so it is a move, not an erase.
            proj = edit.parent
            for root in self.projects_roots:
                if proj.resolve() == root.resolve():   # never the roots themselves
                    self._json({"ok": False, "error": "isso e uma pasta raiz, nao um projeto"}, 400)
                    return
            # Confirmation is required and must name the folder: an accidental
            # POST cannot delete anything, and the UI has to have shown the
            # user which project it is about to remove.
            if (body.get("confirm") or "").strip() != proj.name:
                self._json({"ok": False, "error": "confirmacao nao confere com o nome do projeto"}, 400)
                return
            from app.recycle import RecycleError, send_to_recycle_bin

            try:
                send_to_recycle_bin(proj)
            except RecycleError as e:
                self._json({"ok": False, "error": str(e)[:200]}, 500)
                return
            self._json({"ok": True, "deleted": proj.name, "recycled": True})
            return

        if action == "fixTemplate":
            # Delegates to the existing checker rather than copying files here:
            # it already owns which files are template-owned and which one
            # (CustomGraphics.tsx) the project keeps. Two implementations of
            # that rule would drift.
            rem = edit / "remotion"
            if not rem.is_dir():
                self._json({"ok": False, "error": "projeto sem pasta remotion/"}, 404)
                return
            script = Path(__file__).resolve().parent / "check_template_integrity.py"
            p = _run([sys.executable, str(script), str(rem), "--fix"],
                     capture_output=True, text=True)
            state = template_state(edit)
            if state != "ok":
                tail = (p.stderr or p.stdout or "").strip().splitlines()
                self._json({"ok": False, "error": (tail[-1] if tail else "--fix falhou")[:200]}, 500)
                return
            self._json({"ok": True, "template": state})
            return

        self._json({"ok": False, "error": f"ação desconhecida: {action}"}, 400)

    def _append_cta(self) -> None:
        """Copia um MP4/MOV para a pasta do projeto e devolve o take do fim."""
        from app.append_source import append_cta

        if self.root.name.lower() != "edit":
            self._json({"error": "abra o vídeo pelo editor"}, 400)
            return
        project = self.root.parent
        ctype = self.headers.get("Content-Type", "")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n else b""
        filename = ""
        payload = b""
        src_path = ""
        duration_hint = None
        try:
            if "multipart/form-data" in ctype:
                from email import policy as email_policy
                from email.parser import BytesParser

                mime = (
                    b"Content-Type: " + ctype.encode("ascii", "ignore")
                    + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
                )
                msg = BytesParser(policy=email_policy.default).parsebytes(mime)
                for part in msg.iter_parts():
                    field = part.get_param("name", header="content-disposition") or ""
                    body = part.get_payload(decode=True) or b""
                    if field == "path":
                        src_path = body.decode("utf-8", "replace").strip()
                    elif field == "duration":
                        try:
                            duration_hint = float(body.decode("utf-8", "replace").strip())
                        except ValueError:
                            duration_hint = None
                    elif field == "file" or part.get_filename():
                        filename = part.get_filename() or filename
                        payload = body
            else:
                body = json.loads(raw or b"{}")
                src_path = str(body.get("path") or "")
                filename = str(body.get("filename") or "")
                try:
                    duration_hint = float(body.get("duration") or 0) or None
                except (TypeError, ValueError):
                    duration_hint = None
            self._json(append_cta(
                project,
                filename=filename,
                data=payload or None,
                src_path=src_path or None,
                duration_hint=duration_hint,
            ))
        except ValueError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self._json({"error": f"Não deu para acrescentar esse vídeo ({e})"}, 500)

    def _save_cover(self) -> None:
        """Frame at playhead → cover.jpg + thumb.jpg. Does not remux the MP4."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        video = self._current_video()
        try:
            from app.delivery_pack import resolve_final_mp4

            final = resolve_final_mp4(self.root)
            if final is not None:
                video = final
        except Exception:
            pass
        if not video:
            self._json({"ok": False, "error": "vídeo ainda não está pronto"}, 404)
            return
        try:
            t = float(body.get("t", 0) or 0)
        except (TypeError, ValueError):
            t = 0.0
        dur = probe_duration(video)
        if dur > 0:
            t = min(max(0.0, t), max(0.0, dur - 0.04))
        else:
            t = max(0.0, t)
        cover = self.root / "cover.jpg"
        thumb = self.root / "thumb.jpg"
        tmp = self.root / "_cover_pick.jpg"
        try:
            proc = _run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{t:.3f}", "-i", str(video),
                    "-frames:v", "1", "-q:v", "2", str(tmp),
                ],
                capture_output=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._json({"ok": False, "error": "não consegui capturar esse frame"}, 500)
            return
        if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 400:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            self._json({"ok": False, "error": "não consegui capturar esse frame"}, 500)
            return
        try:
            tmp.replace(cover)
        except OSError as e:
            self._json({"ok": False, "error": str(e)}, 500)
            return
        _run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(cover), "-vf", "scale=360:-2", "-q:v", "3", str(thumb),
            ],
            capture_output=True, timeout=20,
        )
        if self.root.name.lower() == "edit":
            try:
                shutil.copy2(cover, self.root.parent / "cover.jpg")
            except OSError:
                pass
        pack_name = ""
        try:
            from app.delivery_pack import ensure_delivery_pack

            packed = ensure_delivery_pack(self.root, force_cover=True)
            if packed:
                pack_name = packed.name
        except Exception:
            pack_name = ""
        self._json({
            "ok": True,
            "t": round(t, 3),
            "file": "capa.jpg" if pack_name else "cover.jpg",
            "pack": pack_name,
        })

    def _save_default_style(self) -> None:
        """The "house style" — every NEW project's Estilo tab starts here.
        Shared across every project's preview_server.py because it lives
        under APP_DIR (the skill's own assets/preview/), not under --root.
        A plain style object, same shape as state.json's own "style" key."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        out = APP_DIR / "default-style.json"
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out)
        self._json({"ok": True})

    # ---- image picker (search first, download only what's picked) ----
    def _images_search(self, query: str, source: str = "", kind: str = "") -> None:
        if not query:
            self._json({"ok": False, "error": "busca vazia"}, 400)
            return
        if source == "freepik":
            self._images_search_freepik(query, kind or "image")
            return
        if pexels_search is None:
            self._json({"ok": False, "error": "helper indisponível (requests instalado?)"}, 500)
            return
        try:
            key = pexels_search.load_api_key()
        except SystemExit as e:  # the helper sys.exit()s when the key is absent
            self._json({"ok": False, "error": str(e)}, 400)
            return
        try:
            # portrait: every short-form project is 9:16, and a landscape
            # insert in a vertical frame is nearly always the wrong crop
            photos = pexels_search.search(query, key, 12, "portrait")
        except Exception as e:  # noqa: BLE001 — network/API errors are the UI's problem to show
            self._json({"ok": False, "error": str(e)}, 502)
            return
        self._json({"ok": True, "results": [
            {
                "id": p.get("id"),
                "thumb": (p.get("src") or {}).get("medium"),
                "full": (p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("large"),
                "credit": p.get("photographer", "?"),
                "creditUrl": p.get("url", ""),
            }
            for p in photos if (p.get("src") or {}).get("medium")
        ]})

    def _images_search_freepik(self, query: str, kind: str) -> None:
        """Fotos ou vídeos da Freepik (Magnific). A busca devolve só a
        prévia; o arquivo grande vem no pick, por id — é essa a chamada que
        a Freepik conta (e cobra) como download."""
        try:
            import freepik_search  # type: ignore
        except ImportError:
            self._json({"ok": False, "error": "helper da Freepik indisponível"}, 500)
            return
        try:
            key = freepik_search.load_api_key()
        except SystemExit as e:
            self._json({"ok": False, "error": str(e)}, 400)
            return
        try:
            if kind == "video":
                itens = freepik_search.search_videos(query, key, 18, "portrait")
            else:
                # 24 e nao 12: o banco da Freepik e grande e a pessoa compara
                itens = freepik_search.search(query, key, 24, "portrait")
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": str(e)}, 502)
            return
        self._json({"ok": True, "source": "freepik", "kind": kind, "results": itens})

    def _images_pick_freepik(self, body: dict) -> None:
        """Baixa pelo ID (nunca por URL vinda do cliente) para public/freepik/."""
        try:
            import freepik_search  # type: ignore
        except ImportError:
            self._json({"ok": False, "error": "helper da Freepik indisponível"}, 500)
            return
        try:
            key = freepik_search.load_api_key()
        except SystemExit as e:
            self._json({"ok": False, "error": str(e)}, 400)
            return
        rid = str(body.get("id") or "").strip()
        if not rid.isdigit():
            self._json({"ok": False, "error": "id inválido"}, 400)
            return
        kind = "video" if str(body.get("kind") or "") == "video" else "image"
        out_dir = self.root / "remotion" / "public" / "freepik"
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = ".mp4" if kind == "video" else ".jpg"
        name = f"{freepik_search.slugify(body.get('query') or 'img')}-{rid}{ext}"
        dest = out_dir / name
        try:
            if kind == "video":
                freepik_search.download_video(rid, key, dest)
            else:
                freepik_search.download(rid, key, dest, image_size="large")
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": str(e)}, 502)
            return
        self._json({"ok": True, "ref": f"freepik/{name}", "kind": kind,
                    "credit": body.get("credit", "")})

    def _images_pick(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        if str(body.get("source") or "").lower() == "freepik":
            self._images_pick_freepik(body)
            return
        url = body.get("url") or ""
        # only ever fetch a Pexels-hosted image: this endpoint takes a URL
        # from the client, so without this it would be an open proxy that
        # writes arbitrary remote content into the project folder
        if not url.startswith("https://images.pexels.com/"):
            self._json({"ok": False, "error": "url não permitida"}, 400)
            return
        if pexels_search is None:
            self._json({"ok": False, "error": "helper indisponível"}, 500)
            return
        out_dir = self.root / "remotion" / "public" / "pexels"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"{pexels_search.slugify(body.get('query') or 'img')}-{body.get('id') or 'x'}.jpg"
        dest = out_dir / name
        try:
            pexels_search.download(url, dest)
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": str(e)}, 502)
            return
        # path relative to remotion/public/ — what edit-data.json refs look like
        self._json({"ok": True, "ref": f"pexels/{name}", "credit": body.get("credit", "")})

    # ---- dynamic bits ----
    # ---- /painel: every sibling project at a glance ----
    def _scan_projects(self) -> None:
        """One row per project, built from files only — never writes anything.

        Exists because this machine runs many projects in parallel and the
        things that go wrong are invisible per-project: a delivery that never
        got re-opened and is silently truncated, a `finalVideo` naming a file
        that is not there, a saved request nobody applied. Each of those is one
        cheap check here, and none of them shows up in the single-project UI.
        """
        rows = []
        seen: set[Path] = set()
        try:
            procs = running_ativavid_processes()
        except Exception:
            procs = []   # never let an optional signal 500 the whole page
        for proot in self.projects_roots:
            if not proot.exists():
                continue
            for edit in sorted(proot.glob("*/edit")):
                if not edit.is_dir() or edit in seen:
                    continue
                seen.add(edit)
                state: dict = {}
                sp = edit / "state.json"
                if sp.exists():
                    try:
                        state = json.loads(sp.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        state = {}
                declared = state.get("finalVideo")
                resolved = self._resolve_final_video(state, edit)
                delivery = None
                if resolved:
                    dp = edit / resolved
                    dur = probe_duration_cached(dp)
                    delivery = {
                        "name": resolved,
                        "durationSec": dur,
                        "broken": dur is None,          # readable header, unreadable stream
                        "stalePointer": bool(declared) and declared != resolved,
                        "declared": declared,
                    }
                cut = edit / (state.get("video") or "cut.mp4")
                # Match the FULL edit path, not the folder name: "kevin" is a
                # substring of "kevin contar capinas", so a name match reported
                # one project's server as belonging to the other. Separators
                # differ between launches (--root uses \, the watcher was armed
                # with /), so normalise both sides before comparing.
                needle = str(edit).replace("\\", "/").lower()
                mine = [c for c in procs if needle in c.replace("\\", "/").lower()]
                # Dedupe on the ARGUMENTS, not the whole command line: the
                # venv's python.exe spawns the base interpreter as a child, so
                # one logical server appears twice with different exe paths and
                # identical arguments. Keying from the script name onward
                # collapses that pair while keeping two real servers apart
                # (they differ by --port).
                def _args_key(c: str) -> str:
                    low = c.replace("\\", "/").lower()
                    for script in ("preview_server.py", "watch_edits.py"):
                        i = low.find(script)
                        if i != -1:
                            return low[i:]
                    return low
                mine = list({_args_key(c): c for c in mine}.values())
                rows.append({
                    "servers": sum(1 for c in mine if "preview_server" in c),
                    "watchers": sum(1 for c in mine if "watch_edits" in c),
                    "pendingDetail": describe_pending(edit),
                    "template": template_state(edit),
                    "project": state.get("project") or edit.parent.name,
                    "folder": edit.parent.name,
                    "path": str(edit),
                    "phase": state.get("phase"),
                    "message": state.get("message") or "",
                    "awaitingStyle": bool(state.get("awaitingStyle")),
                    "hasState": sp.exists(),
                    "hasCut": cut.exists(),
                    "cutDurationSec": probe_duration_cached(cut) if cut.exists() else None,
                    "delivery": delivery,
                    # PENDENTE e o pedido MAIS NOVO que o video entregue.
                    # So "existe o arquivo" contava sobra: dos 12 projetos
                    # que o painel marcava, 10 tinham o pedido mais velho
                    # que a entrega — ja aplicados, arquivo esquecido. A
                    # Fila usa a mesma regra (`_pedido_nao_aplicado`), e
                    # duas telas dizendo coisas diferentes sobre o mesmo
                    # projeto e pior que uma so.
                    "pendingEdits": _pedido_e_novo(
                        edit / "preview_edits.json", delivery, edit),
                    "pendingStyle": _pedido_e_novo(
                        edit / "preview_style.json", delivery, edit),
                    "mtime": sp.stat().st_mtime if sp.exists() else 0,
                })
        rows.sort(key=lambda r: r["mtime"], reverse=True)
        self._json({
            "ok": True,
            "roots": [str(p) for p in self.projects_roots],
            "current": str(self.root),
            "serverStale": Path(__file__).stat().st_mtime != SERVER_MTIME_AT_BOOT,
            "projects": rows,
        })

    def _resolve_final_video(self, state: dict, root: Path | None = None) -> str | None:
        """state.json's `finalVideo` relative path, or the best stand-in.

        The declared name goes stale constantly: the skill writes
        `"finalVideo": "final.mp4"` while the actual delivery gets exported
        under a human name ("Cabo magnetico.mp4"), and nothing updates the
        pointer. Measured across this machine: 10 of 32 projects. Rather than
        rewrite anyone's state.json, resolve it at read time — the newest
        top-level .mp4 that isn't a working file is the delivery in every one
        of those cases. Returns a path relative to root (what the UI and the
        /media/ route expect), or None when nothing has been delivered yet.
        """
        base = root or self.root  # /painel resolves for OTHER projects, not just this server's
        rel = state.get("finalVideo")
        if rel:
            p = self._safe(base, rel)
            if p and p.exists():
                return rel
        # `final_proxy.mp4` nasce DEPOIS do entregue e seria o mp4 mais
        # novo da pasta: sem pular, a copia leve viraria "o video".
        skip = {"cut.mp4", "base.mp4", "cut_proxy.mp4", "final_proxy.mp4"}
        search = [base]
        if base.name.lower() == "edit":
            search.append(base.parent)
        cands: list[Path] = []
        for folder in search:
            if not folder.is_dir():
                continue
            cands.extend(
                p for p in folder.glob("*.mp4")
                if p.name not in skip and not p.name.endswith(".prenorm.mp4")
            )
        if not cands:
            return None
        chosen = max(cands, key=lambda p: p.stat().st_mtime)
        try:
            return str(chosen.relative_to(base)).replace("\\", "/")
        except ValueError:
            return chosen.name

    def _state(self) -> None:
        state_p = self.root / "state.json"
        state: dict = {}
        if state_p.exists():
            try:
                state = json.loads(state_p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {"error": "state.json inválido"}
        # Patch the RESPONSE only — never the file on disk. The UI then plays
        # the real delivery on the Final tab instead of silently falling back
        # to the Phase-1 cut, and the project's own bookkeeping is left alone.
        resolved_final = self._resolve_final_video(state)
        if resolved_final:
            state["finalVideo"] = resolved_final
        elif "finalVideo" in state:
            state.pop("finalVideo")  # declared but nothing on disk → treat as absent
        # O nome do CARD do hub (mesma regra do displayTitle), quando o hub
        # emprestou o resolvedor — o editor mostrava o stem do arquivo final
        # e o card o titulo travado ("G2 · C1 · CTA2"), 03/09. So na resposta.
        resolvedor = getattr(type(self), "titulo_do_card", None)
        if callable(resolvedor):
            try:
                ficha = resolvedor(self.root)
                # str (so o nome) ou dict {id, title}: o id e o que deixa o
                # editor renomear/aprovar o video (03/09)
                if isinstance(ficha, dict):
                    if ficha.get("title"):
                        state["jobTitle"] = str(ficha["title"])[:80]
                    if ficha.get("id"):
                        state["jobId"] = str(ficha["id"])
                elif ficha:
                    state["jobTitle"] = str(ficha)[:80]
            except Exception:  # noqa: BLE001 — o nome nunca derruba o estado
                pass
        # attach small data files + mtimes so the UI hot-reloads on change
        mtimes: dict[str, float] = {}
        for key in ("video", "finalVideo", "edl", "captions", "editData"):
            rel = state.get(key)
            if not rel:
                continue
            p = self._safe(self.root, rel)
            if p and p.exists():
                mtimes[key] = p.stat().st_mtime
        edl = None
        rel = state.get("edl") or "edl.json"
        p = self._safe(self.root, rel)
        if p and p.exists():
            try:
                edl = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        edits_p = self.root / "preview_edits.json"
        video = self._current_video()
        dur = 0.0
        if video:
            cached = probe_duration_cached(video)
            dur = float(cached) if cached is not None else 0.0
        preset_used = None
        used_p = self.root / "preset-used.json"
        if used_p.exists():
            try:
                raw_used = json.loads(used_p.read_text(encoding="utf-8-sig"))
                if isinstance(raw_used, dict):
                    preset_used = raw_used
            except (OSError, json.JSONDecodeError):
                preset_used = None
        intent = None
        intent_p = self.root / "job_intent.json"
        if intent_p.exists():
            try:
                intent = json.loads(intent_p.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                intent = None
        relatorio = None
        rel_p = self.root / "corte_relatorio.json"
        if rel_p.exists():
            try:
                relatorio = json.loads(rel_p.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                relatorio = None
        corrections = None
        try:
            from app.quick_corrections import load as load_corrections

            corrections = load_corrections(self.root)
        except Exception:
            corrections = None
        apply_status = None
        try:
            from app.apply_execute import read_apply_status

            apply_status = read_apply_status(self.root)
        except Exception:
            apply_status = None
        apply_task = None
        try:
            from app.apply_tasks import public_view, read_task

            apply_task = public_view(read_task(self.root), self.root)
        except Exception:
            apply_task = None
        headline_options: list[str] = []
        opts_p = self.root / "headline_options.json"
        if opts_p.exists():
            try:
                raw_opts = json.loads(opts_p.read_text(encoding="utf-8-sig"))
                if isinstance(raw_opts, dict) and isinstance(raw_opts.get("options"), list):
                    headline_options = [
                        str(o).strip() for o in raw_opts["options"] if str(o or "").strip()
                    ][:3]
            except (OSError, json.JSONDecodeError):
                headline_options = []
        self._json({
            "state": state,
            "edl": edl,
            "intent": intent,
            "corteRelatorio": relatorio,
            "mtimes": mtimes,
            "videoDuration": dur,
            "hasCut": video is not None,
            "presetUsed": preset_used,
            "hasPendingEdits": edits_p.exists(),
            "corrections": corrections,
            "applyStatus": apply_status,
            "applyTask": apply_task,
            "headlineOptions": headline_options,
            "now": time.time(),
        })

    def _style_export(self) -> None:
        """Grava o estilo atual como JSON em ~/ATIVAVID/presets-exportados/."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"ok": False, "error": "invalid JSON"}, 400)
            return
        style = body.get("style")
        if not isinstance(style, dict) or not style:
            self._json({"ok": False, "error": "estilo vazio"}, 400)
            return
        import re as _re

        name = _re.sub(r"[^\w\- ]+", "", str(body.get("name") or "preset"), flags=_re.UNICODE)
        name = _re.sub(r"\s+", "_", name.strip())[:48] or "preset"
        out_dir = Path.home() / "ATIVAVID" / "presets-exportados"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.json"
        n = 2
        while path.exists():
            path = out_dir / f"{name}_{n}.json"
            n += 1
        payload = {"ativavidPreset": 1, "name": str(body.get("name") or name), "style": style}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._json({"ok": True, "path": str(path), "folder": str(out_dir)})

    def _intent_get(self) -> None:
        from app.editing_intent import load as load_intent

        self._json({"ok": True, "intent": load_intent(self.root)})

    def _intent_post(self) -> None:
        from app.editing_intent import load as load_intent
        from app.editing_intent import save as save_intent

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        cur = load_intent(self.root) or {}
        if isinstance(body, dict):
            cur.update(body)
        saved = save_intent(self.root, cur)
        self._json({"ok": True, "intent": saved})

    def _restaurar_trecho(self) -> None:
        """"Traz de volta": recoloca um trecho removido no corte, sem refazer
        o plano. Recebe {start, end} em segundos DO ORIGINAL (os mesmos do
        corte_relatorio.json), insere no EDL atual e grava preview_edits.json
        — o mesmo caminho do corte do editor: o proximo render entra como
        backend preview_edits e o replanejo da IA nao mexe mais nisso."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            ini = float(body.get("start"))
            fim = float(body.get("end"))
        except (TypeError, ValueError, json.JSONDecodeError):
            self._json({"error": "start/end invalidos"}, 400)
            return
        if not (fim > ini >= 0):
            self._json({"error": "start/end invalidos"}, 400)
            return
        try:
            edl = json.loads((self.root / "edl.json").read_text(
                encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            self._json({"error": "este projeto ainda nao tem corte"}, 409)
            return
        ranges = edl.get("ranges") or []
        fontes = {str(r.get("source") or "") for r in ranges}
        if len(fontes) != 1:
            self._json({"error": "restaurar por trecho so em fonte unica"}, 409)
            return
        from app.editing_intent import _insert_range

        novo = _insert_range([dict(r) for r in ranges], ini, fim,
                             "KEEP", "trazido de volta")
        if sum(r["end"] - r["start"] for r in novo) <=                 sum(float(r.get("end") or 0) - float(r.get("start") or 0)
                    for r in ranges) + 0.01:
            self._json({"ok": True, "changed": False,
                        "hint": "esse trecho ja esta no corte"})
            return
        out = self.root / "preview_edits.json"
        out.write_text(json.dumps({
            "type": "timeline-edits",
            "savedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "origem": "trazer-de-volta",
            "edl": {"ranges": novo},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[restaurar] trecho {ini:.2f}-{fim:.2f}s de volta ao corte",
              flush=True)
        self._json({"ok": True, "changed": True})

    def _health(self) -> None:
        """Versao do sistema. O rodape e a etiqueta do topo leem daqui.

        Sem esta rota o preview solto mostra "Versão sistema: —" e "v?".
        Magra de proposito: este servidor serve UM projeto, nao tem fila
        nem trabalhador para relatar.
        """
        try:
            from app.update_check import boot_fingerprint, running_version

            self._json({"ok": True, "version": running_version(),
                        "fingerprint": boot_fingerprint(),
                        "projectsRoot": str(self.root.parent.parent)})
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "erro": f"{type(e).__name__}: {e}"[:200]})

    def _brand_presets(self) -> None:
        """Presets da marca ativa — a aba Estilo lista a partir daqui."""
        # MESMA resposta do servidor do hub, inclusive o `brandName`: a tela
        # rotula os presets com ele, e sem o nome ela dizia "Padrao" para os
        # presets de outra marca.
        try:
            from app.brand_kits import list_brands
            from app.brand_presets import get_active, load as load_presets

            qs = parse_qs(urlparse(self.path).query)
            bid = (qs.get("brandId") or [""])[0].strip()
            marcas = list_brands()
            if not bid:
                ativa = next((b for b in marcas if b.get("active")),
                             marcas[0] if marcas else None)
                bid = str((ativa or {}).get("id") or "padrao")
            pack = load_presets(bid)
            nome = next((str(b.get("name") or "") for b in marcas
                         if str(b.get("id") or "") == bid), "")
            self._json({"ok": True, **pack, "brandName": nome,
                        "active": get_active(bid)})
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "presets": [],
                        "erro": f"{type(e).__name__}: {e}"[:200]})

    def _events(self) -> None:
        """Batida de coracao, so para o cliente parar de tentar num 404.

        Nada AQUI muda estado de fila — este servidor nao tem fila. Quem
        precisa de atualizacao usa o proprio relogio (o poll do editor).
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(b"retry: 5000\n\n")
            self.wfile.flush()
            for _ in range(240):          # ~20 min e a conexao se renova
                time.sleep(5.0)
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError,
                ConnectionAbortedError, OSError):
            return

    def _versions_get(self) -> None:
        from app.project_versions import list_versions

        self._json({"ok": True, "versions": list_versions(self.root)})

    def _versions_post(self) -> None:
        from app.project_versions import list_versions, restore, snapshot

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        action = str((body or {}).get("action") or "snapshot").strip().lower()
        try:
            if action == "restore":
                out = restore(self.root, str(body.get("id") or ""))
                self._json(out)
                return
            item = snapshot(
                self.root,
                origin=str(body.get("origin") or "manual"),
                description=str(body.get("description") or "Versão"),
                extra=body.get("extra") if isinstance(body.get("extra"), dict) else None,
            )
            self._json({"ok": True, "version": item, "versions": list_versions(self.root)})
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}
        return body if isinstance(body, dict) else {}

    def _apply_plan_get(self) -> None:
        try:
            from app.quick_corrections import plan_for_edit

            plan = plan_for_edit(self.root)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)
            return
        self._json({"ok": True, "plan": plan, "execute": False})

    def _apply_status_get(self) -> None:
        try:
            from app.apply_execute import read_apply_status

            st = read_apply_status(self.root)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)
            return
        self._json({"ok": True, **st})

    def _corrections_get(self) -> None:
        try:
            from app.quick_corrections import handle

            self._json(handle(self.root, {"op": "load"}))
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _corrections_post(self) -> None:
        body = self._read_json_body()
        try:
            from app.quick_corrections import handle

            self._json(handle(self.root, body, fallback_full=self._requeue_full_fallback()))
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 500)

    def _requeue_full_fallback(self):
        """Fallback do Apply: reenfileirar o job deste projeto no pipeline
        completo quando o atalho rápido não serve (PrepareError). Só existe
        no app desktop, onde o handler tem store/worker; no preview
        standalone devolve None e o Apply falha como antes."""
        store = getattr(self, "store", None)
        worker = getattr(self, "worker", None)
        if store is None or worker is None:
            return None
        folder = self.root.parent.name if self.root.name.lower() == "edit" else self.root.name
        busy_id = getattr(worker, "busy_id", None)

        def _requeue() -> bool:
            for j in store.list():
                if Path(j.get("projectDir", "")).name != folder:
                    continue
                if j.get("status") == "processing" or j.get("id") == busy_id:
                    return False  # não briga com um job em andamento
                store.update(
                    j["id"],
                    status="queued",
                    message="Na fila — aplicando ajustes",
                    reason=None,
                    detail=None,
                )
                worker.enqueue(j["id"])
                return True
            return False

        return _requeue

    def _waveform(self) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out = self.root / ".preview_cache" / "waveform.json"
        stale = True
        if out.exists():
            try:
                stale = json.loads(out.read_text(encoding="utf-8")).get("srcMtime") != video.stat().st_mtime
            except json.JSONDecodeError:
                pass
        if stale:
            gen_waveform(video, out)
        self._send_file(out)

    def _thumbs(self, name: str) -> None:
        # A tira de miniaturas so precisa da IMAGEM, e o proxy tem a mesma
        # imagem 7,6x mais barato: medido no `20260829-171222`, as mesmas
        # 62 miniaturas saem em 1,16s contra 8,79s do corte cheio. (A onda
        # de audio, logo acima, continua no corte: o proxy nao tem faixa de
        # audio nenhuma.)
        video = self._proxy_util() or self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out_dir = self.root / ".preview_cache" / "thumbs"
        meta = out_dir / "meta.json"
        with _thumb_lock:
            stale = True
            if meta.exists():
                try:
                    stale = json.loads(meta.read_text(encoding="utf-8")).get("srcMtime") != video.stat().st_mtime
                except json.JSONDecodeError:
                    pass
            if stale:
                gen_thumbs(video, out_dir)
        p = self._safe(out_dir, name)
        self._send_file(p) if p else self._json({"error": "bad path"}, 400)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # quiet


def main() -> None:
    ap = argparse.ArgumentParser(description="ATIVAVID preview interface server")
    ap.add_argument("--root", type=Path, required=True, help="the session <edit> dir")
    ap.add_argument("--port", type=int, default=4820)
    ap.add_argument("--projects-root", type=Path, action="append", default=None,
                    help="folder holding sibling projects, for /painel. Repeatable. "
                         "Defaults to the dir two levels above --root "
                         "(<projects-root>/<project>/edit).")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.exists():
        raise SystemExit(f"edit dir not found: {root}")
    if not (APP_DIR / "index.html").exists():
        raise SystemExit(f"app not found at {APP_DIR}")

    Handler.root = root
    # <projects-root>/<project>/edit is the layout every session already uses,
    # so the sensible default is simply "the folder my siblings live in".
    Handler.projects_roots = ([p.resolve() for p in args.projects_root]
                              if args.projects_root else [root.parent.parent])
    esquentar_painel(Handler.projects_roots)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"ATIVAVID preview → http://127.0.0.1:{args.port}  (root: {root})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
