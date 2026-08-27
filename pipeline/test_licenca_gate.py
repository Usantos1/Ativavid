"""Gate de licença: as regressões que deixavam o app rodar sem assinatura.

Cada teste aqui corresponde a um bypass real que já existiu:
não pagar apagando a URL, editar o cache local, cair numa rota sem gate,
ou mandar POST a partir de um site aberto no navegador.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import http_guard as guard  # noqa: E402
from app import license as lic  # noqa: E402


def _utc(delta_h: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=delta_h)).isoformat()


@pytest.fixture
def blob(tmp_path: Path, monkeypatch):
    """Aponta o license.json para tmp — nunca mexer no do usuário."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")

    def write(cached: dict, cached_at: str):
        lic._save_blob({"deviceId": "dev-test", "cached": cached, "cachedAt": cached_at})

    return write


# --- gate por exclusão ----------------------------------------------------


@pytest.mark.parametrize("path", [
    "/api/auth/login",
    "/api/auth/signup",
    "/api/license/activate",
    "/api/license/refresh",
    "/api/settings",
    "/api/admin/access",
    "/api/jobs/open-folder",
    "/api/jobs/delete",
    "/api/settings?x=1",
])
def test_rotas_para_sair_do_bloqueio_ficam_livres(path):
    assert lic.gate_free(path) is True


@pytest.mark.parametrize("path", [
    "/api/jobs",
    "/api/jobs/retry",
    "/api/jobs/append-cta",
    "/api/jobs/requeue-folder",
    "/api/ai-edit",       # escapava: edição por IA sem gate
    "/api/corrections",   # escapava: re-render do final pelo editor
    "/api/save",
    "/api/proxy/rebuild",
    "/api/rota-nova-que-ainda-nao-existe",
])
def test_rotas_que_produzem_video_exigem_licenca(path):
    assert lic.gate_free(path) is False


def _rotas_post_do_codigo() -> set[str]:
    """Toda rota /api/ que os handlers de POST realmente despacham.

    Lê o código em vez de uma lista escrita à mão: era exatamente uma lista à
    mão que deixou /api/ai-edit e /api/corrections de fora do gate.
    """
    import re

    rotas: set[str] = set()
    for nome in ("app/local_server.py", "app/desktop_server.py", "helpers/preview_server.py"):
        texto = (REPO / nome).read_text(encoding="utf-8")
        # As rotas moram em _do_POST_rotas desde o involucro de higiene do
        # socket (26/08); no preview_server seguem no do_POST.
        i = texto.find("def _do_POST_rotas")
        if i < 0:
            i = texto.find("def do_POST")
        if i < 0:
            continue
        fim = texto.find("\n    def ", i + 10)
        corpo = texto[i:fim if fim > 0 else len(texto)]
        rotas |= set(re.findall(r'["\'](/api/[a-z0-9\-/]+)["\']', corpo))
    return rotas


def test_toda_rota_post_esta_gateada_ou_explicitamente_livre():
    """Rota nova nasce gateada. Se alguém liberar uma, tem de ser de propósito
    — adicionando a license._GATE_FREE_*, que este teste enumera."""
    rotas = _rotas_post_do_codigo()
    assert len(rotas) > 15, f"a varredura quebrou: só achei {len(rotas)} rotas"

    livres = {r for r in rotas if lic.gate_free(r)}
    gateadas = rotas - livres

    # As que produzem vídeo NÃO podem estar livres.
    for critica in ("/api/jobs", "/api/ai-edit", "/api/corrections", "/api/apply-plan",
                    "/api/intent", "/api/cover", "/api/images/pick", "/api/append-cta"):
        if critica in rotas:
            assert critica in gateadas, f"{critica} ficou fora do gate"

    # As que permitem sair do bloqueio NÃO podem estar gateadas.
    for saida in ("/api/auth/login", "/api/license/activate", "/api/settings"):
        assert lic.gate_free(saida), f"{saida} ficou gateada — o cliente não consegue se desbloquear"

    # Nem as que só alcançam o que o cliente já produziu.
    for guardado in ("/api/open-folder", "/api/open-final", "/api/project/action",
                     "/api/jobs/open-folder", "/api/jobs/delete"):
        assert lic.gate_free(guardado), (
            f"{guardado} ficou gateada — bloqueado não conseguiria abrir o próprio vídeo"
        )


# --- fail-closed ----------------------------------------------------------


