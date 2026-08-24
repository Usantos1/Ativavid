"""LLM via cookies de sessão web (extensão) — sem chave de proxy.

Prioridade: Gemini Web → ChatGPT Web. Cookies vêm de
`%USERPROFILE%/ATIVAVID/sessions.json` (capturados pela extensão).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any
from urllib.parse import urlencode

from curl_cffi import requests as cffi_requests


def _cookie_map(provider_id: str) -> dict[str, str]:
    from app.local_server import load_sessions

    block = (load_sessions().get("providers") or {}).get(provider_id) or {}
    out: dict[str, str] = {}
    for c in block.get("cookies") or []:
        name = str(c.get("name") or "")
        if name:
            out[name] = str(c.get("value") or "")
    return out


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


def _join_chunked_cookie(cookies: dict[str, str], base: str) -> str | None:
    """Une cookies particionados (ex.: session-token.0 + .1)."""
    if cookies.get(base):
        return cookies[base]
    parts: list[tuple[int, str]] = []
    prefix = base + "."
    for k, v in cookies.items():
        if k.startswith(prefix) and k[len(prefix):].isdigit():
            parts.append((int(k[len(prefix):]), v))
    if not parts:
        return None
    parts.sort()
    return "".join(v for _, v in parts)


def has_gemini_session() -> bool:
    c = _cookie_map("gemini-web")
    return bool(
        c.get("__Secure-1PSID")
        or c.get("__Secure-1PSIDTS")
        or c.get("__Secure-3PSID")
        or c.get("__Secure-3PSIDTS")
        or c.get("SID")
        or c.get("SAPISID")
    )


def has_chatgpt_session() -> bool:
    c = _cookie_map("chatgpt-web")
    if not c:
        return False
    if _join_chunked_cookie(c, "__Secure-next-auth.session-token"):
        return True
    return bool(c.get("__Secure-next-auth.session-token"))


def friendly_llm_error(err: str | BaseException) -> str:
    """Mensagem curta em PT para UI (sem jargão técnico)."""
    msg = str(err or "").strip()
    low = msg.lower()
    # As DUAS sessões falharam. O `chat()` junta os erros num blob
    # ("gemini: … · chatgpt: …"), e os padrões abaixo são testados em ordem —
    # o primeiro vencia e a metade do ChatGPT sumia da mensagem. Na prática:
    # as duas sessões expiram juntas (mesmo navegador, mesma extensão), o
    # usuário recaptura só o Gemini como a mensagem manda, e a IA continua
    # morta pelo lado que a mensagem escondeu. Visto ao vivo em 23/08: vídeo
    # saiu sem headline com os dois tokens ausentes e o aviso só citava um.
    gem_morto = "token gemini" in low or "snlm0e" in low or (
        "psid" in low and "gemini" in low)
    gpt_morto = "accesstoken" in low or ("chatgpt" in low and "session" in low)
    if gem_morto and gpt_morto:
        return (
            "As sessões Gemini e ChatGPT expiraram. Abra gemini.google.com e "
            "chatgpt.com já logados, deixe carregar e capture de novo na "
            "extensão — depois Testar IA em Chaves & IA."
        )
    if "token gemini" in low or "snlm0e" in low:
        return (
            "Sessão Gemini incompleta. Abra gemini.google.com já logado, "
            "deixe a página carregar e capture de novo na extensão."
        )
    if "psid" in low and "gemini" in low:
        return (
            "Falta o cookie de login do Gemini. Abra gemini.google.com logado e capture na extensão."
        )
    if "accesstoken" in low or ("chatgpt" in low and "session" in low):
        return (
            "Sessão ChatGPT incompleta. Abra chatgpt.com já logado, "
            "deixe carregar e capture de novo na extensão."
        )
    if "recapture" in low or "recaptur" in low:
        return msg if "abra" in low else f"{msg} — depois use Testar IA em Chaves & IA."
    if "gemini" in low and "chatgpt" in low:
        return (
            "Nenhuma sessão pronta. Em Chaves & IA: abra Gemini ou ChatGPT logado "
            "e capture com a extensão, depois Testar IA."
        )
    return msg[:280] or "Falha na IA"


def available_backends() -> list[dict]:
    out = []
    if has_gemini_session():
        out.append({"id": "gemini-web/default", "owned_by": "gemini-web", "object": "model"})
        out.append({"id": "gemini-web/flash", "owned_by": "gemini-web", "object": "model"})
        out.append({"id": "gemini-web/pro", "owned_by": "gemini-web", "object": "model"})
    if has_chatgpt_session():
        out.append({"id": "chatgpt-web/auto", "owned_by": "chatgpt-web", "object": "model"})
    return out


def status() -> dict:
    backends = available_backends()
    return {
        "ok": bool(backends),
        "backend": backends[0]["owned_by"] if backends else None,
        "hasGemini": has_gemini_session(),
        "hasChatGPT": has_chatgpt_session(),
        "models": [b["id"] for b in backends],
        "message": (
            f"Sessão pronta · {', '.join(sorted({b['owned_by'] for b in backends}))}"
            if backends
            else "Capture a sessão (extensão) em Gemini ou ChatGPT"
        ),
    }


def _messages_to_prompt(messages: list[dict]) -> str:
    parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "user").strip()
        content = m.get("content")
        if isinstance(content, list):
            text = " ".join(
                str(p.get("text") or "") for p in content if isinstance(p, dict)
            )
        else:
            text = str(content or "")
        if role == "system":
            parts.append(f"[sistema]\n{text}")
        elif role == "assistant":
            parts.append(f"[assistente]\n{text}")
        else:
            parts.append(text)
    return "\n\n".join(parts).strip() or "oi"


def _gemini_model_header(model_hint: str) -> dict[str, str]:
    hint = (model_hint or "").lower()
    # ids alinhados ao gemini_webapi.constants.Model
    if "flash" in hint:
        mid, cap = "fbb127bbb056c959", 1
    elif "pro" in hint:
        mid, cap = "9d8ca3786ebdfbea", 1
    else:
        return {}
    return {
        "x-goog-ext-525001261-jspb": (
            f'[1,null,null,null,"{mid}",null,null,0,[4],null,null,{cap}]'
        ),
        "x-goog-ext-73010989-jspb": "[0]",
        "x-goog-ext-73010990-jspb": "[0]",
    }


def _parse_gemini_stream(raw: str) -> str:
    """Extrai o texto final do StreamGenerate (path clássico [4][0][1][0])."""
    best = ""
    # chunks batchexecute: )]}'\n数字\n[json]\n数字\n[json]...
    parts = re.split(r"\n\d+\n", raw)
    for chunk in parts:
        chunk = chunk.strip()
        if "[[" in chunk and not chunk.startswith("["):
            chunk = chunk[chunk.index("["):]
        if not chunk.startswith("["):
            continue
        try:
            arr = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        for part in arr if isinstance(arr, list) else []:
            if not isinstance(part, list) or len(part) < 3:
                continue
            payload = part[2]
            if not isinstance(payload, str) or not payload.startswith("["):
                continue
            try:
                body = json.loads(payload)
            except json.JSONDecodeError:
                continue
            try:
                text = body[4][0][1][0]
            except (IndexError, TypeError, KeyError):
                continue
            if isinstance(text, str) and text.strip():
                best = text.strip()
    if not best:
        raise RuntimeError("Gemini não devolveu texto — recapture a sessão")
    return best


def _gemini_generate(prompt: str, model_hint: str = "") -> str:
    """Chat Gemini via cookies (curl_cffi) — sem chave de API."""
    cookies = _cookie_map("gemini-web")
    if not (
        cookies.get("__Secure-1PSID")
        or cookies.get("__Secure-3PSID")
        or cookies.get("SID")
    ):
        raise RuntimeError("Cookie __Secure-1PSID ausente — recapture a sessão Gemini")

    session = cffi_requests.Session(impersonate="chrome131")
    try:
        session.get("https://www.google.com/", cookies=cookies, timeout=20)
        r = session.get(
            "https://gemini.google.com/app",
            cookies=cookies,
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Gemini init HTTP {r.status_code}")
        # sincroniza cookies rotacionados
        try:
            session.cookies.update(cookies)
        except Exception:
            pass

        at = (
            re.search(r'"SNlM0e"\s*:\s*"(.*?)"', r.text)
            or re.search(r'\\"SNlM0e\\"\s*:\s*\\"(.*?)\\"', r.text)
            or re.search(r"SNlM0e['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", r.text)
        )
        bl = (
            re.search(r'"cfb2h"\s*:\s*"(.*?)"', r.text)
            or re.search(r'\\"cfb2h\\"\s*:\s*\\"(.*?)\\"', r.text)
        )
        sid = (
            re.search(r'"FdrFJe"\s*:\s*"(.*?)"', r.text)
            or re.search(r'\\"FdrFJe\\"\s*:\s*\\"(.*?)\\"', r.text)
        )
        if not at:
            raise RuntimeError(
                "Token Gemini ausente — abra gemini.google.com logado, "
                "aguarde a página carregar e recapture"
            )

        req_uuid = str(uuid.uuid4()).upper()
        inner: list[Any] = [None] * 69
        inner[0] = [prompt, 0, None, None, None, None, 0]
        inner[1] = ["pt-BR"]
        inner[2] = ["", "", "", None, None, None, None, None, None, ""]
        inner[4] = uuid.uuid4().hex
        inner[6] = [1]
        inner[7] = 1  # streaming flag
        inner[10] = 1
        inner[11] = 0
        inner[17] = [[0]]
        inner[18] = 0
        inner[27] = 1
        inner[30] = [4]
        inner[41] = [1]
        inner[53] = 0
        inner[55] = [[1]]
        inner[59] = req_uuid
        inner[61] = []
        inner[68] = 2

        params = {"hl": "pt-BR", "_reqid": str(uuid.uuid4().int % 100000), "rt": "c"}
        if bl:
            params["bl"] = bl.group(1)
        if sid:
            params["f.sid"] = sid.group(1)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Origin": "https://gemini.google.com",
            "Referer": "https://gemini.google.com/",
            "X-Same-Domain": "1",
            "x-goog-ext-525005358-jspb": f'["{req_uuid}",1]',
            **_gemini_model_header(model_hint),
        }
        data = {
            "at": at.group(1),
            "f.req": json.dumps([None, json.dumps(inner)]),
        }
        url = (
            "https://gemini.google.com/_/BardChatUi/data/"
            "assistant.lamda.BardFrontendService/StreamGenerate"
        )
        resp = session.post(
            url,
            params=params,
            data=urlencode(data),
            headers=headers,
            timeout=90,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {resp.status_code}: {(resp.text or '')[:200]}")
        return _parse_gemini_stream(resp.text or "")
    finally:
        session.close()


def chatgpt_access_token(cookies: dict[str, str]) -> str:
    # reconstrói session-token particionado se necessário
    joined = _join_chunked_cookie(cookies, "__Secure-next-auth.session-token")
    jar = dict(cookies)
    if joined and "__Secure-next-auth.session-token" not in jar:
        jar["__Secure-next-auth.session-token"] = joined

    r = cffi_requests.get(
        "https://chatgpt.com/api/auth/session",
        cookies=jar,
        headers={"Accept": "application/json"},
        impersonate="chrome131",
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ChatGPT session HTTP {r.status_code}")
    data = r.json() if r.content else {}
    token = (data or {}).get("accessToken") or ""
    if not token:
        raise RuntimeError("ChatGPT sem accessToken — abra chatgpt.com logado e recapture")
    return token


def _chatgpt_requirements(token: str, cookies: dict[str, str], device_id: str) -> dict:
    r = cffi_requests.post(
        "https://chatgpt.com/backend-api/sentinel/chat-requirements",
        json={"conversation_mode_kind": "primary_assistant"},
        cookies=cookies,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Oai-Device-Id": device_id,
            "Oai-Language": "pt-BR",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
        },
        impersonate="chrome131",
        timeout=30,
    )
    if r.status_code != 200:
        return {}
    try:
        return r.json() or {}
    except Exception:
        return {}


def _chatgpt_generate(prompt: str) -> str:
    cookies = _cookie_map("chatgpt-web")
    if not cookies:
        raise RuntimeError("Sessão ChatGPT vazia — capture pela extensão")
    joined = _join_chunked_cookie(cookies, "__Secure-next-auth.session-token")
    if joined:
        cookies = {**cookies, "__Secure-next-auth.session-token": joined}

    token = chatgpt_access_token(cookies)
    device_id = cookies.get("oai-did") or str(uuid.uuid4())
    reqs = _chatgpt_requirements(token, cookies, device_id)

    msg_id = str(uuid.uuid4())
    parent_id = str(uuid.uuid4())
    body = {
        "action": "next",
        "messages": [{
            "id": msg_id,
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": [prompt]},
        }],
        "model": "auto",
        "parent_message_id": parent_id,
        "conversation_mode": {"kind": "primary_assistant"},
        "websocket_request_id": str(uuid.uuid4()),
        "history_and_training_disabled": True,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Oai-Device-Id": device_id,
        "Oai-Language": "pt-BR",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
    }
    req_token = reqs.get("token")
    if req_token:
        headers["Openai-Sentinel-Chat-Requirements-Token"] = req_token

    r = cffi_requests.post(
        "https://chatgpt.com/backend-api/conversation",
        json=body,
        cookies=cookies,
        headers=headers,
        impersonate="chrome131",
        timeout=90,
    )
    if r.status_code != 200:
        detail = (r.text or "")[:400]
        raise RuntimeError(f"ChatGPT HTTP {r.status_code}: {detail}")

    stream = r.text or ""
    text = ""
    for line in stream.splitlines():
        if not line.startswith("data: "):
            continue
        chunk = line[6:].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        msg = (obj.get("message") or {})
        content = msg.get("content") or {}
        parts = content.get("parts") or []
        if parts and isinstance(parts[0], str) and parts[0].strip():
            text = parts[0]
    if not text:
        raise RuntimeError(
            "ChatGPT bloqueou ou não devolveu texto "
            "(sentinel/PoW). Prefira Gemini ou recapture a sessão."
        )
    return text.strip()


def chat(messages: list[dict], model: str | None = None) -> tuple[str, str]:
    """Return (text, backend_id). Raises RuntimeError on failure."""
    prompt = _messages_to_prompt(messages)
    mid = (model or "").lower()

    prefer_chatgpt = mid.startswith("chatgpt")
    prefer_gemini = mid.startswith("gemini") or not prefer_chatgpt
    errors: list[str] = []

    if prefer_gemini and has_gemini_session():
        try:
            text = _gemini_generate(prompt, mid)
            if text:
                return text, "gemini-web"
        except Exception as e:  # noqa: BLE001
            errors.append(f"gemini: {e}")

    if has_chatgpt_session() and (prefer_chatgpt or not prefer_gemini or errors):
        try:
            text = _chatgpt_generate(prompt)
            if text:
                return text, "chatgpt-web"
        except Exception as e:  # noqa: BLE001
            errors.append(f"chatgpt: {e}")

    if prefer_chatgpt and has_gemini_session() and not any(x.startswith("gemini:") for x in errors):
        try:
            text = _gemini_generate(prompt, mid)
            if text:
                return text, "gemini-web"
        except Exception as e:  # noqa: BLE001
            errors.append(f"gemini: {e}")

    if errors:
        # Uma mensagem só, amigável — evita "gemini: … · chatgpt: …" cru na UI
        raise RuntimeError(friendly_llm_error(" · ".join(errors)))
    raise RuntimeError(
        friendly_llm_error(
            "Nenhuma sessão Gemini/ChatGPT pronta — capture na extensão em Chaves & IA"
        )
    )
