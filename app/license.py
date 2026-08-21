"""Licença / trial ATIVAVID — cliente local + Supabase RPC.

Sem supabaseUrl configurado → modo aberto (dev).
Com URL → trial 7 dias ou licença anual (gate no /api/jobs).
Gate de versão: resposta `update.force` trava builds abaixo de min_version.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from app import settings_store as ss

LICENSE_DIR = Path.home() / "ATIVAVID"
LICENSE_PATH = LICENSE_DIR / "license.json"
TRIAL_DAYS_LOCAL = 7  # fallback se o servidor estiver offline e já houver trial local


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _app_version() -> str:
    try:
        from app.update_check import current_version

        return current_version()
    except Exception:  # noqa: BLE001
        return "0.0.0"


def _load_blob() -> dict[str, Any]:
    if LICENSE_PATH.exists():
        try:
            raw = json.loads(LICENSE_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                return raw
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_blob(data: dict[str, Any]) -> None:
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    LICENSE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def device_id() -> str:
    blob = _load_blob()
    did = str(blob.get("deviceId") or "").strip()
    if did:
        return did
    did = _machine_guid() or ("av-" + uuid.uuid4().hex)
    blob["deviceId"] = did
    _save_blob(blob)
    return did


def _machine_guid() -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        )
        val, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        s = str(val or "").strip()
        return f"win-{s}" if s else None
    except OSError:
        return None


def _cfg() -> dict[str, Any]:
    s = ss.load_settings()
    return {
        "url": str(s.get("supabaseUrl") or "").strip().rstrip("/"),
        "anon": str(s.get("supabaseAnonKey") or "").strip(),
        "checkout": str(s.get("checkoutUrl") or "").strip(),
    }


def configured() -> bool:
    c = _cfg()
    return bool(c["url"] and c["anon"])


def _unconfigured_status() -> dict[str, Any]:
    """Sem config de licença: aberto só em dev; build de cliente falha fechada.

    Antes, qualquer instalação sem supabaseUrl liberava tudo — e o instalador
    não embutia config nenhuma, então todo cliente rodava sem gate.
    """
    if ss.is_dev_install():
        return {"entitled": True, "mode": "open", "reason": "not_configured"}
    return {
        "entitled": False,
        "mode": "blocked",
        "error": "license_not_provisioned",
        "message": (
            "Esta instalação está sem a configuração de licença. "
            "Reinstale o ATIVAVID pelo instalador oficial."
        ),
    }


def _normalize_update(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "currentOk": bool(raw.get("currentOk", not raw.get("force"))),
        "force": bool(raw.get("force")),
        "updateAvailable": bool(raw.get("updateAvailable") or raw.get("force")),
        "minVersion": raw.get("minVersion"),
        "latestVersion": raw.get("latestVersion"),
        "downloadUrl": raw.get("downloadUrl"),
        "message": raw.get("message"),
        "appVersion": raw.get("appVersion") or _app_version(),
    }


def _apply_update_gate(status: dict[str, Any]) -> dict[str, Any]:
    """Garante bloqueio local se a API pediu force (ou cache)."""
    out = dict(status)
    upd = _normalize_update(out.get("update"))
    if upd:
        out["update"] = upd
        if upd.get("force"):
            out["entitled"] = False
            out["mode"] = "update_required"
            if not out.get("message"):
                out["message"] = upd.get("message") or "Atualize o ATIVAVID para continuar."
    return out


def _http_rpc(payload: dict[str, Any]) -> tuple[int, Any]:
    c = _cfg()
    endpoint = f"{c['url']}/rest/v1/rpc/ativavid_license"
    raw = json.dumps(payload).encode("utf-8")
    # JWT do usuário logado → RPC resolve account_access; senão anon (chave/trial)
    bearer = c["anon"]
    try:
        from app import auth as au

        tok = au.access_token()
        if tok:
            bearer = tok
    except Exception:  # noqa: BLE001
        pass
    req = request.Request(
        endpoint,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer}",
            "apikey": c["anon"],
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data
    except error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(text) if text else {"error": f"http_{e.code}"}
        except json.JSONDecodeError:
            parsed = {"msg": text[:300] or f"http_{e.code}"}
        return e.code, parsed
    except Exception as e:  # noqa: BLE001
        return 502, {"error": "offline", "message": str(e)}


def _call(action: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    c = _cfg()
    if not c["url"] or not c["anon"]:
        return _unconfigured_status()

    payload: dict[str, Any] = {
        "p_action": action,
        "p_device_id": device_id(),
        "p_key": None,
        "p_app_version": _app_version(),
    }
    if extra and extra.get("key"):
        payload["p_key"] = str(extra["key"]).strip().upper()

    code, data = _http_rpc(payload)

    # RPC antigo (3 args) — tenta sem p_app_version só se a assinatura nova não existir
    if code >= 400 and isinstance(data, dict):
        msg = str(data.get("message") or data.get("msg") or data.get("hint") or data.get("error") or "").lower()
        code_s = str(data.get("code") or "")
        needs_legacy = (
            "p_app_version" in msg
            or "could not find the function" in msg
            or code_s == "PGRST202"
            or (code == 404 and "ativavid_license" in msg)
        )
        if needs_legacy:
            legacy = {
                "p_action": payload["p_action"],
                "p_device_id": payload["p_device_id"],
                "p_key": payload["p_key"],
            }
            code2, data2 = _http_rpc(legacy)
            if code2 < 400:
                code, data = code2, data2
            elif "could not find" in msg or "ativavid_license" in msg or code_s == "PGRST202":
                return {
                    "entitled": False,
                    "mode": "error",
                    "error": "rpc_missing",
                    "message": (
                        "Falta criar/atualizar a função no Supabase: SQL Editor → "
                        "cole supabase/rpc_license.sql → Run."
                    ),
                }

    if code == 502 and isinstance(data, dict) and data.get("error") == "offline":
        return _offline_fallback(str(data.get("message") or "offline"))

    # Servidor fora do ar / rate limit é falha transitória, não "sem licença":
    # bloquear na hora derrubava cliente pagante numa manutenção do Supabase.
    if code >= 500 or code == 429:
        return _offline_fallback(f"http_{code}")

    if code >= 400:
        if isinstance(data, dict):
            body = dict(data)
            body.setdefault("entitled", False)
            body.setdefault("mode", "error")
            msg = str(body.get("message") or body.get("msg") or body.get("error") or "")
            if msg:
                body["message"] = msg
                body["error"] = body.get("error") or msg
            return _apply_update_gate(body)
        return {
            "entitled": False,
            "mode": "error",
            "error": f"http_{code}",
            "message": f"HTTP {code}",
        }

    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        return {"entitled": False, "mode": "error", "error": "bad_response"}
    return _apply_update_gate(data)


def _expired(valid_until: Any) -> bool:
    """True se validUntil já passou. Desconhecido/ausente não expira."""
    if not valid_until:
        return False
    try:
        ts = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts <= datetime.now(timezone.utc)


def _offline_fallback(err: str) -> dict[str, Any]:
    """Cache 72h para licença; force-update permanece bloqueado."""
    blob = _load_blob()
    cached = blob.get("cached")
    cached_at = blob.get("cachedAt")
    if isinstance(cached, dict) and cached_at:
        upd = _normalize_update(cached.get("update"))
        if upd and upd.get("force"):
            out = dict(cached)
            out["entitled"] = False
            out["mode"] = "update_required"
            out["update"] = upd
            out["offline"] = True
            out["message"] = upd.get("message") or cached.get("message") or (
                "Atualize o ATIVAVID para continuar."
            )
            return _apply_update_gate(out)
        if cached.get("entitled") and not _expired(cached.get("validUntil")):
            try:
                ts = datetime.fromisoformat(str(cached_at).replace("Z", "+00:00"))
                age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
                # Idade negativa = cachedAt adulterado para o futuro. Antes isso
                # passava no <= 72 e valia para sempre.
                if 0 <= age_h <= 72:
                    out = dict(cached)
                    out["offline"] = True
                    out["cacheAgeHours"] = round(age_h, 1)
                    if upd:
                        out["update"] = upd
                    return _apply_update_gate(out)
            except ValueError:
                pass
    return {
        "entitled": False,
        "mode": "blocked",
        "error": "offline",
        "message": "Sem conexão para validar a licença. Tente de novo.",
        "detail": err,
    }


def _cache(status: dict[str, Any]) -> dict[str, Any]:
    status = _apply_update_gate(status)
    # Resposta que saiu do próprio cache offline não pode regravar cachedAt:
    # isso renovava a janela de 72h a cada checagem sem rede, para sempre.
    if status.get("offline"):
        return status
    # Erro transitório não substitui um snapshot bom — senão um 5xx do servidor
    # apagava a licença guardada e o fallback offline achava entitled=false.
    if status.get("mode") == "error" and not status.get("entitled"):
        return status
    blob = _load_blob()
    blob["deviceId"] = device_id()
    blob["cached"] = {
        "entitled": bool(status.get("entitled")),
        "mode": status.get("mode"),
        "validUntil": status.get("validUntil"),
        "trialDaysLeft": status.get("trialDaysLeft"),
        "trialDaysTotal": status.get("trialDaysTotal"),
        "licenseKeyHint": status.get("licenseKeyHint"),
        "accountEmail": status.get("accountEmail"),
        "message": status.get("message"),
        "update": status.get("update"),
    }
    blob["cachedAt"] = _utc()
    _save_blob(blob)
    return status


def entitlement(*, refresh: bool = False) -> dict[str, Any]:
    if not configured():
        out = _unconfigured_status()
        out["ok"] = True
        out["deviceId"] = device_id()
        out["checkoutUrl"] = _cfg()["checkout"] or None
        out["configured"] = False
        out["appVersion"] = _app_version()
        return out

    blob = _load_blob()
    if not refresh and isinstance(blob.get("cached"), dict) and blob.get("cachedAt"):
        try:
            ts = datetime.fromisoformat(str(blob["cachedAt"]).replace("Z", "+00:00"))
            age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            cached = dict(blob["cached"])
            cached = _apply_update_gate(cached)
            # Idade negativa = cachedAt no futuro (adulterado): cache inválido.
            fresh = 0 <= age_min <= 30
            # Force-update: respeita cache sem liberar edição
            if cached.get("mode") == "update_required" or (cached.get("update") or {}).get("force"):
                # ...mas não depois de o usuário atualizar: o veredito era sobre
                # a build antiga e travava por 30min quem já instalou a nova.
                judged = str((cached.get("update") or {}).get("appVersion") or "")
                if fresh and judged == _app_version():
                    out = cached
                    out["ok"] = True
                    out["entitled"] = False
                    out["deviceId"] = device_id()
                    out["checkoutUrl"] = _cfg()["checkout"] or None
                    out["configured"] = True
                    out["fromCache"] = True
                    out["appVersion"] = _app_version()
                    return out
            elif fresh and cached.get("entitled") and not _expired(cached.get("validUntil")):
                out = cached
                out["ok"] = True
                out["deviceId"] = device_id()
                out["checkoutUrl"] = _cfg()["checkout"] or None
                out["configured"] = True
                out["fromCache"] = True
                out["appVersion"] = _app_version()
                return out
        except ValueError:
            pass

    # 'trial' CRIA trial no servidor. Como ação de rotina, dava 7 dias novos a
    # quem tinha assinatura vencida; agora só no primeiro contato deste device.
    remote = _call("trial" if not blob.get("trialAskedAt") else "status")
    if not blob.get("trialAskedAt") and not remote.get("error"):
        blob = _load_blob()
        blob["trialAskedAt"] = _utc()
        _save_blob(blob)
    if remote.get("error") and remote.get("mode") not in ("blocked", "update_required"):
        remote = _call("status")
    status = _cache(remote)
    status["ok"] = True
    status["deviceId"] = device_id()
    status["checkoutUrl"] = _cfg()["checkout"] or None
    status["configured"] = True
    status["appVersion"] = _app_version()
    return status


def activate(key: str) -> dict[str, Any]:
    if not configured():
        return {"ok": False, "error": "not_configured", "message": "Configure o Supabase em Sistema."}
    remote = _call("activate", {"key": key.strip().upper()})
    status = _cache(remote)
    # A chave pode ter sido aceita e ainda assim vir entitled=false por
    # force-update. Tratar como falha fazia o cliente tentar no outro PC e
    # levar device_limit por uma ativação que funcionou.
    status["ok"] = bool(status.get("entitled") or status.get("activated"))
    status["deviceId"] = device_id()
    status["checkoutUrl"] = _cfg()["checkout"] or None
    status["configured"] = True
    status["appVersion"] = _app_version()
    return status


# Rotas POST que seguem valendo sem licença: as que permitem SAIR do bloqueio
# (entrar, ativar, configurar) e as que só mexem no que já existe (abrir pasta,
# renomear, apagar). Todo o resto é gateado por exclusão — a lista de rotas que
# produzem vídeo cresce a cada release, e gate por inclusão deixava passar
# /api/ai-edit e /api/corrections.
_GATE_FREE_EXACT = frozenset({
    "/api/settings",
    "/api/preset",
    "/api/default-style",
    "/api/keys",
    "/api/keys/test",
    "/api/cache/clear",
    "/api/open-path",
    "/api/apply-ack",
    "/api/brands",
    "/api/brand-presets",
    "/api/hardware/bench",
    "/api/llm-gateway",
    "/v1/chat/completions",
    "/api/jobs/open-folder",
    "/api/jobs/open-final",
    "/api/jobs/rename",
    "/api/jobs/cancel",
    "/api/jobs/delete",
})
_GATE_FREE_PREFIX = (
    "/api/auth/",
    "/api/license/",
    "/api/admin/",
    "/api/update/",
    "/api/llm-proxy",
    "/api/library/",
    "/api/doutor",
)


def gate_free(path: str) -> bool:
    p = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if p in _GATE_FREE_EXACT:
        return True
    return any(p.startswith(x) for x in _GATE_FREE_PREFIX)


def gate(path: str) -> dict[str, Any] | None:
    """None = pode seguir. dict = corpo do 403 que o handler deve devolver."""
    if gate_free(path):
        return None
    st = entitlement()
    if st.get("entitled"):
        return None
    return {"error": deny_reason(st), "license": public_status()}


def deny_reason(st: dict[str, Any] | None = None) -> str:
    """Erro HTTP para gates de job."""
    st = st or entitlement()
    if (st.get("update") or {}).get("force") or st.get("mode") == "update_required":
        return "update_required"
    return "license_required"


def public_status() -> dict[str, Any]:
    st = entitlement(refresh=False)
    mode = st.get("mode")
    if not mode:
        if st.get("error") in ("offline",) or str(st.get("error") or "").startswith("http_"):
            mode = "error"
        elif st.get("error") or st.get("message"):
            mode = "error"
        elif st.get("configured") is False or st.get("reason") == "not_configured":
            mode = "open"
        elif st.get("entitled"):
            mode = "licensed"
        else:
            mode = "blocked"
    msg = st.get("message")
    err = st.get("error")
    low_msg = str(msg or "").lower()
    low_err = str(err or "").lower()
    if "invalid credentials" in low_msg or "invalid credentials" in low_err:
        msg = (
            "Falha no gateway (JWT). Confirme que rodou supabase/rpc_license.sql "
            "e clique em Atualizar status."
        )
    elif err and not msg:
        if "credential" in low_err or "jwt" in low_err or err == "http_401":
            msg = "Anon key inválida — copie de novo em API Keys → anon (public)."
        else:
            msg = str(err)
    upd = _normalize_update(st.get("update"))
    return {
        "ok": True,
        "configured": bool(st.get("configured")),
        "entitled": bool(st.get("entitled")),
        "mode": mode,
        "trialDaysLeft": st.get("trialDaysLeft"),
        "trialDaysTotal": st.get("trialDaysTotal") or TRIAL_DAYS_LOCAL,
        "validUntil": st.get("validUntil"),
        "licenseKeyHint": st.get("licenseKeyHint"),
        "accountEmail": st.get("accountEmail"),
        "message": msg,
        "error": err,
        "checkoutUrl": st.get("checkoutUrl"),
        "deviceId": st.get("deviceId"),
        "offline": st.get("offline"),
        "priceLabel": "R$ 399 / ano",
        "appVersion": st.get("appVersion") or _app_version(),
        "update": upd,
    }
