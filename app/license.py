"""Licença / trial ATIVAVID — cliente local + Supabase RPC.

Sem supabaseUrl configurado: aberto em dev, BLOQUEADO em build de cliente.
Com URL → trial 7 dias, chave anual ou acesso por conta (gate no do_POST).
Gate de versão: resposta `update.force` trava builds abaixo de min_version.

O cache local é assinado (HMAC): editar `entitled` no license.json deixou de
render licença. Não é à prova de quem lê o código — nada client-side é —, mas
tira o bypass do alcance de um editor de texto.
"""
from __future__ import annotations

import hashlib
import hmac
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


def _cache_key() -> bytes | None:
    """Segredo de assinatura do cache.

    Vem do license_config.json da build (não versionado), então cada build tem
    o seu e o valor não está no código público. Em dev cai num padrão — lá o
    cache não protege nada mesmo.
    """
    cfg = ss.bundled_raw()
    seed = str(cfg.get("cacheSecret") or "")
    if not seed and not ss.is_dev_install():
        # Sem cacheSecret numa build de cliente, o fallback antigo era a
        # anon key — que e PUBLICA e vai embutida no proprio cliente, entao
        # a assinatura virava forjavel por qualquer um. O build.ps1 barra
        # build sem cacheSecret, mas quem burlasse o script ganhava um
        # cache "assinado" de mentira. None = nenhuma cache e confiada.
        return None
    return ("ativavid-cache-v1|" + (seed or "dev")).encode("utf-8")


