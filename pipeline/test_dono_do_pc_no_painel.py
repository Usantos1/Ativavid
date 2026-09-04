# -*- coding: utf-8 -*-
"""De quem e este PC? (4.93)

Ele em 03/09, com a tela de Licenca na frente: "esse tem conta de email e
nao exibe ali e nao consigo validar o plano dele". Os dados do servidor
contavam a historia inteira:

  - o painel mostra ao cliente o CODIGO CURTO (`8372A270`), o cliente
    manda o codigo, e o "Liberar dispositivo" aceitava qualquer texto —
    nasceu um dispositivo fantasma chamado `8372A270`, liberado e depois
    bloqueado, enquanto o PC de verdade (`win-8372a270-ab08-…`) seguia em
    trial;
  - a lista "Quem esta liberado" so mostrava o dono quando o vinculo era
    por CONTA: PC liberado pelo ID com e-mail preenchido saia "Dono —";
  - a tabela de maquinas so sabia o que o log de aberturas contava, e o
    log nao carregava e-mail;
  - a coluna "PCs" das contas mostrava o LIMITE (1), lido como "1 PC
    vinculado" — a conta tinha zero.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license_admin as la  # noqa: E402
from app import registro_de_uso as reg  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SQL = (REPO / "supabase" / "registro_de_uso.sql").read_text(encoding="utf-8")

REAL = "win-8372a270-ab08-45ee-a444-eaab6a7705cc"


def _servidor(monkeypatch, *, devices=(), trials=(), aberturas=(), donos=None):
    """Um Supabase de mentira: devolve por prefixo de caminho."""
    chamadas = []

    def rest(metodo, caminho, corpo=None):
        chamadas.append((metodo, caminho, corpo))
        if caminho.startswith("devices?select=device_id,host,os_user,account_access_id"):
            if ",email&" in caminho and donos is None:
                return 400, {"message": "column devices.email does not exist"}
            return 200, list(donos or [])
        if caminho.startswith("devices?select=device_id,account_access_id"):
            return 200, [d for d in devices if d.get("account_access_id")]
        if caminho.startswith("devices"):
            return 200, list(devices)
        if caminho.startswith("trials"):
            return 200, list(trials)
        if caminho.startswith("aberturas"):
            return 200, list(aberturas)
        return 404, {}

    monkeypatch.setattr(la, "_rest_service", rest)
    return chamadas


# --------------------------------------------------------- o codigo curto
def test_o_codigo_curto_e_o_mesmo_da_tela():
    assert la.codigo_do_pc(REAL) == "8372A270"
    assert la.codigo_do_pc("8372A270") == "8372A270"
    assert la.codigo_do_pc("av-abcdef12-9") == "ABCDEF12"
    assert la.codigo_do_pc("") == ""
    # a regra do studio.js, palavra por palavra
    i = JS.index("function codigoDoPc(")
    bloco = JS[i:JS.index("\n}", i)]
    assert 'replace(/^(win|av)-/i, "")' in bloco and "slice(0, 8).toUpperCase()" in bloco


def test_o_codigo_curto_vira_o_id_completo(monkeypatch):
    _servidor(monkeypatch, devices=[{"device_id": REAL}],
              trials=[{"device_id": REAL}], aberturas=[])
    r = la.resolver_device_id("8372a270")
    assert r["ok"] and r["deviceId"] == REAL and r["resolvido"] is True
    r = la.resolver_device_id(REAL)
    assert r["ok"] and r["deviceId"] == REAL and r["resolvido"] is False


def test_codigo_que_o_servidor_nunca_viu_nao_vira_fantasma(monkeypatch):
    _servidor(monkeypatch, devices=[{"device_id": REAL}])
    r = la.resolver_device_id("ZZZZ9999")
    assert not r["ok"] and r["error"] == "codigo_desconhecido"
    assert "ZZZZ9999" in r["message"] and "win-" in r["message"]


def test_codigo_ambiguo_pede_o_id_completo(monkeypatch):
    _servidor(monkeypatch, devices=[{"device_id": REAL},
                                    {"device_id": "win-8372a270-0000-0000-0000-000000000000"}])
    r = la.resolver_device_id("8372A270")
    assert not r["ok"] and r["error"] == "codigo_ambiguo" and "2" in r["message"]


def test_o_fantasma_da_lista_nao_conta_como_pc(monkeypatch):
    """O `8372A270` que ja existe na tabela devices nao pode ser a resposta
    para o codigo `8372A270` — e o proprio erro, nao o PC."""
    _servidor(monkeypatch, devices=[{"device_id": "8372A270"}, {"device_id": REAL}])
    assert la.resolver_device_id("8372A270")["deviceId"] == REAL


def test_liberar_e_bloquear_aceitam_o_codigo(monkeypatch):
    _servidor(monkeypatch, devices=[{"device_id": REAL}])
    chamadas = {}

    def rpc(action, **kw):
        chamadas[action] = kw
        return {"ok": True, "message": "Dispositivo liberado até 03/09/2027."}

    monkeypatch.setattr(la, "_rpc_admin", rpc)
    out = la.grant_device(device_id="8372A270", days=365, email="leandro@ativacrm.com")
    assert chamadas["grant"]["device_id"] == REAL if "grant" in chamadas else chamadas["grant_device"]["device_id"] == REAL
    assert out["ok"] and out["resolvidoDe"] == "8372A270" and REAL in out["message"]

    posts = []
    real_rest = la._rest_service

    def rest(metodo, caminho, corpo=None):
        if caminho == "rpc/ativavid_block_device":
            posts.append(corpo)
            return 200, {"ok": True}
        return real_rest(metodo, caminho, corpo)

    monkeypatch.setattr(la, "_rest_service", rest)
    monkeypatch.setattr(la, "_cfg", lambda: {"url": "u", "anon": "a", "service": "s"})
    monkeypatch.setattr(la, "_servidor_ignora_o_bloqueio", lambda did: "")
    out = la.block_device("8372a270", block=True, reason="teste")
    assert out["ok"] and out["deviceId"] == REAL
    assert posts and posts[0]["p_device_id"] == REAL


def test_liberar_com_codigo_desconhecido_nao_chama_o_servidor(monkeypatch):
    _servidor(monkeypatch, devices=[])
    monkeypatch.setattr(la, "_rpc_admin", lambda *a, **k: 1 / 0)
    out = la.grant_device(device_id="8372A270")
    assert not out["ok"] and out["error"] == "codigo_desconhecido"


# ------------------------------------------------------------ o dono
def _donos_reais():
    return [
        {"device_id": REAL, "host": "8372A270-PC", "os_user": "leandro",
         "account_access_id": None, "license_id": "L1",
         "licenses": {"email": "leandro@ativacrm.com"}, "account_access": None},
        {"device_id": "win-conta-0000-0000-0000-000000000000", "host": None, "os_user": None,
         "account_access_id": "A1", "license_id": None,
         "licenses": None, "account_access": {"email": "vitor@ativacrm.com"}},
    ]


def test_o_dono_vem_do_email_da_liberacao_quando_nao_ha_conta(monkeypatch):
    _servidor(monkeypatch, donos=_donos_reais())
    monkeypatch.setattr(la, "_list_devices_cru", lambda *a, **k: {"ok": True, "devices": [
        {"device_id": REAL, "account_email": None, "label": None},
        {"device_id": "win-conta-0000-0000-0000-000000000000", "account_email": "vitor@ativacrm.com"},
    ]})
    devs = {d["device_id"]: d for d in la.list_devices()["devices"]}
    assert devs[REAL]["email"] == "leandro@ativacrm.com"
    assert devs[REAL]["codigo"] == "8372A270"
    assert devs["win-conta-0000-0000-0000-000000000000"]["email"] == "vitor@ativacrm.com"


def test_a_conta_vinculada_ganha_do_email_da_liberacao(monkeypatch):
    donos = _donos_reais()
    donos[0]["account_access"] = {"email": "conta@x.com"}
    _servidor(monkeypatch, donos=donos)
    assert la._donos_por_device()[REAL]["email"] == "conta@x.com"


def test_banco_sem_a_coluna_email_ainda_lista(monkeypatch):
    """Sem o SQL da 4.93 o PostgREST responde 400 para `email`; a lista
    tem de sair do mesmo jeito, so sem o terceiro palpite."""
    chamadas = _servidor(monkeypatch, donos=None)
    # donos=None faz a primeira consulta (com email) falhar com 400
    monkeypatch.setattr(la, "_rest_service", lambda m, c, b=None: (
        (400, {"message": "column devices.email does not exist"}) if ",email&" in c
        else (200, _donos_reais())))
    assert la._donos_por_device()[REAL]["email"] == "leandro@ativacrm.com"
    del chamadas


def test_a_maquina_mostra_o_email_mesmo_sem_abertura_no_log(monkeypatch):
    _servidor(monkeypatch,
              aberturas=[],
              trials=[{"device_id": REAL, "started_at": "2026-09-03T20:12:54+00:00"}],
              devices=[{"device_id": REAL, "license_id": "L1", "blocked_at": None,
                        "last_seen": "2026-09-03T21:17:45+00:00"}],
              donos=_donos_reais())
    m = {x["deviceId"]: x for x in la.list_aberturas()["maquinas"]}[REAL]
    assert m["aberturas"] == 0 and m["semRegistro"] is True
    assert m["email"] == "leandro@ativacrm.com"
    assert m["host"] == "8372A270-PC" and m["usuario"] == "leandro", "host/usuario do devices"
    assert m["codigo"] == "8372A270"


def test_o_email_da_abertura_conta_quando_o_servidor_nao_tem_dono(monkeypatch):
    _servidor(monkeypatch,
              aberturas=[{"device_id": "win-trial-0000-0000-0000-000000000000",
                          "criado_em": "2026-09-03T10:00:00+00:00",
                          "email": "trial@x.com"}],
              trials=[], devices=[], donos=[])
    m = la.list_aberturas()["maquinas"][0]
    assert m["email"] == "trial@x.com"


def test_as_contas_dizem_quais_pcs_tem_de_verdade(monkeypatch):
    _servidor(monkeypatch, devices=[
        {"device_id": "win-conta-0000-0000-0000-000000000000", "account_access_id": "A1"},
        {"device_id": REAL, "account_access_id": None},
    ])
    monkeypatch.setattr(la, "_rpc_admin", lambda *a, **k: {"ok": True, "access": [
        {"id": "A1", "email": "vitor@ativacrm.com", "max_devices": 1},
        {"id": "A2", "email": "leandro@ativacrm.com", "max_devices": 1},
    ]})
    contas = {r["email"]: r for r in la.list_access()["access"]}
    assert contas["vitor@ativacrm.com"]["devices"] == ["win-conta-0000-0000-0000-000000000000"]
    assert contas["vitor@ativacrm.com"]["codigos"] == ["CONTA"]
    assert contas["leandro@ativacrm.com"]["devices"] == [], "o caso dele: limite 1, vinculados 0"


# --------------------------------------------------- o e-mail na abertura
def test_a_abertura_manda_o_email_logado(monkeypatch):
    from app import license as lic

    envios = []
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_http_rpc", lambda payload, fn="": (envios.append((fn, payload)) or (200, {})))
    reg._avisar_servidor({"device": "X", "versao": "4.93", "email": "Leandro@AtivaCRM.com"})
    assert len(envios) == 1
    fn, payload = envios[0]
    assert fn == "ativavid_open" and payload["p_email"] == "leandro@ativacrm.com"


def test_servidor_antigo_recebe_a_abertura_sem_o_email(monkeypatch):
    """Funcao ainda com 6 argumentos: o PostgREST devolve 404 (PGRST202)
    para a chamada com `p_email`; a abertura tem de chegar mesmo assim."""
    from app import license as lic

    envios = []

    def rpc(payload, fn=""):
        envios.append(payload)
        return (404, {"code": "PGRST202"}) if "p_email" in payload else (200, {})

    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_http_rpc", rpc)
    reg._avisar_servidor({"device": "X", "email": "a@b.c"})
    assert len(envios) == 2 and "p_email" not in envios[1]


def test_sem_email_logado_manda_uma_vez_so(monkeypatch):
    from app import license as lic

    envios = []
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_http_rpc", lambda payload, fn="": (envios.append(payload) or (200, {})))
    reg._avisar_servidor({"device": "X", "email": ""})
    assert len(envios) == 1 and "p_email" not in envios[0]


def test_o_sql_derruba_a_assinatura_antiga_antes_de_criar_a_nova():
    """Duas assinaturas com parametros opcionais deixam o PostgREST
    ambiguo (ja mordeu na 4.27)."""
    assert "drop function if exists public.ativavid_open(text, text, text, text, text, text);" in SQL
    i = SQL.index("create or replace function public.ativavid_open(")
    assert SQL.index("drop function if exists public.ativavid_open(") < i
    bloco = SQL[i:SQL.index("$$;", i)]
    assert "p_email" in bloco and "email" in bloco
    assert "add column if not exists email text" in SQL
    assert "grant execute on function public.ativavid_open(text, text, text, text, text, text, text)" in SQL


def test_a_validacao_anota_o_email_logado_no_pc():
    """O caso de 03/09: cliente logado com leandro@plusmidia… num PC em
    trial, liberacao em OUTRO e-mail, app sem registro de abertura. So a
    `ativavid_license` (que TODA versao chama) sabe quem esta logado."""
    lic_sql = (REPO / "supabase" / "rpc_license.sql").read_text(encoding="utf-8")
    assert "alter table public.devices add column if not exists email text;" in lic_sql
    i = lic_sql.index("create or replace function public.ativavid_license(")
    fn = lic_sql[i:lic_sql.index("\n$$;", i)]
    j = fn.index("update devices set email = v_jwt_email")
    bloco = fn[j - 200:j + 300]
    assert "where device_id = p_device_id" in bloco
    assert "exception when others" in bloco, "coluna ausente nao pode derrubar a licenca"
    # anota ANTES de decidir acesso, e nao decide nada
    assert j < fn.index("IDENTIDADE É O user_id DO JWT")
    assert "insert into devices" not in bloco, "PC em trial nao vira device"


# ------------------------------------------------------------- a tela
def test_a_lista_de_liberados_mostra_o_dono_pelo_email():
    i = JS.index("function renderDeviceList(")
    bloco = JS[i:JS.index("\nasync function loadDeviceList", i)]
    assert "r.account_email || r.email || r.label" in bloco
    assert "codigoDoPc(id)" in bloco, "o codigo curto que o cliente le tem de aparecer na lista"


def test_a_tabela_de_maquinas_mostra_o_email():
    i = JS.index("async function loadAberturas()")
    bloco = JS[i:JS.index("\nfunction wireAberturas", i)]
    assert "m.email || m.host" in bloco


def test_as_contas_mostram_vinculados_sobre_o_limite():
    i = JS.index("function renderAccessList(") if "function renderAccessList(" in JS else JS.index("<th>E-mail</th><th>Status</th><th>Até</th><th>PCs</th>")
    bloco = JS[i:i + 6000]
    assert "r.devices" in bloco and "de ${escapeHtml(limite)}" in bloco
    assert "nenhum PC entrou com esta conta" in bloco


def test_o_dialogo_avisa_que_o_codigo_curto_serve():
    i = HTML.index('id="adminDeviceForm"')
    bloco = HTML[i:i + 1500]
    assert "código curto" in bloco and "8372A270" in bloco



def test_a_abertura_leva_o_email_logado_mesmo_sem_licenca_por_conta(monkeypatch):
    """5.0.15: trial/bloqueado/chave abriam com e-mail vazio; o logado vale."""
    from app import registro_de_uso as ru
    from app import license as lic
    from app import auth as au
    monkeypatch.setattr(lic, "entitlement", lambda refresh=False: {"mode": "trial", "entitled": True})
    monkeypatch.setattr(lic, "device_id", lambda: "win-teste")
    monkeypatch.setattr(lic, "_app_version", lambda: "5.0.15")
    monkeypatch.setattr(au, "_load", lambda: {"email": "Vitor@PrimeCamp.com", "access_token": "x"})
    d = ru.dados_da_maquina()
    assert d["email"] == "vitor@primecamp.com"
    monkeypatch.setattr(lic, "entitlement", lambda refresh=False: {"mode": "account", "entitled": True, "accountEmail": "dono@x.com"})
    assert ru.dados_da_maquina()["email"] == "dono@x.com", "a conta liberada continua mandando"
    monkeypatch.setattr(au, "_load", lambda: {})
    monkeypatch.setattr(lic, "entitlement", lambda refresh=False: {"mode": "blocked"})
    assert ru.dados_da_maquina()["email"] == ""
