"""Gestão de licenças — preferência: JWT admin (RPC). Fallback: service role local."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import error, request
from urllib.parse import quote

from app import auth as auth_mod
from app import settings_store as ss


def _cfg() -> dict[str, str]:
    s = ss.load_settings()
    return {
        "url": str(s.get("supabaseUrl") or "").strip().rstrip("/"),
        "anon": str(s.get("supabaseAnonKey") or "").strip(),
        "service": str(s.get("supabaseServiceRoleKey") or "").strip(),
    }


def _new_key() -> str:
    def chunk() -> str:
        return secrets.token_hex(2).upper()

    return f"ATIV-{chunk()}-{chunk()}-{chunk()}"


def _rpc_admin(action: str, **kwargs: Any) -> dict[str, Any]:
    c = _cfg()
    tok = auth_mod.access_token()
    if not c["url"] or not c["anon"]:
        return {"ok": False, "error": "not_configured", "message": "Configure Supabase URL + anon."}
    if not tok:
        return {"ok": False, "error": "login_required", "message": "Faça login de admin (e-mail/senha)."}

    payload = {
        "p_action": action,
        "p_email": kwargs.get("email"),
        "p_days": int(kwargs.get("days") or 365),
        "p_max_devices": int(kwargs.get("max_devices") or 1),
        "p_notes": kwargs.get("notes"),
        "p_device_id": kwargs.get("device_id"),
        "p_license_key": kwargs.get("license_key"),
    }
    raw = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{c['url']}/rest/v1/rpc/ativavid_admin_license",
        data=raw,
        method="POST",
        headers={
            "apikey": c["anon"],
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                if data.get("error") == "unknown_action":
                    data.setdefault(
                        "message",
                        "RPC admin desatualizado no Supabase. Rode de novo o arquivo supabase/rpc_admin.sql (inteiro) no SQL Editor.",
                    )
                return data
            return {"ok": False, "error": "bad_response", "raw": data}
    except error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        # RPC ausente → tenta service role legado
        if e.code in (404, 400) and "ativavid_admin_license" in text.lower():
            return {"ok": False, "error": "rpc_missing", "message": "Rode supabase/rpc_admin.sql no SQL Editor."}
        if e.code == 401:
            return {"ok": False, "error": "unauthorized", "message": "Sessão expirada — faça login de novo."}
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"message": text[:300]}
        if isinstance(parsed, dict):
            parsed.setdefault("ok", False)
            return parsed
        return {"ok": False, "error": f"http_{e.code}", "message": text[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "offline", "message": str(e)}


def _rest_service(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    c = _cfg()
    if not c["url"] or not c["service"]:
        return 400, {"error": "admin_not_configured", "message": "Login admin ou service role necessária."}
    url = f"{c['url']}/rest/v1/{path.lstrip('/')}"
    headers = {
        "apikey": c["service"],
        "Authorization": f"Bearer {c['service']}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw) if raw else {"error": f"http_{e.code}"}
        except json.JSONDecodeError:
            parsed = {"error": raw[:300] or f"http_{e.code}"}
        return e.code, parsed
    except Exception as e:  # noqa: BLE001
        return 502, {"error": "offline", "message": str(e)}


def create_license(
    *,
    email: str | None = None,
    days: int = 365,
    max_devices: int = 1,
    notes: str | None = None,
) -> dict[str, Any]:
    out = _rpc_admin(
        "create",
        email=(email or "").strip() or None,
        days=days,
        max_devices=max_devices,
        notes=notes,
    )
    if out.get("ok") or out.get("error") in ("forbidden", "unauthorized"):
        return out
    if out.get("error") not in ("login_required", "rpc_missing") or not _cfg()["service"]:
        return out

    days_i = max(1, min(int(days or 365), 3650))
    max_i = max(1, min(int(max_devices or 1), 10))
    valid_until = (datetime.now(timezone.utc) + timedelta(days=days_i)).isoformat()
    key = _new_key()
    row = {
        "license_key": key,
        "email": (email or "").strip() or None,
        "status": "active",
        "valid_until": valid_until,
        "max_devices": max_i,
        "provider": "manual",
        "notes": (notes or "").strip() or None,
    }
    code, data = _rest_service("POST", "licenses", row)
    if code >= 400:
        return {"ok": False, "status": code, "error": data}
    created = data[0] if isinstance(data, list) and data else data
    return {
        "ok": True,
        "license": created,
        "licenseKey": (created or {}).get("license_key") if isinstance(created, dict) else key,
        "message": "Licença criada. Envie a chave ao cliente.",
        "via": "service_role",
    }


def list_licenses(limit: int = 50) -> dict[str, Any]:
    out = _rpc_admin("list")
    if out.get("ok") or out.get("error") in ("forbidden", "unauthorized", "login_required"):
        return out
    if out.get("error") != "rpc_missing" and not _cfg()["service"]:
        return out
    code, data = _rest_service("GET", f"licenses?select=*&order=created_at.desc&limit={max(1, min(limit, 200))}")
    if code >= 400:
        return {"ok": False, "status": code, "error": data}
    return {"ok": True, "licenses": data if isinstance(data, list) else [], "via": "service_role"}


def list_devices(license_key: str | None = None, limit: int = 50) -> dict[str, Any]:
    out = _rpc_admin("list_devices", license_key=(license_key or "").strip().upper() or None)
    if out.get("ok") or out.get("error") in ("forbidden", "unauthorized", "login_required", "not_found"):
        return out
    if not _cfg()["service"]:
        return out
    if license_key:
        key = license_key.strip().upper()
        code, lic = _rest_service("GET", f"licenses?license_key=eq.{key}&select=id,license_key")
        if code >= 400:
            return {"ok": False, "status": code, "error": lic}
        if not isinstance(lic, list) or not lic:
            return {"ok": False, "error": "not_found", "message": "Licença não encontrada."}
        lid = lic[0]["id"]
        code, data = _rest_service(
            "GET",
            f"devices?license_id=eq.{lid}&select=*&order=last_seen.desc.nullslast&limit={max(1, min(limit, 200))}",
        )
    else:
        code, data = _rest_service(
            "GET",
            f"devices?select=*&order=last_seen.desc.nullslast&limit={max(1, min(limit, 200))}",
        )
    if code >= 400:
        return {"ok": False, "status": code, "error": data}
    return {"ok": True, "devices": data if isinstance(data, list) else [], "via": "service_role"}


def list_aberturas(limit: int = 300) -> dict[str, Any]:
    """As aberturas do app, agrupadas por MAQUINA.

    Uma linha por abertura seria ilegivel (o app abre varias vezes por
    dia); o que responde "esta sendo compartilhado?" e quantas maquinas
    diferentes existem e com que frequencia cada uma abre.

    Sem o SQL aplicado, a tabela nao existe e o PostgREST devolve 404 —
    isso vira um recado com a instrucao, nao um erro tecnico.
    """
    limit = max(1, min(int(limit or 300), 1000))
    code, data = _rest_service(
        "GET",
        "aberturas?select=device_id,host,os_user,so,app_version,licenca,criado_em"
        f"&order=criado_em.desc&limit={limit}",
    )
    if code == 404 or (isinstance(data, dict) and "aberturas" in str(data.get("message") or "")):
        return {"ok": False, "error": "sem_tabela", "message": (
            "Falta aplicar o SQL: Supabase → SQL Editor → cole "
            "supabase/registro_de_uso.sql → Run.")}
    if code >= 400:
        return {"ok": False, "status": code, "error": data}
    linhas = data if isinstance(data, list) else []

    code2, devs = _rest_service(
        "GET", "devices?select=device_id,blocked_at,blocked_reason,license_id&limit=1000")
    bloq = {}
    if code2 < 400 and isinstance(devs, list):
        bloq = {str(d.get("device_id")): d for d in devs}

    por_maquina: dict[str, dict[str, Any]] = {}
    for ln in linhas:
        did = str(ln.get("device_id") or "")
        if not did:
            continue
        m = por_maquina.setdefault(did, {
            "deviceId": did, "aberturas": 0, "ultima": None,
            "host": None, "usuario": None, "so": None, "versao": None,
            "licenca": None,
        })
        m["aberturas"] += 1
        quando = str(ln.get("criado_em") or "")
        if not m["ultima"] or quando > str(m["ultima"]):
            m["ultima"] = quando
            m["host"] = ln.get("host")
            m["usuario"] = ln.get("os_user")
            m["so"] = ln.get("so")
            m["versao"] = ln.get("app_version")
            m["licenca"] = ln.get("licenca")
    for did, m in por_maquina.items():
        d = bloq.get(did) or {}
        m["bloqueado"] = bool(d.get("blocked_at"))
        m["motivo"] = d.get("blocked_reason")
        m["temLicenca"] = bool(d.get("license_id"))
    ordenado = sorted(por_maquina.values(),
                      key=lambda m: str(m.get("ultima") or ""), reverse=True)
    return {"ok": True, "maquinas": ordenado, "eventos": len(linhas)}


def block_device(device_id: str, *, block: bool = True,
                 reason: str = "") -> dict[str, Any]:
    """Bloqueia (ou libera) UMA maquina.

    O app 4.27+ grava o veredito: depois de bloqueada, ficar offline ou
    atrasar o relogio nao devolve a licenca.
    """
    did = (device_id or "").strip()
    if not did:
        return {"ok": False, "error": "device_id_required"}
    c = _cfg()
    if not c["url"] or not c["service"]:
        return {"ok": False, "error": "admin_not_configured",
                "message": "Service role necessária."}
    code, data = _rest_service("POST", "rpc/ativavid_block_device", {
        "p_device_id": did,
        "p_reason": (reason or "").strip() or None,
        "p_block": bool(block),
    })
    if code == 404:
        return {"ok": False, "error": "sem_funcao", "message": (
            "Falta aplicar o SQL: Supabase → SQL Editor → cole "
            "supabase/registro_de_uso.sql → Run.")}
    if code >= 400:
        return {"ok": False, "status": code, "error": data}
    return {"ok": True, "deviceId": did, "bloqueado": bool(block)}


def create_auth_user(*, email: str, password: str) -> dict[str, Any]:
    """Cria usuário no Supabase Auth (service role). Confirma e-mail automaticamente."""
    c = _cfg()
    mail = (email or "").strip().lower()
    pwd = (password or "").strip()
    if not mail or "@" not in mail:
        return {"ok": False, "error": "email_required", "message": "Informe o e-mail do cliente."}
    if len(pwd) < 6:
        return {"ok": False, "error": "password_short", "message": "Senha com pelo menos 6 caracteres."}
    if not c["url"] or not c["service"]:
        return {
            "ok": False,
            "error": "service_role_required",
            "message": "Para criar conta, cole a Service role key em Licença → Chave ATIV- (legado) → Salvar service role.",
        }
    payload = {
        "email": mail,
        "password": pwd,
        "email_confirm": True,
        "user_metadata": {"created_by": "ativavid_admin"},
    }
    raw = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{c['url']}/auth/v1/admin/users",
        data=raw,
        method="POST",
        headers={
            "apikey": c["service"],
            "Authorization": f"Bearer {c['service']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            uid = None
            if isinstance(data, dict):
                uid = data.get("id") or (data.get("user") or {}).get("id")
            return {
                "ok": True,
                "created": True,
                "userId": uid,
                "email": mail,
                "message": f"Conta criada: {mail}",
            }
    except error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        low = text.lower()
        # Já existe → ok para seguir no grant
        if e.code in (422, 400) and (
            "already" in low or "registered" in low or "exists" in low or "duplicate" in low
        ):
            return {
                "ok": True,
                "created": False,
                "exists": True,
                "email": mail,
                "message": f"Conta já existia: {mail} — liberando acesso.",
            }
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {}
        msg = ""
        if isinstance(parsed, dict):
            msg = str(parsed.get("msg") or parsed.get("message") or parsed.get("error_description") or "")
        return {
            "ok": False,
            "error": "auth_admin_failed",
            "status": e.code,
            "message": msg or text[:280] or f"HTTP {e.code}",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "offline", "message": str(e)}


def create_account_and_grant(
    *,
    email: str,
    password: str | None = None,
    days: int = 7,
    max_devices: int = 1,
    notes: str | None = None,
) -> dict[str, Any]:
    """Cria (ou reusa) conta Auth + libera dias no account_access."""
    mail = (email or "").strip().lower()
    pwd = (password or "").strip()
    generated = False
    if not pwd:
        pwd = secrets.token_urlsafe(10)
        generated = True

    created = create_auth_user(email=mail, password=pwd)
    if not created.get("ok"):
        return created

    granted = grant_access(
        email=mail,
        days=days,
        max_devices=max_devices,
        notes=notes,
    )
    out: dict[str, Any] = {
        "ok": bool(granted.get("ok")),
        "email": mail,
        "account": created,
        "access": granted,
        "passwordGenerated": generated,
        "message": granted.get("message") or created.get("message"),
    }
    if generated and created.get("created"):
        out["password"] = pwd
        out["message"] = (
            f"Conta criada e liberada ({days}d). Senha gerada: {pwd} — envie ao cliente."
        )
    elif created.get("created") and granted.get("ok"):
        out["message"] = f"Conta criada e liberada: {mail} ({days} dia(s))."
    elif created.get("exists") and granted.get("ok"):
        out["message"] = f"Conta já existia — acesso liberado: {mail} ({days} dia(s))."
    if not granted.get("ok"):
        out["ok"] = False
        out["message"] = granted.get("message") or "Conta ok, mas falhou ao liberar dias."
        out["error"] = granted.get("error") or "grant_failed"
    return out


def grant_access(
    *,
    email: str,
    days: int = 7,
    max_devices: int = 1,
    notes: str | None = None,
) -> dict[str, Any]:
    return _rpc_admin(
        "grant_access",
        email=(email or "").strip().lower() or None,
        days=days,
        max_devices=max_devices,
        notes=notes,
    )


def list_access() -> dict[str, Any]:
    return _rpc_admin("list_access")


def revoke_access(*, email: str) -> dict[str, Any]:
    return _rpc_admin(
        "revoke_access",
        email=(email or "").strip().lower() or None,
    )


def grant_device(
    *,
    device_id: str,
    days: int = 365,
    email: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Libera pelo ID do dispositivo — sem conta e sem o cliente digitar chave.

    O cliente lê o ID na tela de Licença e manda; depois de liberar, ele clica
    em Atualizar e já entra.
    """
    did = (device_id or "").strip()
    if not did:
        return {
            "ok": False,
            "error": "device_id_required",
            "message": "Informe o ID do dispositivo (o cliente vê em Licença).",
        }
    return _rpc_admin(
        "grant_device",
        device_id=did,
        days=days,
        email=(email or "").strip().lower() or None,
        notes=notes,
    )


def release_device(device_id: str) -> dict[str, Any]:
    did = (device_id or "").strip()
    if not did:
        return {"ok": False, "error": "device_id_required", "message": "Informe o device id."}
    out = _rpc_admin("release_device", device_id=did)
    if out.get("ok") or out.get("error") in ("forbidden", "unauthorized", "login_required"):
        return out
    if not _cfg()["service"]:
        return out
    c = _cfg()
    url = f"{c['url']}/rest/v1/devices?device_id=eq.{quote(did, safe='')}"
    headers = {
        "apikey": c["service"],
        "Authorization": f"Bearer {c['service']}",
        "Prefer": "return=representation",
    }
    req = request.Request(url, method="DELETE", headers=headers)
    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else []
            return {"ok": True, "removed": data, "message": f"Device liberado: {did}", "via": "service_role"}
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": e.code, "error": raw[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "offline", "message": str(e)}