def _sign_cache(blob: dict[str, Any]) -> str | None:
    cached = blob.get("cached")
    if not isinstance(cached, dict):
        return None
    payload = {
        "cached": cached,
        "cachedAt": blob.get("cachedAt"),
        # Amarra ao device: copiar o license.json de outra máquina não vale.
        "deviceId": blob.get("deviceId"),
    }
    # Campos novos entram na assinatura SO quando existem: assim o
    # license.json de quem ja esta instalado continua valendo depois de
    # atualizar (senao a atualizacao exigiria internet para abrir). Tirar
    # um deles a mao muda o payload e quebra a assinatura, que e o ponto.
    for extra in ("maxSeenAt", "blockedAt"):
        if blob.get(extra):
            payload[extra] = blob[extra]
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    chave = _cache_key()
    if chave is None:
        return None  # build sem cacheSecret: nenhum cache e assinado nem aceito
    return hmac.new(chave, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _cache_intact(blob: dict[str, Any]) -> bool:
    """False se o cache foi editado à mão (ou é de uma versão sem assinatura)."""
    sig = str(blob.get("sig") or "")
    expected = _sign_cache(blob)
    if not sig or not expected:
        return False
    return hmac.compare_digest(sig, expected)


def _save_blob(data: dict[str, Any]) -> None:
    LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    sig = _sign_cache(data)
    if sig:
        data["sig"] = sig
    else:
        data.pop("sig", None)
    LICENSE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


_REG_KEY = r"Software\ATIVAVID"


def _reg_device_id() -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            val, _ = winreg.QueryValueEx(key, "DeviceId")
        return str(val or "").strip() or None
    except OSError:
        return None


def _reg_set_device_id(did: str) -> None:
    if os.name != "nt" or not did:
        return
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            winreg.SetValueEx(key, "DeviceId", 0, winreg.REG_SZ, did)
    except OSError:
        pass


def device_id() -> str:
    blob = _load_blob()
    did = str(blob.get("deviceId") or "").strip()
    if did:
        _reg_set_device_id(did)
        return did
    # Segunda cópia no registro: quando o MachineGuid não existe, o id caía num
    # uuid guardado só no license.json — apagar o arquivo dava trial novo, sem
    # limite. O registro sobrevive a isso.
    did = _reg_device_id() or _machine_guid() or ("av-" + uuid.uuid4().hex)
    blob["deviceId"] = did
    _save_blob(blob)
    _reg_set_device_id(did)
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
        "mensal": str(s.get("checkoutUrlMensal") or "").strip(),
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
        # 5.0.41: SHA-256 do instalador publicado. O app confere o arquivo
        # baixado antes de executar; sem o campo (política antiga), passa.
        "downloadSha256": (str(raw.get("downloadSha256") or "").strip().lower() or None),
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


def _http_rpc(payload: dict[str, Any], fn: str = "ativavid_license") -> tuple[int, Any]:
    """`fn` existe para o registro de abertura (`ativavid_open`) usar o
    mesmo transporte sem virar mais uma assinatura de `ativavid_license` —
    duas funcoes com parametros opcionais deixam o PostgREST ambiguo, e foi
    por isso que a versao de 3 argumentos precisou ser derrubada."""
    c = _cfg()
    endpoint = f"{c['url']}/rest/v1/rpc/{fn}"
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


def _device_bloqueado() -> bool:
    """Esta maquina esta na lista de bloqueio do servidor?

    A `ativavid_license` do banco NAO consulta isso (medido em 30/08:
    bloquear um device nao mudava uma virgula da resposta dela). Enquanto
    o servidor nao checar, quem checa e o cliente — com a mesma funcao,
    que ja existe no banco.

    Falha de rede devolve False de proposito: uma consulta que nao
    respondeu nao pode barrar cliente pagante.
    """
    try:
        code, data = _http_rpc({"p_device_id": device_id()},
                               fn="ativavid_device_blocked")
    except Exception:  # noqa: BLE001
        return False
    if code >= 400:
        return False
    return data is True or str(data).strip().lower() == "true"


# De quanto em quanto tempo o cache bom ainda pergunta "fui bloqueado?".
# O cache de licenca dura 30 min de proposito (o app consulta o gate em
# toda rota); manter o bloqueio refem desses 30 min dava meia hora de
# trabalho a uma maquina ja barrada no painel — foi o que ele viu em
# 31/08. A consulta e uma linha no banco e roda no maximo a cada 5 min.
_MIN_ENTRE_CHECAGENS_DE_BLOQUEIO = 5 * 60


def _veredito(action: str) -> dict[str, Any]:
    """Resposta do servidor JA com o bloqueio por maquina aplicado.

    Existia em um caminho so (o principal). Os outros dois — cache de 30
    min vencido com `blockedAt` grudado, e relogio para tras — pediam
    `_call("status")` cru: como a `ativavid_license` respondia
    `entitled: true` para maquina bloqueada, a primeira checagem online
    LIMPAVA o bloqueio grudado (`_cache` apaga `blockedAt` quando o
    veredito vem liberado). Bloqueava, e alguns minutos depois o PC
    voltava a trabalhar sozinho.
    """
    remote = _call(action)
    if remote.get("entitled") and not remote.get("offline") and _device_bloqueado():
        remote = dict(remote)
        remote["entitled"] = False
        remote["mode"] = "blocked"
        remote["error"] = "device_blocked"
        remote["message"] = (
            "Este computador foi bloqueado. Fale com o suporte do ATIVAVID.")
    return remote


def _bloqueio_com_cache_bom(blob: dict[str, Any]) -> bool:
    """Pergunta o bloqueio mesmo servindo do cache, no maximo 1x/5min."""
    ultima = str(blob.get("blockedCheckAt") or "")
    if ultima:
        try:
            ts = datetime.fromisoformat(ultima.replace("Z", "+00:00"))
            idade = (datetime.now(timezone.utc) - ts).total_seconds()
            # Data no futuro (relogio mexido) conta como vencida.
            if 0 <= idade < _MIN_ENTRE_CHECAGENS_DE_BLOQUEIO:
                return False
        except ValueError:
            pass
    bloqueado = _device_bloqueado()
    novo = _load_blob()
    novo["blockedCheckAt"] = _utc()
    if bloqueado:
        novo["blockedAt"] = _utc()
    _save_blob(novo)
    return bloqueado


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
    if _cache_intact(blob) and blob.get("blockedAt"):
        # Bloqueado pelo servidor: cache antigo nao ressuscita a licenca.
        return {
            "entitled": False,
            "mode": "blocked",
            "error": "device_blocked",
            "message": ("Este computador foi bloqueado. Fale com o suporte "
                        "do ATIVAVID."),
            "detail": err,
        }
    if _cache_intact(blob) and _relogio_voltou(blob):
        return {
            "entitled": False,
            "mode": "blocked",
            "error": "clock_rollback",
            "message": ("A data do computador está atrás da última vez que "
                        "o ATIVAVID rodou. Acerte o relógio e conecte-se à "
                        "internet para validar a licença."),
            "detail": err,
        }
    if isinstance(cached, dict) and cached_at and not _cache_intact(blob):
        return {
            "entitled": False,
            "mode": "blocked",
            "error": "cache_tampered",
            "message": "Não foi possível validar a licença guardada. Conecte-se à internet.",
            "detail": err,
        }
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


def _marcar_hora(blob: dict[str, Any]) -> dict[str, Any]:
    """Guarda a MAIOR hora que este app ja viu.

    A janela offline mede `agora - cachedAt`. Sem isto, atrasar o relogio
    do Windows deixa a conta abaixo de 72h para sempre — e o cache, que e
    assinado contra edicao, nao protegia a hora da propria maquina.
    """
    agora = _utc()
    if str(blob.get("maxSeenAt") or "") < agora:
        blob["maxSeenAt"] = agora
    return blob


def _relogio_voltou(blob: dict[str, Any]) -> bool:
    """A maquina esta antes da ultima hora que o app viu? (5 min de folga
    para fuso e acerto de NTP.)"""
    marca = str(blob.get("maxSeenAt") or "")
    if not marca:
        return False
    try:
        ts = datetime.fromisoformat(marca.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - ts).total_seconds() < -300


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
    blob = _marcar_hora(_load_blob())
    blob["deviceId"] = device_id()
    # Veredito de bloqueio do SERVIDOR gruda. Sem isto bastava puxar o
    # cabo depois de ser bloqueado: o fallback offline voltava ao ultimo
    # cache bom e liberava por mais 72h.
    if status.get("mode") == "blocked" and not status.get("offline"):
        blob["blockedAt"] = _utc()
    elif status.get("entitled"):
        blob.pop("blockedAt", None)
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


def _acao_inicial(blob: dict[str, Any]) -> str:
    """'trial' ate o servidor responder sobre o trial deste PC; depois 'status'.

    Desde a 4.94 o trial so nasce com CADASTRO: o primeiro contato sem
    login volta `signupRequired` e o pedido fica em aberto — a proxima
    consulta (depois de criar a conta) pergunta 'trial' de novo. Se
    marcasse `trialAskedAt` na recusa, o cliente se cadastrava e ficava
    bloqueado para sempre, porque 'status' nunca cria trial.
    """
    return "trial" if not blob.get("trialAskedAt") else "status"


def _marcar_trial_pedido(remote: dict[str, Any]) -> None:
    if remote.get("error") or remote.get("signupRequired"):
        return
    blob = _load_blob()
    if not blob.get("trialAskedAt"):
        blob["trialAskedAt"] = _utc()
        _save_blob(blob)


def _carimbar(status: dict[str, Any]) -> dict[str, Any]:
    """Os campos que TODA resposta de `entitlement` leva.

    O caminho do bloqueio grudado devolvia o veredito cru, sem
    `configured`, `deviceId` nem `checkoutUrl`. A tela lia
    `configured=false` e escrevia "Modo aberto — licença não exigida"
    num PC bloqueado, sem os planos, sem o modal e sem o código do
    computador para mandar ao suporte (caso do vitor@primecamp.com,
    04/09: trial vencido + conta recém-criada).
    """
    status["ok"] = True
    status["deviceId"] = device_id()
    status["checkoutUrl"] = _cfg()["checkout"] or None
    status["configured"] = True
    status["appVersion"] = _app_version()
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
    if _cache_intact(blob) and (blob.get("blockedAt") or _relogio_voltou(blob)):
        # Nem o cache de 30 minutos vale: os dois casos exigem uma resposta
        # ONLINE para voltar a liberar — e ela ja vem com o bloqueio por
        # maquina aplicado, senao "voltar a liberar" era automatico.
        # `blockedAt` tambem gruda na recusa "crie sua conta": por isso a
        # acao aqui e a inicial, e nao 'status' fixo — senao o cadastro
        # nunca chegava a pedir o trial.
        remote = _veredito(_acao_inicial(blob))
        _marcar_trial_pedido(remote)
        return _carimbar(_cache(remote))
    if (
        not refresh
        and isinstance(blob.get("cached"), dict)
        and blob.get("cachedAt")
        and _cache_intact(blob)
    ):
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
                # Antes de entregar o cache bom: este PC foi bloqueado nos
                # ultimos minutos? Sem esta pergunta, bloquear no painel so
                # valia depois que o cache de 30 min vencesse.
                if _bloqueio_com_cache_bom(blob):
                    return _cache(_veredito("status"))
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
    remote = _veredito(_acao_inicial(blob))
    _marcar_trial_pedido(remote)
    if remote.get("error") and remote.get("mode") not in ("blocked", "update_required"):
        remote = _veredito("status")
    # O bloqueio por maquina ja veio aplicado por `_veredito` — em TODOS os
    # caminhos, nao so neste.
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
    # Medicoes de LEITURA da propria maquina: o card de Desempenho, o
    # espaco e o cache. Quem esta bloqueado ainda precisa ver o estado do
    # computador — e `hardware/bench` (que MEDE) ja era livre enquanto
    # `hardware` (que so LE o resultado) nao era.
    "/api/hardware",
    "/api/espaco",
    "/api/espaco/liberar",
    "/api/cache",
    "/api/llm-gateway",
    # /v1/chat/completions NAO entra: e um endpoint OpenAI-compativel
    # completo — livre, um PC bloqueado viraria proxy de LLM gratis (a
    # sessao Gemini/ChatGPT capturada respondendo para qualquer cliente
    # apontado ao localhost). O pipeline nao passa por aqui: ele chama
    # llm_gateway como modulo. So o botao "Testar" da tela IA usa a rota,
    # e quem esta bloqueado nao tem por que testar IA.
    "/api/jobs/open-folder",
    "/api/jobs/open-final",
    # Mesma familia: so ABRE um arquivo que ja existe. E quando alguem esta
    # bloqueado e algo deu errado, o log e justamente o que ele precisa
    # mandar para o suporte.
    "/api/jobs/open-log",
    "/api/jobs/rename",
    "/api/jobs/cancel",
    "/api/jobs/delete",
    # Mesmas ações, nomes do preview_server: quem está bloqueado ainda precisa
    # alcançar os vídeos que já produziu. /api/project/action só abre pasta,
    # abre o vídeo e conserta o ponteiro do arquivo final — não edita nada.
    "/api/open-folder",
    "/api/open-final",
    "/api/style-export",
    "/api/project/action",
})
_GATE_FREE_PREFIX = (
    "/api/auth/",
    "/api/license/",
    "/api/admin/",
    "/api/update/",
    "/api/llm-proxy",
    # /api/library/ saiu da lista: as LEITURAS sao GET (o gate so roda no
    # POST), e as escritas — add, upload, use, remover, categoria — sao
    # mutacao de projeto/biblioteca que nao deve rodar sem licenca. `use`
    # em particular copia bytes arbitrarios para dentro do projeto.
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
        # 4.94: trial so com cadastro — a tela abre "Criar conta" em vez
        # de "bloqueado".
        "signupRequired": bool(st.get("signupRequired")),
        # Os DOIS links saem da mesma fonte (`_cfg`, que le a config
        # empacotada). Ate a 4.44 o anual vinha carona no payload do
        # entitlement e o mensal da config: dois caminhos para a mesma
        # coisa e um deles podia faltar sem ninguem notar.
        "checkoutUrl": st.get("checkoutUrl") or _cfg().get("checkout") or None,
        "checkoutUrlMensal": _cfg().get("mensal") or None,
        "deviceId": st.get("deviceId"),
        "offline": st.get("offline"),
        "appVersion": st.get("appVersion") or _app_version(),
        "update": upd,
    }
