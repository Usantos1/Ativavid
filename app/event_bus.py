"""Barramento de eventos do processo do app — versão + condition.

Quem muda estado visível (JobStore, índice de applies) chama bump();
o endpoint /api/events (SSE) espera em wait() e acorda os clientes.
Tudo in-process: no app desktop, worker, quick-apply e HTTP vivem no
mesmo processo. Subprocessos (run_fast) NÃO passam por aqui — o progresso
fino deles continua vindo por poll rápido só enquanto há job ativo.
"""
from __future__ import annotations

import threading

_cv = threading.Condition()
_version = 0


def bump() -> None:
    global _version
    with _cv:
        _version += 1
        _cv.notify_all()


def version() -> int:
    with _cv:
        return _version


def wait_for_change(last_seen: int, timeout: float) -> int:
    """Bloqueia até a versão passar de last_seen (ou timeout). Devolve a atual."""
    with _cv:
        if _version != last_seen:
            return _version
        _cv.wait(timeout)
        return _version
