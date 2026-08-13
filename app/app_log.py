"""Logs locais com rotação — sem secrets."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG_DIR = REPO / ".ativavid-logs"
_SECRET = re.compile(
    r"(api[_-]?key|token|cookie|authorization|psid|session)[=:]\s*[^\s,;\"']+",
    re.I,
)
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I)


def scrub(msg: str) -> str:
    s = _SECRET.sub(r"\1=••••", msg or "")
    s = _BEARER.sub("Bearer ••••", s)
    return s


def get_logger(name: str = "ativavid") -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    path = LOG_DIR / "ativavid.log"
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    class ScrubFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.msg = scrub(str(record.msg))
            if record.args:
                record.args = tuple(scrub(str(a)) if isinstance(a, str) else a for a in record.args)
            return True

    handler.addFilter(ScrubFilter())
    log.addHandler(handler)
    return log
