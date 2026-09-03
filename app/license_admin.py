"""Gestão de licenças — preferência: JWT admin (RPC). Fallback: service role local."""
from __future__ import annotations

import json
import math
import re
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


def codigo_do_pc(device_id: str) -> str:
    """O codigo curto que a tela de Licenca mostra ao cliente (`8372A270`
    para `win-8372a270-ab08-…`). Mesma regra do `codigoDoPc` do studio.js."""
    cru = str(device_id or "").strip()
    if not cru:
        return ""
    sem_prefixo = re.sub(r"^(win|av)-", "", cru, flags=re.IGNORECASE)
    bloco = sem_prefixo.split("-")[0] or sem_prefixo
    return bloco[:8].upper()


def _e_id_completo(device_id: str) -> bool:
    """`win-8372a270-ab08-45ee-a444-eaab6a7705cc` sim; `8372A270` nao."""
    did = str(device_id or "").strip()
    return "-" in did and len(did) >= 20


def _ids_conhecidos() -> list[str]:
    """Todo device_id que o servidor ja viu: liberados, em trial ou que
    so abriram o app."""
    ids: set[str] = set()
    for caminho in ("devices?select=device_id&limit=2000",
                    "trials?select=device_id&limit=2000",
                    "aberturas?select=device_id&limit=2000"):
        code, data = _rest_service("GET", caminho)
        if code < 400 and isinstance(data, list):
            ids.update(str(r.get("device_id") or "") for r in data)
    ids.discard("")
    return sorted(ids)


def resolver_device_id(device_id: str) -> dict[str, Any]:
    """Aceita o CODIGO CURTO que o cliente le na tela e devolve o ID completo.

    Em 03/09 ele digitou `8372A270` no "Liberar dispositivo": o painel
    mostra esse codigo ao cliente, o cliente manda o codigo, e o campo
    aceitava qualquer coisa — nasceu um dispositivo fantasma com esse nome,
    liberado e depois bloqueado, enquanto o PC de verdade
    (`win-8372a270-ab08-…`) seguia em trial. Um codigo que a propria tela
    inventou tem de ser aceito pela propria tela.

    Devolve `{"ok": True, "deviceId": <completo>, "resolvido": bool}` ou
    `{"ok": False, "error", "message"}` quando nao ha exatamente 1 PC.
    """
    did = str(device_id or "").strip()
    if not did:
        return {"ok": False, "error": "device_id_required",
                "message": "Informe o ID do dispositivo (o cliente vê em Licença)."}
    if _e_id_completo(did):
        return {"ok": True, "deviceId": did, "resolvido": False}
    alvo = did.upper()
    iguais = [i for i in _ids_conhecidos() if codigo_do_pc(i) == alvo and _e_id_completo(i)]
    if len(iguais) == 1:
        return {"ok": True, "deviceId": iguais[0], "resolvido": True, "codigo": alvo}
    if not iguais:
        return {"ok": False, "error": "codigo_desconhecido", "message": (
            f"Nenhum computador com o código {alvo} apareceu no servidor ainda. "
            "Peça ao cliente para abrir o ATIVAVID uma vez (ou mandar o ID "
            "completo, que começa com win-).")}
    return {"ok": False, "error": "codigo_ambiguo", "message": (
        f"O código {alvo} bate com {len(iguais)} computadores: "
        + ", ".join(iguais) + ". Use o ID completo.")}


