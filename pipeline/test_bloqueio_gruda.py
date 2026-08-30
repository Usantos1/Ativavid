# -*- coding: utf-8 -*-
"""Bloquear um computador tem de valer sem internet.

Testando o gate (pedido de 30/08) achei dois caminhos por onde uma
maquina bloqueada continuava trabalhando:

1. RELOGIO PARA TRAS — a janela offline de 72h e `agora - cachedAt`.
   Atrasando o relogio do Windows a conta nunca passa de 72h e o cache
   velho vale para sempre. O arquivo e assinado contra edicao, mas a HORA
   da maquina nao estava no que ele protege.

2. O BLOQUEIO NAO GRUDAVA — o servidor responde `blocked`, e bastava
   ficar offline na abertura seguinte: o fallback voltava ao ultimo cache
   bom e liberava por mais 72h.

Cada teste aqui e um desses ataques, encenado.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def maquina(tmp_path, monkeypatch):
    """Uma maquina com licenca boa, validada ha 1 hora."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    monkeypatch.setattr(lic, "device_id", lambda: "DEV-TESTE")
    agora = datetime.now(timezone.utc)
    blob = {
        "deviceId": "DEV-TESTE",
        "cachedAt": _iso(agora - timedelta(hours=1)),
        "maxSeenAt": _iso(agora),
        "cached": {"entitled": True, "mode": "licensed", "validUntil": None},
    }
    lic._save_blob(blob)
    return tmp_path / "license.json"


def _blob(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _regravar(caminho: Path, mudanca: dict) -> None:
    """Reescreve o arquivo ASSINANDO — o pirata que edita a mao ja era
    pego pela assinatura; estes testes simulam o ataque que ela nao pega."""
    b = _blob(caminho)
    b.update(mudanca)
    lic._save_blob(b)


def test_offline_com_cache_bom_ainda_libera(maquina):
    """A base: sem ataque nenhum, a janela de 72h continua funcionando —
    senao qualquer queda de internet derrubaria cliente pagante."""
    st = lic._offline_fallback("sem rede")
    assert st.get("entitled") is True, st


def test_relogio_para_tras_nao_estica_a_janela(maquina):
    """O ataque: atrasar o relogio do Windows deixa `agora - cachedAt`
    abaixo de 72h para sempre."""
    futuro = datetime.now(timezone.utc) + timedelta(days=30)
    _regravar(maquina, {"maxSeenAt": _iso(futuro)})
    st = lic._offline_fallback("sem rede")
    assert st.get("entitled") is False
    assert st.get("error") == "clock_rollback", st


def test_folga_de_cinco_minutos_para_ntp(maquina):
    """Acerto de relogio e fuso mexem poucos minutos — isso nao pode
    bloquear ninguem."""
    pouco = datetime.now(timezone.utc) + timedelta(minutes=3)
    _regravar(maquina, {"maxSeenAt": _iso(pouco)})
    assert lic._offline_fallback("sem rede").get("entitled") is True


def test_bloqueio_do_servidor_gruda_no_arquivo(maquina):
    """O veredito chega ONLINE e fica gravado."""
    lic._cache({"entitled": False, "mode": "blocked",
                "message": "compartilhamento"})
    assert _blob(maquina).get("blockedAt")


def test_depois_de_bloqueado_ficar_offline_nao_libera(maquina):
    """O ataque: puxar o cabo depois de ser bloqueado. Antes, o fallback
    voltava ao ultimo cache bom."""
    lic._cache({"entitled": False, "mode": "blocked", "message": "x"})
    st = lic._offline_fallback("sem rede")
    assert st.get("entitled") is False
    assert st.get("error") == "device_blocked", st


def test_o_bloqueio_sai_quando_o_servidor_libera(maquina):
    """Desbloquear tem de funcionar — senao um bloqueio por engano vira
    definitivo e o cliente pagante fica de fora."""
    lic._cache({"entitled": False, "mode": "blocked", "message": "x"})
    lic._cache({"entitled": True, "mode": "licensed"})
    assert not _blob(maquina).get("blockedAt")
    assert lic._offline_fallback("sem rede").get("entitled") is True


def test_apagar_a_marca_a_mao_quebra_a_assinatura(maquina):
    """Sem isto o pirata so removia `blockedAt` do json."""
    lic._cache({"entitled": False, "mode": "blocked", "message": "x"})
    b = _blob(maquina)
    b.pop("blockedAt")
    maquina.write_text(json.dumps(b), encoding="utf-8")   # sem reassinar
    assert lic._cache_intact(_blob(maquina)) is False


def test_license_json_de_antes_da_atualizacao_continua_valendo(tmp_path, monkeypatch):
    """Os campos novos entram na assinatura so quando existem: quem ja tem
    o app instalado nao pode precisar de internet para abrir depois de
    atualizar."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    monkeypatch.setattr(lic, "device_id", lambda: "DEV-TESTE")
    antigo = {
        "deviceId": "DEV-TESTE",
        "cachedAt": _iso(datetime.now(timezone.utc) - timedelta(hours=2)),
        "cached": {"entitled": True, "mode": "licensed", "validUntil": None},
    }
    lic._save_blob(antigo)            # assinado sem maxSeenAt/blockedAt
    assert lic._cache_intact(_blob(tmp_path / "license.json")) is True
    assert lic._offline_fallback("sem rede").get("entitled") is True
