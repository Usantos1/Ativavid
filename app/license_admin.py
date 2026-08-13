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
