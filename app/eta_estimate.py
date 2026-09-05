"""ETA local a partir de timing.json histórico. Sem cronômetro falso."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def features(timing: dict | None, *, duration_s: float | None = None, cuts: int | None = None) -> dict:
    t = dict(timing or {})
    dur = duration_s if duration_s is not None else t.get("finalDuration") or t.get("sourceDuration")
    ncuts = cuts if cuts is not None else t.get("cuts") or t.get("rangeCount")
    path = str(t.get("renderPath") or t.get("zoomEngine") or "").lower()
    hdr = bool(t.get("hdr") or t.get("isHdr"))
    if not hdr:
        hdr = "hdr" in path or "hlg" in str(t.get("color") or "").lower()
    return {
        "duration": _f(dur),
        "cuts": int(_f(ncuts)),
        "hdr": hdr,
        "path": path,
        "total": _f(t.get("wholeJobSec") or t.get("totalSec")),
    }


def _weight(feat: dict) -> float:
    w = 8.0 + feat["duration"] * 1.15
    if feat["cuts"] > 12:
        w += (feat["cuts"] - 12) * 0.8
    if feat["hdr"]:
        w *= 1.35
    if "overlay" in feat["path"]:
        w *= 0.72
    if feat["duration"] >= 70:
        w *= 1.1
    return max(8.0, w)


def estimate_seconds(job: dict | None, history: list[dict] | None) -> float | None:
    """Devolve segundos previstos, ou None se não houver histórico suficiente."""
    hist = [h for h in (history or []) if _f((h or {}).get("wholeJobSec") or (h or {}).get("totalSec")) > 3]
    if len(hist) < 2:
        return None
    ratios: list[float] = []
    for h in hist:
        feat = features(h)
        if feat["duration"] < 3 or feat["total"] < 3:
            continue
        ratios.append(feat["total"] / _weight(feat))
    if len(ratios) < 2:
        return None
    ratios.sort()
    mid = ratios[len(ratios) // 2]
    want = features(job or {})
    if want["duration"] < 1:
        return None
    return round(max(12.0, _weight(want) * mid), 1)


def format_eta(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 45:
        return "~40s restantes"
    if s < 90:
        return "~1 min restante"
    mins = s // 60
    rem = s % 60
    if rem < 15:
        return f"~{mins} min restantes"
    return f"~{mins}min{rem:02d}s restantes"


def label_for_job(job: dict | None, history: list[dict] | None) -> str | None:
    return format_eta(estimate_seconds(job, history))


def enrich_from_edit(timing: dict | None, edit_dir: Path | None) -> dict:
    """Completa duration/cuts a partir de intent/EDL já gravados — sem probe."""
    t = dict(timing or {})
    if edit_dir is None:
        return t
    edit = Path(edit_dir)
    intent_p = edit / "job_intent.json"
    if intent_p.exists() and not t.get("sourceDuration") and not t.get("finalDuration"):
        try:
            intent = json.loads(intent_p.read_text(encoding="utf-8-sig"))
            if intent.get("sourceDurationSec"):
                t["sourceDuration"] = float(intent["sourceDurationSec"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    edl_p = edit / "edl.json"
    if edl_p.exists():
        try:
            edl = json.loads(edl_p.read_text(encoding="utf-8-sig"))
            ranges = [r for r in (edl.get("ranges") or []) if isinstance(r, dict)]
            if ranges and not t.get("cuts") and not t.get("rangeCount"):
                t["cuts"] = len(ranges)
            if ranges and not t.get("sourceDuration") and not t.get("finalDuration"):
                t["sourceDuration"] = max(float(r.get("end") or 0) for r in ranges)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return t


def collect_history(projects_root: Path | None, *, limit: int = 30) -> list[dict]:
    root = Path(projects_root) if projects_root else None
    if root is None or not root.is_dir():
        return []
    files = sorted(
        root.glob("*/edit/timing.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out: list[dict] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        out.append(enrich_from_edit(data, path.parent))
    return out


def _elapsed_s(job: dict) -> float | None:
    raw = str(job.get("startedAt") or "").strip().replace("Z", "+00:00")
    if not raw:
        return None
    from datetime import datetime, timezone

    try:
        t0 = datetime.fromisoformat(raw)
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - t0).total_seconds())
    except ValueError:
        return None


def remaining_seconds(job: dict, est_total: float | None) -> float | None:
    """Tempo restante que RESPEITA o relógio e o progresso.

    O rótulo antigo era o total previsto pela média histórica, parado: ficava
    "~23 min restantes" por horas enquanto o trabalho corria — o usuário
    reclamou disso três vezes num dia, com razão. Regras:

      - o previsto ENCOLHE com o tempo já decorrido (nunca fica parado);
      - com progresso real (>15%), o ritmo observado corrige a previsão
        (elapsed * restante/feito), com peso crescente no observado;
      - nunca sobe de volta; nunca abaixo de 10 s enquanto roda.
    """
    elapsed = _elapsed_s(job)
    if est_total is None and elapsed is None:
        return None
    rest_hist = None
    if est_total is not None:
        rest_hist = max(10.0, est_total - (elapsed or 0.0))
    try:
        p = float(job.get("progress") or 0) / 100.0
    except (TypeError, ValueError):
        p = 0.0
    if elapsed is not None and elapsed > 20 and 0.15 <= p < 1.0:
        rest_obs = elapsed * (1.0 - p) / p
        if rest_hist is None:
            return rest_obs
        peso = min(1.0, (p - 0.15) / 0.45)   # 15% -> só histórico; 60%+ -> só observado
        return rest_obs * peso + rest_hist * (1.0 - peso)
    return rest_hist


def format_elapsed(seconds: float | None) -> str | None:
    """Há quanto tempo está rodando. Verdade, não previsão."""
    if seconds is None or seconds < 20:
        return None
    s = int(seconds)
    if s < 90:
        return "há 1 min"
    return f"há {s // 60} min"


def attach_eta(job: dict, history: list[dict] | None, edit_dir: Path | None = None) -> dict:
    """Anexa o TEMPO JÁ CORRIDO. Não promete quanto falta.

    A previsão saiu na 4.14. Medida nos 172 vídeos do usuário, prevendo
    cada um com os outros como histórico: erro relativo de **47% na
    mediana**, e só 24% das previsões dentro de 25% do real. Os extremos
    diziam "~1 min restante" num vídeo de 15 minutos e "~9 min" num de
    1,5.

    É a mesma conclusão que o apply já tinha tirado, com o mesmo número, e
    a frase que ficou no código de lá vale aqui: dizer "cerca de 2
    minutos" e levar 40s é pior que não dizer nada.

    O tempo corrido responde à mesma pergunta de quem olha a Fila — "isso
    travou?" — sem prometer nada.
    """
    # 5.0.76: o rotulo NUNCA vem do registro. 41 jobs gravados na epoca da
    # previsao (18-20/08) ainda carregam `etaLabel` no blob ("~22min34s
    # restantes"), e ao refazer um deles o card mostrava esse numero velho
    # nos primeiros 20 s — ate o "ha 1 min" cobrir. Visto por ele em 05/09.
    job.pop("etaLabel", None)
    status = str(job.get("status") or "")
    if status not in ("processing", "queued", "importing"):
        return job
    if status == "processing":
        rodando = _segundos_rodando(job)
        label = format_elapsed(rodando)
        if label:
            job["etaLabel"] = label
    return job


def _segundos_rodando(job: dict) -> float | None:
    from datetime import datetime, timezone

    bruto = str(job.get("startedAt") or job.get("createdAt") or "").strip()
    if not bruto:
        return None
    try:
        t = datetime.fromisoformat(bruto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - t).total_seconds())
