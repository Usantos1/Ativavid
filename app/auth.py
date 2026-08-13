"""Login e-mail/senha via Supabase Auth (sessão local)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlencode

from app import settings_store as ss

AUTH_PATH = Path.home() / "ATIVAVID" / "auth.json"


def _cfg() -> dict[str, str]:
    s = ss.load_settings()
    return {
        "url": str(s.get("supabaseUrl") or "").strip().rstrip("/"),
        "anon": str(s.get("supabaseAnonKey") or "").strip(),
    }


def _load() -> dict[str, Any]:
    if AUTH_PATH.exists():
        try:
            raw = json.loads(AUTH_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                return raw
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save(data: dict[str, Any]) -> None:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_session() -> None:
    try:
        if AUTH_PATH.exists():
            AUTH_PATH.unlink()
    except OSError:
        pass


def _http(method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> tuple[int, Any]:
    raw = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=raw, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, (json.loads(text) if text else {})
    except error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(text) if text else {"error": f"http_{e.code}"}
        except json.JSONDecodeError:
            parsed = {"msg": text[:300] or f"http_{e.code}"}
        return e.code, parsed
    except Exception as e:  # noqa: BLE001
        return 502, {"error": "offline", "message": str(e)}


def login(email: str, password: str) -> dict[str, Any]:
    c = _cfg()
    if not c["url"] or not c["anon"]:
        return {"ok": False, "error": "not_configured", "message": "Configure Supabase URL + anon key em Sistema."}
    email = (email or "").strip().lower()
    password = password or ""
    if not email or not password:
        return {"ok": False, "error": "missing", "message": "Informe e-mail e senha."}

    code, data = _http(
        "POST",
        f"{c['url']}/auth/v1/token?{urlencode({'grant_type': 'password'})}",
        {
            "apikey": c["anon"],
            "Content-Type": "application/json",
            "Authorization": f"Bearer {c['anon']}",
        },
        {"email": email, "password": password},
    )
    if code >= 400 or not isinstance(data, dict) or not data.get("access_token"):
        msg = ""
        if isinstance(data, dict):
            msg = str(data.get("error_description") or data.get("msg") or data.get("error") or data.get("message") or "")
        return {
            "ok": False,
            "error": "auth_failed",
            "message": msg or "E-mail ou senha inválidos.",
            "status": code,
        }

    expires_in = int(data.get("expires_in") or 3600)
    session = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": int(time.time()) + max(60, expires_in - 60),
        "user": data.get("user") or {},
        "email": ((data.get("user") or {}).get("email") or email),
    }
    _save(session)
    admin = check_admin(force=True)
    is_admin = bool(admin.get("admin"))
    session["is_admin"] = is_admin
    _save(session)
    return {
        "ok": True,
        "email": session["email"],
        "isAdmin": is_admin,
        "message": "Login OK" + (" · admin" if is_admin else ""),
    }


def signup(email: str, password: str) -> dict[str, Any]:
    """Cria conta de cliente (ou admin) no Supabase Auth e já inicia sessão se o projeto permitir."""
    c = _cfg()
    if not c["url"] or not c["anon"]:
        return {"ok": False, "error": "not_configured", "message": "Configure Supabase URL + anon key em Sistema."}
    email = (email or "").strip().lower()
    password = password or ""
    if not email or not password:
        return {"ok": False, "error": "missing", "message": "Informe e-mail e senha."}
    if len(password) < 6:
        return {"ok": False, "error": "weak_password", "message": "Senha com pelo menos 6 caracteres."}

    code, data = _http(
        "POST",
        f"{c['url']}/auth/v1/signup",
        {
            "apikey": c["anon"],
            "Content-Type": "application/json",
            "Authorization": f"Bearer {c['anon']}",
        },
        {"email": email, "password": password},
    )
    if code >= 400 or not isinstance(data, dict):
        msg = ""
        if isinstance(data, dict):
            msg = str(
                data.get("error_description")
                or data.get("msg")
                or data.get("error")
                or data.get("message")
                or ""
            )
        low = msg.lower()
        if "already" in low or "registered" in low or "exists" in low:
            msg = "Este e-mail já tem conta. Use Entrar."
        return {
            "ok": False,
            "error": "signup_failed",
            "message": msg or "Não foi possível criar a conta.",
            "status": code,
        }

    # Se o projeto exige confirm e-mail, signup pode não devolver access_token
    if data.get("access_token"):
        expires_in = int(data.get("expires_in") or 3600)
        session = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": int(time.time()) + max(60, expires_in - 60),
            "user": data.get("user") or {},
            "email": ((data.get("user") or {}).get("email") or email),
        }
        _save(session)
        admin = check_admin(force=True)
        is_admin = bool(admin.get("admin"))
        session["is_admin"] = is_admin
        _save(session)
        return {
            "ok": True,
            "email": session["email"],
            "isAdmin": is_admin,
            "loggedIn": True,
            "message": "Conta criada. Peça ao admin para liberar os dias de acesso.",
        }

    # Fallback: tenta login imediato (Confirm email off)
    logged = login(email, password)
    if logged.get("ok"):
        logged["message"] = "Conta criada e logada. Peça ao admin para liberar os dias de acesso."
        logged["loggedIn"] = True
        return logged

    return {
        "ok": True,
        "email": email,
        "isAdmin": False,
        "loggedIn": False,
        "message": "Conta criada. Confirme o e-mail (se pedido) e entre. Depois o admin libera os dias.",
    }


def logout() -> dict[str, Any]:
    clear_session()
    return {"ok": True, "message": "Saiu da conta."}


def _refresh_if_needed() -> dict[str, Any]:
    blob = _load()
    token = str(blob.get("access_token") or "")
    if not token:
        return {}
    exp = int(blob.get("expires_at") or 0)
    if exp > int(time.time()) + 30:
        return blob
    refresh = str(blob.get("refresh_token") or "")
    if not refresh:
        clear_session()
        return {}
    c = _cfg()
    if not c["url"] or not c["anon"]:
        return blob
    code, data = _http(
        "POST",
        f"{c['url']}/auth/v1/token?{urlencode({'grant_type': 'refresh_token'})}",
        {
            "apikey": c["anon"],
            "Content-Type": "application/json",
            "Authorization": f"Bearer {c['anon']}",
        },
        {"refresh_token": refresh},
    )
    if code >= 400 or not isinstance(data, dict) or not data.get("access_token"):
        clear_session()
        return {}
    expires_in = int(data.get("expires_in") or 3600)
    blob["access_token"] = data["access_token"]
    if data.get("refresh_token"):
        blob["refresh_token"] = data["refresh_token"]
    blob["expires_at"] = int(time.time()) + max(60, expires_in - 60)
    if data.get("user"):
        blob["user"] = data["user"]
        blob["email"] = data["user"].get("email") or blob.get("email")
    _save(blob)
    return blob


def access_token() -> str | None:
    blob = _refresh_if_needed()
    tok = str(blob.get("access_token") or "").strip()
    return tok or None


def check_admin(*, force: bool = False) -> dict[str, Any]:
    """Confere se o JWT atual é admin (RPC ativavid_is_admin / whoami)."""
    c = _cfg()
    tok = access_token()
    if not c["url"] or not c["anon"] or not tok:
        return {"ok": True, "loggedIn": False, "admin": False, "email": None}

    # whoami via admin RPC (exige grant authenticated)
    payload = {
        "p_action": "whoami",
        "p_email": None,
        "p_days": 365,
        "p_max_devices": 1,
        "p_notes": None,
        "p_device_id": None,
        "p_license_key": None,
    }
    code, data = _http(
        "POST",
        f"{c['url']}/rest/v1/rpc/ativavid_admin_license",
        {
            "apikey": c["anon"],
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        payload,
    )
    email = (_load().get("email") if _load() else None)
    if code >= 400:
        # fallback: só is_admin boolean
        code2, data2 = _http(
            "POST",
            f"{c['url']}/rest/v1/rpc/ativavid_is_admin",
            {
                "apikey": c["anon"],
                "Authorization": f"Bearer {tok}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            {},
        )
        is_adm = bool(data2 is True or data2 == "true")
        return {
            "ok": True,
            "loggedIn": True,
            "admin": is_adm,
            "email": email,
            "rpcStatus": code,
            "detail": data if force else None,
        }

    if isinstance(data, dict):
        return {
            "ok": True,
            "loggedIn": True,
            "admin": bool(data.get("admin") or data.get("ok")),
            "email": data.get("email") or email,
        }
    return {"ok": True, "loggedIn": True, "admin": False, "email": email}


def public_status() -> dict[str, Any]:
    """Status rápido só do arquivo local — sem RPC (evita 'Failed to fetch' no sidebar)."""
    blob = _load()
    if not str(blob.get("access_token") or "").strip():
        return {"ok": True, "loggedIn": False, "isAdmin": False, "email": None}
    # Sessão antiga sem flag: ainda conta como logado; admin exige novo login (ou require_admin)
    return {
        "ok": True,
        "loggedIn": True,
        "isAdmin": bool(blob.get("is_admin")),
        "email": blob.get("email"),
    }


def require_admin() -> dict[str, Any]:
    """Gate de admin com RPC real; atualiza cache local."""
    adm = check_admin(force=True)
    if not adm.get("loggedIn"):
        return {"ok": False, "loggedIn": False, "isAdmin": False, "email": None}
    is_admin = bool(adm.get("admin"))
    blob = _load()
    if blob.get("access_token"):
        blob["is_admin"] = is_admin
        if adm.get("email"):
            blob["email"] = adm.get("email") or blob.get("email")
        _save(blob)
    return {
        "ok": True,
        "loggedIn": True,
        "isAdmin": is_admin,
        "email": adm.get("email") or blob.get("email"),
    }
