"""Canary OVERLAY — teto rígido da rodada (canaryLimit), depois off.

Estado persistente em %USERPROFILE%/ATIVAVID/canary-state.json
(sobrevive a restart). overlayRollout em settings.json é o interruptor.
O motor OVERLAY não mora aqui — só o limite e o lock.
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

CANARY_LIMIT = 5  # fallback se state/settings não tiverem teto
USER_DIR = Path.home() / "ATIVAVID"
STATE_PATH = Path(os.environ.get("ATIVAVID_CANARY_STATE") or (USER_DIR / "canary-state.json"))
LOCK_PATH = Path(os.environ.get("ATIVAVID_OVERLAY_LOCK") or (USER_DIR / ".ativavid" / "overlay-heavy.lock"))

_EMPTY = {
    "canaryAttempt": 0,
    "canaryLimit": CANARY_LIMIT,
    "paused": False,
    "pausedReason": None,
    "jobs": [],
}


def _positive_int(value: Any, default: int = CANARY_LIMIT) -> int:
    try:
        n = int(value)
        return n if n > 0 else default
    except (TypeError, ValueError):
        return default


def canary_limit(state: dict[str, Any] | None = None) -> int:
    """Teto da rodada atual — vem do state persistente, depois settings."""
    if state is not None:
        return _positive_int(state.get("canaryLimit"))
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict) and raw.get("canaryLimit") is not None:
            return _positive_int(raw.get("canaryLimit"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    try:
        from app.settings_store import load_settings

        return _positive_int(load_settings().get("canaryLimit"))
    except Exception:
        return CANARY_LIMIT


def load_state() -> dict[str, Any]:
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            data = dict(_EMPTY)
            data.update(raw)
            data["canaryLimit"] = canary_limit(data)
            data["canaryAttempt"] = int(data.get("canaryAttempt") or 0)
            data["jobs"] = list(data.get("jobs") or [])
            return data
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return dict(_EMPTY)


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    out = dict(_EMPTY)
    out.update(state)
    out["canaryLimit"] = _positive_int(out.get("canaryLimit"))
    out["canaryAttempt"] = int(out.get("canaryAttempt") or 0)
    STATE_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        from app.settings_store import save_settings

        save_settings({
            "canaryAttempt": out["canaryAttempt"],
            "canaryLimit": out["canaryLimit"],
        })
    except Exception:
        pass
    return out


def _set_rollout(value: str) -> None:
    try:
        from app.settings_store import save_settings

        save_settings({"overlayRollout": value})
    except Exception as e:  # noqa: BLE001
        print(f"[warn] overlayRollout={value} não gravou: {e}", flush=True)


def canary_allows_attempt() -> bool:
    """True só se canary ativo, não pausado, e attempt < canaryLimit."""
    from app.overlay_path import overlay_rollout

    if overlay_rollout() != "canary":
        return False
    st = load_state()
    if st.get("paused"):
        return False
    limit = canary_limit(st)
    if int(st.get("canaryAttempt") or 0) >= limit:
        if overlay_rollout() == "canary":
            _set_rollout("off")
            print(
                f"CANARY_CLOSED attempts={st['canaryAttempt']} limit={limit} "
                f"overlayRollout=off",
                flush=True,
            )
        return False
    return True


def begin_overlay_attempt() -> int:
    """Incrementa o contador persistente. Fallback também já passou daqui.

    ATIVAVID_OVERLAY=1 (gates) não consome cota — só overlayRollout=canary.
    """
    from app.overlay_path import overlay_rollout

    if overlay_rollout() != "canary":
        return 0
    st = load_state()
    st["canaryAttempt"] = int(st.get("canaryAttempt") or 0) + 1
    save_state(st)
    n = st["canaryAttempt"]
    limit = canary_limit(st)
    print(f"CANARY_ATTEMPT {n}/{limit}", flush=True)
    try:
        from app.settings_store import save_settings

        save_settings({"canaryAttempt": n, "canaryLimit": limit})
    except Exception:
        pass
    return n


def pause_canary(reason: str) -> None:
    from app.overlay_path import overlay_rollout

    if overlay_rollout() != "canary":
        return
    st = load_state()
    st["paused"] = True
    st["pausedReason"] = str(reason or "unknown")
    save_state(st)
    _set_rollout("off")
    print(f"CANARY_PAUSED {st['pausedReason']}", flush=True)


def close_canary_if_done() -> None:
    st = load_state()
    limit = canary_limit(st)
    if int(st.get("canaryAttempt") or 0) >= limit and not st.get("paused"):
        _set_rollout("off")
        print(
            f"CANARY_CLOSED attempts={st['canaryAttempt']} limit={limit} "
            f"overlayRollout=off",
            flush=True,
        )


def record_canary_job(job: dict[str, Any]) -> None:
    st = load_state()
    jobs = list(st.get("jobs") or [])
    jobs.append(job)
    st["jobs"] = jobs
    save_state(st)


def try_acquire_overlay_slot():
    """Lock exclusivo não-bloqueante. None = outro OVERLAY pesado em curso."""
    path = LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write(b"\0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()}\n".encode())
        fh.flush()
        return fh
    except OSError:
        try:
            fh.close()
        except OSError:
            pass
        return None


def release_overlay_slot(fh) -> None:
    if fh is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fh.close()
    except OSError:
        pass


@contextmanager
def overlay_heavy_slot():
    """1 OVERLAY pesado por vez. Se ocupado, levanta — o caller vai de FULL."""
    fh = try_acquire_overlay_slot()
    if fh is None:
        raise RuntimeError("OVERLAY_SLOT_BUSY")
    print("OVERLAY_SLOT acquired", flush=True)
    try:
        yield
    finally:
        release_overlay_slot(fh)
        print("OVERLAY_SLOT released", flush=True)
