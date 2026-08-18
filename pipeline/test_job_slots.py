"""Teto compartilhado entre fila e Apply."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.job_slots import acquire, active, configure, limit, release, reset


def test_ceiling_blocks_second_slot():
    reset(1)
    assert acquire(timeout=0.05) is True
    assert active() == 1
    assert acquire(timeout=0.05) is False
    release()
    assert acquire(timeout=0.05) is True
    release()
    reset(1)


def test_two_slots_allow_apply_plus_job():
    reset(2)
    assert acquire(timeout=0.05) is True
    assert acquire(timeout=0.05) is True
    assert acquire(timeout=0.05) is False
    release()
    release()
    reset(1)


def test_configure_wakes_waiter():
    reset(1)
    assert acquire(timeout=0.05) is True
    woke = []

    def waiter():
        woke.append(acquire(timeout=1.0))
        if woke[-1]:
            release()

    t = threading.Thread(target=waiter)
    t.start()
    configure(2)
    t.join(timeout=2)
    assert woke == [True]
    release()
    reset(1)
    assert limit() == 1
