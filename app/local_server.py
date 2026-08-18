#!/usr/bin/env python3
"""ATIVAVID Local — studio server (preset + drop + queue + run_fast).

    uv run python app/local_server.py --projects-root ~/ATIVAVID/Projetos --port 4850

Opens on http://127.0.0.1:4850/ — no cloud, no Redis. Queue is JSON on disk;
one worker thread runs pipeline/run_fast.py per job.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# UTF-8 stdout on Windows consoles (same idea as helpers/_utf8.py)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "helpers"
STUDIO = REPO / "assets" / "studio"
PREVIEW = REPO / "assets" / "preview"
PRESET_PATH = PREVIEW / "default-style.json"
USER_PRESET_PATH = Path.home() / "ATIVAVID" / "default-style.json"

# Chaves em %USERPROFILE%\ATIVAVID\.env (Program Files é só leitura)
USER_DIR = Path.home() / "ATIVAVID"
ENV_PATH = USER_DIR / ".env"
_LEGACY_ENV = REPO / ".env"
RUN_FAST = REPO / "pipeline" / "run_fast.py"

sys.path.insert(0, str(HELPERS))

REASON_LABELS = {
    "out_of_format": "Formato fora do padrão (use vertical curto)",
    "missing_brand_copy": "Falta o texto da marca no preset (end card)",
    "bad_transcript": "Transcrição ruim ou vazia — confira o áudio",
    "inaudible_voice": "Voz muito baixa / inaudível",
    "color_uncertain": "Cor ambígua (LOG?) — precisa revisão",
    "no_speech": "Não achou fala no áudio",
    "black_frames": "Frames pretos no corte",
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07|\x1b.")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s or "")


def friendly_error(raw: str) -> str:
    """Short UI label; keep the raw string in `detail` for diagnostics."""
    text = strip_ansi((raw or "").strip())
    if not text:
        return "Não foi possível concluir este vídeo."
    low = text.lower()
    if "cancel" in low:
        return "Cancelado pelo usuário"
    return "Não foi possível concluir este vídeo."


STAGE_LABELS = {
    "queued": "Aguardando",
    "analyzing": "Preparando vídeo...",
    "transcribing": "Preparando vídeo...",
    "planning": "Preparando vídeo...",
    "cutting": "Preparando vídeo...",
    "visuals": "Aplicando legendas e efeitos...",
    "preview": "Aplicando legendas e efeitos...",
    "waiting_render": "Aplicando edição...",
    "rendering": "Aplicando edição...",
    "exporting": "Finalizando vídeo...",
    "done": "Vídeo concluído",
    "error": "Não foi possível concluir este vídeo.",
    "cancelled": "Cancelado",
    "needs_review": "Não foi possível concluir este vídeo.",
    "processing": "Preparando vídeo...",
}

def resolve_delivery_mp4(edit: Path) -> Path | None:
    """Arquivo final do projeto: state.finalVideo, senão final.mp4, senão o .mp4 mais novo.

    Depois da 1.70 o arquivo leva o nome da headline ("Transformando celular.mp4"),
    não necessariamente final.mp4.
    """
    skip = {"cut.mp4", "base.mp4", "cut_proxy.mp4"}
    state_p = edit / "state.json"
    if state_p.exists():
        try:
            rel = str(json.loads(state_p.read_text(encoding="utf-8-sig")).get("finalVideo") or "").strip()
            if rel and rel not in skip and ".." not in Path(rel).parts:
                cand = edit / rel
                if cand.is_file():
                    return cand
                parent_cand = edit.parent / Path(rel).name
                if parent_cand.is_file():
                    return parent_cand
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    hard = edit / "final.mp4"
    if hard.is_file():
        return hard
    search = [edit]
    if edit.name.lower() == "edit":
        search.append(edit.parent)
    cands = []
    for folder in search:
        if not folder.is_dir():
            continue
        cands.extend(
            p for p in folder.glob("*.mp4")
            if p.name not in skip and not p.name.endswith(".prenorm.mp4")
        )
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def ensure_job_thumb(job: dict) -> Path | None:
    """JPEG poster for hub cards. Prefer cover.jpg (1º frame), senão extrai o frame 0."""
    edit = Path(job["editDir"])
    edit.mkdir(parents=True, exist_ok=True)
    thumb = edit / "thumb.jpg"
    cover = edit / "cover.jpg"
    delivery = resolve_delivery_mp4(edit)
    src = next((p for p in (cover, delivery, edit / "final.mp4", edit / "cut.mp4", Path(job.get("source") or "")) if p and p.is_file()), None)
    if thumb.exists() and thumb.stat().st_size > 400:
        if not src or src.stat().st_mtime <= thumb.stat().st_mtime:
            return thumb
    if not src:
        return thumb if thumb.exists() else None
    if shutil.which("ffmpeg") is None:
        return cover if cover.exists() and cover.stat().st_size > 400 else (thumb if thumb.exists() else None)
    try:
        from app.win_process import hide_console_kwargs

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-frames:v", "1", "-q:v", "3",
            "-vf", "scale=360:-2",
            str(thumb),
        ]
        subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            timeout=40,
            **hide_console_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return cover if cover.exists() else None
    return thumb if thumb.exists() and thumb.stat().st_size > 400 else (cover if cover.exists() else None)


def load_llm_proxy() -> dict:
    keys = load_env_keys()
    key = keys.get("LLM_PROXY_API_KEY", "")
    hint = ""
    if key:
        hint = key[:6] + "…" + key[-4:] if len(key) > 12 else "••••"
    # Local OpenAI-compatible gateway is embedded in this app (/v1 on the same port).
    base = keys.get("LLM_PROXY_BASE_URL", "").rstrip("/") or "http://127.0.0.1:4850/v1"
    dash = keys.get("LLM_PROXY_DASHBOARD", "").rstrip("/")
    return {
        "baseUrl": base,
        "hasKey": bool(key),
        "keyHint": hint,
        "mode": keys.get("LLM_PROXY_MODE", "session") or "session",  # session (cookies) | apikey
        "model": keys.get("LLM_PROXY_MODEL", ""),
        "dashboardUrl": dash,
        "baseUrlSaved": bool(keys.get("LLM_PROXY_BASE_URL", "").strip()),
        "embedded": True,
    }


def save_llm_proxy(body: dict) -> dict:
    updates: dict[str, str] = {}
    if "baseUrl" in body:
        updates["LLM_PROXY_BASE_URL"] = str(body.get("baseUrl") or "").strip().rstrip("/")
    if "apiKey" in body and str(body.get("apiKey") or "").strip():
        updates["LLM_PROXY_API_KEY"] = str(body["apiKey"]).strip()
    if "mode" in body and body["mode"] in ("session", "apikey"):
        updates["LLM_PROXY_MODE"] = body["mode"]
    if "model" in body:
        updates["LLM_PROXY_MODEL"] = str(body.get("model") or "").strip()
    if "dashboardUrl" in body:
        updates["LLM_PROXY_DASHBOARD"] = str(body.get("dashboardUrl") or "").strip().rstrip("/")
    if updates:
        save_env_keys(updates)
    return load_llm_proxy()


SESSION_PROVIDERS = {
    "gemini-web": {
        "id": "gemini-web",
        "name": "Gemini Web",
        "hosts": ["gemini.google.com", "google.com"],
        "url": "https://gemini.google.com/app",
    },
    "chatgpt-web": {
        "id": "chatgpt-web",
        "name": "ChatGPT Web",
        "hosts": ["chatgpt.com", "chat.openai.com", "openai.com"],
        "url": "https://chatgpt.com",
    },
    "claude-web": {
        "id": "claude-web",
        "name": "Claude Web",
        "hosts": ["claude.ai"],
        "url": "https://claude.ai",
    },
    "deepseek-web": {
        "id": "deepseek-web",
        "name": "DeepSeek Web",
        "hosts": ["chat.deepseek.com", "deepseek.com"],
        "url": "https://chat.deepseek.com",
    },
}

SESSIONS_PATH = USER_DIR / "sessions.json"
_LEGACY_SESSIONS = REPO / ".ativavid-sessions.json"


def load_sessions() -> dict:
    path = SESSIONS_PATH if SESSIONS_PATH.exists() else _LEGACY_SESSIONS
    if not path.exists():
        return {"providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {"providers": {}}
    # Migra sessão antiga (Program Files / repo) para a pasta do usuário
    if path == _LEGACY_SESSIONS and isinstance(data, dict) and data.get("providers"):
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            SESSIONS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return data if isinstance(data, dict) else {"providers": {}}


def save_session_capture(provider_id: str, cookies: list[dict], meta: dict | None = None) -> dict:
    """Store cookies captured by the browser extension (user's own session)."""
    if provider_id not in SESSION_PROVIDERS:
        raise ValueError("provedor desconhecido")
    if not isinstance(cookies, list) or not cookies:
        raise ValueError("cookies vazios")
    # keep only name/value/domain/path — never log
    clean = []
    for c in cookies[:200]:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        clean.append({
            "name": str(c.get("name"))[:120],
            "value": str(c.get("value", ""))[:4000],
            "domain": str(c.get("domain", ""))[:120],
            "path": str(c.get("path", "/"))[:120],
        })
    if not clean:
        raise ValueError("nenhum cookie válido")
    data = load_sessions()
    providers = data.setdefault("providers", {})
    providers[provider_id] = {
        "id": provider_id,
        "name": SESSION_PROVIDERS[provider_id]["name"],
        "capturedAt": _utc(),
        "cookieCount": len(clean),
        "cookies": clean,
        "meta": meta or {},
    }
    USER_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SESSIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SESSIONS_PATH)
    return {
        "ok": True,
        "provider": provider_id,
        "cookieCount": len(clean),
        "capturedAt": providers[provider_id]["capturedAt"],
    }


def sessions_public() -> list[dict]:
    from app.llm_session import has_chatgpt_session, has_gemini_session

    stored = load_sessions().get("providers") or {}
    out = []
    for pid, info in SESSION_PROVIDERS.items():
        st = stored.get(pid) or {}
        count = int(st.get("cookieCount") or 0)
        if pid == "gemini-web":
            ready = has_gemini_session()
            hint = (
                "Pronto para usar"
                if ready
                else (
                    "Cookies salvos, mas falta login completo — abra gemini.google.com e recapture"
                    if count
                    else "Ainda não capturado"
                )
            )
        elif pid == "chatgpt-web":
            ready = has_chatgpt_session()
            hint = (
                "Pronto para usar"
                if ready
                else (
                    "Cookies salvos, mas sem sessão válida — abra chatgpt.com e recapture"
                    if count
                    else "Ainda não capturado"
                )
            )
        else:
            ready = count > 0
            hint = "Capturado (suporte experimental)" if ready else "Ainda não capturado"
        out.append({
            **info,
            "configured": count > 0,
            "ready": ready,
            "cookieCount": count,
            "capturedAt": st.get("capturedAt"),
            "hint": hint,
        })
    return out


