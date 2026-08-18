"""Teto compartilhado entre a fila de jobs e o Apply.

Os workers da fila e o Apply competem pelo mesmo número de vagas
(`parallelJobs` do perfil). Sem isso o Aplicar alterações abre thread
extra e passa do limite da máquina.
"""
from __future__ import annotations

import threading
from typing import Any

__all__ = ["acquire", "active", "configure", "limit", "release", "reset", "snapshot"]

_lock = threading.Lock()
_cv = threading.Condition(_lock)
_limit = 1
_active = 0


def configure(n: int) -> None:
    global _limit
    with _cv:
        _limit = max(1, int(n or 1))
        _cv.notify_all()


def limit() -> int:
    with _lock:
        return _limit


def active() -> int:
    with _lock:
        return _active


def acquire(*, timeout: float | None = None) -> bool:
    """Espera uma vaga. False se o timeout estourar."""
    global _active
    with _cv:
        ok = _cv.wait_for(lambda: _active < _limit, timeout=timeout)
        if not ok:
            return False
        _active += 1
        return True


def release() -> None:
    global _active
    with _cv:
        _active = max(0, _active - 1)
        _cv.notify_all()


def snapshot() -> dict[str, Any]:
    with _lock:
        return {"active": _active, "limit": _limit}


def reset(n: int = 1) -> None:
    """Só testes: zera ocupação e recoloca o teto."""
    global _active, _limit
    with _cv:
        _active = 0
        _limit = max(1, int(n or 1))
        _cv.notify_all()
