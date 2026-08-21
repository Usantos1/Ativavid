"""Confere se o Supabase está com a configuração de licença correta.

Rode depois de mexer no projeto (SQL, secrets, Auth) para saber o que ainda
falta, em vez de descobrir por um cliente que não conseguiu usar o app.

    py tools/checar_licenca.py

Só LÊ. Nunca cria licença, nunca chama o webhook com POST (isso emitiria uma
chave), nunca imprime segredo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib import error, request

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import settings_store as ss  # noqa: E402

OK = "[ok]"
FALTA = "[FALTA]"
AVISO = "[aviso]"

problemas: list[str] = []
avisos: list[str] = []


def diz(marca: str, texto: str) -> None:
    print(f"  {marca} {texto}")


def _partes(v: str) -> list[int]:
    out = []
    for p in str(v or "").lstrip("vV").split("."):
        digitos = "".join(c for c in p if c.isdigit())
        out.append(int(digitos) if digitos else 0)
    return out


def _menor(a: str, b: str) -> bool:
    """a < b numericamente (2.50 > 0.1.24, e 2.5 < 2.46)."""
    if not a or not b:
        return False
    pa, pb = _partes(a), _partes(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return pa < pb


def http(method: str, url: str, headers: dict, body: dict | None = None, timeout: int = 20):
    raw = None if body is None else json.dumps(body).encode("utf-8")
    req = request.Request(url, data=raw, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(txt) if txt else {}
            except json.JSONDecodeError:
                return r.status, txt
    except error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(txt) if txt else {}
        except json.JSONDecodeError:
            return e.code, txt
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def main() -> int:
    s = ss.load_settings()
    url = str(s.get("supabaseUrl") or "").strip().rstrip("/")
    anon = str(s.get("supabaseAnonKey") or "").strip()
    service = str(s.get("supabaseServiceRoleKey") or "").strip()

    print("\n== Config local ==")
    if not url or not anon:
        diz(FALTA, "supabaseUrl/anonKey ausentes — nada a checar.")
        return 1
    diz(OK, f"projeto: {url}")
    diz(OK if ss.license_managed() else FALTA,
        "license_config.json embutido (build de venda liga o gate)")
    if not ss.bundled_raw().get("cacheSecret"):
        avisos.append("license_config.json sem cacheSecret")
    if not str(s.get("checkoutUrl") or "").strip():
        avisos.append("checkoutUrl vazio — o botão Assinar fica escondido")

    anon_h = {"apikey": anon, "Authorization": f"Bearer {anon}", "Content-Type": "application/json"}

    print("\n== Auth ==")
    code, data = http("GET", f"{url}/auth/v1/settings", {"apikey": anon})
    if code == 200 and isinstance(data, dict):
        autoconfirm = bool(data.get("mailer_autoconfirm"))
        if autoconfirm:
            diz(FALTA, "Confirm email DESLIGADO (mailer_autoconfirm=true)")
            problemas.append(
                "Ligue Confirm email: sem isso, alguém registra o e-mail de um "
                "cliente liberado e herda o acesso pago."
            )
        else:
            diz(OK, "Confirm email ligado")
        if data.get("disable_signup"):
            avisos.append("signup desabilitado — o cliente não consegue criar conta")
    else:
        avisos.append(f"não deu para ler /auth/v1/settings (HTTP {code})")

    print("\n== RPC de licença ==")
    code, data = http("POST", f"{url}/rest/v1/rpc/ativavid_license", anon_h, {
        "p_action": "status",
        "p_device_id": "diagnostico-somente-leitura",
        "p_key": None,
        "p_app_version": "0.0.1",
    })
    if code == 200 and isinstance(data, dict):
        diz(OK, "ativavid_license responde (assinatura de 4 args)")
        if "update" in data:
            diz(OK, "gate de versão presente no payload")
        else:
            problemas.append("RPC sem payload de update — rode supabase/rpc_license.sql")
        # 'status' não cria trial; device desconhecido tem de vir bloqueado.
        if data.get("entitled"):
            problemas.append("device desconhecido veio entitled — confira o rpc_license.sql")
        else:
            diz(OK, "device desconhecido vem bloqueado (status não cria trial)")
        # A versão que exige e-mail confirmado marca emailVerified no bloqueio.
        if "emailVerified" in json.dumps(data):
            diz(OK, "rpc_license.sql ATUAL (exige e-mail confirmado)")
        else:
            diz(FALTA, "rpc_license.sql desatualizado (casa conta por e-mail não confirmado)")
            problemas.append(
                "Rode supabase/rpc_license.sql de novo: a versão no ar ainda deixa "
                "alguém herdar o acesso de um cliente registrando o e-mail dele."
            )
    else:
        diz(FALTA, f"ativavid_license falhou (HTTP {code})")
        problemas.append("Rode supabase/rpc_license.sql no SQL Editor.")

    print("\n== RPC de admin ==")
    code, data = http("POST", f"{url}/rest/v1/rpc/ativavid_admin_license", anon_h, {
        "p_action": "whoami", "p_email": None, "p_days": 365, "p_max_devices": 1,
        "p_notes": None, "p_device_id": None, "p_license_key": None,
    })
    if code in (401, 403) or (isinstance(data, dict) and data.get("error") == "forbidden"):
        diz(OK, "ativavid_admin_license existe e recusa anônimo")
    elif code == 200 and isinstance(data, dict) and data.get("admin"):
        diz(FALTA, "ativavid_admin_license aceitou ANÔNIMO como admin")
        problemas.append("Gate de admin aberto — rode supabase/rpc_admin.sql.")
    elif code == 404:
        diz(FALTA, "ativavid_admin_license não existe")
        problemas.append("Rode supabase/rpc_admin.sql no SQL Editor.")
    else:
        diz(OK, f"ativavid_admin_license não libera anônimo (HTTP {code})")

    print("\n== Tabelas expostas ao anônimo (RLS) ==")
    for tabela in ("licenses", "account_access", "devices", "trials", "admins"):
        code, data = http("GET", f"{url}/rest/v1/{tabela}?select=*&limit=1", anon_h)
        if code == 200 and isinstance(data, list) and data:
            diz(FALTA, f"{tabela}: anônimo LEU dados")
            problemas.append(f"RLS de {tabela} deixa o anônimo ler — revise as policies.")
        else:
            diz(OK, f"{tabela}: anônimo não lê")

    print("\n== Edge Functions ==")
    # GET de propósito: POST no webhook emitiria uma licença na versão antiga.
    code, data = http("GET", f"{url}/functions/v1/payments-webhook", {"apikey": anon})
    if code == 0:
        avisos.append("não deu para alcançar payments-webhook")
    elif code == 404:
        diz(AVISO, "payments-webhook não deployada (sem cobrança automática)")
        avisos.append("payments-webhook não deployada — a venda não libera acesso sozinha")
    else:
        diz(OK, f"payments-webhook no ar (HTTP {code})")
        if isinstance(data, dict) and str(data.get("error")) == "method_not_allowed":
            diz(OK, "recusa GET, como esperado")

    code, data = http("GET", f"{url}/functions/v1/license", {"apikey": anon})
    if code == 404:
        diz(OK, "função license removida")
    elif code == 410:
        diz(OK, "função license aposentada (410)")
    else:
        diz(FALTA, f"função license ainda ativa (HTTP {code})")
        problemas.append(
            "A Edge Function 'license' ignora o force-update e o acesso por conta. "
            "Rode: supabase functions delete license"
        )

    if service:
        srv_h0 = {"apikey": service, "Authorization": f"Bearer {service}", "Accept": "application/json"}
        print("\n== Política de versão (app_config) ==")
        code, data = http("GET", f"{url}/rest/v1/app_config?select=*", srv_h0)
        if code == 200 and isinstance(data, list) and data:
            cfg = data[0]
            latest = str(cfg.get("latest_version") or "")
            minv = str(cfg.get("min_version") or "")
            local = (REPO / "VERSION").read_text(encoding="utf-8").strip()
            diz(OK, f"min={minv} · latest={latest} · app local={local}")
            if _menor(latest, local):
                diz(FALTA, f"latest_version ({latest}) atrás da versão publicada ({local})")
                problemas.append(
                    f"app_config parado em {latest} com o app em {local}. O download_url "
                    f"aponta para uma build antiga — se você subir min_version para forçar "
                    f"update, o cliente baixa a versão errada."
                )
            url_dl = str(cfg.get("download_url") or "")
            if url_dl and latest and latest not in url_dl:
                avisos.append("download_url não combina com latest_version")
        else:
            avisos.append(f"não deu para ler app_config (HTTP {code})")

        print("\n== Dados (service role) ==")
        srv_h = {"apikey": service, "Authorization": f"Bearer {service}", "Accept": "application/json"}
        for tabela in ("licenses", "account_access", "devices", "trials"):
            code, data = http("GET", f"{url}/rest/v1/{tabela}?select=*", {**srv_h, "Prefer": "count=exact"})
            n = len(data) if isinstance(data, list) else "?"
            diz(OK, f"{tabela}: {n} linha(s)")
        # Acesso liberado que ainda não vale: o rpc_license casa por user_id, e
        # esses registros não têm nenhum. O cliente paga e fica bloqueado.
        code, data = http(
            "GET",
            f"{url}/rest/v1/account_access?select=email,valid_until"
            f"&user_id=is.null&status=eq.active",
            srv_h,
        )
        if isinstance(data, list) and data:
            for row in data:
                diz(FALTA, f"acesso sem conta vinculada: {row.get('email')}")
            problemas.append(
                f"{len(data)} acesso(s) liberado(s) sem conta vinculada — o cliente fica "
                "bloqueado. Crie a conta dele e clique em Liberar de novo."
            )
        else:
            diz(OK, "todo acesso liberado está vinculado a uma conta")

        code, data = http(
            "GET",
            f"{url}/rest/v1/licenses?select=provider,provider_ref&provider_ref=not.is.null",
            srv_h,
        )
        if isinstance(data, list):
            refs = [(d.get("provider"), d.get("provider_ref")) for d in data]
            dups = len(refs) - len(set(refs))
            if dups:
                diz(FALTA, f"{dups} licença(s) duplicada(s) por provider_ref")
                problemas.append("Limpe as duplicadas antes de criar o índice único.")
            else:
                diz(OK, "sem licença duplicada por provider_ref")

    print("\n" + "=" * 60)
    if problemas:
        print("PENDENTE:")
        for p in problemas:
            print(f"  - {p}")
    else:
        print("Nenhuma pendência bloqueante.")
    if avisos:
        print("\nAvisos:")
        for a in avisos:
            print(f"  - {a}")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
