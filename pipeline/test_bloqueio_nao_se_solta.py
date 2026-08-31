# -*- coding: utf-8 -*-
"""Bloqueou no painel, o PC para. E continua parado.

"mesmo eu mandando bloquear ele segue com acesso" (31/08), sobre o
`win-8256b455...`. Medido contra o banco de producao naquele momento:

  * `devices.blocked_at` estava preenchido (12:25, motivo compartilhamento);
  * a consulta `ativavid_device_blocked` respondia **true** para a chave
    anon — a mesma que o app usa;
  * e a `ativavid_license` respondia **`entitled: true, mode: trial,
    trialDaysLeft: 4`**. O servidor nao olhava o bloqueio.

Ou seja, quem barrava era so o app, com uma segunda pergunta que existe
da 4.27 para cima e que falha ABERTA. Dois furos nisso:

  1. O cache de licenca dura 30 min e era entregue sem perguntar nada —
     meia hora de trabalho para uma maquina ja barrada.
  2. Pior: o veredito grudado (`blockedAt`) mandava buscar uma resposta
     ONLINE para decidir, e essa resposta vinha crua do `_call`. Como o
     servidor dizia "liberado", o `_cache` APAGAVA o `blockedAt`. O PC
     bloqueava por instantes e voltava a trabalhar sozinho.

Agora o bloqueio e do SERVIDOR (o SQL para aqui antes de olhar chave,
conta ou trial) e, no cliente, toda resposta do servidor passa pelo mesmo
`_veredito`.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402

SQL = (REPO / "supabase" / "rpc_license.sql").read_text(encoding="utf-8")


@pytest.fixture()
def maquina(tmp_path, monkeypatch):
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    monkeypatch.setattr(lic, "device_id", lambda: "DEV-TESTE")
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_cfg", lambda: {"url": "http://x", "anon": "k",
                                              "checkout": ""})
    return tmp_path


def _servidor(monkeypatch, *, entitled=True, bloqueado=False, contador=None):
    monkeypatch.setattr(lic, "_call", lambda _a: {
        "entitled": entitled, "mode": "trial" if entitled else "blocked",
        "trialDaysLeft": 4})

    def bloq():
        if contador is not None:
            contador.append(1)
        return bloqueado

    monkeypatch.setattr(lic, "_device_bloqueado", bloq)


def _cache_bom(idade_min: float = 0.0) -> None:
    quando = (datetime.now(timezone.utc) - timedelta(minutes=idade_min)).isoformat()
    lic._save_blob(lic._marcar_hora({
        "deviceId": "DEV-TESTE", "trialAskedAt": quando,
        "cached": {"entitled": True, "mode": "trial", "trialDaysLeft": 4},
        "cachedAt": quando,
    }))


def test_cache_bom_nao_da_30_minutos_a_quem_foi_bloqueado(maquina, monkeypatch):
    _cache_bom()
    _servidor(monkeypatch, entitled=True, bloqueado=True)
    st = lic.entitlement()
    assert st["entitled"] is False and st["mode"] == "blocked"


def test_o_bloqueio_grudado_NAO_se_solta_na_proxima_checagem(maquina, monkeypatch):
    """O defeito que ele viu: bloqueava e voltava sozinho."""
    _cache_bom()
    _servidor(monkeypatch, entitled=True, bloqueado=True)
    assert lic.entitlement()["entitled"] is False
    for _ in range(3):
        st = lic.entitlement()
        assert st["entitled"] is False, "o PC voltou a trabalhar sozinho"


def test_desbloquear_no_painel_libera_de_novo(maquina, monkeypatch):
    _cache_bom()
    _servidor(monkeypatch, entitled=True, bloqueado=True)
    assert lic.entitlement()["entitled"] is False
    _servidor(monkeypatch, entitled=True, bloqueado=False)
    assert lic.entitlement()["entitled"] is True


def test_a_pergunta_extra_nao_roda_a_cada_rota(maquina, monkeypatch):
    """O gate roda em TODA rota POST; uma viagem de rede por rota seria
    pior que o problema."""
    _cache_bom()
    contador: list[int] = []
    _servidor(monkeypatch, entitled=True, bloqueado=False, contador=contador)
    for _ in range(6):
        assert lic.entitlement()["entitled"] is True
    assert len(contador) == 1, f"perguntou {len(contador)}x em segundos"


def test_depois_de_cinco_minutos_pergunta_de_novo(maquina, monkeypatch):
    _cache_bom()
    contador: list[int] = []
    _servidor(monkeypatch, entitled=True, bloqueado=False, contador=contador)
    lic.entitlement()
    blob = lic._load_blob()
    blob["blockedCheckAt"] = (datetime.now(timezone.utc)
                              - timedelta(minutes=6)).isoformat()
    lic._save_blob(blob)
    lic.entitlement()
    assert len(contador) == 2


@pytest.mark.parametrize("resposta", [(500, None), (200, None), (401, {"m": 1})])
def test_consulta_que_falha_nao_barra_quem_pagou(maquina, monkeypatch, resposta):
    """Uma consulta que nao respondeu nao pode barrar cliente pagante."""
    monkeypatch.setattr(lic, "_http_rpc", lambda *_a, **_k: resposta)
    assert lic._device_bloqueado() is False


def test_o_SERVIDOR_para_antes_de_olhar_chave_conta_ou_trial():
    """Enquanto o veredito vinha `entitled: true`, o bloqueio dependia de o
    app fazer uma segunda pergunta — e app velho nao faz."""
    i = SQL.index("d.blocked_at is not null")
    assert i < SQL.index("-- 3) Trial por device"), "o trial ganharia do bloqueio"
    assert i < SQL.index("Chave ATIV- já ativada")
    bloco = SQL[SQL.index("-- COMPUTADOR BLOQUEADO"):i + 400]
    assert "'entitled', false" in bloco and "'device_blocked'" in bloco


def test_toda_resposta_do_servidor_passa_pelo_mesmo_veredito():
    src = (REPO / "app" / "license.py").read_text(encoding="utf-8")
    i = src.index("def entitlement(")
    corpo = src[i:src.index("\ndef activate(", i)]
    assert "_call(" not in corpo, "resposta crua do servidor pula o bloqueio"
    assert corpo.count("_veredito(") >= 3


def test_o_painel_avisa_quando_o_bloqueio_nao_vale_no_servidor(monkeypatch):
    """Bloqueio gravado no banco mas `ativavid_license` ainda liberando =
    so o app 4.27+ barra. Isso tem de aparecer na tela, nao ficar mudo."""
    from app import license_admin as la

    monkeypatch.setattr(la, "_rest_service",
                        lambda *_a, **_k: (200, {"entitled": True, "mode": "trial"}))
    aviso = la._servidor_ignora_o_bloqueio("win-x")
    assert "rpc_license.sql" in aviso and "4.27" in aviso

    monkeypatch.setattr(la, "_rest_service",
                        lambda *_a, **_k: (200, {"entitled": False, "mode": "blocked"}))
    assert la._servidor_ignora_o_bloqueio("win-x") == ""


def test_a_conferencia_nao_confunde_bloqueio_com_versao_velha(monkeypatch):
    """Com uma versao falsa o servidor barra por ATUALIZACAO e a resposta
    sai `entitled: false` por outro motivo — a conferencia diria que esta
    tudo certo com o bloqueio furado. Aconteceu na primeira versao."""
    from app import license_admin as la

    monkeypatch.setattr(la, "_rest_service", lambda *_a, **_k: (
        200, {"entitled": False, "mode": "update_required"}))
    assert la._servidor_ignora_o_bloqueio("win-x") == ""
    src = (REPO / "app" / "license_admin.py").read_text(encoding="utf-8")
    import re

    i = src.index("def _servidor_ignora_o_bloqueio")
    # Sem os comentarios: o comentario CONTA essa historia e cita o
    # "0.0.0" — ancorar no texto cru acusaria a propria explicacao.
    codigo = re.sub(r"#[^\n]*", "", src[i:i + 1800])
    assert "current_version()" in codigo and '"0.0.0"' not in codigo


def test_a_tela_mostra_o_aviso():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "r.avisoServidor" in js
