#!/usr/bin/env python3
"""Verify the Phase-2 Remotion template code was not touched.

Hard Rule 10/11: PHASE 2 is data-driven — the video is described in
`public/edit-data.json`, the ONLY editable code file is `src/CustomGraphics.tsx`
(bespoke graphics only), and everything else under `src/` is immutable template
code copied verbatim from `<skill>/assets/<track>/src/` at scaffold time.

In practice that rule gets broken under pressure: a caption style needs a tweak,
the fastest-looking fix is editing `Main.tsx` directly instead of routing it
through `edit-data.json`, and nothing catches it — the render still succeeds,
it just silently diverges from the data-driven contract the rest of the skill
(and the next session working on the same project) assumes holds.

This script hashes every immutable src file in `<edit>/remotion/src/` against
the shipped template it was copied from and reports any mismatch or missing
file. Run it before every Phase-2 `npx remotion render` (see references/
shortform.md and longform.md) — cheap (sub-second, no deps beyond stdlib) and
turns a silent rule violation into a visible one.

Usage:
    python helpers/check_template_integrity.py <edit>/remotion
    python helpers/check_template_integrity.py <edit>/remotion --track shortform
    python helpers/check_template_integrity.py <edit>/remotion --fix   # restore from template

Exit code 0 = clean, 1 = drift detected (or missing files), 2 = usage/setup error.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"

# The one file per track that IS meant to be edited — never checked, never
# touched by --fix.
EDITABLE = {"CustomGraphics.tsx"}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def detect_track(remotion_dir: Path) -> str | None:
    """Guess shortform vs longform by which template's src/ filenames match best.

    Shortform's file set is a SUPERSET of longform's (both ship index.ts/Main.tsx/
    Root.tsx; shortform adds CustomGraphics.tsx + the caption-style components), so
    a raw intersection count ties on longform projects (3 == 3) and always breaks
    the tie toward whichever track is checked first. Jaccard similarity (intersection
    over union) instead rewards the track whose file set has the fewest files NOT
    present locally — longform scores 1.0 (exact match) where shortform only scores
    3/8, so the tie is resolved correctly.
    """
    src = remotion_dir / "src"
    if not src.is_dir():
        return None
    have = {p.name for p in src.glob("*.ts*")}
    best, best_score = None, -1.0
    for track in ("shortform", "longform"):
        template_src = ASSETS / track / "src"
        if not template_src.is_dir():
            continue
        want = {p.name for p in template_src.glob("*.ts*")}
        union = have | want
        score = len(have & want) / len(union) if union else 0.0
        if score > best_score:
            best, best_score = track, score
    return best


def check(remotion_dir: Path, track: str, fix: bool = False) -> int:
    template_src = ASSETS / track / "src"
    live_src = remotion_dir / "src"
    if not template_src.is_dir():
        print(f"error: no shipped template at {template_src}", file=sys.stderr)
        return 2
    if not live_src.is_dir():
        print(f"error: no src/ at {live_src} — scaffold the track first", file=sys.stderr)
        return 2

    mismatches: list[str] = []
    missing: list[str] = []
    ok = 0

    for template_file in sorted(template_src.glob("*.ts*")):
        name = template_file.name
        if name in EDITABLE:
            continue
        live_file = live_src / name
        if not live_file.exists():
            missing.append(name)
            continue
        if sha256(live_file) != sha256(template_file):
            mismatches.append(name)
            if fix:
                shutil.copy2(template_file, live_file)
        else:
            ok += 1

    if not mismatches and not missing:
        print(f"template integrity OK ({track}, {ok} file(s) match the shipped template)")
        return 0

    print(f"TEMPLATE INTEGRITY VIOLATION ({track}) — Hard Rule 10/11 says PHASE 2 is data-driven;")
    print("these files should never be hand-edited, only src/CustomGraphics.tsx is:")
    for name in mismatches:
        tag = "restored from template" if fix else "content differs from the shipped template"
        print(f"  MODIFIED  src/{name}  — {tag}")
    for name in missing:
        print(f"  MISSING   src/{name}  — not present in remotion/src at all")
    if not fix:
        print(
            "\nFix: move whatever this file was hand-patched for into "
            "public/edit-data.json (or src/CustomGraphics.tsx for bespoke graphics), "
            f"then re-run with --fix to restore the template, or manually: "
            f"cp {template_src}/<file> {live_src}/<file>"
        )
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("remotion_dir", type=Path, help="Path to <edit>/remotion")
    ap.add_argument("--track", choices=["shortform", "longform"], default=None,
                     help="Skip auto-detection and check against this track's template.")
    ap.add_argument("--fix", action="store_true",
                     help="Overwrite drifted/modified files with the shipped template. "
                          "Never touches src/CustomGraphics.tsx.")
    args = ap.parse_args()

    remotion_dir = args.remotion_dir.resolve()
    track = args.track or detect_track(remotion_dir)
    if track is None:
        print(f"error: could not detect track (shortform/longform) from {remotion_dir}/src — "
              "pass --track explicitly", file=sys.stderr)
        return 2

    return check(remotion_dir, track, fix=args.fix)


if __name__ == "__main__":
    raise SystemExit(main())
