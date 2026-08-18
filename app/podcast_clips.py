"""Clipes de podcast — 1 vídeo longo vira N Reels independentes na Fila.

O job MÃE roda a fase 1 normal (transcrição + análise), pede à IA a divisão
em clipes e grava clips_plan.json. O Worker vê o plano e materializa um
projeto FILHO por clipe: hardlink da fonte (cópia se falhar), edit/
preview_edits.json com os ranges (o pipeline já prioriza preview_edits
sobre o plano LLM) e a headline do clipe, herdando marca/tipo de conteúdo.
Cada filho roda como um job "dynamic" comum.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

MIN_CLIP_SEC = 10.0
MAX_CLIP_SEC = 120.0
MAX_CLIPS = 6

SYSTEM = (
    "Você divide um vídeo longo (podcast/entrevista/aula) em CLIPES curtos "
    "independentes para Reels. Cada clipe precisa se sustentar sozinho: "
    "começa num gancho forte e termina numa conclusão — nunca no meio de "
    "uma frase.\n"
    "- 2 a 6 clipes, cada um com 20 a 90 segundos no total.\n"
    "- Um clipe pode juntar mais de um trecho (ranges), na ordem original.\n"
    "- start/end em segundos no vídeo ORIGINAL, dentro da fala real.\n"
    "- headline curta por clipe (máx 6 palavras), específica do clipe.\n"
    "- Clipes NÃO podem se sobrepor.\n"
    'Responda SOMENTE JSON: {"clips":[{"headline":"…",'
    '"ranges":[{"start":12.5,"end":48.2}]}]}'
)

RETRY_PROMPT = (
    "Sua resposta não veio como JSON válido no formato pedido. Responda de "
    'novo SOMENTE com {"clips":[{"headline":"…","ranges":[{"start":0.0,'
    '"end":30.0}]}]}'
)


def clip_messages(packed: str, duration: float, regions: list[tuple[float, float]]) -> list[dict]:
    reg = "\n".join(f"- {a:.2f} → {b:.2f}" for a, b in (regions or [])[:120])
    user = (
        f"DURAÇÃO_TOTAL: {duration:.1f}s\n"
        f"REGIÕES DE FALA (acústicas):\n{reg}\n\n"
        f"TRANSCRIÇÃO:\n{packed[:24000]}"
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("sem JSON na resposta")
    return json.loads(m.group(0))


def parse_clips_plan(text: str, *, duration: float) -> list[dict[str, Any]]:
    """Valida e normaliza a resposta da IA. Levanta ValueError se inútil."""
    data = _extract_json(text)
    raw = data.get("clips")
    if not isinstance(raw, list) or not raw:
        raise ValueError("clips ausentes")
    out: list[dict[str, Any]] = []
    last_end = -1.0
    for c in raw[:MAX_CLIPS]:
        if not isinstance(c, dict):
            continue
        ranges = []
        for r in c.get("ranges") or []:
            try:
                a = max(0.0, float(r["start"]))
                b = min(float(duration), float(r["end"]))
            except (KeyError, TypeError, ValueError):
                continue
            if b - a >= 1.0:
                ranges.append({"start": round(a, 3), "end": round(b, 3)})
        if not ranges:
            continue
        total = sum(r["end"] - r["start"] for r in ranges)
        if not (MIN_CLIP_SEC <= total <= MAX_CLIP_SEC):
            continue
        # sem sobreposição entre clipes (ordem de chegada)
        first = min(r["start"] for r in ranges)
        if first < last_end:
            continue
        last_end = max(r["end"] for r in ranges)
        headline = str(c.get("headline") or "").strip()[:80]
        out.append({"headline": headline, "ranges": ranges,
                    "totalSec": round(total, 3)})
    if not out:
        raise ValueError("nenhum clipe válido após validação")
    return out


def plan_clips(
    edit_dir: Path,
    *,
    packed: str,
    duration: float,
    regions: list[tuple[float, float]],
    chat_fn: Callable[..., tuple[str, str]],
) -> list[dict[str, Any]]:
    """Chama a IA (com 1 retry de formato), grava clips_plan.json e devolve."""
    messages = clip_messages(packed, duration, regions)
    last_err: Exception | None = None
    for attempt in (1, 2):
        text, backend = chat_fn(messages, model="gemini-web/default")
        try:
            clips = parse_clips_plan(text, duration=duration)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
            if attempt == 1:
                messages.append({"role": "assistant", "content": text or ""})
                messages.append({"role": "user", "content": RETRY_PROMPT})
            continue
        payload = {"clips": clips, "backend": backend, "sourceDuration": duration}
        (Path(edit_dir) / "clips_plan.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return clips
    raise RuntimeError(f"clips_plan inválido: {last_err}")


def _safe_slug(text: str, fallback: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", str(text or ""), flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)[:40]
    return s or fallback


def materialize_clip_projects(
    projects_root: Path,
    mother_source: Path,
    plan: list[dict[str, Any]],
    *,
    intent: dict | None = None,
    style: dict | None = None,
) -> list[dict[str, Any]]:
    """Cria um projeto por clipe. Devolve [{id,name,source,editDir,projectDir}].

    A fonte entra por HARDLINK (mesmo volume, custo zero); cai para cópia se
    o link falhar. preview_edits.json carrega os ranges + headline — o
    pipeline usa esses ranges no lugar do plano LLM e a headline vira o hook.
    """
    projects_root = Path(projects_root)
    mother_source = Path(mother_source)
    out: list[dict[str, Any]] = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for i, clip in enumerate(plan, start=1):
        job_id = uuid.uuid4().hex[:10]
        slug = _safe_slug(clip.get("headline"), f"clipe_{i}")
        project = projects_root / f"{stamp}_clip{i:02d}_{slug}_{job_id}"
        project.mkdir(parents=True, exist_ok=True)
        dest = project / mother_source.name
        try:
            os.link(mother_source, dest)
        except OSError:
            shutil.copy2(mother_source, dest)
        edit = project / "edit"
        edit.mkdir(parents=True, exist_ok=True)
        (edit / "preview_edits.json").write_text(
            json.dumps({
                "edl": {"ranges": [dict(r) for r in clip["ranges"]]},
                "headline": str(clip.get("headline") or ""),
                "fromClips": True,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if intent:
            child_intent = dict(intent)
            child_intent["editingIntent"] = "dynamic"
            try:
                from app.editing_intent import save as save_intent

                save_intent(edit, child_intent)
            except Exception:
                pass
        _ = style  # estilo herdado pela cadeia normal de preset (marca ativa)
        name = clip.get("headline") or f"Clipe {i}"
        out.append({
            "id": job_id,
            "name": str(name)[:60],
            "source": str(dest),
            "editDir": str(edit),
            "projectDir": str(project),
            "totalSec": clip.get("totalSec"),
        })
    return out
