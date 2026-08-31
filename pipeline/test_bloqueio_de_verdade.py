# -*- coding: utf-8 -*-
"""Bloquear uma maquina nao bloqueava nada — agora bloqueia.

Testado contra o Supabase de producao, com um device de mentira e um
license.json temporario (nada da maquina real foi tocado):

    1. status ANTES de bloquear   -> mode=blocked, "Trial encerrado..."
    2. ativavid_device_blocked    -> True
    3. status DEPOIS de bloquear  -> resposta IDENTICA a de antes

A funcao existe no banco e ninguem a chamava: a `ativavid_license` nunca
consultava o bloqueio. Marcar uma maquina como bloqueada nao mudava nada
para ela — nem para uma com licenca valida.

Ligar do lado do servidor pede substituir a `ativavid_license`, que
decide o acesso de TODO cliente; errar ali derruba todo mundo. Entao o
cliente passou a checar, com a funcao que ja existe. Depois do conserto,
o mesmo teste ponta a ponta deu:

    licenca boa + device bloqueado -> entitled=False, mode=blocked
    gravou blockedAt               -> sim
    offline depois disso           -> continua bloqueado
    desbloqueou                    -> voltou na hora
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402


@pytest.fixture()
def maquina(tmp_path, monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    monkeypatch.setattr(lic, "device_id", lambda: "DEV-TESTE")
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_cfg", lambda: {
        "url": "https://x", "anon": "a", "service": "", "checkout": ""})
    monkeypatch.setattr(lic, "_call", lambda a, extra=None: {
        "entitled": True, "mode": "licensed", "validUntil": None})
    return tmp_path


def _bloqueio(monkeypatch, resposta):
    """Troca a consulta de bloqueio. `resposta` = (code, data)."""
    def _rpc(payload, fn="ativavid_license"):
        assert fn == "ativavid_device_blocked", fn
        return resposta
    monkeypatch.setattr(lic, "_http_rpc", _rpc)


def test_licenca_boa_e_device_bloqueado_nao_entra(maquina, monkeypatch):
    """O caso que interessa: a chave e valida, a MAQUINA que nao pode."""
    _bloqueio(monkeypatch, (200, True))
    st = lic.entitlement(refresh=True)
    assert st["entitled"] is False
    assert st["mode"] == "blocked"
    assert st["error"] == "device_blocked"


def test_o_veredito_gruda_e_o_offline_nao_devolve(maquina, monkeypatch):
    _bloqueio(monkeypatch, (200, True))
    lic.entitlement(refresh=True)
    assert lic._offline_fallback("sem rede")["entitled"] is False


def test_desbloquear_volta_na_hora(maquina, monkeypatch):
    _bloqueio(monkeypatch, (200, True))
    lic.entitlement(refresh=True)
    _bloqueio(monkeypatch, (200, False))
    st = lic.entitlement(refresh=True)
    assert st["entitled"] is True, st
    assert lic._offline_fallback("sem rede")["entitled"] is True


def test_consulta_que_falha_nao_bloqueia_ninguem(maquina, monkeypatch):
    """Rede ruim nao pode derrubar cliente pagante."""
    for resposta in ((500, {"error": "x"}), (404, {"error": "nao existe"})):
        _bloqueio(monkeypatch, resposta)
        assert lic.entitlement(refresh=True)["entitled"] is True, resposta


def test_excecao_na_consulta_tambem_nao_bloqueia(maquina, monkeypatch):
    def _explode(payload, fn="ativavid_license"):
        raise RuntimeError("sem rede")
    monkeypatch.setattr(lic, "_http_rpc", _explode)
    assert lic.entitlement(refresh=True)["entitled"] is True


def test_quem_ja_esta_barrado_nao_paga_outra_viagem(maquina, monkeypatch):
    """Sem licenca, perguntar do bloqueio e viagem perdida."""
    monkeypatch.setattr(lic, "_call", lambda a, extra=None: {
        "entitled": False, "mode": "trial"})
    chamou = []
    monkeypatch.setattr(lic, "_http_rpc",
                        lambda p, fn="x": chamou.append(fn) or (200, False))
    lic.entitlement(refresh=True)
    assert chamou == [], chamou


def test_resposta_offline_nao_dispara_a_consulta(maquina, monkeypatch):
    """Offline nao muda veredito de bloqueio."""
    monkeypatch.setattr(lic, "_call", lambda a, extra=None: {
        "entitled": True, "mode": "licensed", "offline": True})
    chamou = []
    monkeypatch.setattr(lic, "_http_rpc",
                        lambda p, fn="x": chamou.append(fn) or (200, True))
    assert lic.entitlement(refresh=True)["entitled"] is True
    assert chamou == []


def test_o_sql_libera_a_consulta_para_o_app():
    sql = (REPO / "supabase" / "registro_de_uso.sql").read_text(encoding="utf-8")
    assert ("grant execute on function public.ativavid_device_blocked(text) "
            "to anon, authenticated;") in sql
    # e o bloquear continua fechado para o cliente
    assert "revoke execute on function public.ativavid_block_device" in sql
