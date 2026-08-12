#!/usr/bin/env python3
"""Emit one event per save from the preview UI.

Two files, both written by the UI and neither able to reach the chat on its own:
  - preview_edits.json — timeline adjustments and correction markers
  - preview_style.json — the Fase 1 → Fase 2 gate: editing style, caption style,
    edit elements

Run this under the Monitor tool so every save notifies the session automatically:

    Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'",
            description="marcações do preview", persistent=True)

Each stdout line is one notification. Stays quiet while nothing changes.
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import atexit
import json
import os
import signal
import sys
import time
from pathlib import Path

PIDFILE_NAME = ".watch_edits.pid"


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


def acquire_singleton(root: Path) -> Path | None:
    """Claim `<root>/.watch_edits.pid` for this process.

    Returns the pidfile Path on success, or None if a live watcher already
    owns this edit dir (caller should print a message and exit 0 — a second
    watcher racing the first one is silent-and-broken, not an error worth a
    nonzero exit). A stale pidfile (dead PID, or crashed without cleanup) is
    reclaimed automatically.
    """
    pidfile = root / PIDFILE_NAME
    if pidfile.exists():
        try:
            old_pid = int(pidfile.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            old_pid = None
        if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
            return None
    pidfile.write_text(str(os.getpid()), encoding="utf-8")

    def _release() -> None:
        try:
            if pidfile.exists() and pidfile.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pidfile.unlink()
        except OSError:
            pass

    atexit.register(_release)
    # Monitor typically stops this process with SIGTERM (POSIX) or a Windows
    # equivalent kill; make sure the pidfile is released either way instead of
    # only on a clean return from main().
    if hasattr(signal, "SIGTERM"):
        prev = signal.getsignal(signal.SIGTERM)

        def _on_term(signum, frame):
            _release()
            if callable(prev):
                prev(signum, frame)
            else:
                raise SystemExit(0)

        signal.signal(signal.SIGTERM, _on_term)
    return pidfile


def digest(p: Path) -> str:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_edits.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    parts: list[str] = []
    notes = d.get("notes") or []
    for i, n in enumerate(notes, 1):
        start, end = n.get("start", 0), n.get("end", 0)
        fase = n.get("phase", 1)
        parts.append(f'  {i}. [{fmt(start)} → {fmt(end)}] (fase {fase}) {n.get("text", "").strip()}')

    edl = d.get("edl") or {}
    n_ch = len(edl.get("changes") or [])
    n_rm = len(edl.get("removed") or [])
    ed = d.get("editData") or {}

    head = []
    if notes:
        head.append(f"{len(notes)} marcação(ões)")
    if n_ch:
        head.append(f"{n_ch} take(s) reajustado(s)")
    if n_rm:
        head.append(f"{n_rm} take(s) removido(s)")
    if ed:
        head.append("inserts/gancho movidos")
    if not head:
        head.append("ajustes salvos")

    out = [f"AJUSTES DO PREVIEW ({d.get('savedAt', '')}) — {', '.join(head)}. Aplique-os."]
    out += parts
    return "\n".join(out)


def style_digest(p: Path) -> str:
    """The gate choice: what Fase 2 should be built as."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_style.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    els = d.get("elementNames") or [
        k for k, v in (d.get("elements") or {}).items() if v
    ]
    head = (
        "TROCA DE ESTILO NO PREVIEW ({}) — REFAÇA a Fase 2 assim:"
        if d.get("rerender")
        else "ESTILO ESCOLHIDO NO PREVIEW ({}) — monte a Fase 2 assim:"
    ).format(d.get("savedAt", ""))
    out = [
        head,
        f'  · tipo de edição: {d.get("editName") or d.get("edit")}',
        f'  · headline: {d.get("headlineName") or d.get("headline")}',
        f'  · legenda: {d.get("captionsName") or d.get("captions")}',
    ]
    # Only worth reporting when the chosen styles actually paint an accent —
    # naming a colour that nothing uses reads as an instruction to go find a
    # place for it.
    accent = d.get("accent")
    if accent:
        if d.get("accentUsed"):
            name = d.get("accentName") or accent
            label = f"{name} ({accent})" if name.lower() != str(accent).lower() else accent
            out.append(f"  · cor de destaque: {label}")
        else:
            out.append("  · cor de destaque: não se aplica (o estilo de headline escolhido não usa destaque)")
    # Three independent picks from here on — captionAccent (BASE legenda text:
    # karaoke line, static styles), emphasisAccent (the one accented element:
    # stacked serif line, scatter highlighted word) and circleAccent (stacked's
    # pencil-circle stroke only). Each *Used flag already accounts for BOTH
    # "legenda desligada" and "this style doesn't have that element" — the
    # preview computes it from the actual style pick, so trust it rather than
    # re-deriving here. null/absent means the user left it on "Padrão do
    # estilo": do not write the corresponding edit-data field at all.
    cap_accent = d.get("captionAccent")
    if cap_accent:
        if d.get("captionAccentUsed"):
            name = d.get("captionAccentName") or cap_accent
            label = f"{name} ({cap_accent})" if name.lower() != str(cap_accent).lower() else cap_accent
            out.append(f"  · cor da legenda: {label}")
        else:
            out.append("  · cor da legenda: não se aplica (legenda desligada, ou o estilo escolhido não tem texto-base — veja cor de ênfase)")
    else:
        out.append("  · cor da legenda: padrão do estilo (não escrever captions.accent)")
    emph_accent = d.get("emphasisAccent")
    if emph_accent:
        if d.get("emphasisAccentUsed"):
            name = d.get("emphasisAccentName") or emph_accent
            label = f"{name} ({emph_accent})" if name.lower() != str(emph_accent).lower() else emph_accent
            out.append(f"  · cor de ênfase (legenda): {label}")
        else:
            out.append("  · cor de ênfase (legenda): não se aplica (legenda desligada, ou o estilo escolhido não tem palavra de ênfase)")
    else:
        out.append("  · cor de ênfase (legenda): padrão do estilo (não escrever captions.emphasisAccent)")
    circle_accent = d.get("circleAccent")
    if circle_accent:
        if d.get("circleAccentUsed"):
            name = d.get("circleAccentName") or circle_accent
            label = f"{name} ({circle_accent})" if name.lower() != str(circle_accent).lower() else circle_accent
            out.append(f"  · cor do círculo riscado: {label}")
        else:
            out.append("  · cor do círculo riscado: não se aplica (só o estilo Empilhado tem círculo riscado)")
    else:
        out.append("  · cor do círculo riscado: padrão do estilo (não escrever captions.circleAccent)")
    out.append(f'  · elementos: {", ".join(els) if els else "nenhum"}')
    # everything NOT chosen is an instruction too — it is what must stay out
    off = [k for k, v in (d.get("elements") or {}).items() if not v]
    if off:
        out.append(f'  · fora: {", ".join(off)}')
    if (d.get("note") or "").strip():
        out.append(f'  · observação do usuário: {d["note"].strip()}')
    return "\n".join(out)


