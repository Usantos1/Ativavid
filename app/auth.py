"""Login e-mail/senha via Supabase Auth — sessão local persistente.

A sessão fica em %USERPROFILE%/ATIVAVID/auth.json e sobrevive a fechar/abrir
o app. Só some com Sair explícito ou refresh_token inválido de verdade
(não em falha de rede).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlencode

from app import settings_store as ss

AUTH_PATH = Path.home() / "ATIVAVID" / "auth.json"

# Os servidores são ThreadingHTTPServer: duas rotas podem renovar ao mesmo
# tempo. O Supabase trata reuso de refresh_token como ataque e revoga a família
# inteira, então o refresh é serializado.
_REFRESH_LOCK = threading.RLock()

# Access JWT do Supabase costuma durar ~1h; refresh cobre semanas/meses.
# Margem para renovar antes de expirar.
_REFRESH_SKEW_S = 120
# Se a rede falhar, ainda consideramos “logado” na UI por este prazo
# depois do expires_at (até conseguir renovar).
_STALE_GRACE_S = 7 * 24 * 3600


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
    data = dict(data)
    data["remember"] = True
    data["saved_at"] = int(time.time())
    # Nome único: com duas threads o .tmp fixo virava escrita entrelaçada.
    tmp = AUTH_PATH.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(AUTH_PATH)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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


def _apply_token_response(blob: dict[str, Any], data: dict[str, Any], *, email_fallback: str = "") -> dict[str, Any]:
    expires_in = int(data.get("expires_in") or 3600)
    blob["access_token"] = data["access_token"]
    # Supabase pode rotacionar o refresh; se não vier, mantém o anterior.
    if data.get("refresh_token"):
        blob["refresh_token"] = data["refresh_token"]
    blob["expires_at"] = int(time.time()) + max(60, expires_in - 60)
    blob["remember"] = True
    if data.get("user"):
        blob["user"] = data["user"]
        blob["email"] = data["user"].get("email") or blob.get("email") or email_fallback
    elif email_fallback and not blob.get("email"):
        blob["email"] = email_fallback
    _save(blob)
    return blob


_ASK_ADMIN = "Conta criada. Peça ao admin para liberar os dias de acesso."


def _signup_message() -> str:
    """O admin pode ter liberado o e-mail ANTES do cadastro (pendingSignup).

    Mandar 'peça ao admin' para quem já está liberado gerava chamado de suporte
    com o acesso funcionando atrás do aviso.
    """
    try:
        from app import license as lic

        st = lic.entitlement(refresh=True)
    except Exception:  # noqa: BLE001
        return _ASK_ADMIN
    if not st.get("entitled"):
        return _ASK_ADMIN
    if st.get("mode") == "trial":
        left = st.get("trialDaysLeft")
        return f"Conta criada. Teste liberado — {left} dia(s)." if left else "Conta criada."
    until = str(st.get("validUntil") or "")[:10]
    return "Conta criada — acesso já liberado" + (f" até {until}." if until else ".")


def _mark_admin(is_admin: bool) -> dict[str, Any]:
    """Grava só o is_admin, relendo o disco.

    Regravar o blob que estava em memória desfazia a renovação que o
    check_admin acabou de salvar, ressuscitando um refresh_token já rotacionado.
    """
    with _REFRESH_LOCK:
        blob = _load()
        if not blob.get("access_token"):
            return blob
        blob["is_admin"] = bool(is_admin)
        _save(blob)
        return blob


def _session_from_password_grant(data: dict[str, Any], email: str) -> dict[str, Any]:
    session: dict[str, Any] = {
        "remember": True,
        "email": ((data.get("user") or {}).get("email") or email),
        "user": data.get("user") or {},
        "is_admin": False,
    }
    return _apply_token_response(session, data, email_fallback=email)


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

    session = _session_from_password_grant(data, email)
    admin = check_admin(force=True)
    is_admin = bool(admin.get("admin"))
    session = _mark_admin(is_admin) or session
    msg = "Login OK" + (" · admin" if is_admin else "") + " · sessão salva neste PC"
    if admin.get("error") == "unknown_action" and admin.get("message"):
        msg = f"{msg} · {admin['message']}"
    return {
        "ok": True,
        "email": session.get("email") or email,
        "isAdmin": is_admin,
        "loggedIn": True,
        "message": msg,
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

    if data.get("access_token"):
        session = _session_from_password_grant(data, email)
        admin = check_admin(force=True)
        is_admin = bool(admin.get("admin"))
        session = _mark_admin(is_admin) or session
        return {
            "ok": True,
            "email": session.get("email") or email,
            "isAdmin": is_admin,
            "loggedIn": True,
            "message": _signup_message(),
        }

    logged = login(email, password)
    if logged.get("ok"):
        logged["message"] = _signup_message()
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
    # Revogar no servidor também: só apagar o arquivo deixava o refresh_token
    # (semanas de validade) utilizável por qualquer cópia do auth.json feita
    # antes do "Sair" — inclusive de uma sessão de admin.
    c = _cfg()
    blob = _load()
    tok = str(blob.get("access_token") or "").strip()
    if c["url"] and c["anon"] and tok:
        try:
            _http(
                "POST",
                f"{c['url']}/auth/v1/logout?scope=global",
                {
                    "apikey": c["anon"],
                    "Authorization": f"Bearer {tok}",
                    "Content-Type": "application/json",
                },
                {},
            )
        except Exception:  # noqa: BLE001
            pass  # sem rede: ainda assim limpa localmente
    clear_session()
    return {"ok": True, "message": "Saiu da conta."}


def _is_fatal_refresh_error(code: int, data: Any) -> bool:
    """Só apaga sessão em rejeição definitiva do refresh_token."""
    blob = ""
    if isinstance(data, dict):
        blob = " ".join(
            str(data.get(k) or "")
            for k in ("error", "error_description", "msg", "message")
        ).lower()
    # 401 também é a resposta para anon key errada/rotacionada — problema de
    # config, não de sessão. Apagar aqui deslogava todo mundo por engano.
    if "api key" in blob or "apikey" in blob:
        return False
    if code in (401, 403):
        return True
    if code == 400:
        fatal_hints = (
            "invalid_grant",
            "invalid refresh",
            "refresh token not found",
            "already used",
            "revoked",
        )
        # Marcadores específicos do GoTrue. Substrings soltas como "expired" ou
        # "not found" também casam com erro transitório; na dúvida, conservar a
        # sessão (o pior caso é pedir login no próximo 401 de verdade).
        if any(h in blob for h in fatal_hints):
            return True
    return False


def _refresh_if_needed(*, force: bool = False) -> dict[str, Any]:
    blob = _load()
    token = str(blob.get("access_token") or "")
    if not token:
        return {}
    exp = int(blob.get("expires_at") or 0)
    now = int(time.time())
    if not force and exp > now + _REFRESH_SKEW_S:
        return blob

    with _REFRESH_LOCK:
        return _refresh_locked()


def _refresh_locked() -> dict[str, Any]:
    # Reler: outra thread pode ter renovado enquanto esperávamos o lock. Se já
    # está fresco, reaproveitar — refazer aqui é justamente o reuso que o
    # GoTrue pune revogando a sessão.
    blob = _load()
    if not blob.get("access_token"):
        return {}
    exp = int(blob.get("expires_at") or 0)
    now = int(time.time())
    if exp > now + _REFRESH_SKEW_S:
        return blob

    refresh = str(blob.get("refresh_token") or "")
    if not refresh:
        # Sem refresh: mantém enquanto o access token ainda vale; depois some.
        if exp > now:
            return blob
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

    if code < 400 and isinstance(data, dict) and data.get("access_token"):
        return _apply_token_response(blob, data)

    # Rede / 5xx / timeout: NÃO desloga — tenta de novo na próxima abertura.
    if code >= 500 or code == 502 or (isinstance(data, dict) and data.get("error") == "offline"):
        return blob

    if _is_fatal_refresh_error(code, data):
        clear_session()
        return {}

    # Outros erros: conserva sessão local (usuário continua “logado” na UI).
    return blob


def access_token() -> str | None:
    blob = _refresh_if_needed()
    tok = str(blob.get("access_token") or "").strip()
    if not tok:
        return None
    # Token já expirado e refresh falhou de forma não-fatal: ainda devolve
    # para tentativas autenticadas (API pode 401; UI permanece logada).
    return tok


def ensure_session() -> dict[str, Any]:
    """Chamado no boot / GET /api/auth — renova se precisar, sem apagar por rede."""
    blob = _refresh_if_needed(force=False)
    if not blob.get("access_token"):
        return {"ok": True, "loggedIn": False, "isAdmin": False, "email": None}
    exp = int(blob.get("expires_at") or 0)
    now = int(time.time())
    # Se está muito velho sem conseguir renovar, aí sim considera deslogado.
    if exp and exp < now - _STALE_GRACE_S and not blob.get("refresh_token"):
        clear_session()
        return {"ok": True, "loggedIn": False, "isAdmin": False, "email": None}
    return {
        "ok": True,
        "loggedIn": True,
        "isAdmin": bool(blob.get("is_admin")),
        "email": blob.get("email"),
        "expiresAt": exp or None,
        "remember": True,
    }


def check_admin(*, force: bool = False) -> dict[str, Any]:
    """Confere se o JWT atual é admin (RPC ativavid_is_admin / whoami)."""
    c = _cfg()
    tok = access_token()
    if not c["url"] or not c["anon"] or not tok:
        return {"ok": True, "loggedIn": False, "admin": False, "email": None}

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
        # `ok` NÃO é sinônimo de admin: qualquer RPC que responda ok:true sem o
        # campo admin promoveria um não-admin.
        is_adm = bool(data.get("admin")) if data.get("ok") else False
        out = {
            "ok": True,
            "loggedIn": True,
            "admin": is_adm,
            "email": data.get("email") or email,
        }
        # RPC antigo sem o branch 'whoami' devolve unknown_action com HTTP 200:
        # o admin de verdade virava não-admin sem nenhuma pista do porquê.
        if data.get("error") == "unknown_action":
            out["message"] = data.get("message") or (
                "RPC admin desatualizado — rode supabase/rpc_admin.sql de novo no SQL Editor."
            )
            out["error"] = "unknown_action"
        return out
    return {"ok": True, "loggedIn": True, "admin": False, "email": email}


def public_status() -> dict[str, Any]:
    """Status da sessão: tenta renovar; não desloga por falha de rede."""
    return ensure_session()


def require_admin() -> dict[str, Any]:
    """Gate de admin com RPC real; atualiza cache local."""
    adm = check_admin(force=True)
    if not adm.get("loggedIn"):
        return {"ok": False, "loggedIn": False, "isAdmin": False, "email": None}
    is_admin = bool(adm.get("admin"))
    with _REFRESH_LOCK:
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
