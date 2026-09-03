# -*- coding: utf-8 -*-
"""Trial so com cadastro; conta removida por inteiro no painel (4.94).

Ele em 03/09: "Quero liberar pra usar apenas com cadastro os novos
usuarios" e "quero apagar esses leandro@ativacrm.com nao apenas revogar".

O ponto perigoso do primeiro pedido esta no APP, nao no SQL: o app so
pergunta 'trial' uma vez (`trialAskedAt`) e o veredito "bloqueado" gruda
(`blockedAt`) e forca 'status' dali em diante. Se a recusa "crie sua
conta" marcasse qualquer um dos dois, o cliente se cadastrava e ficava
bloqueado para sempre — 'status' nunca cria trial.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402
from app import license_admin as la  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
SQL = (REPO / "supabase" / "rpc_license.sql").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")

RECUSA = {"entitled": False, "mode": "blocked", "error": "signup_required",
          "signupRequired": True, "trialDaysLeft": 0, "trialDaysTotal": 7,
          "message": "Crie sua conta (e-mail e senha) para começar os 7 dias grátis."}
TRIAL = {"entitled": True, "mode": "trial", "trialDaysLeft": 7, "trialDaysTotal": 7}


def _app(monkeypatch, respostas):
    """Um app com blob em memoria e um servidor que responde da lista."""
    blob = {}
    pedidos = []

    def veredito(acao):
        pedidos.append(acao)
        return dict(respostas.pop(0))

    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_load_blob", lambda: dict(blob))
    monkeypatch.setattr(lic, "_save_blob", lambda b: (blob.clear(), blob.update(b)))
    monkeypatch.setattr(lic, "_veredito", veredito)
    monkeypatch.setattr(lic, "_cache", lambda st: st)
    monkeypatch.setattr(lic, "_cache_intact", lambda b: True)
    monkeypatch.setattr(lic, "_relogio_voltou", lambda b: False)
    monkeypatch.setattr(lic, "device_id", lambda: "win-novo-0000")
    monkeypatch.setattr(lic, "_cfg", lambda: {"checkout": None, "mensal": None})
    monkeypatch.setattr(lic, "_app_version", lambda: "4.94")
    return blob, pedidos


def test_a_recusa_nao_gasta_o_pedido_de_trial(monkeypatch):
    blob, pedidos = _app(monkeypatch, [RECUSA, TRIAL])
    st = lic.entitlement(refresh=True)
    assert st["signupRequired"] and not st["entitled"]
    assert pedidos == ["trial"]
    assert not blob.get("trialAskedAt"), "a recusa nao pode marcar o pedido como feito"
    # ...cadastrou, entrou: o app pergunta 'trial' DE NOVO, e agora nasce
    st2 = lic.entitlement(refresh=True)
    assert st2["mode"] == "trial" and pedidos == ["trial", "trial"]
    assert blob.get("trialAskedAt"), "trial concedido: agora sim o pedido esta feito"


def test_com_o_bloqueio_grudado_a_acao_continua_sendo_trial(monkeypatch):
    """`blockedAt` gruda em qualquer 'blocked' (inclusive a recusa) e manda
    o app para o caminho online fixo. Esse caminho pedia 'status'."""
    blob, pedidos = _app(monkeypatch, [TRIAL])
    blob["blockedAt"] = "2026-09-03T00:00:00Z"
    st = lic.entitlement(refresh=False)
    assert pedidos == ["trial"] and st["mode"] == "trial"


def test_depois_do_trial_concedido_a_acao_e_status(monkeypatch):
    blob, pedidos = _app(monkeypatch, [{"entitled": True, "mode": "trial"}])
    blob["trialAskedAt"] = "2026-09-01T00:00:00Z"
    lic.entitlement(refresh=True)
    assert pedidos == ["status"]


def test_public_status_leva_o_sinal_para_a_tela(monkeypatch):
    monkeypatch.setattr(lic, "entitlement", lambda refresh=False: dict(RECUSA, configured=True))
    monkeypatch.setattr(lic, "_cfg", lambda: {"checkout": None, "mensal": None})
    st = lic.public_status()
    assert st["signupRequired"] is True and st["mode"] == "blocked"
    assert "Crie sua conta" in st["message"]


# ------------------------------------------------------------------ SQL
def test_o_sql_so_cria_trial_com_login():
    i = SQL.index("create or replace function public.ativavid_license(")
    fn = SQL[i:SQL.index("\n$$;", i)]
    assert "if not v_has_trial and p_action = 'trial' and v_jwt_uid is not null then" in fn
    assert "insert into trials (device_id, email) values (p_device_id, v_jwt_email)" in fn
    assert "v_signup := (not v_has_trial and v_jwt_uid is null);" in fn
    assert "'signupRequired', v_signup" in fn
    assert "'error', case when v_signup then 'signup_required' else null end" in fn
    assert "v_signup boolean := false;" in fn
    assert "alter table public.trials add column if not exists email text;" in SQL


def test_a_mensagem_de_cadastro_vem_antes_das_outras():
    fn = SQL[SQL.index("create or replace function public.ativavid_license("):]
    i = fn.index("'signupRequired', v_signup")
    bloco = fn[i:i + 400]
    assert "when v_signup then" in bloco and bloco.index("when v_signup") < bloco.index("when v_pending")


# ----------------------------------------------------------------- tela
def test_a_janela_vira_convite_de_cadastro():
    i = JS.index("function openLicenseDialog(")
    bloco = JS[i:JS.index("\nfunction openCheckout", i)]
    assert "L.signupRequired" in bloco
    assert "Crie sua conta para testar" in bloco
    assert '"Criar conta grátis"' in bloco
    assert 'login.dataset.modo = cadastro ? "signup" : "login"' in bloco
    j = JS.index('const btnDlgLogin = $("#btnLicDlgLogin");')
    assert 'openLoginDialog(btnDlgLogin.dataset.modo === "signup" ? "signup" : "login")' in JS[j:j + 600]


# ------------------------------------------------- remover conta inteira
def _servidor(monkeypatch, *, acessos, devices, usuarios):
    feito = {"patch": [], "remocoes": [], "logins_removidos": []}

    def rest(metodo, caminho, corpo=None):
        if metodo == "GET" and caminho.startswith("account_access"):
            return 200, [a for a in acessos]
        if metodo == "PATCH" and caminho.startswith("devices?account_access_id=eq."):
            aid = caminho.split("eq.")[1]
            feito["patch"].append((aid, corpo))
            return 200, [d for d in devices if d.get("account_access_id") == aid]
        if metodo == "DELETE" and caminho.startswith("account_access?email=eq."):
            feito["remocoes"].append(caminho)
            return 200, [a for a in acessos]
        return 404, {}

    def auth(metodo, caminho):
        if metodo == "GET" and caminho.startswith("users?"):
            return 200, {"users": usuarios}
        if metodo == "DELETE" and caminho.startswith("users/"):
            feito["logins_removidos"].append(caminho.split("/")[1])
            return 200, {}
        return 404, {}

    monkeypatch.setattr(la, "_rest_service", rest)
    monkeypatch.setattr(la, "_auth_admin", auth)
    monkeypatch.setattr(la, "_cfg", lambda: {"url": "u", "anon": "a", "service": "s"})
    return feito


def test_remover_conta_tira_liberacao_vinculo_e_login(monkeypatch):
    feito = _servidor(monkeypatch,
                      acessos=[{"id": "A1", "email": "leandro@ativacrm.com"}],
                      devices=[{"device_id": "win-1", "account_access_id": "A1"}],
                      usuarios=[{"id": "U1", "email": "Leandro@AtivaCRM.com"},
                                {"id": "U2", "email": "vitor@ativacrm.com"}])
    out = la.delete_account(email="leandro@ativacrm.com")
    assert out["ok"] and out["acessos"] == 1 and out["pcsDesvinculados"] == 1 and out["login"] is True
    assert feito["patch"] == [("A1", {"account_access_id": None})]
    assert feito["logins_removidos"] == ["U1"], "so o usuario daquele e-mail"
    assert "login removido" in out["message"]


def test_remover_conta_sem_login_ainda_funciona(monkeypatch):
    _servidor(monkeypatch, acessos=[{"id": "A1", "email": "x@y.z"}], devices=[], usuarios=[])
    out = la.delete_account(email="x@y.z")
    assert out["ok"] and out["login"] is False and "não tinha login" in out["message"]


def test_remover_conta_exige_email_e_service_role(monkeypatch):
    assert la.delete_account(email="")["error"] == "email_required"
    monkeypatch.setattr(la, "_cfg", lambda: {"url": "u", "anon": "a", "service": ""})
    assert la.delete_account(email="a@b.c")["error"] == "service_role_required"


def test_a_rota_e_o_botao_existem():
    i = SERVER.index('if action == "revoke":')
    bloco = SERVER[i:i + 600]
    assert 'if action == "delete":' in bloco and "la.delete_account(" in bloco
    j = JS.index("<th>E-mail</th><th>Status</th><th>Até</th><th>PCs</th>")
    bloco = JS[j:j + 5000]
    assert 'class="ghost-btn preset-del access-delete"' in bloco
    assert 'action: "delete"' in bloco
    assert "pedirConfirmacao(" in bloco and '"Apagar", true' in bloco
    assert ".access-table .cel-sub" in CSS, "'0 de 1nenhum PC' — a linha de baixo precisa da regra"
