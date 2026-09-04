"""Aulas (5.0.3): a central de ajuda dentro do app.

A lista de aulas (título, link do YouTube, seção) mora no Supabase e é
gerida pelo admin na própria tela "Aulas". Qualquer app lê (anon). Sem
rede, vale a última lista baixada (`~/ATIVAVID/aulas.json`), para a ajuda
não sumir justamente quando a pessoa está sem internet.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

CACHE = Path.home() / "ATIVAVID" / "aulas.json"

# Minutagem (5.0.5): o YouTube nao da a duracao pelo embed antes de tocar,
# e o admin nao vai digitar. A pagina do video traz `lengthSeconds`; le
# uma vez por video e guarda no cache. Em thread: /api/aulas responde na
# hora e a tela pede de novo em seguida.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_DUR_LOCK = threading.Lock()
_DUR_EM_ANDAMENTO = False

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


def _gravar_cache(aulas: list[dict[str, Any]] | None = None,
                  duracoes: dict[str, int] | None = None) -> None:
    """Grava a lista e/ou as duracoes SEM apagar o que ja estava."""
    try:
        atual = _ler_cache() or {}
        if aulas is not None:
            atual["aulas"] = aulas
            atual["fetchedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if duracoes:
            d = dict(atual.get("duracoes") or {})
            d.update({k: int(v) for k, v in duracoes.items() if v})
            atual["duracoes"] = d
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(atual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _duracoes_conhecidas() -> dict[str, int]:
    c = _ler_cache() or {}
    d = c.get("duracoes") or {}
    out: dict[str, int] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            try:
                if int(v) > 0:
                    out[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
    return out


def _baixar_html(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with request.urlopen(req, timeout=10) as r:
        return r.read(2_000_000).decode("utf-8", "replace")


def duracao_no_html(html: str) -> int | None:
    m = re.search(r'"lengthSeconds"\s*:\s*"(\d+)"', html or "")
    if m:
        return int(m.group(1))
    m = re.search(r'"approxDurationMs"\s*:\s*"(\d+)"', html or "")
    if m:
        return max(1, round(int(m.group(1)) / 1000))
    return None


def _duracao_youtube(yid: str) -> int | None:
    try:
        return duracao_no_html(_baixar_html(f"https://www.youtube.com/watch?v={yid}&hl=pt"))
    except Exception:  # noqa: BLE001 — sem rede, sem minutagem por enquanto
        return None


def _completar_duracoes(ids: list[str]) -> None:
    global _DUR_EM_ANDAMENTO
    try:
        achadas: dict[str, int] = {}
        for yid in ids:
            d = _duracao_youtube(yid)
            if d:
                achadas[yid] = d
        if achadas:
            _gravar_cache(duracoes=achadas)
    finally:
        with _DUR_LOCK:
            _DUR_EM_ANDAMENTO = False


def _com_duracoes(aulas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Poe `duracaoSeg` em cada aula; dispara a busca do que falta."""
    global _DUR_EM_ANDAMENTO
    conhecidas = _duracoes_conhecidas()
    faltam: list[str] = []
    for a in aulas:
        d = conhecidas.get(a["youtubeId"])
        a["duracaoSeg"] = d or 0
        if not d and a["youtubeId"] not in faltam:
            faltam.append(a["youtubeId"])
    disparar = False
    if faltam:
        with _DUR_LOCK:
            if not _DUR_EM_ANDAMENTO:
                _DUR_EM_ANDAMENTO = True
                disparar = True
    # fora do lock: a thread devolve o lock no `finally`, e um start que
    # rodasse na hora (teste) travava esperando o proprio lock
    if disparar:
        threading.Thread(target=_completar_duracoes, args=(faltam,),
                         daemon=True, name="aulas-duracao").start()
    return aulas, len(faltam)


def listar() -> dict[str, Any]:
    """As aulas ativas: do servidor quando dá, senão a última lista baixada."""
    code, data = _rpc({}, "ativavid_aulas")
    if code == 200 and isinstance(data, list):
        aulas = [x for x in (_limpa(a) for a in data) if x]
        _gravar_cache(aulas)
        aulas, pendentes = _com_duracoes(aulas)
        return {"ok": True, "aulas": aulas, "origem": "servidor", "duracoesPendentes": pendentes}
    erro = ""
    if isinstance(data, dict):
        erro = str(data.get("message") or data.get("error") or data.get("msg") or "")
    cache = _ler_cache()
    if cache and isinstance(cache.get("aulas"), list):
        aulas = [x for x in (_limpa(a) for a in cache["aulas"]) if x]
        aulas, _ = _com_duracoes(aulas)
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
    aulas, pendentes = _com_duracoes(aulas)
    return {"ok": True, "id": data.get("id"), "aulas": aulas, "duracoesPendentes": pendentes}