def preset_from_style_payload(body: dict, base: dict | None = None) -> dict:
    """Map preview_style.json / style-setup payload onto the brand preset shape."""
    from app.brand_presets import STYLE_KEYS

    out = dict(base if base is not None else load_preset())
    for k in (*STYLE_KEYS, "outputFormat"):
        if k in body and body[k] is not None:
            out[k] = body[k]
    # oneClick e fastMode são o mesmo interruptor de produto
    if "oneClick" in body and body["oneClick"] is not None:
        out["fastMode"] = bool(body["oneClick"])
        out["oneClick"] = bool(body["oneClick"])
    elif "fastMode" in body and body["fastMode"] is not None:
        out["fastMode"] = bool(body["fastMode"])
        out["oneClick"] = bool(body["fastMode"])
    if isinstance(body.get("elements"), dict):
        elems = dict(out.get("elements") or {})
        elems.update(body["elements"])
        out["elements"] = elems
    return out


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_IMPORT_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".mts", ".m2ts"}
_IMPORT_SKIP_DIRS = {"edit", "node_modules", ".git", "__pycache__", "remotion"}
_IMPORT_SKIP_FILES = {"cut.mp4", "final.mp4", "base.mp4", "cut_proxy.mp4"}


def _is_import_video(path: Path) -> bool:
    name = path.name.lower()
    if name in _IMPORT_SKIP_FILES or name.endswith(".prenorm.mp4"):
        return False
    return path.suffix.lower() in _IMPORT_VIDEO_EXT


def _walk_import_videos(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name.lower() not in _IMPORT_SKIP_DIRS and not name.startswith(".")
        ]
        for name in filenames:
            src = Path(dirpath) / name
            if _is_import_video(src):
                found.append(src)
    found.sort(key=lambda item: str(item).lower())
    return found


def _safe_name(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_")
    return (stem or "video")[:60]


_OPAQUE_NAME = re.compile(
    r"^(?:"
    r"IMG|DSC|VID|MOV|MVI|PXL|WA|GX|Screenshot|screen|copy"
    r")[_-]?",
    re.I,
)


def _is_opaque_title(name: str) -> bool:
    """Camera codes / UUIDs — ruim como título na UI."""
    raw = (name or "").strip()
    if not raw:
        return True
    base = re.sub(r"\s*\(\+\d+\)\s*$", "", raw).strip()
    stem = Path(base).stem if "." in base else base
    if _OPAQUE_NAME.match(stem):
        return True
    if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", stem, re.I):
        return True
    if re.fullmatch(r"[A-Za-z]{0,4}_?\d{3,}", stem):
        return True
    return False


def _job_recency_key(job: dict) -> str:
    """Mais recente: término (reedição) > atualização > criação."""
    return str(job.get("finishedAt") or job.get("updatedAt") or job.get("createdAt") or "")


def _fmt_job_when(iso: str | None) -> str:
    """Data/hora local pt-BR a partir de ISO UTC."""
    if not iso:
        return ""
    try:
        raw = str(iso).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%d/%m/%Y · %H:%M")
    except Exception:
        return str(iso)[:16]


def enrich_job_display(job: dict, edit_dir: Path | None = None) -> dict:
    """Campos de UI: título amigável + início/fim formatados."""
    edit = edit_dir or Path(job.get("editDir") or ".")
    created = job.get("createdAt") or job.get("startedAt")
    finished = job.get("finishedAt")
    if not finished and job.get("status") == "done":
        finished = job.get("updatedAt")
    job["createdAtLabel"] = _fmt_job_when(created)
    job["startedAtLabel"] = job["createdAtLabel"]
    job["finishedAtLabel"] = _fmt_job_when(finished) if finished else ""
    job["title"] = _resolve_job_title(job, edit)
    return job


def _humanize_stem(stem: str) -> str:
    t = re.sub(r"[_\-]+", " ", (stem or "").strip())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return "Vídeo"
    return t[:1].upper() + t[1:]


def _default_job_title(name: str, created_at: str | None = None, extra_takes: int = 0) -> str:
    when = _fmt_job_when(created_at)
    base = re.sub(r"\s*\(\+\d+\)\s*$", "", (name or "").strip())
    stem = Path(base).stem if base else "video"
    if _is_opaque_title(stem):
        title = f"Vídeo · {when}" if when else "Vídeo"
    else:
        title = _humanize_stem(stem)
    if extra_takes > 0:
        title = f"{title} (+{extra_takes})"
    return title[:80]


def _suggest_title_from_edit(edit_dir: Path) -> str | None:
    """Primeira linha útil da legenda ou gancho do edit-data."""
    leg = edit_dir / "legenda.txt"
    if leg.exists():
        try:
            for line in leg.read_text(encoding="utf-8-sig").splitlines():
                s = line.strip().strip('"').strip("'")
                if len(s) >= 8 and not s.startswith("#"):
                    # corta hashtags no fim
                    s = re.split(r"\s+#", s, maxsplit=1)[0].strip()
                    if len(s) >= 8:
                        return (s[:72] + ("…" if len(s) > 72 else ""))
        except OSError:
            pass
    ed = edit_dir / "remotion" / "public" / "edit-data.json"
    if ed.exists():
        try:
            data = json.loads(ed.read_text(encoding="utf-8-sig"))
            hook = data.get("hook") or {}
            lines = hook.get("lines") or hook.get("text") or []
            if isinstance(lines, str):
                lines = [lines]
            for ln in lines:
                s = str(ln or "").strip()
                if len(s) >= 6:
                    return s[:72] + ("…" if len(s) > 72 else "")
            hl = (data.get("headline") or data.get("aiHeadline") or "").strip()
            if len(hl) >= 6:
                return hl[:72]
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return None


def _resolve_job_title(job: dict, edit_dir: Path | None = None) -> str:
    """Título para a UI: manual > legenda/gancho > nome humanizado."""
    if job.get("titleLocked") and (job.get("title") or "").strip():
        return str(job["title"]).strip()[:80]
    edit = edit_dir or Path(job.get("editDir") or ".")
    name = str(job.get("name") or "")
    stored = str(job.get("title") or "").strip()
    # Legenda/gancho quando o nome é código de câmera ou o título ainda é genérico
    if _is_opaque_title(name) or not stored or stored.startswith("Vídeo ·"):
        suggested = _suggest_title_from_edit(edit)
        if suggested:
            return suggested
    if stored:
        return stored[:80]
    extra = 0
    m = re.search(r"\(\+(\d+)\)\s*$", name)
    if m:
        extra = int(m.group(1))
    return _default_job_title(name, job.get("createdAt"), extra_takes=extra)


def load_env_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    path = ENV_PATH if ENV_PATH.exists() else (_LEGACY_ENV if _LEGACY_ENV.exists() else None)
    if path is None:
        return keys
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def save_env_keys(updates: dict[str, str]) -> None:
    current = load_env_keys()
    for k, v in updates.items():
        if v is None:
            continue
        val = str(v).strip()
        if val:
            current[k] = val
        elif k in current:
            del current[k]
    lines = [f"{k}={v}" for k, v in sorted(current.items())]
    USER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError as e:
        raise OSError(
            f"Não foi possível gravar chaves em {ENV_PATH}: {e}"
        ) from e
    # expose to this process (worker children inherit)
    for k, v in current.items():
        os.environ[k] = v
    for k in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "PEXELS_API_KEY"):
        if k not in current and k in os.environ:
            os.environ.pop(k, None)


def merge_preset(base: dict, overlay: dict | None) -> dict:
    """Copia o overlay por cima do base. Arquivo curto do usuário não apaga o card final."""
    out = dict(base or {})
    if not isinstance(overlay, dict):
        return out
    for k, v in overlay.items():
        if k == "endCardCopy":
            from app.brand_kits import end_card_copy_filled

            if not end_card_copy_filled(v):
                continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


def _shipped_preset() -> dict:
    from app.brand_kits import fill_end_card_copy
    from app.style_defaults import load_shipped_style

    return fill_end_card_copy(load_shipped_style())


def load_preset() -> dict:
    shipped = _shipped_preset()
    if USER_PRESET_PATH.exists():
        try:
            user = json.loads(USER_PRESET_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(user, dict) and user:
                return merge_preset(shipped, user)
        except (OSError, json.JSONDecodeError):
            pass
    return shipped


def save_preset(data: dict) -> None:
    data = dict(data)
    data["fastMode"] = True
    from app.brand_kits import fill_end_card_copy, load_brand, save_brand
    from app.brand_presets import style_snapshot

    data = fill_end_card_copy(data)
    raw = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    USER_PRESET_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PRESET_PATH.write_text(raw, encoding="utf-8")
    try:
        brand = load_brand()
        brand.update(style_snapshot(data))
        if data.get("brandName"):
            brand["brandName"] = data["brandName"]
        if data.get("brandId"):
            brand["brandId"] = data["brandId"]
        save_brand(brand)
    except Exception:
        pass


def run_doutor() -> dict:
    from app.win_process import hide_console_kwargs

    env = os.environ.copy()
    env["PYTHONPATH"] = str(HELPERS) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        ["uv", "run", "python", str(HELPERS / "doutor.py"), "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **hide_console_kwargs(),
    )
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"bloqueios": proc.returncode, "itens": [], "raw": proc.stdout[-2000:]}


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_dir = self.root / ".ativavid"
        self.meta_dir.mkdir(exist_ok=True)
        self.jobs_path = self.meta_dir / "jobs.json"
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.jobs_path.exists():
            try:
                raw = json.loads(self.jobs_path.read_text(encoding="utf-8-sig"))
                self._jobs = {j["id"]: j for j in raw.get("jobs", [])}
            except (json.JSONDecodeError, TypeError, KeyError):
                self._jobs = {}

    def _save(self) -> None:
        payload = {"jobs": sorted(self._jobs.values(), key=_job_recency_key, reverse=True)}
        tmp = self.jobs_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.jobs_path)

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self._jobs.values(), key=_job_recency_key, reverse=True)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            return dict(self._jobs[job_id]) if job_id in self._jobs else None

    def upsert(self, job: dict) -> None:
        with self._lock:
            self._jobs[job["id"]] = job
            self._save()

    def update(self, job_id: str, **fields: object) -> dict | None:
        with self._lock:
            if job_id not in self._jobs:
                return None
            self._jobs[job_id].update(fields)
            self._jobs[job_id]["updatedAt"] = _utc()
            self._save()
            return dict(self._jobs[job_id])

    def delete(self, job_id: str) -> dict | None:
        """Remove job from the queue index. Caller deletes files if wanted."""
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is None:
                return None
            self._save()
            return dict(job)


