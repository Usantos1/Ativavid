"""Force UTF-8 on stdout/stderr. Import this FIRST in every helper.

Windows gives a redirected stdout the cp1252 codec, and every helper here
prints Portuguese and box-drawing characters — accents, "→", "≈", "·". So the
moment output goes to a pipe or a log file instead of a console, a print
raises UnicodeEncodeError and takes the process down with it.

That is not a corner case, it is the normal path: every call made by an agent,
every `>` redirect, every background launch. Measured on this repo before the
fix, 8 of 28 helpers could not even print their own --help that way, render.py
among them. The failure is also maximally confusing, because running the exact
same command by hand in a console works.

Importing this module is the whole fix — there is nothing to call:

    import _utf8  # noqa: F401  (must come before anything that prints)

errors="replace" rather than "strict": a helper that cannot render one glyph
should show a "?" and keep going, never abort a render that already cost
minutes.
"""
from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # not a reconfigurable text stream (already wrapped, or replaced by a
        # test harness) — leave it alone rather than fail at import time
        pass
