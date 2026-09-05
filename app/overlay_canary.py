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
JOBS_GUARDADOS = 300
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
    # Atomico: write_text direto trunca antes de escrever; um leitor nesse
    # instante ve JSON pela metade, load_state devolve _EMPTY e o proximo
    # save_state APAGA um `paused: true` legitimo — o canario pausado por
    # defeito real voltava sozinho.
    _tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    _tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(_tmp, STATE_PATH)
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



@contextmanager
def _trava_do_estado(timeout_s: float = 5.0):
    """Serializa load->muda->save entre processos (parallelJobs=2).

    Sem isto, o worker A le o estado ANTES de o B pausar e o save do A
    apaga a pausa — a mesma perda que a escrita truncada causava, por
    outra porta. Falha ABERTA com aviso: nunca derruba job por causa de
    trava de telemetria.
    """
    USER_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_PATH.with_name(STATE_PATH.name + ".lock")
    fim = time.monotonic() + timeout_s
    fh = None
    while fh is None and time.monotonic() < fim:
        fh = _tentar_pegar(path)
        if fh is None:
            time.sleep(0.05)
    if fh is None:
        print("[warn] trava do canary-state ocupada — seguindo sem", flush=True)
    try:
        yield
    finally:
        if fh is not None:
            release_overlay_slot(fh)

def canary_allows_attempt() -> bool:
    """True só se canary ativo, não pausado, e attempt < canaryLimit."""
    from app.overlay_path import overlay_rollout

    if overlay_rollout() != "canary":
        return False
    st = load_state()
    if st.get("paused") and not st.get("pausedAt"):
        # Pausa fossil: anterior ao codigo que grava a data. Na maquina do
        # usuario havia um "TRUE_PEAK -0.9" de agosto que hoje nem pausaria
        # (cabe na folga) — e qualquer volta ao modo canario nasceria
        # bloqueada por ele. Sem data = de outra era = limpa, com registro.
        with _trava_do_estado():
            st = load_state()
            if st.get("paused") and not st.get("pausedAt"):
                print(f"CANARY_PAUSA_FOSSIL_LIMPA {st.get('pausedReason')}",
                      flush=True)
                st["paused"] = False
                st["pausedReason"] = None
                save_state(st)
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
    with _trava_do_estado():
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
    from datetime import datetime

    with _trava_do_estado():
        st = load_state()
        st["paused"] = True
        st["pausedReason"] = str(reason or "unknown")
        # QUANDO. Sem a data, uma pausa antiga por um defeito ja consertado
        # fica indistinguivel de uma pausa de agora — e o estado sobrevive a
        # versoes.
        st["pausedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
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
    """Guarda o registro do job — com a DATA.

    Sem ela os 416 registros viram um monte sem tempo: em 30/08, 21 deles
    estavam com o pico acima de -1,0 dBTP e nao havia como saber se eram
    anteriores ao `garantir_true_peak` (que existe justamente para isso) ou
    um defeito vivo. Ficar sem resposta ja custou caro aqui — totais sem
    data fizeram perseguir tres defeitos que ja estavam consertados.
    """
    from datetime import datetime

    with _trava_do_estado():
        st = load_state()
        jobs = list(st.get("jobs") or [])
        # 5.0.46: a lista crescia para sempre (804 jobs, 229 KB em 05/09),
        # lida e reescrita a CADA render. O canario decide com os ultimos
        # `canaryLimit` (20); guardar os ultimos JOBS_GUARDADOS basta para
        # auditoria, e o arquivo volta a caber numa leitura.
        jobs = jobs[-(JOBS_GUARDADOS - 1):] if len(jobs) >= JOBS_GUARDADOS else jobs
        jobs.append(dict(job, at=datetime.now().astimezone().isoformat(
            timespec="seconds")))
        st["jobs"] = jobs
        save_state(st)


# Quanto esperar pela vaga antes de desistir e ir pelo caminho lento.
#
# Medido nos projetos reais: a vaga cobre 150s de um job de 575s -- 26% dele.
# Bate com os 28% de jobs que perderam a corrida e foram para o Remotion
# inteiro. Como a espera maxima e o proprio tamanho da janela, o pior caso de
# esperar (150s) e metade do que custa cair (+294s de mediana), e o caso medio
# (~75s) e quatro vezes menor.
#
# O teto e generoso de proposito: se a espera estourar, o job segue pelo
# caminho lento como antes -- perde-se o tempo esperado, nunca o job.
ESPERA_MAXIMA_S = 180.0
_INTERVALO_S = 2.0


def _tentar_pegar(path: Path):
    """Uma tentativa. Devolve o arquivo travado, ou None."""
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


def try_acquire_overlay_slot(espera_s: float = ESPERA_MAXIMA_S):
    """Pega a vaga do OVERLAY, esperando ate `espera_s`. None = desistiu.

    Era nao-bloqueante: quem perdesse a corrida ia direto para o Remotion
    inteiro, que custa 1,91x contra 1,31x de rodar acompanhado. Como a vaga so
    fica ocupada por 26% do job, esperar quase sempre e mais barato do que cair.

    `espera_s=0` mantem o comportamento antigo, para teste.
    """
    path = LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = _tentar_pegar(path)
    if fh is not None or espera_s <= 0:
        return fh

    t0 = time.monotonic()
    print(f"OVERLAY_SLOT esperando vaga (ate {espera_s:.0f}s)", flush=True)
    while time.monotonic() - t0 < espera_s:
        time.sleep(_INTERVALO_S)
        fh = _tentar_pegar(path)
        if fh is not None:
            print(f"OVERLAY_SLOT vaga liberada apos {time.monotonic() - t0:.0f}s",
                  flush=True)
            return fh
    print(f"OVERLAY_SLOT desistiu apos {espera_s:.0f}s — FULL", flush=True)
    return None


def _try_acquire_overlay_slot_antigo():
    """Versao original, sem espera — mantida so como referencia do teste."""
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
