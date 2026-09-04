"""Aulas (5.0.3): a central de ajuda dentro do app.

A lista de aulas (título, link do YouTube, seção) mora no Supabase e é
gerida pelo admin na própria tela "Aulas". Qualquer app lê (anon). Sem
rede, vale a última lista baixada (`~/ATIVAVID/aulas.json`), para a ajuda
não sumir justamente quando a pessoa está sem internet.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE = Path.home() / "ATIVAVID" / "aulas.json"

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/|/v/)([A-Za-z0-9_-]{11})")


def youtube_id_de(texto: str | None) -> str:
    """O id de 11 caracteres a partir de qualquer link do YouTube (ou do
    próprio id). Vazio quando não reconhece."""
    t = str(texto or "").strip()
    if not t:
        return ""
    m = _URL.search(t)
    if m:
        return m.group(1)
    return t if _ID.match(t) else ""


def _limpa(a: Any) -> dict[str, Any] | None:
    if not isinstance(a, dict):
        return None
    yid = youtube_id_de(a.get("youtubeId") or a.get("youtube_id"))
    if not yid:
        return None
    try:
        ordem = int(a.get("ordem") or 100)
    except (TypeError, ValueError):
        ordem = 100
    return {
        "id": str(a.get("id") or ""),
        "titulo": str(a.get("titulo") or "").strip() or "Aula",
        "descricao": str(a.get("descricao") or "").strip(),
        "youtubeId": yid,
        "secao": str(a.get("secao") or "").strip() or "Começando",
        "ordem": ordem,
        "ativo": bool(a.get("ativo", True)),
    }


def _rpc(payload: dict[str, Any], fn: str) -> tuple[int, Any]:
    from app.license import _http_rpc

    return _http_rpc(payload, fn)


def _ler_cache() -> dict[str, Any] | None:
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _gravar_cache(aulas: list[dict[str, Any]]) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({
            "aulas": aulas,
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def listar() -> dict[str, Any]:
    """As aulas ativas: do servidor quando dá, senão a última lista baixada."""
    code, data = _rpc({}, "ativavid_aulas")
    if code == 200 and isinstance(data, list):
        aulas = [x for x in (_limpa(a) for a in data) if x]
        _gravar_cache(aulas)
        return {"ok": True, "aulas": aulas, "origem": "servidor"}
    erro = ""
    if isinstance(data, dict):
        erro = str(data.get("message") or data.get("error") or data.get("msg") or "")
    cache = _ler_cache()
    if cache and isinstance(cache.get("aulas"), list):
        aulas = [x for x in (_limpa(a) for a in cache["aulas"]) if x]
        return {"ok": True, "aulas": aulas, "origem": "cache",
                "fetchedAt": cache.get("fetchedAt") or "", "erro": erro}
    return {"ok": True, "aulas": [], "origem": "vazio", "erro": erro, "http": code}


def admin(action: str, **campos: Any) -> dict[str, Any]:
    """Cria / edita / apaga uma aula (só admin logado; o servidor confere)."""
    acao = str(action or "").strip().lower()
    if acao not in ("list", "upsert", "delete"):
        return {"ok": False, "error": "unknown_action", "message": "Ação desconhecida."}
    yid = youtube_id_de(campos.get("youtube")) if campos.get("youtube") else ""
    if acao == "upsert" and campos.get("youtube") and not yid:
        return {"ok": False, "error": "youtube",
                "message": "Não reconheci esse link do YouTube. Cole o link do vídeo (youtu.be/… ou watch?v=…)."}
    if acao == "upsert" and not campos.get("id") and not str(campos.get("titulo") or "").strip():
        return {"ok": False, "error": "titulo", "message": "A aula precisa de título."}
    ordem = campos.get("ordem")
    try:
        ordem = int(ordem) if ordem not in (None, "") else None
    except (TypeError, ValueError):
        ordem = None
    payload = {
        "p_action": acao,
        "p_id": (str(campos.get("id") or "").strip() or None),
        "p_titulo": (str(campos.get("titulo") or "").strip() or None),
        "p_descricao": (str(campos.get("descricao")) if campos.get("descricao") is not None else None),
        "p_youtube": yid or None,
        "p_secao": (str(campos.get("secao") or "").strip() or None),
        "p_ordem": ordem,
        "p_ativo": (bool(campos["ativo"]) if campos.get("ativo") is not None else None),
    }
    code, data = _rpc(payload, "ativavid_admin_aulas")
    if code != 200 or not isinstance(data, dict):
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("message") or data.get("msg") or data.get("error") or "")
        if code == 404:
            msg = "A função de aulas ainda não existe no Supabase: rode o RODAR-NO-SUPABASE-aulas.sql."
        return {"ok": False, "error": f"http_{code}", "message": msg or f"Erro {code} ao salvar."}
    if not data.get("ok"):
        return {"ok": False, "error": str(data.get("error") or "erro"),
                "message": str(data.get("message") or "O servidor recusou.")}
    aulas = [x for x in (_limpa(a) for a in (data.get("aulas") or [])) if x]
    _gravar_cache([a for a in aulas if a.get("ativo", True)])
    return {"ok": True, "id": data.get("id"), "aulas": aulas}
