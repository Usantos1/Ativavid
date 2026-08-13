"""Cliente OpenAI-compatível para o LLM Proxy (BYOK)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _cfg_and_keys() -> tuple[dict, dict[str, str]]:
    from app.local_server import load_env_keys, load_llm_proxy

    return load_llm_proxy(), load_env_keys()


def _headers(api_key: str | None = None) -> dict[str, str]:
    _, keys = _cfg_and_keys()
    token = (api_key or keys.get("LLM_PROXY_API_KEY") or "").strip()
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _url(path: str, base: str | None = None) -> str:
    cfg, _ = _cfg_and_keys()
    root = (base or cfg.get("baseUrl") or "").rstrip("/")
    if not root:
        raise ValueError("LLM_PROXY_BASE_URL não configurada")
    if not path.startswith("/"):
        path = "/" + path
    if root.endswith("/v1") and path.startswith("/v1/"):
        path = path[3:]
    return root + path


def request_json(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    base: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> tuple[int, Any]:
    url = _url(path, base=base)
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(api_key), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw[:500]}
            return int(resp.status), parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"error": e.reason}
        except json.JSONDecodeError:
            parsed = {"error": raw[:500] or e.reason}
        return int(e.code), parsed
    except urllib.error.URLError as e:
        reason = str(e.reason if hasattr(e, "reason") else e)
        low = reason.lower()
        if "10061" in reason or "refused" in low or "actively refused" in low:
            reason = (
                "Nada escutando nesse endereço — suba o seu LLM Proxy "
                "(ex.: na porta 8080) e teste de novo"
            )
        elif "timed out" in low or "timeout" in low:
            reason = "Timeout — o proxy não respondeu a tempo"
        return 0, {"error": reason}
    except ValueError as e:
        return 0, {"error": str(e)}


def test_connection(
    *,
    base: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Ping GET /models (OpenAI)."""
    try:
        code, payload = request_json("GET", "/models", base=base, api_key=api_key, timeout=15)
    except ValueError as e:
        return {"ok": False, "error": str(e), "status": 0}
    if code == 0:
        return {"ok": False, "error": payload.get("error") or "sem rede", "status": 0}
    if code >= 400:
        err = payload.get("error")
        if isinstance(err, dict):
            err = err.get("message") or err.get("code") or str(err)
        return {"ok": False, "error": err or f"HTTP {code}", "status": code, "raw": payload}
    models = []
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and m.get("id"):
                models.append({
                    "id": m["id"],
                    "owned_by": m.get("owned_by") or m.get("provider") or "",
                })
    return {
        "ok": True,
        "status": code,
        "models": models,
        "count": len(models),
        "message": f"{len(models)} modelo(s) disponíveis",
    }


def list_models() -> dict:
    return test_connection()


def chat_ping(model: str | None = None) -> dict:
    """Minimal completion to prove chat works."""
    _, keys = _cfg_and_keys()
    mid = model or keys.get("LLM_PROXY_MODEL") or ""
    if not mid:
        probed = test_connection()
        if not probed.get("ok") or not probed.get("models"):
            return {"ok": False, "error": probed.get("error") or "sem modelos"}
        mid = probed["models"][0]["id"]
    code, payload = request_json(
        "POST",
        "/chat/completions",
        body={
            "model": mid,
            "messages": [{"role": "user", "content": "Responda só: ok"}],
            "max_tokens": 8,
            "temperature": 0,
        },
        timeout=45,
    )
    if code == 0 or code >= 400:
        err = payload.get("error") if isinstance(payload, dict) else payload
        if isinstance(err, dict):
            err = err.get("message") or str(err)
        return {"ok": False, "error": err or f"HTTP {code}", "status": code, "model": mid}
    text = ""
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        text = str(payload)[:200]
    return {"ok": True, "model": mid, "reply": text, "status": code}