def test_dev_sem_config_fica_aberto(monkeypatch):
    monkeypatch.setattr(lic.ss, "is_dev_install", lambda: True)
    st = lic._unconfigured_status()
    assert st["entitled"] is True
    assert st["mode"] == "open"


def test_build_de_cliente_sem_config_bloqueia(monkeypatch):
    """Antes, instalação sem Supabase liberava tudo — e era o padrão de fábrica."""
    monkeypatch.setattr(lic.ss, "is_dev_install", lambda: False)
    st = lic._unconfigured_status()
    assert st["entitled"] is False
    assert st["mode"] == "blocked"


# --- cache local ----------------------------------------------------------


def test_offline_libera_dentro_da_janela(blob):
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(-40))
    out = lic._offline_fallback("sem rede")
    assert out["entitled"] is True
    assert out["offline"] is True


def test_offline_nao_renova_a_janela(blob):
    """Cada checagem sem rede regravava cachedAt: 72h viravam para sempre."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(-40))
    antes = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))["cachedAt"]
    lic._cache(lic._offline_fallback("sem rede"))
    depois = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))["cachedAt"]
    assert depois == antes


def test_erro_transitorio_nao_apaga_cache_bom(blob):
    """Um 503 do Supabase apagava a licença guardada e bloqueava quem pagou."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(-1))
    lic._cache({"entitled": False, "mode": "error", "error": "http_503"})
    salvo = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))
    assert salvo["cached"]["entitled"] is True


def test_cached_at_no_futuro_nao_libera(blob):
    """Editar cachedAt para 2900 dava idade negativa, que passava no <= 72h."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(24 * 365 * 900))
    assert lic._offline_fallback("sem rede")["entitled"] is False


def test_valid_until_vencido_nao_libera_offline(blob):
    blob({"entitled": True, "mode": "account", "validUntil": _utc(-24)}, _utc(-1))
    assert lic._offline_fallback("sem rede")["entitled"] is False


@pytest.mark.parametrize("valor,esperado", [
    (None, False),
    ("", False),
    (_utc(24), False),
    (_utc(-24), True),
])
def test_expired(valor, esperado):
    assert lic._expired(valor) is esperado


# --- CSRF do servidor local ----------------------------------------------


class _H(dict):
    """Stand-in para self.headers (case-insensitive o bastante para o guard)."""

    def get(self, k, default=None):  # noqa: D102
        for key, v in self.items():
            if key.lower() == k.lower():
                return v
        return default


def test_sem_origin_passa():
    """O próprio app e ferramentas locais não mandam Origin."""
    assert guard.origin_allowed(_H({"Host": "127.0.0.1:4850"})) is True


def test_origin_do_proprio_app_passa():
    h = _H({"Host": "127.0.0.1:4850", "Origin": "http://127.0.0.1:4850"})
    assert guard.origin_allowed(h) is True


@pytest.mark.parametrize("origin", [
    "https://site-malicioso.com",
    "http://evil.example",
    "https://127.0.0.1.evil.com",
])
def test_site_externo_e_recusado(origin):
    h = _H({"Host": "127.0.0.1:4850", "Origin": origin})
    assert guard.origin_allowed(h) is False


def test_sec_fetch_site_cross_site_e_recusado():
    h = _H({"Host": "127.0.0.1:4850", "Sec-Fetch-Site": "cross-site"})
    assert guard.origin_allowed(h) is False


def test_cors_nunca_devolve_wildcard():
    h = _H({"Host": "127.0.0.1:4850", "Origin": "https://site-malicioso.com"})
    assert guard.cors_origin(h) != "*"
    assert "site-malicioso" not in guard.cors_origin(h)


# --- segredos em repouso --------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI é do Windows")
def test_segredo_nao_fica_legivel_em_disco():
    from app import secret_store

    cifrado = secret_store.protect("service-role-secreta")
    assert cifrado.startswith("dpapi:")
    assert "service-role-secreta" not in cifrado
    assert secret_store.unprotect(cifrado) == "service-role-secreta"


def test_valor_legado_em_texto_plano_continua_valendo():
    """Migração não pode invalidar a sessão/chave de quem já tinha o arquivo."""
    from app import secret_store

    assert secret_store.unprotect("valor-antigo-sem-prefixo") == "valor-antigo-sem-prefixo"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI é do Windows")
def test_cifrar_duas_vezes_nao_corrompe():
    from app import secret_store

    uma = secret_store.protect("abc")
    assert secret_store.protect(uma) == uma
    assert secret_store.unprotect(uma) == "abc"


# --- identidade no SQL ----------------------------------------------------


def _rpc_license_sql() -> str:
    return (REPO / "supabase" / "rpc_license.sql").read_text(encoding="utf-8")


def test_acesso_por_conta_casa_por_user_id_e_nunca_por_email():
    """Casar por e-mail deixava qualquer um registrar o endereço de um cliente
    liberado e herdar o acesso pago. Exigir e-mail confirmado não resolve: com
    'Confirm email' desligado o Auth marca email_confirmed_at no cadastro."""
    sql = _rpc_license_sql()
    i = sql.index("IDENTIDADE É O user_id")
    trecho = sql[i:sql.index("if found then", i)]
    assert "a.user_id = v_jwt_uid" in trecho
    assert "a.email" not in trecho, "voltou a conceder acesso casando por e-mail"


def test_nao_existe_auto_bind_de_user_id_no_caminho_do_cliente():
    """O vínculo é ato do ADMIN (grant_access). Gravar o user_id de quem chegar
    primeiro tornava o sequestro irreversível."""
    sql = _rpc_license_sql()
    corpo = sql[sql.index("function public.ativavid_license"):]
    assert "set user_id = v_jwt_uid" not in corpo


def test_grant_do_admin_reatribui_o_vinculo():
    """Com o coalesce invertido, um vínculo errado virava permanente."""
    sql = (REPO / "supabase" / "rpc_admin.sql").read_text(encoding="utf-8")
    assert "coalesce(excluded.user_id, account_access.user_id)" in sql


def test_admin_e_reconhecido_por_usuario_confirmado():
    sql = (REPO / "supabase" / "rpc_admin.sql").read_text(encoding="utf-8")
    trecho = sql[sql.index("function public.ativavid_is_admin"):sql.index("revoke all on function public.ativavid_is_admin")]
    assert "auth.users" in trecho and "email_confirmed_at is not null" in trecho


# --- cache assinado -------------------------------------------------------


def test_cache_legitimo_libera_offline(blob):
    blob({"entitled": True, "mode": "account", "validUntil": _utc(720)}, _utc(-1))
    assert lic._offline_fallback("sem rede")["entitled"] is True


def test_cache_editado_a_mao_nao_libera(blob):
    """O bypass do bloco de notas: trocar entitled/validUntil no license.json."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(720)}, _utc(-1))
    d = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))
    d["cached"]["validUntil"] = _utc(24 * 3650)
    lic.LICENSE_PATH.write_text(json.dumps(d), encoding="utf-8")
    out = lic._offline_fallback("sem rede")
    assert out["entitled"] is False
    assert out["error"] == "cache_tampered"