def _donos_por_device() -> dict[str, dict[str, Any]]:
    """Quem e o dono de cada PC, pelo que o SERVIDOR sabe.

    A conta vinculada (`account_access`) vem primeiro; se nao houver, o
    e-mail digitado no "Liberar dispositivo" (`licenses.email`). Ate a 4.92
    o painel so mostrava a conta: um PC liberado pelo ID com e-mail
    preenchido saia como "Dono —", e a tela de maquinas so sabia o que o
    log de aberturas contava — que nem e-mail carrega.
    """
    base = ("devices?select=device_id,host,os_user,account_access_id,license_id,"
            "licenses(email),account_access(email)")
    # `devices.email` (quem estava logado na ultima abertura) so existe com
    # o SQL da 4.93; sem a coluna o PostgREST responde 400 e a lista sai
    # sem esse terceiro palpite.
    code, data = _rest_service("GET", base + ",email&limit=2000")
    if code == 400:
        code, data = _rest_service("GET", base + "&limit=2000")
    donos: dict[str, dict[str, Any]] = {}
    if code >= 400 or not isinstance(data, list):
        return donos
    for r in data:
        did = str(r.get("device_id") or "")
        if not did:
            continue
        conta = r.get("account_access") or {}
        lic = r.get("licenses") or {}
        if isinstance(conta, list):
            conta = conta[0] if conta else {}
        if isinstance(lic, list):
            lic = lic[0] if lic else {}
        email_conta = str((conta or {}).get("email") or "")
        email_lic = str((lic or {}).get("email") or "")
        email_abriu = str(r.get("email") or "")
        donos[did] = {
            "email": email_conta or email_lic or email_abriu,
            "abriuComEmail": email_abriu,
            "contaEmail": email_conta,
            "licencaEmail": email_lic,
            "host": r.get("host"),
            "usuario": r.get("os_user"),
            "accountAccessId": r.get("account_access_id"),
        }
    return donos


def list_devices(license_key: str | None = None, limit: int = 50) -> dict[str, Any]:
    out = _list_devices_cru(license_key, limit)
    if out.get("ok"):
        donos = _donos_por_device()
        for r in out.get("devices") or []:
            d = donos.get(str(r.get("device_id") or "")) or {}
            r["email"] = r.get("account_email") or d.get("email") or ""
            r["codigo"] = codigo_do_pc(str(r.get("device_id") or ""))
    return out


def _list_devices_cru(license_key: str | None = None, limit: int = 50) -> dict[str, Any]:
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


