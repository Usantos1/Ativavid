# -*- coding: utf-8 -*-
"""5.0.31: "admin" gravado em disco não vale sozinho.

Print de um PC de cliente (04/09), na 5.0.30: a janela "Editar acesso" —
criar conta, liberar dias, revogar — aberta, com o servidor respondendo
"forbidden" no canto. O servidor estava certo; a tela acreditava no disco.

O flag `is_admin` é escrito no login e ficava ali para sempre: inclusive
quando veio de uma versão antiga que promovia quem não era ("`ok` não é
sinônimo de admin", diz o comentário do `check_admin`), ou de um login de
admin feito naquela máquina para configurar o cliente.

Duas pontas:
  1. `ensure_session()` reconfere no servidor quando o disco diz admin. Só
     REBAIXA com resposta definitiva — sem rede o cache fica, e as rotas de
     admin continuam recusando de qualquer jeito.
  2. `api()` da tela, no 403 "forbidden", rebaixa `state.auth.isAdmin` e
     fecha o painel. É o único lugar por onde toda resposta passa.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import auth as au  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _sessao(monkeypatch, tmp_path, is_admin=True):
    blob = {"access_token": "tok", "refresh_token": "r", "email": "x@y",
            "is_admin": is_admin, "expires_at": 4102444800}
    gravado = {}
    monkeypatch.setattr(au, "_refresh_if_needed", lambda force=False: dict(blob))
    monkeypatch.setattr(au, "_load", lambda: dict(blob))
    monkeypatch.setattr(au, "_save", lambda b: gravado.update(b))
    return blob, gravado


def test_servidor_diz_nao_e_a_sessao_deixa_de_ser_admin(monkeypatch, tmp_path):
    """O caso do print: disco diz admin, RPC responde 403."""
    _, gravado = _sessao(monkeypatch, tmp_path)
    monkeypatch.setattr(au, "check_admin", lambda force=False: {
        "ok": True, "loggedIn": True, "admin": False, "rpcStatus": 403})
    st = au.ensure_session()
    assert st["isAdmin"] is False, "a tela continuaria abrindo o painel"
    assert gravado.get("is_admin") is False, "o disco continuaria mentindo no próximo boot"


def test_servidor_confirma_e_continua_admin(monkeypatch, tmp_path):
    _, gravado = _sessao(monkeypatch, tmp_path)
    monkeypatch.setattr(au, "check_admin", lambda force=False: {
        "ok": True, "loggedIn": True, "admin": True})
    assert au.ensure_session()["isAdmin"] is True
    assert "is_admin" not in gravado, "regravou o disco sem precisar"


def test_sem_rede_o_cache_fica(monkeypatch, tmp_path):
    """Rebaixar por falha de rede deslogaria o admin toda vez que o Wi-Fi
    piscasse — e as rotas de admin já recusam sozinhas."""
    _, gravado = _sessao(monkeypatch, tmp_path)
    monkeypatch.setattr(au, "check_admin", lambda force=False: {
        "ok": False, "loggedIn": True, "admin": False, "rpcStatus": 502})
    assert au.ensure_session()["isAdmin"] is True
    assert "is_admin" not in gravado


def test_check_admin_que_explode_nao_derruba_o_boot(monkeypatch, tmp_path):
    _sessao(monkeypatch, tmp_path)

    def explode(force=False):
        raise RuntimeError("dns")
    monkeypatch.setattr(au, "check_admin", explode)
    assert au.ensure_session()["isAdmin"] is True


def test_quem_nao_e_admin_no_disco_nao_bate_no_servidor(monkeypatch, tmp_path):
    """Cliente comum abre o app dezenas de vezes por dia; não há por que
    perguntar ao RPC quando o disco já diz não."""
    _sessao(monkeypatch, tmp_path, is_admin=False)
    chamou = []
    monkeypatch.setattr(au, "check_admin", lambda force=False: chamou.append(1) or {})
    assert au.ensure_session()["isAdmin"] is False
    assert not chamou


def test_a_tela_fecha_o_painel_no_forbidden():
    i = SJS.index("async function api(path, opts)")
    corpo = SJS[i:i + 1600]
    assert 'data.error === "forbidden"' in corpo
    assert "isAdmin: false" in corpo, "o painel de contas ficaria aberto por cima do 403"
    assert "syncLicenseChrome()" in corpo, "rebaixar sem repintar não fecha nada"
    assert "Login de admin necessário" in corpo, "o cliente veria 'forbidden' cru"
