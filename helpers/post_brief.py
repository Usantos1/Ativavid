#!/usr/bin/env python3
"""Assemble everything needed to write the post's caption + hashtags.

This helper deliberately does NOT write the caption. Wording is a judgement
call about a specific brand and a specific joke, and a template would produce
the generic "Confira! 🔥 #reels #viral" that makes a feed look automated. What
it does is gather the facts that decision needs — the spoken text, the hook,
the actual duration, the style, the CTA if one was written — into one small
brief, so the caption gets written from what the video SAYS instead of from a
guess about it.

Reads (whatever exists):
  <edit>/state.json                    project name, phase, style, delivery
  <edit>/edl.json                      the cut: beats, quotes per take
  <edit>/remotion/public/edit-data.json  hook lines, inserts, soundtrack
  <edit>/remotion/public/captions.json   the spoken words, in order
  <edit>/takes_packed.md               fallback transcript when captions.json is absent

Output: <edit>/post_brief.md  (and stdout)

Usage:
    python helpers/post_brief.py --edit-dir <edit>
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import argparse
import json
import re
import sys
from pathlib import Path


def read_json(p: Path) -> dict | list | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def spoken_text(edit: Path) -> str:
    """The words actually in the delivered video, in order."""
    caps = read_json(edit / "remotion" / "public" / "captions.json")
    if isinstance(caps, list) and caps:
        words = [str(w.get("text", "")).strip() for w in caps if isinstance(w, dict)]
        return " ".join(w for w in words if w)
    # takes_packed.md is per-SOURCE, not per-cut, so it over-reports: it still
    # beats having no transcript, but say so rather than pass it off as the cut.
    packed = edit / "takes_packed.md"
    if packed.exists():
        lines = []
        for ln in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = re.sub(r"^\s*\[[\d.:\s\-]+\]\s*", "", ln).strip()
            if ln and not ln.startswith("#"):
                lines.append(ln)
        return " ".join(lines)
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Brief for writing the post caption + hashtags")
    ap.add_argument("--edit-dir", type=Path, required=True)
    args = ap.parse_args()
    edit = args.edit_dir.resolve()
    if not edit.is_dir():
        sys.exit(f"edit dir not found: {edit}")

    state = read_json(edit / "state.json") or {}
    edl = read_json(edit / "edl.json") or {}
    ed = read_json(edit / "remotion" / "public" / "edit-data.json") or {}

    hook = ed.get("hook") or {}
    # same precedence the template uses (Main.tsx: `H.text ?? H.lines.join(' ')`)
    # — reading only `lines` reported "no headline" on a video that plainly had
    # one, because the field that actually carries it is `text`.
    hook_text = ""
    if hook.get("enabled", True):
        hook_text = (hook.get("text") or " ".join(hook.get("lines") or [])).strip()
    style = state.get("style") or {}
    ranges = edl.get("ranges") or []

    beats = []
    for r in ranges:
        beat, quote = (r.get("beat") or "").strip(), (r.get("quote") or "").strip()
        if beat or quote:
            beats.append((beat, quote))

    words = spoken_text(edit)
    from_packed = not (edit / "remotion" / "public" / "captions.json").exists()

    L: list[str] = []
    L.append(f"# Brief do post — {state.get('project') or edit.parent.name}")
    L.append("")
    L.append("Material para escrever a legenda e as hashtags. **Escreva a partir do que o")
    L.append("vídeo diz** — não use fórmula pronta.")
    L.append("")
    L.append("## O vídeo")
    if ed.get("durationSec"):
        L.append(f"- Duração: {ed['durationSec']}s")
    if state.get("finalVideo"):
        L.append(f"- Entrega: `{state['finalVideo']}`")
    if hook_text:
        L.append(f"- Headline na tela: **{hook_text}**")
    else:
        L.append("- Sem headline na tela (o texto tem de carregar o gancho sozinho)")
    if style:
        el = style.get("elements") or {}
        on = [k for k, v in el.items() if v]
        L.append(f"- Estilo: edição {style.get('edit')} · legenda {style.get('captions')}"
                 + (f" · elementos: {', '.join(on)}" if on else ""))
    if (ed.get("soundtrack") or {}).get("enabled"):
        L.append("- Tem trilha (creditar a música não é necessário, é gerada)")

    if beats:
        L.append("")
        L.append("## Estrutura do corte")
        for beat, quote in beats:
            L.append(f"- **{beat or '—'}**" + (f" — “{quote}”" if quote else ""))

    L.append("")
    L.append("## Fala do vídeo")
    if words:
        if from_packed:
            L.append("> Atenção: veio de `takes_packed.md`, que é por FONTE e não pelo corte —")
            L.append("> pode conter fala que ficou de fora da edição final.")
            L.append("")
        L.append(words if len(words) < 2000 else words[:2000] + " […]")
    else:
        L.append("_Sem transcrição disponível._")

    L.append("")
    L.append("## Ao escrever")
    L.append("- Primeira linha é o que aparece antes do “mais” — o gancho vive ali.")
    L.append("- Não repita a headline palavra por palavra; ela já está na tela.")
    L.append("- Hashtags: **no máximo 5, e isso é um teto, não uma meta.**")
    L.append("  Prefira nicho e negócio ao invés de alcance: as genéricas")
    L.append("  (#viral, #fyp, #reels) competem com contas enormes e não trazem")
    L.append("  o público certo — ocupam vaga sem devolver nada.")
    L.append("- Termine com uma pergunta ou CTA que caiba na conversa do vídeo.")

    # direto no <edit>: a pasta post/ existia por causa das capas, que sairam
    out = edit / "post_brief.md"
    text = "\n".join(L) + "\n"
    out.write_text(text, encoding="utf-8")

    # The caption itself is written by the model, not here — but the FILE is
    # created here so it always has an obvious home. Without it the text only
    # ever existed in the chat, which is not where anyone looks at posting time.
    legenda = edit / "legenda.txt"
    if not legenda.exists():
        legenda.write_text(
            "(a legenda do post entra aqui — escrita a partir de post_brief.md)\n",
            encoding="utf-8",
        )

    print(text)
    print(f"[post_brief] escrito em {out}", file=sys.stderr)
    print(f"[post_brief] legenda: {legenda}", file=sys.stderr)


if __name__ == "__main__":
    main()