class Worker:
    def __init__(self, store: JobStore):
        self.store = store
        self.q: queue.Queue[str] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self.busy_id: str | None = None  # último job ativo (compat health)
        self._busy: set[str] = set()
        self._procs: dict[str, subprocess.Popen] = {}
        self._proc: subprocess.Popen | None = None  # compat cancel legado
        self._proc_lock = threading.Lock()
        self._cancel_ids: set[str] = set()
        self._queued: set[str] = set()
        self.recovered_ids: list[str] = []
        self.parallel_jobs = 1

    def start(self) -> None:
        try:
            from app.performance import profile_settings
            from app.settings_store import load_settings

            perf = profile_settings(load_settings().get("performanceProfile"))
            self.parallel_jobs = max(1, int(perf.get("parallelJobs") or 1))
        except Exception:  # noqa: BLE001
            self.parallel_jobs = 1
        try:
            from app.job_slots import configure as configure_slots

            configure_slots(self.parallel_jobs)
        except Exception:
            pass

        try:
            from app.apply_tasks import sweep_stale_applies

            sweep_stale_applies(self.store.root, boot=True)
        except Exception:
            pass

        # re-queue anything left as queued/processing after crash
        recovered: list[str] = []
        for j in self.store.list():
            if j.get("status") in ("queued", "processing"):
                self.store.update(
                    j["id"],
                    status="queued",
                    message="Na fila (recuperado)",
                    recovered=True,
                )
                recovered.append(j["id"])
                with self._proc_lock:
                    self._queued.add(j["id"])
                self.q.put(j["id"])
        self.recovered_ids = recovered

        for i in range(self.parallel_jobs):
            t = threading.Thread(
                target=self._loop, name=f"ativavid-worker-{i}", daemon=True
            )
            t.start()
            self._threads.append(t)

    def enqueue(self, job_id: str) -> None:
        self._cancel_ids.discard(job_id)
        # Evita 2+ run_fast no mesmo projeto (trava remotion no Windows).
        with self._proc_lock:
            if job_id in self._busy or job_id in self._queued:
                return
            self._queued.add(job_id)
        self.q.put(job_id)

    def cancel(self, job_id: str) -> dict:
        """Para edição em andamento ou tira da fila. Sempre permite sair do 'Editando'."""
        self._cancel_ids.add(job_id)
        killed = False
        with self._proc_lock:
            proc = self._procs.get(job_id) or (
                self._proc if self.busy_id == job_id else None
            )
            if proc is not None and proc.poll() is None:
                killed = self._kill_proc(proc)
        job = self.store.get(job_id)
        if job and job.get("status") in ("queued", "processing"):
            self.store.update(
                job_id,
                status="error",
                message="Cancelado",
                reason="cancelled",
                detail="Cancelado pelo usuário",
            )
        return {"ok": True, "killed": killed, "id": job_id}

    @staticmethod
    def _kill_proc(proc: subprocess.Popen) -> bool:
        try:
            if sys.platform == "win32":
                from app.win_process import hide_console_kwargs

                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    **hide_console_kwargs(),
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            return True
        except Exception:
            try:
                proc.kill()
                return True
            except Exception:
                return False

    def _loop(self) -> None:
        while True:
            job_id = self.q.get()
            with self._proc_lock:
                self._queued.discard(job_id)
            try:
                if job_id in self._cancel_ids:
                    self._cancel_ids.discard(job_id)
                    job = self.store.get(job_id)
                    if job and job.get("status") in ("queued", "processing"):
                        self.store.update(
                            job_id,
                            status="error",
                            message="Cancelado",
                            reason="cancelled",
                        )
                    continue
                with self._proc_lock:
                    if job_id in self._busy:
                        continue
                from app.job_slots import acquire as acquire_slot
                from app.job_slots import release as release_slot

                if not acquire_slot(timeout=3600):
                    self.store.update(
                        job_id,
                        status="queued",
                        message="Na fila...",
                    )
                    self.enqueue(job_id)
                    continue
                try:
                    self._run_one(job_id)
                finally:
                    release_slot()
            except Exception as e:  # noqa: BLE001
                self.store.update(
                    job_id,
                    status="error",
                    message=friendly_error(str(e)),
                    reason="error",
                    detail=strip_ansi(str(e))[:2000],
                )
            finally:
                with self._proc_lock:
                    self._busy.discard(job_id)
                    self._procs.pop(job_id, None)
                    self.busy_id = next(iter(self._busy), None)
                    self._proc = self._procs.get(self.busy_id) if self.busy_id else None
                self.q.task_done()

    def _run_one(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if not job:
            return
        if job_id in self._cancel_ids:
            self._cancel_ids.discard(job_id)
            return
        with self._proc_lock:
            self._busy.add(job_id)
            self.busy_id = job_id
        self.store.update(
            job_id,
            status="processing",
            message="IA + edição…",
            phase=1,
            recovered=False,
        )

        source = Path(job["source"])
        edit_dir = Path(job["editDir"])
        edit_dir.mkdir(parents=True, exist_ok=True)
        preset_path = edit_dir / "preset-used.json"
        from app.preset_chain import resolve_for_edit

        try:
            save_preset_snap = resolve_for_edit(edit_dir, job=job, write=False)
        except Exception:
            save_preset_snap = load_preset()
        try:
            from app.editing_intent import load as load_intent, merge_into_preset

            save_preset_snap = merge_into_preset(save_preset_snap, load_intent(edit_dir))
        except Exception:
            pass
        from app.brand_kits import fill_end_card_copy

        save_preset_snap = fill_end_card_copy(save_preset_snap)
        preset_path.write_text(json.dumps(save_preset_snap, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env.update(load_env_keys())
        try:
            from app.win_process import child_env

            env = child_env(env)
        except Exception:
            try:
                from app.win_process import refresh_path_env

                env = refresh_path_env(env)
            except Exception:
                pass
        # helpers + repo (app.llm_session usado pelo plano de corte IA)
        # Dedupa PYTHONPATH também — jobs paralelos não podem inflar sem limite.
        py_parts = [str(HELPERS), str(REPO)]
        for p in (env.get("PYTHONPATH") or "").split(os.pathsep):
            p = p.strip()
            if p and p not in py_parts:
                py_parts.append(p)
        env["PYTHONPATH"] = os.pathsep.join(py_parts)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            from app.ffmpeg_tools import ensure_ffmpeg_on_path
            from app.win_process import dedupe_path

            vend = ensure_ffmpeg_on_path()
            if vend:
                env["PATH"] = dedupe_path(env.get("PATH", ""), prefer=[str(vend)])
        except Exception:
            pass
        try:
            from app.performance import profile_settings
            from app.settings_store import load_settings

            perf = profile_settings(load_settings().get("performanceProfile"))
            env["ATIVAVID_PROXY"] = "1" if perf.get("proxyEnabled") else "0"
            env["ATIVAVID_PROXY_HEIGHT"] = str(perf.get("proxyHeight") or 540)
            try:
                from app.render_engine import ensure_profile

                env["ATIVAVID_ENCODER"] = str(
                    (ensure_profile() or {}).get("recommendedEncoder")
                    or perf.get("encoder")
                    or "libx264"
                )
            except Exception:
                env["ATIVAVID_ENCODER"] = str(perf.get("encoder") or "libx264")
            env["ATIVAVID_EXTRACT_JOBS"] = str(perf.get("extractJobs") or 1)
            env["ATIVAVID_PARALLEL_JOBS"] = str(self.parallel_jobs)
            env["ATIVAVID_RENDER_SLOTS"] = str(max(1, int(perf.get("renderSlots") or 1)))
            env["ATIVAVID_REMOTION_LOCK"] = str(
                self.store.root / ".ativavid" / "remotion.lock"
            )
        except Exception:  # noqa: BLE001
            pass

        from app.win_process import hide_console_kwargs, resolve_python_cmd
        import tempfile

        # Nunca use PIPE sem drain: npm/ffmpeg enchem o buffer (~64KB) e no
        # Windows o filho morre com [Errno 22] Invalid argument na fase visuals.
        # Arquivos binários — text=True + file handle no Popen também gera Errno 22.
        out_fd, out_name = tempfile.mkstemp(suffix=".out", prefix=f"ativavid_job_{job_id}_")
        err_fd, err_name = tempfile.mkstemp(suffix=".err", prefix=f"ativavid_job_{job_id}_")
        out_path_tmp = Path(out_name)
        err_path_tmp = Path(err_name)

        popen_kwargs: dict = {
            "cwd": str(REPO),
            "stdout": out_fd,
            "stderr": err_fd,
            "env": env,
            **hide_console_kwargs(),
        }

        py_cmd = resolve_python_cmd(REPO)
        cmd = [
            *py_cmd,
            str(RUN_FAST),
            str(source),
            "--edit-dir", str(edit_dir),
            "--preset", str(preset_path),
            "--json",
        ]
        for extra in job.get("sources") or []:
            ep = Path(extra)
            if ep.exists() and ep.resolve() != source.resolve():
                cmd.extend(["--also", str(ep)])

        with self._proc_lock:
            try:
                proc = subprocess.Popen(cmd, **popen_kwargs)
            except FileNotFoundError as e:
                try:
                    os.close(out_fd)
                except OSError:
                    pass
                try:
                    os.close(err_fd)
                except OSError:
                    pass
                for p in (out_path_tmp, err_path_tmp):
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass
                self.store.update(
                    job_id,
                    status="error",
                    message="Instalação incompleta — falta Python/uv no PATH",
                    reason="error",
                    detail=(
                        f"{e}\nComando: {' '.join(cmd)}\n"
                        "Feche o ATIVAVID e rode de novo o instalador, "
                        "ou no PowerShell: winget install astral-sh.uv Gyan.FFmpeg OpenJS.NodeJS.LTS"
                    ),
                )
                return
            self._procs[job_id] = proc
            self._proc = proc

        returncode = proc.wait()
        # fds inherited by child; close our copies after wait
        try:
            os.close(out_fd)
        except OSError:
            pass
        try:
            os.close(err_fd)
        except OSError:
            pass
        try:
            stdout = out_path_tmp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stdout = ""
        try:
            stderr = err_path_tmp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            stderr = ""
        for p in (out_path_tmp, err_path_tmp):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

        if job_id in self._cancel_ids:
            self._cancel_ids.discard(job_id)
            self.store.update(
                job_id,
                status="error",
                message="Cancelado",
                reason="cancelled",
                detail="Cancelado pelo usuário",
            )
            return

        result: dict = {}
        # Prefer last JSON line on stdout
        for line in reversed((stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if not result and (edit_dir / "result.json").exists():
            try:
                result = json.loads((edit_dir / "result.json").read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                result = {}

        if returncode == 0 and result.get("status") in ("done", "cut_ready"):
            legenda = ""
            leg_path = edit_dir / "legenda.txt"
            if leg_path.exists():
                legenda = leg_path.read_text(encoding="utf-8-sig")
            delivery = resolve_delivery_mp4(edit_dir)
            self.store.update(
                job_id,
                status="done",
                message="Pronto",
                phase=3,
                final=str(delivery or result.get("final") or (edit_dir / "final.mp4")),
                legenda=legenda,
                durationSec=result.get("durationSec"),
                finishedAt=_utc(),
            )
            ensure_job_thumb(self.store.get(job_id) or job)
            return

        if returncode == 2 or result.get("status") == "needs_review":
            reason = result.get("reason") or "needs_review"
            detail = result.get("detail") or ""
            label = REASON_LABELS.get(reason, reason)
            self.store.update(
                job_id,
                status="needs_review",
                reason=reason,
                detail=detail,
                message=label,
                phase=0,
            )
            return

        err = result.get("error") or (stderr or stdout or "falha desconhecida")[-800:]
        err = strip_ansi(err)
        self.store.update(
            job_id,
            status="error",
            message=friendly_error(err),
            reason="error",
            detail=err[-4000:],
        )


# ---- HTTP ----

class StudioHandler(BaseHTTPRequestHandler):
    store: JobStore
    worker: Worker
    projects_root: Path

    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def log_request(self, code: object = "-", size: object = "-") -> None:  # noqa: ARG002
        return

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        """Write a full response without BaseHTTPRequestHandler.log_request.

        desktop_server builds a bare StudioHandler via __new__ (no parse of the
        request line), so send_response() → log_request() → self.requestline
        crashes. Avoid that path entirely.
        """
        if not hasattr(self, "protocol_version"):
            self.protocol_version = "HTTP/1.1"
        if not hasattr(self, "requestline"):
            self.requestline = f"{getattr(self, 'command', 'POST')} {getattr(self, 'path', '/')} HTTP/1.1"
        if not hasattr(self, "_headers_buffer"):
            self._headers_buffer = []
        # Manual status line + headers — never call send_response()/log_request().
        try:
            self.send_response_only(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            if body:
                self.wfile.write(body)
        except Exception:
            # Absolute last resort for a broken shim
            head = (
                f"HTTP/1.1 {code} OK\r\n"
                f"Content-Type: {ctype}\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Cache-Control: no-store\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii", "ignore")
            self.wfile.write(head + body)

    def _json(self, obj: object, code: int = 200) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, "application/json; charset=utf-8", raw)

    def _file(self, path: Path, ctype: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send(200, ctype, data)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/studio"):
            self._file(STUDIO / "index.html", "text/html; charset=utf-8")
            return
        # Mesmas rotas do desktop/preview: catálogo de Estilos no iframe do hub.
        if path in ("/estilo-padrao", "/estilo", "/fase1", "/fase2"):
            self._file(PREVIEW / "index.html", "text/html; charset=utf-8")
            return
        if path == "/api/state":
            preset = load_preset()
            self._json({
                "state": {
                    "project": "Estilo padrão da marca",
                    "phase": 1,
                    "message": "Escolha o visual padrão",
                    "fps": 30,
                    "awaitingStyle": True,
                    "style": preset,
                },
                "edl": None,
                "mtimes": {},
                "videoDuration": 0.0,
                "hasPendingEdits": False,
            })
            return
        if path.startswith("/assets/studio/"):
            rel = path[len("/assets/studio/"):]
            self._file(STUDIO / rel)
            return
        if path.startswith("/assets/"):
            # reuse preview brand assets (logo, app.css tokens)
            rel = path[len("/assets/"):]
            for base in (PREVIEW, STUDIO):
                cand = base / rel
                if cand.exists():
                    self._file(cand)
                    return
            self._json({"error": "not found"}, 404)
            return

        if path == "/api/health":
            keys = load_env_keys()
            from app.update_check import boot_fingerprint, running_version
            from app import license as lic

            self._json({
                "ok": True,
                "version": running_version(),
                "fingerprint": boot_fingerprint(),
                "projectsRoot": str(self.projects_root),
                "hasGroq": bool(keys.get("GROQ_API_KEY")),
                "hasElevenLabs": bool(keys.get("ELEVENLABS_API_KEY")),
                "busy": self.worker.busy_id,
                "queued": self.worker.q.qsize(),
                "license": lic.public_status(),
            })
            return
        if path == "/api/license":
            from app import license as lic

            self._json(lic.public_status())
            return
        if path == "/api/auth":
            from app import auth as au

            self._json(au.public_status())
            return
        if path == "/api/admin/licenses":
            from app import auth as au
            from app import license_admin as la

            st = au.require_admin()
            if not st.get("isAdmin"):
                self._json({"ok": False, "error": "forbidden", "message": "Login de admin necessário."}, 403)
                return
            self._json(la.list_licenses())
            return
        if path == "/api/admin/access":
            from app import auth as au
            from app import license_admin as la

            st = au.require_admin()
            if not st.get("isAdmin"):
                self._json({"ok": False, "error": "forbidden", "message": "Login de admin necessário."}, 403)
                return
            self._json(la.list_access())
            return
        if path == "/api/admin/devices":
            from app import auth as au
            from app import license_admin as la

            st = au.require_admin()
            if not st.get("isAdmin"):
                self._json({"ok": False, "error": "forbidden", "message": "Login de admin necessário."}, 403)
                return
            qs = parse_qs(urlparse(self.path).query)
            key = (qs.get("licenseKey") or qs.get("key") or [None])[0]
            self._json(la.list_devices(license_key=key))
            return
        if path == "/api/doutor":
            self._json(run_doutor())
            return
        if path == "/api/preset":
            self._json(load_preset())
            return
        if path == "/api/keys":
            keys = load_env_keys()
            self._json({
                "GROQ_API_KEY": bool(keys.get("GROQ_API_KEY")),
                "ELEVENLABS_API_KEY": bool(keys.get("ELEVENLABS_API_KEY")),
                "PEXELS_API_KEY": bool(keys.get("PEXELS_API_KEY")),
            })
            return
        if path == "/api/llm-proxy":
            self._json(load_llm_proxy())
            return
        if path == "/api/llm-gateway":
            from app import llm_gateway as gw

            self._json(gw.status())
            return
        if path in ("/v1/models", "/v1/models/"):
            from app import llm_gateway as gw

            code, payload = gw.list_models()
            self._json(payload, code)
            return
        if path == "/api/llm-proxy/models":
            from app.llm_proxy import list_models

            result = list_models()
            self._json(result, 200 if result.get("ok") else 502)
            return
        if path == "/api/llm-proxy/sessions":
            self._json({"providers": sessions_public()})
            return
        if path == "/api/jobs":
            jobs = self.store.list()
            for j in jobs:
                edit = Path(j["editDir"])
                j["hasCut"] = (edit / "cut.mp4").exists()
                j["hasFinal"] = resolve_delivery_mp4(edit) is not None
                j["hasThumb"] = (edit / "thumb.jpg").exists()
                j["thumbUrl"] = f"/api/jobs/{j['id']}/thumb"
                st_path = edit / "pipeline_status.json"
                if j.get("status") == "processing" and st_path.exists():
                    try:
                        st = json.loads(st_path.read_text(encoding="utf-8-sig"))
                        j["stage"] = st.get("stage") or "processing"
                        j["progress"] = st.get("progress")
                        if st.get("message"):
                            j["message"] = st["message"]
                    except (OSError, json.JSONDecodeError):
                        j["stage"] = "processing"
                else:
                    j["stage"] = j.get("status")
                j["stageLabel"] = STAGE_LABELS.get(str(j.get("stage") or ""), j.get("message") or "")
                score_path = edit / "score.json"
                if score_path.exists():
                    try:
                        j["score"] = json.loads(score_path.read_text(encoding="utf-8-sig"))
                    except (OSError, json.JSONDecodeError):
                        pass
                enrich_job_display(j, edit)
            from app.eta_estimate import attach_eta, collect_history

            hist = collect_history(self.projects_root)
            for j in jobs:
                attach_eta(j, hist, Path(j["editDir"]))
            try:
                from app.apply_tasks import enrich_jobs_list

                enrich_jobs_list(jobs, self.projects_root)
            except Exception:
                pass
            self._json({"jobs": jobs, "busy": self.worker.busy_id})
            return
        if path == "/api/content-types":
            from app.content_type import choices

            self._json({"ok": True, "items": choices()})
            return
        if path == "/api/brand-presets":
            from app.brand_presets import get_active, load as load_presets

            q = parse_qs(urlparse(self.path).query)
            brand_id = (q.get("brandId") or [""])[0].strip()
            if not brand_id:
                from app.brand_kits import list_brands

                brands = list_brands()
                active = next((b for b in brands if b.get("active")), brands[0] if brands else None)
                brand_id = str((active or {}).get("id") or "padrao")
            pack = load_presets(brand_id)
            self._json({"ok": True, **pack, "active": get_active(brand_id)})
            return
        if path == "/api/system":
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

            from app.system_info import detect_machine, _minimal_machine
            from app.performance import profile_settings
            from app.settings_store import load_settings, public_settings

            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(detect_machine, self.projects_root, quick=True)
                    try:
                        m = fut.result(timeout=5.0)
                    except FutTimeout:
                        m = _minimal_machine(
                            self.projects_root,
                            err="detecção demorou — veja Diagnóstico abaixo",
                        )
            except Exception as e:  # noqa: BLE001
                m = _minimal_machine(self.projects_root, err=str(e)[:240])
            try:
                s = load_settings()
                pub = public_settings()
            except Exception:
                s = {}
                pub = {}
            try:
                perf = profile_settings(s.get("performanceProfile") if s else None, m)
            except Exception:
                perf = {
                    "profile": "auto",
                    "label": "Automático",
                    "parallelJobs": 1,
                    "proxyEnabled": True,
                    "proxyHeight": 540,
                }
            self._json({
                "machine": m,
                "settings": pub,
                "performance": perf,
            })
            return
        if path == "/api/settings":
            from app.settings_store import public_settings
            self._json(public_settings())
            return
        if path == "/api/cache":
            sys.path.insert(0, str(HELPERS))
            from cache_cleanup import measure_cache  # type: ignore
            self._json(measure_cache(self.projects_root))
            return
        if path == "/api/recovery":
            ids = list(getattr(self.worker, "recovered_ids", []) or [])
            jobs = [j for j in (self.store.get(i) for i in ids) if j]
            # one-shot: UI já viu
            try:
                self.worker.recovered_ids = []
            except Exception:
                pass
            self._json({"recovered": jobs, "ids": [j["id"] for j in jobs]})
            return
        if path == "/api/update/check":
            from app.settings_store import load_settings
            from app.update_check import check_update
            s = load_settings()
            result = check_update(channel=str(s.get("updateChannel") or "stable"))
            result["enabled"] = True
            result["githubRepo"] = result.get("githubRepo") or s.get("githubRepo") or ""
            self._json(result)
            return
        if path == "/api/brands":
            from app.brand_kits import list_brands, list_export_presets, get_active_id
            self._json({
                "brands": list_brands(),
                "activeId": get_active_id(),
                "exportPresets": list_export_presets(),
            })
            return
        if path == "/api/library":
            from app.broll_library import list_assets
            self._json(list_assets(self.projects_root))
            return
        if path == "/api/library/file":
            from app.broll_library import library_root
            from urllib.parse import unquote
            qs = parse_qs(urlparse(self.path).query)
            rel = unquote((qs.get("rel") or [""])[0]).replace("\\", "/").lstrip("/")
            if not rel or ".." in rel.split("/"):
                self._json({"error": "rel inválido"}, 400)
                return
            root = library_root(self.projects_root).resolve()
            target = (root / rel).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                self._json({"error": "fora da biblioteca"}, 403)
                return
            if not target.is_file():
                self._json({"error": "não encontrado"}, 404)
                return
            self._file(target)
            return
        if path == "/api/doutor/copy":
            data = run_doutor()
            lines = ["ATIVAVID — diagnóstico (sem chaves/cookies)", ""]
            for it in data.get("itens") or []:
                lines.append(f"[{it.get('nivel')}] {it.get('titulo')}")
                if it.get("detalhe"):
                    lines.append(f"  {it['detalhe']}")
            self._json({"ok": True, "text": "\n".join(lines)})
            return
        if path.startswith("/api/jobs/"):
            parts = path.strip("/").split("/")
            # /api/jobs/<id> or /api/jobs/<id>/legenda or /api/jobs/<id>/final
            if len(parts) >= 3:
                job_id = parts[2]
                job = self.store.get(job_id)
                if not job:
                    self._json({"error": "job not found"}, 404)
                    return
                if len(parts) == 3:
                    self._json(job)
                    return
                action = parts[3]
                edit = Path(job["editDir"])
                if action == "thumb":
                    thumb = ensure_job_thumb(job)
                    if not thumb:
                        self._json({"error": "sem preview"}, 404)
                        return
                    self._file(thumb, "image/jpeg")
                    return
                if action == "final":
                    final = resolve_delivery_mp4(edit)
                    if not final:
                        self._json({"error": "sem vídeo final"}, 404)
                        return
                    self._file(final, "video/mp4")
                    return
                if action == "legenda":
                    leg = edit / "legenda.txt"
                    if not leg.exists():
                        self._json({"error": "sem legenda"}, 404)
                        return
                    self._file(leg, "text/plain; charset=utf-8")
                    return
            self._json({"error": "not found"}, 404)
            return

        self._json({"error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/preset":
            body = self._read_json()
            if not body:
                self._json({"error": "preset vazio"}, 400)
                return
            save_preset(body)
            self._json({"ok": True, "preset": load_preset()})
            return

        if path == "/api/default-style":
            body = self._read_json()
            if not body:
                self._json({"error": "estilo vazio"}, 400)
                return
            save_preset(body)
            self._json({"ok": True, "preset": load_preset()})
            return

        if path == "/api/keys":
            body = self._read_json() or {}
            allowed = {k: body[k] for k in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "PEXELS_API_KEY") if k in body}
            try:
                save_env_keys(allowed)
            except OSError as e:
                self._json({"ok": False, "error": str(e)}, 500)
                return
            self._json({"ok": True, "keys": {
                "GROQ_API_KEY": bool(load_env_keys().get("GROQ_API_KEY")),
                "ELEVENLABS_API_KEY": bool(load_env_keys().get("ELEVENLABS_API_KEY")),
                "PEXELS_API_KEY": bool(load_env_keys().get("PEXELS_API_KEY")),
            }})
            return

        if path == "/api/keys/test":
            body = self._read_json() or {}
            which = (body.get("service") or "").strip().lower()
            # Aceita chave no body (salva antes) — Testar sem depender de Salvar antes
            patch: dict[str, str] = {}
            if body.get("GROQ_API_KEY"):
                patch["GROQ_API_KEY"] = str(body["GROQ_API_KEY"])
            if body.get("ELEVENLABS_API_KEY"):
                patch["ELEVENLABS_API_KEY"] = str(body["ELEVENLABS_API_KEY"])
            if body.get("PEXELS_API_KEY"):
                patch["PEXELS_API_KEY"] = str(body["PEXELS_API_KEY"])
            if patch:
                try:
                    save_env_keys(patch)
                except OSError as e:
                    self._json({"ok": False, "error": str(e)}, 500)
                    return
            keys = load_env_keys()
            if which == "groq":
                key = keys.get("GROQ_API_KEY") or ""
                if not key:
                    self._json({"ok": False, "error": "GROQ_API_KEY ausente — cole a chave e salve."}, 400)
                    return
                try:
                    import requests
                    r = requests.get(
                        "https://api.groq.com/openai/v1/models",
                        headers={"Authorization": f"Bearer {key}"},
                        timeout=12,
                    )
                    self._json({"ok": r.status_code < 400, "status": r.status_code})
                except Exception as e:  # noqa: BLE001
                    self._json({"ok": False, "error": str(e)[:120]}, 502)
                return
            if which == "pexels":
                key = keys.get("PEXELS_API_KEY") or ""
                if not key:
                    self._json({"ok": False, "error": "PEXELS_API_KEY ausente — cole a chave e salve."}, 400)
                    return
                try:
                    import requests
                    r = requests.get(
                        "https://api.pexels.com/v1/search",
                        params={"query": "phone", "per_page": 1},
                        headers={"Authorization": key},
                        timeout=12,
                    )
                    self._json({"ok": r.status_code < 400, "status": r.status_code})
                except Exception as e:  # noqa: BLE001
                    self._json({"ok": False, "error": str(e)[:120]}, 502)
                return
            if which == "elevenlabs":
                key = keys.get("ELEVENLABS_API_KEY") or ""
                if not key:
                    self._json({"ok": False, "error": "ELEVENLABS_API_KEY ausente — cole a chave e salve."}, 400)
                    return
                try:
                    import requests
                    r = requests.get(
                        "https://api.elevenlabs.io/v1/user",
                        headers={"xi-api-key": key},
                        timeout=12,
                    )
                    self._json({"ok": r.status_code < 400, "status": r.status_code})
                except Exception as e:  # noqa: BLE001
                    self._json({"ok": False, "error": str(e)[:120]}, 502)
                return
            self._json({"error": "service inválido"}, 400)
            return

        if path == "/api/settings":
            from app.settings_store import public_settings, save_settings
            body = self._read_json() or {}
            try:
                save_settings(body)
                self._json({"ok": True, "settings": public_settings()})
            except OSError as e:
                self._json({"ok": False, "error": str(e)}, 500)
            return

        if path == "/api/auth/login":
            from app import auth as au

            body = self._read_json() or {}
            result = au.login(str(body.get("email") or ""), str(body.get("password") or ""))
            self._json(result, 200 if result.get("ok") else 401)
            return

        if path == "/api/auth/signup":
            from app import auth as au

            body = self._read_json() or {}
            result = au.signup(str(body.get("email") or ""), str(body.get("password") or ""))
            self._json(result, 200 if result.get("ok") else 400)
            return

        if path == "/api/auth/logout":
            from app import auth as au

            self._json(au.logout())
            return

        if path == "/api/admin/access":
            from app import auth as au
            from app import license_admin as la

            st = au.require_admin()
            if not st.get("isAdmin"):
                self._json({"ok": False, "error": "forbidden", "message": "Login de admin necessário."}, 403)
                return
            body = self._read_json() or {}
            action = str(body.get("action") or "grant").strip().lower()
            if action in ("create", "create_account", "provision"):
                self._json(
                    la.create_account_and_grant(
                        email=str(body.get("email") or ""),
                        password=str(body.get("password") or "") or None,
                        days=int(body.get("days") or 7),
                        max_devices=int(body.get("maxDevices") or body.get("max_devices") or 1),
                        notes=str(body.get("notes") or "") or None,
                    )
                )
                return
            if action == "grant":
                self._json(
                    la.grant_access(
                        email=str(body.get("email") or ""),
                        days=int(body.get("days") or 7),
                        max_devices=int(body.get("maxDevices") or body.get("max_devices") or 1),
                        notes=str(body.get("notes") or "") or None,
                    )
                )
                return
            if action == "revoke":
                self._json(la.revoke_access(email=str(body.get("email") or "")))
                return
            if action == "list":
                self._json(la.list_access())
                return
            self._json({"ok": False, "error": "unknown_action"}, 400)
            return

        if path == "/api/admin/licenses":
            from app import auth as au
            from app import license_admin as la

            st = au.require_admin()
            if not st.get("isAdmin"):
                self._json({"ok": False, "error": "forbidden", "message": "Login de admin necessário."}, 403)
                return
            body = self._read_json() or {}
            self._json(
                la.create_license(
                    email=str(body.get("email") or "") or None,
                    days=int(body.get("days") or 365),
                    max_devices=int(body.get("maxDevices") or body.get("max_devices") or 1),
                    notes=str(body.get("notes") or "") or None,
                )
            )
            return

        if path == "/api/admin/devices":
            from app import auth as au
            from app import license_admin as la

            st = au.require_admin()
            if not st.get("isAdmin"):
                self._json({"ok": False, "error": "forbidden", "message": "Login de admin necessário."}, 403)
                return
            body = self._read_json() or {}
            action = str(body.get("action") or "release").strip().lower()
            if action == "release":
                self._json(la.release_device(str(body.get("deviceId") or body.get("device_id") or "")))
                return
            self._json({"ok": False, "error": "unknown_action"}, 400)
            return

        if path == "/api/license/refresh":
            from app import license as lic

            lic.entitlement(refresh=True)
            self._json(lic.public_status())
            return

        if path == "/api/license/activate":
            from app import license as lic

            body = self._read_json() or {}
            key = str(body.get("key") or "").strip()
            if not key:
                self._json({"ok": False, "error": "key_required", "message": "Informe a chave."}, 400)
                return
            result = lic.activate(key)
            # UI espera o mesmo shape de /api/license (mode, message, trialDays…)
            out = lic.public_status()
            out["ok"] = bool(result.get("entitled") or result.get("ok"))
            if result.get("message") and not out.get("entitled"):
                out["message"] = result.get("message")
            self._json(out, 200 if out.get("entitled") else 403)
            return

        if path == "/api/cache/clear":
            sys.path.insert(0, str(HELPERS))
            from cache_cleanup import clear_cache  # type: ignore
            self._json(clear_cache(self.projects_root, keep_graded=True))
            return

        if path == "/api/probe":
            from app.media_probe import probe_video
            body = self._read_json() or {}
            p = Path(str(body.get("path") or ""))
            # only allow under projects root
            try:
                p = p.resolve()
                root = self.projects_root.resolve()
                if root not in p.parents and p != root:
                    self._json({"ok": False, "error": "caminho fora dos projetos"}, 400)
                    return
            except OSError:
                self._json({"ok": False, "error": "caminho inválido"}, 400)
                return
            self._json(probe_video(p))
            return

        if path == "/api/ai-edit":
            from app.ai_actions import (
                apply_actions_to_edits,
                format_apply_log,
                is_apply_confirmation,
                make_pending_edit,
                operations_from_patch,
                pending_is_stale,
                plan_from_prompt,
            )
            from app.broll_library import resolve_query_to_public
            body = self._read_json() or {}
            mode = str(body.get("mode") or "plan").strip().lower()
            if mode == "apply":
                ops = body.get("operations") or []
                if not isinstance(ops, list):
                    ops = []
                pending = body.get("pendingEdit") or {}
                folder = (body.get("folder") or "").strip()
                ranges = body.get("currentRanges")
                if pending and ranges is not None and pending_is_stale(
                    pending, project_id=folder, ranges=ranges,
                ):
                    print("PENDING_EDIT_STALE", flush=True)
                    self._json({
                        "ok": False,
                        "stale": True,
                        "error": "PENDING_EDIT_STALE",
                        "applied": False,
                    }, 409)
                    return
                prot = body.get("protectedRanges")
                if prot is None and folder:
                    for j in self.store.list():
                        if Path(j.get("projectDir", "")).name == folder:
                            ip = Path(j["editDir"]) / "job_intent.json"
                            if ip.exists():
                                try:
                                    prot = json.loads(ip.read_text(encoding="utf-8-sig")).get("protectedRanges")
                                except (OSError, json.JSONDecodeError):
                                    prot = None
                            break
                if prot:
                    from app.protected_ranges import filter_ai_ops, format_blocked_log

                    filtered = filter_ai_ops(ops, prot)
                    ops = filtered["kept"]
                    if filtered["blocked"]:
                        for line in format_blocked_log(filtered["blocked"]):
                            print(line, flush=True)
                lines = format_apply_log(ops)
                for line in lines:
                    print(line, flush=True)
                reps = []
                for op in ops:
                    if isinstance(op, dict) and str(op.get("op") or "") == "fix_captions":
                        reps.extend(op.get("replacements") or [])
                if reps:
                    job_edit = None
                    if folder:
                        for j in self.store.list():
                            if Path(j.get("projectDir", "")).name == folder:
                                job_edit = Path(j["editDir"])
                                break
                    if job_edit is None and body.get("editDir"):
                        job_edit = Path(str(body["editDir"]))
                    if job_edit is not None:
                        try:
                            from app.caption_fixes import apply_caption_fixes

                            apply_caption_fixes(job_edit, reps)
                        except Exception as e:
                            print(f"[warn] captionFixes apply: {e}", flush=True)
                self._json({"ok": True, "applied": True, "pendingEdit": False, "log": lines})
                return
            prompt = (body.get("prompt") or "").strip()
            if is_apply_confirmation(prompt):
                self._json({
                    "ok": True,
                    "confirm": True,
                    "hasPendingEdit": False,
                    "operations": [],
                    "summary": "CONFIRMAÇÃO — aplique a alteração pendente no editor.",
                    "actions": [],
                    "patch": {},
                })
                return
            if len(prompt) < 3:
                self._json({"error": "pedido vazio"}, 400)
                return
            try:
                dur = body.get("durationSec")
                src_dur = body.get("sourceDurationSec")
                try:
                    dur_f = float(dur) if dur is not None else None
                except (TypeError, ValueError):
                    dur_f = None
                try:
                    src_f = float(src_dur) if src_dur is not None else None
                except (TypeError, ValueError):
                    src_f = None
                folder = (body.get("folder") or "").strip()
                job_edit = None
                if folder:
                    for j in self.store.list():
                        if Path(j.get("projectDir", "")).name == folder:
                            job_edit = Path(j["editDir"])
                            break
                if job_edit is None and body.get("editDir"):
                    job_edit = Path(str(body["editDir"]))
                if src_f is None and job_edit is not None:
                    edl_path = job_edit / "edl.json"
                    if edl_path.exists():
                        try:
                            edl = json.loads(edl_path.read_text(encoding="utf-8-sig"))
                            ends = [
                                float(r.get("end") or 0)
                                for r in (edl.get("ranges") or [])
                                if isinstance(r, dict)
                            ]
                            if ends:
                                src_f = max(src_f or 0.0, max(ends))
                            intent_p = job_edit / "job_intent.json"
                            if intent_p.exists():
                                intent = json.loads(intent_p.read_text(encoding="utf-8-sig"))
                                listed = intent.get("sourceDurationSec")
                                if listed:
                                    src_f = max(src_f or 0.0, float(listed))
                        except (OSError, json.JSONDecodeError, TypeError, ValueError):
                            pass
                actions, summary, backend = plan_from_prompt(
                    prompt,
                    duration=dur_f,
                    source_duration=src_f,
                    current_ranges=body.get("currentRanges"),
                )
                prot = body.get("protectedRanges")
                if prot is None and job_edit is not None:
                    ip = job_edit / "job_intent.json"
                    if ip.exists():
                        try:
                            prot = json.loads(ip.read_text(encoding="utf-8-sig")).get("protectedRanges")
                        except (OSError, json.JSONDecodeError):
                            prot = None
                patch = apply_actions_to_edits(
                    actions,
                    style=body.get("style"),
                    edit_data=body.get("editData"),
                    notes=body.get("notes"),
                    duration=src_f or dur_f,
                    protected_ranges=prot,
                )
                # Resolver add_broll_hint → arquivo real em remotion/public
                public = None
                if folder:
                    for j in self.store.list():
                        if Path(j.get("projectDir", "")).name == folder:
                            public = Path(j["editDir"]) / "remotion" / "public"
                            break
                if public is None and body.get("editDir"):
                    public = Path(str(body["editDir"])) / "remotion" / "public"
                if public is not None:
                    public.mkdir(parents=True, exist_ok=True)
                    ed = dict(patch.get("editData") or {})
                    style_patch = dict(patch.get("style") or body.get("style") or {})
                    edit_style = (style_patch.get("edit") or "limpa").lower().strip()
                    inserts = list(ed.get("inserts") or [])
                    # Limpa: não materializa B-roll automático em card/overlay
                    if edit_style in ("limpa", "clean", "limpo"):
                        cleaned = [it for it in inserts if it.get("src") and not it.get("hint") and not it.get("auto")]
                        if len(cleaned) != len(inserts):
                            ed["inserts"] = cleaned
                            patch["editData"] = ed
                    else:
                        changed = False
                        for it in inserts:
                            if not it.get("hint") and it.get("src"):
                                continue
                            q = (it.get("query") or "").strip()
                            if not q:
                                continue
                            resolved = resolve_query_to_public(
                                q, public, projects_root=self.projects_root
                            )
                            if resolved and resolved.get("src"):
                                it["src"] = resolved["src"]
                                it["credit"] = resolved.get("credit") or ""
                                it["hint"] = False
                                it.pop("query", None)
                                changed = True
                        if changed:
                            ed["inserts"] = inserts
                            patch["editData"] = ed
                ops = operations_from_patch(patch, actions)
                pending = make_pending_edit(
                    project_id=folder,
                    ranges=body.get("currentRanges"),
                    operations=ops,
                    actions=actions,
                    patch=patch,
                    summary=summary,
                )
                self._json({
                    "ok": True,
                    "summary": summary,
                    "backend": backend,
                    "actions": actions,
                    "patch": patch,
                    "hasPendingEdit": bool(ops),
                    "operations": ops,
                    "pendingEdit": pending,
                    "applied": False,
                })
            except Exception as e:  # noqa: BLE001
                from app.llm_session import friendly_llm_error
                self._json({"ok": False, "error": friendly_llm_error(e), "needsSession": True}, 502)
            return

        if path == "/api/update/open":
            from app.update_check import check_update, open_setup, open_url
            body = self._read_json() or {}
            action = (body.get("action") or "release").strip().lower()
            if action == "setup":
                self._json(open_setup())
                return
            url = (body.get("url") or "").strip()
            if not url:
                info = check_update()
                url = (
                    str(info.get("downloadUrl") or "").strip()
                    or str(info.get("releaseUrl") or "").strip()
                )
            if not url:
                self._json(open_setup())
                return
            self._json(open_url(url))
            return

        if path == "/api/brand-presets":
            from app.brand_presets import (
                create as create_preset,
                delete as delete_preset,
                duplicate as dup_preset,
                load as load_presets,
                rename as rename_preset,
                set_default,
                update_style,
            )
            body = self._read_json() or {}
            brand_id = str(body.get("brandId") or "padrao")
            action = str(body.get("action") or "create").strip().lower()
            try:
                if action == "create":
                    pack = create_preset(
                        brand_id,
                        str(body.get("name") or "Preset"),
                        style=body.get("style"),
                        content_type=body.get("contentType"),
                        brand_name=str(body.get("brandName") or ""),
                    )
                elif action == "duplicate":
                    pack = dup_preset(brand_id, str(body.get("id") or ""), str(body.get("name") or "Cópia"))
                elif action == "rename":
                    pack = rename_preset(brand_id, str(body.get("id") or ""), str(body.get("name") or ""))
                elif action == "delete":
                    pack = delete_preset(brand_id, str(body.get("id") or ""))
                elif action == "default":
                    pack = set_default(brand_id, str(body.get("id") or ""))
                elif action == "update":
                    pack = update_style(brand_id, str(body.get("id") or ""), dict(body.get("style") or {}))
                else:
                    pack = load_presets(brand_id)
                self._json({"ok": True, **pack})
            except ValueError as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return

        if path == "/api/brands":
            from app.brand_kits import activate_brand, save_brand
            body = self._read_json() or {}
            action = (body.get("action") or "save").strip().lower()
            try:
                if action == "activate":
                    self._json(activate_brand(str(body.get("id") or "")))
                else:
                    saved = save_brand(body)
                    if body.get("activate"):
                        activate_brand(saved["brandId"])
                    self._json({"ok": True, "brand": saved})
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            except OSError as e:
                self._json({"error": f"Não consegui gravar a marca: {e}"}, 500)
            return

        if path == "/api/library/add":
            from app.broll_library import add_file
            body = self._read_json() or {}
            try:
                self._json(add_file(
                    Path(str(body.get("path") or "")),
                    kind=str(body.get("kind") or "image"),
                    projects_root=self.projects_root,
                ))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            return

        if path == "/api/library/use":
            from app.broll_library import copy_into_public
            body = self._read_json() or {}
            src = Path(str(body.get("path") or ""))
            public = None
            folder = (body.get("folder") or "").strip()
            if folder:
                for j in self.store.list():
                    if Path(j.get("projectDir", "")).name == folder:
                        public = Path(j["editDir"]) / "remotion" / "public"
                        break
            if public is None and body.get("editDir"):
                public = Path(str(body["editDir"])) / "remotion" / "public"
            if public is None:
                self._json({"error": "projeto não encontrado"}, 404)
                return
            try:
                self._json(copy_into_public(src, public))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            return

        if path == "/api/library/upload":
            from app.broll_library import add_bytes, copy_into_public
            # multipart: field "file"; optional query ?use=1&folder=
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                self._json({"error": "envie multipart/form-data"}, 400)
                return
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            if "boundary=" not in ctype:
                self._json({"error": "boundary ausente"}, 400)
                return
            mime = b"Content-Type: " + ctype.encode("ascii", "ignore") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
            from email.parser import BytesParser
            from email import policy as email_policy
            msg = BytesParser(policy=email_policy.default).parsebytes(mime)
            saved = None
            for part in msg.iter_parts():
                filename = part.get_filename()
                if not filename:
                    continue
                payload = part.get_payload(decode=True) or b""
                try:
                    saved = add_bytes(filename, payload, projects_root=self.projects_root)
                except ValueError as e:
                    self._json({"error": str(e)}, 400)
                    return
                break
            if not saved:
                self._json({"error": "nenhum arquivo"}, 400)
                return
            qs = parse_qs(urlparse(self.path).query)
            use = (qs.get("use") or ["0"])[0] == "1"
            folder = (qs.get("folder") or [""])[0]
            if use and folder:
                public = None
                for j in self.store.list():
                    if Path(j.get("projectDir", "")).name == folder:
                        public = Path(j["editDir"]) / "remotion" / "public"
                        break
                if public is not None:
                    try:
                        used = copy_into_public(Path(saved["path"]), public)
                        saved["used"] = used
                    except ValueError:
                        pass
            self._json(saved)
            return

        if path == "/api/proxy/rebuild":
            body = self._read_json() or {}
            folder = (body.get("folder") or "").strip()
            edit = None
            if folder:
                for j in self.store.list():
                    if Path(j.get("projectDir", "")).name == folder:
                        edit = Path(j["editDir"])
                        break
            if edit is None and body.get("editDir"):
                edit = Path(str(body["editDir"]))
            if edit is None or not (edit / "cut.mp4").exists():
                self._json({"ok": False, "error": "cut.mp4 não encontrado"}, 404)
                return
            sys.path.insert(0, str(HELPERS))
            from make_proxy import make_cut_proxy  # type: ignore
            from app.performance import profile_settings
            from app.settings_store import load_settings
            perf = profile_settings(load_settings().get("performanceProfile"))
            out = make_cut_proxy(
                edit / "cut.mp4",
                edit / "cut_proxy.mp4",
                height=int(perf.get("proxyHeight") or 540),
                encoder=str(perf.get("encoder") or "libx264"),
            )
            self._json({"ok": bool(out), "proxy": str(out) if out else None})
            return

        if path == "/api/open-path":
            body = self._read_json() or {}
            target = Path(str(body.get("path") or "")).expanduser()
            try:
                target = target.resolve()
                allowed = [
                    self.projects_root.resolve(),
                    (Path.home() / "ATIVAVID").resolve(),
                ]
                ok = any(a == target or a in target.parents for a in allowed)
                if not ok or not target.exists():
                    self._json({"error": "caminho não permitido"}, 400)
                    return
            except OSError:
                self._json({"error": "caminho inválido"}, 400)
                return
            folder = target if target.is_dir() else target.parent
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
            self._json({"ok": True, "path": str(folder)})
            return

        if path == "/api/llm-proxy":
            body = self._read_json() or {}
            self._json({"ok": True, "config": save_llm_proxy(body)})
            return

        if path in ("/v1/chat/completions", "/v1/chat/completions/"):
            from app import llm_gateway as gw

            body = self._read_json() or {}
            code, payload = gw.chat_completions(body if isinstance(body, dict) else {})
            self._json(payload, code)
            return

        if path == "/api/llm-proxy/test":
            from app.llm_proxy import chat_ping, test_connection

            body = self._read_json() or {}
            # allow testing unsaved form values
            base = (body.get("baseUrl") or "").strip() or None
            key = (body.get("apiKey") or "").strip() or None
            if base or key:
                # temporarily not writing — pass through
                result = test_connection(base=base, api_key=key)
            else:
                result = test_connection()
            if result.get("ok") and body.get("chat"):
                ping = chat_ping(body.get("model") or None)
                result["chat"] = ping
            self._json(result, 200 if result.get("ok") else 502)
            return

        if path == "/api/llm-proxy/capture":
            # Browser extension posts cookies for the user's own web session
            body = self._read_json() or {}
            provider = (body.get("provider") or "").strip()
            cookies = body.get("cookies") or []
            try:
                saved = save_session_capture(provider, cookies, meta=body.get("meta"))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            self._json(saved)
            return

        if path == "/api/llm-proxy/open-extension":
            from app.extension_sync import extension_dir

            folder = extension_dir()
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
            self._json({"ok": True, "path": str(folder)})
            return

        if path == "/api/jobs/open-folder":
            body = self._read_json()
            job = self.store.get(body.get("id", ""))
            if not job:
                self._json({"error": "job not found"}, 404)
                return
            edit = Path(job.get("editDir") or "")
            target = None
            if edit:
                try:
                    from app.delivery_pack import folder_to_open

                    packed = folder_to_open(edit)
                    if packed.is_dir():
                        target = packed
                except Exception:
                    target = None
            if target is None:
                target = resolve_delivery_mp4(edit) if edit else None
            if not target:
                raw = Path(job.get("final") or job.get("editDir") or "")
                target = raw if raw.exists() else edit
            folder = target if target.is_dir() else target.parent
            if sys.platform == "win32":
                if target.is_file():
                    subprocess.Popen(f'explorer /select,"{target}"')
                else:
                    subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
            self._json({"ok": True, "path": str(target)})
            return

        if path == "/api/jobs/open-final":
            body = self._read_json() or {}
            job = self.store.get(body.get("id", ""))
            if not job:
                self._json({"error": "job not found"}, 404)
                return
            edit = Path(job.get("editDir") or "")
            target = resolve_delivery_mp4(edit) if edit else None
            if not target or not target.is_file():
                raw = Path(job.get("final") or "")
                target = raw if raw.is_file() else None
            if not target:
                self._json({"error": "sem vídeo final"}, 404)
                return
            try:
                if sys.platform == "win32":
                    os.startfile(str(target))  # noqa: S606
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(target)])
                else:
                    subprocess.Popen(["xdg-open", str(target)])
            except OSError as e:
                self._json({"error": str(e)}, 500)
                return
            self._json({"ok": True, "path": str(target)})
            return

        if path == "/api/apply-ack":
            body = self._read_json() or {}
            try:
                from app.apply_tasks import acknowledge_task

                view = acknowledge_task(
                    self.projects_root,
                    task_id=str(body.get("taskId") or ""),
                    project_id=str(body.get("projectId") or ""),
                )
            except Exception as e:
                self._json({"ok": False, "error": str(e)[:160]}, 500)
                return
            self._json({"ok": True, "quickApply": view})
            return

        if path == "/api/jobs/rename":
            body = self._read_json() or {}
            job = self.store.get(body.get("id", ""))
            if not job:
                self._json({"error": "job not found"}, 404)
                return
            title = re.sub(r"\s+", " ", str(body.get("title") or "").strip())
            if not title:
                self._json({"error": "título vazio"}, 400)
                return
            if len(title) > 80:
                title = title[:80]
            updated = self.store.update(
                job["id"],
                title=title,
                titleLocked=True,
                updatedAt=_utc(),
            )
            self._json({"ok": True, "job": updated})
            return

        if path == "/api/jobs/retry":
            from app import license as lic

            st = lic.entitlement()
            if not st.get("entitled"):
                self._json({"error": lic.deny_reason(st), "license": lic.public_status()}, 403)
                return
            body = self._read_json()
            job = self.store.get(body.get("id", ""))
            if not job:
                self._json({"error": "job not found"}, 404)
                return
            # Se estava editando/na fila, cancela o processo atual antes de reenfileirar
            if self.worker.busy_id == job["id"] or job.get("status") == "processing":
                self.worker.cancel(job["id"])
            self.store.update(job["id"], status="queued", message="Na fila", reason=None, detail=None)
            self.worker.enqueue(job["id"])
            self._json({"ok": True})
            return

        if path == "/api/jobs/cancel":
            body = self._read_json() or {}
            job_id = body.get("id", "")
            job = self.store.get(job_id)
            if not job:
                self._json({"error": "job not found"}, 404)
                return
            self._json(self.worker.cancel(job_id))
            return

        if path == "/api/jobs/append-cta":
            from app import license as lic
            from app.append_source import append_cta

            st = lic.entitlement()
            if not st.get("entitled"):
                self._json({"error": lic.deny_reason(st), "license": lic.public_status()}, 403)
                return
            try:
                self._json(self._append_cta_job(parsed))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"Não deu para acrescentar esse vídeo ({e})"}, 500)
            return

        if path == "/api/jobs/requeue-folder":
            from app import license as lic
            from app.append_source import merge_source_paths

            st = lic.entitlement()
            if not st.get("entitled"):
                self._json({"error": lic.deny_reason(st), "license": lic.public_status()}, 403)
                return
            # Editor Estilo tab → apply saved style and put this project back in queue
            body = self._read_json() or {}
            folder = (body.get("folder") or "").strip().strip("/\\")
            if not folder or "/" in folder or "\\" in folder or folder in (".", ".."):
                self._json({"error": "pasta inválida"}, 400)
                return
            job = None
            for j in self.store.list():
                if Path(j.get("projectDir", "")).name == folder:
                    job = j
                    break
            if not job:
                self._json({"error": "projeto não está na fila"}, 404)
                return
            extras = list(body.get("extraSources") or [])
            edits_p = Path(job.get("editDir") or "") / "preview_edits.json"
            if edits_p.exists():
                try:
                    extras.extend((json.loads(edits_p.read_text(encoding="utf-8-sig")).get("extraSources") or []))
                except (OSError, json.JSONDecodeError, TypeError):
                    pass
            existing = list(job.get("sources") or [])
            if job.get("source") and job["source"] not in existing:
                existing.insert(0, job["source"])
            merged = merge_source_paths(existing, extras, Path(job["projectDir"]))
            if self.worker.busy_id == job["id"] or job.get("status") == "processing":
                self.worker.cancel(job["id"])
            self.store.update(
                job["id"],
                sources=merged or existing,
                status="queued",
                message="Na fila — aplicando ajustes",
                reason=None,
                detail=None,
            )
            self.worker.enqueue(job["id"])
            self._json({"ok": True, "id": job["id"]})
            return

        if path == "/api/jobs/delete":
            body = self._read_json()
            job_id = (body or {}).get("id", "")
            job = self.store.get(job_id)
            if not job:
                self._json({"error": "job not found"}, 404)
                return
            # Sempre permite apagar: cancela edição presa antes de remover
            if self.worker.busy_id == job_id or job.get("status") in ("processing", "queued"):
                self.worker.cancel(job_id)
            removed = self.store.delete(job_id)
            deleted_files = False
            proj = Path(removed["projectDir"]).resolve() if removed else None
            root = self.projects_root.resolve()
            from app.recycle import RecycleError, is_safe_project_dir, send_to_recycle_bin

            if proj and is_safe_project_dir(proj, root):
                try:
                    send_to_recycle_bin(proj)
                    deleted_files = True
                except RecycleError as e:
                    self._json({
                        "ok": True,
                        "removedFromList": True,
                        "deletedFiles": False,
                        "recycled": False,
                        "warning": str(e),
                    })
                    return
            self._json({"ok": True, "removedFromList": True, "deletedFiles": deleted_files, "recycled": deleted_files})
            return

        if path == "/api/jobs":
            from app import license as lic

            st = lic.entitlement()
            if not st.get("entitled"):
                self._json({"error": lic.deny_reason(st), "license": lic.public_status()}, 403)
                return
            qs = parse_qs(parsed.query)
            merge = (qs.get("merge") or ["0"])[0].lower() in ("1", "true", "yes")
            ctype = self.headers.get("Content-Type", "")
            created: list[dict] = []
            if "multipart/form-data" in ctype:
                created = self._ingest_multipart(merge=merge)
            else:
                body = self._read_json()
                paths = body.get("paths") or []
                merge = merge or bool(body.get("merge"))
                created = self._ingest_paths(
                    paths,
                    merge=merge,
                    intent=body.get("intent"),
                    title=(body.get("title") or "").strip() or None,
                )
            self._json({"ok": True, "jobs": created, "merged": bool(merge and len(created) == 1)})
            return

        self._json({"error": "unknown route"}, 404)

    def _find_job_by_folder(self, folder: str) -> dict | None:
        folder = (folder or "").strip().strip("/\\")
        if not folder or "/" in folder or "\\" in folder or folder in (".", ".."):
            return None
        for j in self.store.list():
            if Path(j.get("projectDir", "")).name == folder:
                return j
            if Path(j.get("editDir", "")).parent.name == folder:
                return j
        return None

    def _append_cta_job(self, parsed) -> dict:
        from app.append_source import append_cta

        ctype = self.headers.get("Content-Type", "")
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        folder = (parse_qs(parsed.query).get("folder") or [""])[0]
        filename = ""
        payload = b""
        src_path = ""
        duration_hint = None
        if "multipart/form-data" in ctype:
            if "boundary=" not in ctype:
                raise ValueError("arquivo inválido")
            mime = b"Content-Type: " + ctype.encode("ascii", "ignore") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
            msg = BytesParser(policy=policy.default).parsebytes(mime)
            for part in msg.iter_parts():
                field = part.get_param("name", header="content-disposition") or ""
                body = part.get_payload(decode=True) or b""
                if field == "folder":
                    folder = body.decode("utf-8", "replace").strip()
                elif field == "path":
                    src_path = body.decode("utf-8", "replace").strip()
                elif field == "duration":
                    try:
                        duration_hint = float(body.decode("utf-8", "replace").strip())
                    except ValueError:
                        duration_hint = None
                elif field == "file" or part.get_filename():
                    filename = part.get_filename() or filename
                    payload = body
        else:
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                body = {}
            folder = str(body.get("folder") or folder)
            src_path = str(body.get("path") or "")
            filename = str(body.get("filename") or "")
            try:
                duration_hint = float(body.get("duration") or 0) or None
            except (TypeError, ValueError):
                duration_hint = None
        folder = (folder or "").strip().strip("/\\")
        job = self._find_job_by_folder(folder)
        if not job:
            guess = self.projects_root / folder
            if not guess.is_dir():
                raise ValueError("projeto não encontrado — volte em Concluídos e abra de novo")
            project = guess
        else:
            project = Path(job["projectDir"])
        return append_cta(
            project,
            filename=filename,
            data=payload or None,
            src_path=src_path or None,
            duration_hint=duration_hint,
        )

    def _ingest_paths(
        self,
        paths: list[str],
        merge: bool = False,
        intent: dict | None = None,
        title: str | None = None,
    ) -> list[dict]:
        files: list[Path] = []
        saw_dir = False
        for p in paths:
            src = Path(p)
            if src.is_dir():
                saw_dir = True
                files.extend(_walk_import_videos(src))
            elif src.is_file():
                files.append(src)
        if not files:
            return []
        if saw_dir and not merge:
            groups: dict[str, list[Path]] = {}
            for src in files:
                groups.setdefault(str(src.parent.resolve()), []).append(src)
            jobs: list[dict] = []
            for parent, group in groups.items():
                group.sort(key=lambda item: item.name.lower())
                folder_title = Path(parent).name
                if len(group) > 1:
                    jobs.append(self._create_job_from_many_files(group, intent=intent, title=folder_title))
                else:
                    jobs.append(self._create_job_from_file(group[0], copy=True, intent=intent, title=folder_title))
            return jobs
        if merge and len(files) > 1:
            return [self._create_job_from_many_files(files, intent=intent, title=title)]
        return [self._create_job_from_file(src, copy=True, intent=intent, title=title) for src in files]

    def _ingest_multipart(self, merge: bool = False) -> list[dict]:
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            return []
        raw = b"Content-Type: " + ctype.encode("ascii", "ignore") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        parts: list[tuple[str, bytes]] = []
        intent: dict | None = None
        title: str | None = None
        for part in msg.iter_parts():
            filename = part.get_filename()
            disp = str(part.get("Content-Disposition") or "")
            field = (part.get_param("name", header="content-disposition") or "").strip()
            if not field and "name=" in disp.lower():
                m = re.search(r'name="?([^";]+)"?', disp, flags=re.I)
                field = (m.group(1) if m else "").strip()
            payload = part.get_payload(decode=True) or b""
            if field == "intent" or (not filename and field in ("intent", "jobIntent")):
                try:
                    intent = json.loads(payload.decode("utf-8", errors="replace") or "{}")
                except json.JSONDecodeError:
                    intent = None
                continue
            if field == "title" and not filename:
                title = payload.decode("utf-8", errors="replace").strip() or None
                continue
            if not filename:
                continue
            parts.append((filename, payload))
        if not parts:
            return []
        if merge and len(parts) > 1:
            return [self._create_job_from_many_bytes(parts, intent=intent, title=title)]
        return [self._create_job_from_bytes(name, data, intent=intent, title=title) for name, data in parts]

    def _create_job_from_many_files(self, files: list[Path], intent: dict | None = None, title: str | None = None) -> dict:
        job_id = uuid.uuid4().hex[:10]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        label = _safe_name(title or files[0].stem)[:40] or "takes"
        project = self.projects_root / f"{stamp}_{label}_x{len(files)}_{job_id}"
        project.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for src in files:
            dest = project / src.name
            # Avoid clobber if same basename
            if dest.exists():
                dest = project / f"{src.stem}_{len(copied)}{src.suffix}"
            shutil.copy2(src, dest)
            copied.append(dest)
        primary = copied[0]
        display = (title or "").strip() or (f"{label} (+{len(copied) - 1})" if len(copied) > 1 else label)
        return self._register_job(
            job_id, display, primary, project / "edit", sources=[str(p) for p in copied], intent=intent
        )

    def _create_job_from_many_bytes(self, parts: list[tuple[str, bytes]], intent: dict | None = None, title: str | None = None) -> dict:
        job_id = uuid.uuid4().hex[:10]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        label = _safe_name(title or Path(parts[0][0]).stem)[:40] or "takes"
        project = self.projects_root / f"{stamp}_{label}_x{len(parts)}_{job_id}"
        project.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        for filename, data in parts:
            name = _safe_name(filename)
            ext = Path(filename).suffix or ".mp4"
            dest = project / f"{name}{ext}"
            if dest.exists():
                dest = project / f"{name}_{len(copied)}{ext}"
            dest.write_bytes(data)
            copied.append(dest)
        primary = copied[0]
        display = (title or "").strip() or (f"{label} (+{len(copied) - 1})" if len(copied) > 1 else label)
        return self._register_job(
            job_id, display, primary, project / "edit", sources=[str(p) for p in copied], intent=intent
        )

    def _create_job_from_bytes(self, filename: str, data: bytes, intent: dict | None = None, title: str | None = None) -> dict:
        job_id = uuid.uuid4().hex[:10]
        name = _safe_name(filename)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        project = self.projects_root / f"{stamp}_{name}_{job_id}"
        project.mkdir(parents=True, exist_ok=True)
        ext = Path(filename).suffix or ".mp4"
        source = project / f"{name}{ext}"
        source.write_bytes(data)
        display = (title or "").strip() or name
        return self._register_job(job_id, display, source, project / "edit", intent=intent)

    def _create_job_from_upload(self, filename: str, data: bytes) -> dict:
        return self._create_job_from_bytes(filename, data)

    def _create_job_from_file(self, src: Path, copy: bool = True, intent: dict | None = None, title: str | None = None) -> dict:
        job_id = uuid.uuid4().hex[:10]
        name = _safe_name(src.name)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        project = self.projects_root / f"{stamp}_{name}_{job_id}"
        project.mkdir(parents=True, exist_ok=True)
        dest = project / src.name
        if copy:
            shutil.copy2(src, dest)
        else:
            shutil.move(str(src), str(dest))
        display = (title or "").strip() or name
        return self._register_job(job_id, display, dest, project / "edit", intent=intent)

    def _register_job(
        self,
        job_id: str,
        name: str,
        source: Path,
        edit_dir: Path,
        sources: list[str] | None = None,
        intent: dict | None = None,
    ) -> dict:
        edit_dir.mkdir(parents=True, exist_ok=True)
        if intent:
            try:
                from app.editing_intent import save as save_intent

                save_intent(edit_dir, intent)
            except Exception:
                pass
        # So /p/<pasta>/fase1 always resolves to a real editor session
        state_p = edit_dir / "state.json"
        if not state_p.exists():
            state_p.write_text(
                json.dumps({
                    "project": name,
                    "phase": 1,
                    "message": "Na fila — aguardando o corte",
                    "fps": 30,
                    "style": load_preset(),
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        src_list = sources or [str(source)]
        created = _utc()
        extra = max(0, len(src_list) - 1)
        job = {
            "id": job_id,
            "name": name,
            "title": _default_job_title(name, created, extra_takes=extra),
            "titleLocked": False,
            "source": str(source),
            "sources": src_list,
            "editDir": str(edit_dir),
            "projectDir": str(source.parent),
            "status": "queued",
            "message": "Na fila" + (f" · {len(src_list)} takes" if len(src_list) > 1 else ""),
            "phase": 0,
            "createdAt": created,
            "updatedAt": created,
        }
        self.store.upsert(job)
        self.worker.enqueue(job_id)
        threading.Thread(
            target=ensure_job_thumb,
            args=(job,),
            daemon=True,
            name=f"thumb-{job_id}",
        ).start()
        return job


def main() -> None:
    # load .env into process early
    for k, v in load_env_keys().items():
        os.environ.setdefault(k, v)

    ap = argparse.ArgumentParser(description="ATIVAVID Local studio")
    default_root = Path(os.environ.get("ATIVAVID_PROJECTS") or (Path.home() / "ATIVAVID" / "Projetos"))
    ap.add_argument("--projects-root", type=Path, default=default_root)
    ap.add_argument("--port", type=int, default=4850)
    ap.add_argument("--no-browser", action="store_true",
                    help="nao abre navegador (use app/launcher.py para janela nativa)")
    ap.add_argument("--browser", action="store_true", help="forca abrir no navegador")
    args = ap.parse_args()

    root = args.projects_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not (STUDIO / "index.html").exists():
        raise SystemExit(f"studio UI missing: {STUDIO / 'index.html'}")

    store = JobStore(root)
    worker = Worker(store)
    worker.start()

    StudioHandler.store = store
    StudioHandler.worker = worker
    StudioHandler.projects_root = root

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), StudioHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"ATIVAVID Local -> {url}", flush=True)
    print(f"Projetos: {root}", flush=True)
    # Preferencia: launcher.py (WebView2). Este entrypoint so abre browser se pedido.
    if args.browser and not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado", flush=True)


if __name__ == "__main__":
    main()
