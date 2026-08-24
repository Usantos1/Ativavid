"""Gateway OpenAI-compatible local — prioriza sessão web (cookies).

Base URL típica: http://127.0.0.1:4850/v1

Fluxo:
1. Cookies Gemini/ChatGPT (extensão) → resposta da IA
2. Opcional: GROQ_API_KEY só como fallback se não houver sessão
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from app.llm_session import available_backends, chat as session_chat, status as session_status


# O modelo do plano B. Estava fixo em tres lugares e a Groq o aposentou: a
# chamada voltava HTTP 404 "model does not exist". Como a queda era silenciosa,
# quando a sessao do Gemini expirou o app ficou sem IA nenhuma -- e a headline
# virou um pedaco cru da transcricao. Em 20 e 21/08, 50 de 51 videos sairam
# assim.
#
# `ATIVAVID_GROQ_MODEL` permite trocar sem esperar uma versao nova, que e
# exatamente o que faltou desta vez.
GROQ_MODELO = (os.environ.get("ATIVAVID_GROQ_MODEL") or "").strip() or "openai/gpt-oss-120b"


def _groq_key() -> str:
    return (os.environ.get("GROQ_API_KEY") or "").strip()


def ensure_local_base_url(port: int) -> None:
    """Garante LLM_PROXY_BASE_URL apontando para o gateway embutido nesta porta."""
    try:
        from app.local_server import load_env_keys, save_env_keys

        want = f"http://127.0.0.1:{int(port)}/v1"
        keys = load_env_keys()
        cur = (keys.get("LLM_PROXY_BASE_URL") or "").strip().rstrip("/")
        # Só sobrescreve se vazio ou apontava para o default antigo / porta 8080
        if not cur or "8080" in cur or cur.endswith(":4850/v1") or cur == want:
            if cur != want:
                save_env_keys({"LLM_PROXY_BASE_URL": want})
        os.environ["LLM_PROXY_BASE_URL"] = want if (not cur or "8080" in cur or cur.endswith(":4850/v1")) else cur
    except Exception:
        pass


def status() -> dict:
    sess = session_status()
    base = (os.environ.get("LLM_PROXY_BASE_URL") or "http://127.0.0.1:4850/v1").rstrip("/")
    if sess.get("ok"):
        return {
            "ok": True,
            "backend": sess.get("backend"),
            "baseUrl": base,
            "model": (sess.get("models") or [None])[0],
            "hasKey": False,
            "viaSession": True,
            "hasGemini": sess.get("hasGemini"),
            "hasChatGPT": sess.get("hasChatGPT"),
            "message": sess.get("message"),
        }
    key = _groq_key()
    if key:
        return {
            "ok": True,
            "backend": "groq",
            "baseUrl": base,
            "model": GROQ_MODELO,
            "hasKey": True,
            "viaSession": False,
            "message": "Sem sessão web — usando Groq (fallback)",
        }
    return {
        "ok": False,
        "backend": None,
        "baseUrl": base,
        "model": None,
        "hasKey": False,
        "viaSession": False,
        "message": "Capture a sessão com a extensão (Gemini ou ChatGPT)",
    }


def list_models() -> tuple[int, dict]:
    data = available_backends()
    if data:
        return 200, {"object": "list", "data": data}
    if _groq_key():
        return 200, {
            "object": "list",
            "data": [{
                "id": GROQ_MODELO,
                "object": "model",
                "owned_by": "groq",
            }],
        }
    return 200, {"object": "list", "data": []}


def _openai_chat_shape(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _error(message: str, code: int = 502) -> tuple[int, dict]:
    return code, {
        "error": {
            "message": message,
            "type": "ativavid_gateway_error",
            "code": code,
        }
    }


def _groq_chat(messages: list[dict], model: str | None,
               extras: dict | None = None) -> dict:
    key = _groq_key()
    if not key:
        raise RuntimeError("Sem sessão e sem GROQ_API_KEY")
    mid = model or GROQ_MODELO
    payload = {
        "model": mid,
        "messages": messages,
        "temperature": 0.7,
    }
    # `extras` cobre o que um chamador especifico precisa sem mudar o resto —
    # o planejador pede `response_format json_object`, porque sem isso o
    # modelo devolveu JSON com virgula faltando num plano real (23/08) e o
    # parse caiu.
    if extras:
        payload.update(extras)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Groq HTTP {e.code}: {detail}") from e


def chat_completions(payload: dict[str, Any]) -> tuple[int, dict]:
    messages = payload.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return _error("messages obrigatório", 400)
    model = payload.get("model")
    mid = str(model or "").lower()
    session_err: str | None = None

    try:
        text, backend = session_chat(messages, model=str(model) if model else None)
        return 200, _openai_chat_shape(text, model or backend)
    except RuntimeError as e:
        from app.llm_session import friendly_llm_error

        session_err = friendly_llm_error(e)
        if mid.startswith("gemini") or mid.startswith("chatgpt"):
            return _error(session_err, 502)

    if _groq_key():
        try:
            return 200, _groq_chat(messages, str(model) if model else None)
        except RuntimeError as e:
            from app.llm_session import friendly_llm_error

            return _error(friendly_llm_error(e), 502)

    from app.llm_session import friendly_llm_error

    return _error(
        friendly_llm_error(
            session_err or "Capture a sessão com a extensão (Gemini ou ChatGPT)"
        ),
        503,
    )