def _dias_de_trial(inicio: str | None) -> int | None:
    """Dias que ainda faltam, pela MESMA conta do servidor.

    O `rpc_license.sql` usa `ceil((started_at + 7 dias - now())/86400)`; a
    tela precisa mostrar o mesmo numero que o PC do cliente mostra, senao
    a conferencia nao serve para nada.
    """
    if not inicio:
        return None
    try:
        from app.license import TRIAL_DAYS_LOCAL

        ini = datetime.fromisoformat(str(inicio).replace("Z", "+00:00"))
    except (ValueError, ImportError):
        return None
    fim = ini + timedelta(days=TRIAL_DAYS_LOCAL)
    faltam = (fim - datetime.now(timezone.utc)).total_seconds() / 86400.0
    return max(0, math.ceil(faltam))


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
        "aberturas?select=device_id,host,os_user,so,app_version,licenca,email,criado_em"
        f"&order=criado_em.desc&limit={limit}",
    )
    if code == 400 and "email" in str(data.get("message") if isinstance(data, dict) else ""):
        # Banco sem a coluna `email` (SQL da 4.93 ainda nao aplicado):
        # a tela continua funcionando sem ela.
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
        "GET", "devices?select=device_id,blocked_at,blocked_reason,license_id,"
        "last_seen&limit=1000")
    bloq = {}
    if code2 < 400 and isinstance(devs, list):
        bloq = {str(d.get("device_id")): d for d in devs}

    # O trial e por MAQUINA e comeca no PRIMEIRO CONTATO com o servidor —
    # nao na instalacao. "Tenho um PC com vários dias de instalação e ainda
    # mostra trial 4 dias" (31/08) so tem resposta com esta data na tela,
    # ao lado da primeira abertura: se o trial nasceu DEPOIS da primeira
    # abertura, alguma coisa esta errada; se nasceu junto, o PC ficou dias
    # instalado sem ninguem abrir.
    code3, trials = _rest_service(
        "GET", "trials?select=device_id,started_at&limit=2000")
    inicio_trial: dict[str, str] = {}
    if code3 < 400 and isinstance(trials, list):
        inicio_trial = {str(t.get("device_id")): str(t.get("started_at") or "")
                        for t in trials}

    por_maquina: dict[str, dict[str, Any]] = {}
    for ln in linhas:
        did = str(ln.get("device_id") or "")
        if not did:
            continue
        m = por_maquina.setdefault(did, {
            "deviceId": did, "aberturas": 0, "ultima": None,
            "host": None, "usuario": None, "so": None, "versao": None,
            "licenca": None, "email": None,
        })
        m["aberturas"] += 1
        quando = str(ln.get("criado_em") or "")
        if quando and (not m.get("primeira") or quando < str(m["primeira"])):
            m["primeira"] = quando
        if not m["ultima"] or quando > str(m["ultima"]):
            m["ultima"] = quando
            m["host"] = ln.get("host")
            m["usuario"] = ln.get("os_user")
            m["so"] = ln.get("so")
            m["versao"] = ln.get("app_version")
            m["licenca"] = ln.get("licenca")
            # Coluna nova (SQL da 4.93); em banco antigo vem ausente.
            m["email"] = ln.get("email") or m.get("email")
    # Maquina que TEM trial mas nunca registrou abertura existe de verdade:
    # o registro de aberturas so comecou na 4.27, entao todo PC em versao
    # anterior ficava invisivel aqui — dos 3 trials da conta, a tela
    # mostrava 1 maquina. Um painel que esconde justamente quem esta em
    # trial nao serve para vigiar trial nenhum.
    for did in set(inicio_trial) | set(bloq):
        if did and did not in por_maquina:
            por_maquina[did] = {
                "deviceId": did, "aberturas": 0, "ultima": None,
                "primeira": None, "host": None, "usuario": None,
                "so": None, "versao": None, "licenca": None,
                "semRegistro": True,
            }
    donos = _donos_por_device()
    for did, m in por_maquina.items():
        d = bloq.get(did) or {}
        # `last_seen` do servidor cobre quem nao aparece no log de aberturas:
        # sem isto a coluna "ultima" ficaria vazia justamente nesses PCs.
        visto = str(d.get("last_seen") or "")
        if visto and (not m.get("ultima") or visto > str(m["ultima"])):
            m["ultima"] = visto
        m["bloqueado"] = bool(d.get("blocked_at"))
        m["motivo"] = d.get("blocked_reason")
        m["temLicenca"] = bool(d.get("license_id"))
        m["trialInicio"] = inicio_trial.get(did) or None
        m["trialDias"] = _dias_de_trial(m["trialInicio"])
        # O dono pelo SERVIDOR (conta vinculada ou e-mail da liberacao) e o
        # que responde "de quem e esse PC?" mesmo sem nenhuma abertura no
        # log — o caso do `win-8372a270…` em 03/09.
        dono = donos.get(did) or {}
        m["email"] = (m.get("email") or dono.get("email") or "")
        m["contaEmail"] = dono.get("contaEmail") or ""
        if not m.get("host") and dono.get("host"):
            m["host"] = dono.get("host")
        if not m.get("usuario") and dono.get("usuario"):
            m["usuario"] = dono.get("usuario")
        m["codigo"] = codigo_do_pc(did)
    ordenado = sorted(por_maquina.values(),
                      key=lambda m: str(m.get("ultima") or ""), reverse=True)
    return {"ok": True, "maquinas": ordenado, "eventos": len(linhas)}


def block_device(device_id: str, *, block: bool = True,
                 reason: str = "") -> dict[str, Any]:
    """Bloqueia (ou libera) UMA maquina.

    O app 4.27+ grava o veredito: depois de bloqueada, ficar offline ou
    atrasar o relogio nao devolve a licenca.
    """
    c = _cfg()
    if not c["url"] or not c["service"]:
        return {"ok": False, "error": "admin_not_configured",
                "message": "Service role necessária."}
    res = resolver_device_id(device_id)
    if not res.get("ok"):
        return res
    did = str(res["deviceId"])
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
    out = {"ok": True, "deviceId": did, "bloqueado": bool(block)}
    if block:
        out["avisoServidor"] = _servidor_ignora_o_bloqueio(did)
    return out


