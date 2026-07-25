#!/usr/bin/env python3
"""Emit one event per save of <edit>/preview_edits.json.

The preview UI writes the user's timeline adjustments and correction markers to
preview_edits.json; nothing in that path can reach the chat on its own. Run this
under the Monitor tool so every save notifies the session automatically:

    Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'",
            description="marcações do preview", persistent=True)

Each stdout line is one notification. Stays quiet while nothing changes.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def digest(p: Path) -> str:
    try:
        d = json.loads(p.read_text())
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


def fmt(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    target = root / "preview_edits.json"
    last: float | None = None
    # a file already sitting there at startup means edits are pending — say so once
    if target.exists():
        last = target.stat().st_mtime
        print(digest(target), flush=True)

    while True:
        try:
            cur = target.stat().st_mtime if target.exists() else None
        except OSError:
            cur = None
        if cur is not None and cur != last:
            last = cur
            time.sleep(0.15)  # let the atomic replace settle before reading
            print(digest(target), flush=True)
        elif cur is None:
            last = None  # applied and deleted — re-arm for the next save
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