def test_cache_sem_assinatura_nao_libera(tmp_path, monkeypatch):
    """Blob de versão anterior: revalida contra o servidor em vez de confiar."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    (tmp_path / "license.json").write_text(
        json.dumps({
            "deviceId": "dev-test",
            "cached": {"entitled": True, "mode": "account", "validUntil": _utc(720)},
            "cachedAt": _utc(-1),
        }),
        encoding="utf-8",
    )
    assert lic._offline_fallback("sem rede")["entitled"] is False


def test_cache_de_outra_maquina_nao_vale(blob):
    """A assinatura amarra ao deviceId: copiar o arquivo não transfere licença."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(720)}, _utc(-1))
    d = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))
    d["deviceId"] = "outro-pc"
    lic.LICENSE_PATH.write_text(json.dumps(d), encoding="utf-8")
    assert lic._offline_fallback("sem rede")["entitled"] is False


# --- ativação sob force-update -------------------------------------------


def test_chave_aceita_sob_force_update_nao_conta_como_falha(monkeypatch, tmp_path):
    """O RPC vincula o device ANTES do gate de versão: reportar falha fazia o
    cliente tentar no segundo PC e levar device_limit."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_cfg", lambda: {"url": "https://x", "anon": "k", "checkout": ""})
    monkeypatch.setattr(lic, "_call", lambda *a, **k: {
        "entitled": False,
        "activated": True,
        "mode": "update_required",
        "message": "Chave ativada neste PC. Atualize o ATIVAVID para usar.",
        "update": {"force": True},
    })
    out = lic.activate("ATIV-1111-2222-3333")
    assert out["ok"] is True
    assert out["activated"] is True


# --- "Abrir site" da tela IA ------------------------------------------------
#
# Era `<a target="_blank">` dentro do WebView2, que nao trata janela nova: cada
# clique despejava mais uma guia no navegador do usuario. Agora o clique pede
# ao servidor, que abre UMA guia pelo navegador padrao — e recebe o ID do
# provedor, nunca uma URL: a URL sai do catalogo do servidor.


def test_abrir_site_so_conhece_o_catalogo(monkeypatch):
    import webbrowser

    from app import local_server as lsrv

    abertos = []
    monkeypatch.setattr(webbrowser, "open", lambda u, *a, **k: abertos.append(u) or True)
    prov = lsrv.SESSION_PROVIDERS
    assert "gemini-web" in prov and "chatgpt-web" in prov
    # todo provedor do catalogo tem URL https fixa — e so elas podem abrir
    for p in prov.values():
        assert str(p.get("url", "")).startswith("https://"), p


def test_abrir_site_e_rota_livre_de_licenca():
    """A tela Chaves & IA funciona sem licenca; a rota nova acompanha."""
    from app import license as lic

    assert lic.gate_free("/api/llm-proxy/open-site")


# --- o cartao do provedor reflete a saude REAL ------------------------------
#
# Em 23-24/08 as duas sessoes expiraram e o painel seguiu dizendo "Pronto para
# usar": `has_*_session` so olha a presenca dos cookies. A mentira custou uma
# manha de diagnostico. Agora cada chamada real grava o resultado em
# llm-health.json, e o cartao compara a falha com a hora da captura.


def _sessao_gemini(tmp_path, captured_at):
    import json

    from app import local_server as lsrv

    lsrv.USER_DIR = tmp_path
    lsrv.SESSIONS_PATH = tmp_path / "sessions.json"
    lsrv.SESSIONS_PATH.write_text(json.dumps({"providers": {"gemini-web": {
        "id": "gemini-web", "cookieCount": 3, "capturedAt": captured_at,
        "cookies": [{"name": "__Secure-1PSID", "value": "x",
                     "domain": ".google.com"}],
    }}}), encoding="utf-8")
    return lsrv


def test_falha_real_derruba_o_cartao(tmp_path):
    import app.llm_session as ls

    lsrv = _sessao_gemini(tmp_path, "2026-08-24T10:00:00Z")
    ls._registrar_saude("gemini-web", "Token Gemini ausente — recapture")
    card = {c["id"]: c for c in lsrv.sessions_public()}["gemini-web"]
    assert card["ready"] is False
    assert "recapture" in card["hint"]


def test_recaptura_depois_da_falha_restaura(tmp_path):
    import json

    import app.llm_session as ls

    lsrv = _sessao_gemini(tmp_path, "2026-08-24T10:00:00Z")
    ls._registrar_saude("gemini-web", "Token Gemini ausente")
    d = json.loads(lsrv.SESSIONS_PATH.read_text(encoding="utf-8"))
    # A falha e gravada com o relogio REAL; a recaptura precisa ser mais nova
    # que ela. Data fixa aqui virou bomba-relogio: "23:00Z de hoje" era futuro
    # quando o teste nasceu e passou a ser passado no mesmo dia.
    import datetime as _dt

    depois = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=1)
    d["providers"]["gemini-web"]["capturedAt"] = depois.strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    lsrv.SESSIONS_PATH.write_text(json.dumps(d), encoding="utf-8")
    card = {c["id"]: c for c in lsrv.sessions_public()}["gemini-web"]
    assert card["ready"] is True, card["hint"]


def test_sucesso_real_tambem_restaura(tmp_path):
    import app.llm_session as ls

    lsrv = _sessao_gemini(tmp_path, "2026-08-24T10:00:00Z")
    ls._registrar_saude("gemini-web", "Token Gemini ausente")
    ls._registrar_saude("gemini-web", None)
    card = {c["id"]: c for c in lsrv.sessions_public()}["gemini-web"]
    assert card["ready"] is True


def test_saude_corrompida_nao_derruba_o_painel(tmp_path):
    import app.llm_session as ls

    lsrv = _sessao_gemini(tmp_path, "2026-08-24T10:00:00Z")
    ls._saude_path().write_text("{ nao e json", encoding="utf-8")
    card = {c["id"]: c for c in lsrv.sessions_public()}["gemini-web"]
    assert card["ready"] is True