def _servidor_ignora_o_bloqueio(device_id: str) -> str:
    """Confere se o BANCO ja barra este PC — e nao so o app.

    Em 31/08 ele bloqueou uma maquina e ela continuou trabalhando: o
    `blocked_at` estava gravado, mas a `ativavid_license` respondia
    `entitled: true`. Quem barrava era so o app, com uma segunda pergunta
    que existe da 4.27 para cima. Bloqueio que so funciona no app do
    cliente e um pedido, nao um bloqueio.

    Depois de bloquear, pergunta ao banco como quem pergunta do PC do
    cliente. Se vier liberado, devolve o recado — em vez de deixar o
    defeito mudo outra vez.
    """
    # A VERSAO precisa ser uma de verdade: com "0.0.0" o servidor barra por
    # atualizacao obrigatoria e a resposta sai `entitled: false` por outro
    # motivo — a conferencia diria "esta tudo certo" com o bloqueio
    # furado. (Aconteceu na primeira versao desta funcao, 31/08.)
    try:
        from app.update_check import current_version

        versao = current_version()
    except Exception:  # noqa: BLE001
        versao = "99.0.0"
    try:
        code, data = _rest_service("POST", "rpc/ativavid_license", {
            "p_action": "status", "p_device_id": device_id,
            "p_key": None, "p_app_version": versao,
        })
    except Exception:  # noqa: BLE001
        return ""
    if code >= 400 or not isinstance(data, dict):
        return ""
    if str(data.get("mode") or "") == "update_required":
        return ""   # o servidor respondeu sobre versao, nao sobre bloqueio
    if data.get("entitled"):
        return ("O computador foi marcado, mas o servidor ainda responde "
                "\"liberado\" para ele: só o app 4.27+ vai barrar. Aplique "
                "supabase/rpc_license.sql (SQL Editor → Run) para o "
                "bloqueio valer para qualquer versão.")
    return ""


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
    """As contas — e QUAIS PCs cada uma tem de verdade.

    A coluna "PCs" mostrava `max_devices` (o limite), e ele leu como "1 PC
    vinculado". Em 03/09 a conta leandro@ tinha limite 1 e ZERO PCs
    vinculados: o cliente nunca tinha entrado com o e-mail, e o painel nao
    tinha como dizer isso.
    """
    out = _rpc_admin("list_access")
    if not out.get("ok"):
        return out
    linhas = None
    for chave in ("access", "rows", "accounts", "items"):
        if isinstance(out.get(chave), list):
            linhas = out[chave]
            break
    if linhas is None:
        return out
    por_conta: dict[str, list[str]] = {}
    code, devs = _rest_service(
        "GET", "devices?select=device_id,account_access_id&account_access_id=not.is.null&limit=2000")
    if code < 400 and isinstance(devs, list):
        for d in devs:
            aid = str(d.get("account_access_id") or "")
            did = str(d.get("device_id") or "")
            if aid and did:
                por_conta.setdefault(aid, []).append(did)
        for r in linhas:
            ids = por_conta.get(str(r.get("id") or ""), [])
            r["devices"] = ids
            r["codigos"] = [codigo_do_pc(i) for i in ids]
    return out


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
    res = resolver_device_id(device_id)
    if not res.get("ok"):
        return res
    did = str(res["deviceId"])
    out = _rpc_admin(
        "grant_device",
        device_id=did,
        days=days,
        email=(email or "").strip().lower() or None,
        notes=notes,
    )
    if out.get("ok") and res.get("resolvido"):
        out["resolvidoDe"] = res.get("codigo")
        out["message"] = (f"Código {res.get('codigo')} = {did}. "
                          + str(out.get("message") or ""))
    return out


def release_device(device_id: str) -> dict[str, Any]:
    did = (device_id or "").strip()
    if not did:
        return {"ok": False, "error": "device_id_required", "message": "Informe o device id."}
    # Aqui o codigo curto so vale se for de UM PC conhecido; um id que nao
    # existe em lugar nenhum ainda pode ser apagado pelo nome cru (e assim
    # que se limpa um dispositivo fantasma como o `8372A270` de 03/09).
    if not _e_id_completo(did):
        res = resolver_device_id(did)
        if res.get("ok"):
            did = str(res["deviceId"])
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