def fmt(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}"


def main() -> int:
    # `--help` used to be taken as a DIRECTORY NAME and die on FileNotFoundError,
    # which reads as a broken helper rather than a misuse. Every other helper
    # here answers --help; this one is the odd one out because it takes a bare
    # positional, so answer it by hand instead of pulling in argparse for one arg.
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__ or "uso: watch_edits.py <edit dir>")
        return 0
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()

    if acquire_singleton(root) is None:
        print(
            f"watch_edits.py já está rodando para {root} (pidfile {PIDFILE_NAME} "
            "aponta para um processo vivo) — não iniciando um segundo watcher. "
            "Se isso for um engano (processo morto sem limpar o pidfile), apague "
            f"{root / PIDFILE_NAME} e rode de novo.",
            flush=True,
        )
        return 0

    watched = {
        root / "preview_edits.json": digest,
        root / "preview_style.json": style_digest,
    }
    # a file already sitting there at startup means it is pending — say so once
    last: dict[Path, float | None] = {}
    for target, fn in watched.items():
        last[target] = target.stat().st_mtime if target.exists() else None
        if last[target] is not None:
            print(fn(target), flush=True)

    while True:
        for target, fn in watched.items():
            try:
                cur = target.stat().st_mtime if target.exists() else None
            except OSError:
                cur = None
            if cur is not None and cur != last[target]:
                last[target] = cur
                time.sleep(0.15)  # let the atomic replace settle before reading
                print(fn(target), flush=True)
            elif cur is None:
                last[target] = None  # applied and deleted — re-arm for the next save
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
