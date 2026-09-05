# -*- coding: utf-8 -*-
"""5.0.40: a abertura que não chegou ao servidor tenta de novo.

O aviso de abertura sai numa thread no arranque, uma vez só. O caso comum
é o notebook que abre o app ANTES de o Wi-Fi conectar: a primeira tentativa
morre em segundos e a abertura sumia para sempre. O painel de Licença
mostrava "0 aberturas / versão vazia" para clientes que usam o app todo dia
(vistos às 00:30 e 23:40 de 04-05/09 pelo `last_seen` da licença — que
roda de novo e de novo — enquanto a abertura roda uma vez).

Agora `_avisar_servidor` diz se chegou, e `registrar_abertura` tenta de
novo em 60 s e em 5 min. Sem rede configurada não é falha (não há para
onde mandar), e nada disto pode atrasar o arranque.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402
from app import registro_de_uso as reg  # noqa: E402


def _roda_a_thread():
    reg.registrar_abertura()
    for t in threading.enumerate():
        if t.name == "registro-abertura":
            t.join(timeout=10)


def _prepara(monkeypatch, tmp_path, respostas):
    """`respostas`: lista de codigos HTTP que o RPC devolve, em ordem."""
    monkeypatch.setattr(reg, "LOG_PATH", tmp_path / "aberturas.jsonl")
    monkeypatch.setattr(lic, "configured", lambda: True)
    chamadas: list[dict] = []
    esperas: list[int] = []

    def _rpc(payload, fn="ativavid_license"):
        chamadas.append(dict(payload, fn=fn))
        code = respostas.pop(0) if respostas else 200
        if isinstance(code, Exception):
            raise code
        return code, {}

    monkeypatch.setattr(lic, "_http_rpc", _rpc)
    monkeypatch.setattr(reg.time, "sleep", lambda s: esperas.append(s))
    return chamadas, esperas


def test_chegou_de_primeira_nao_repete(monkeypatch, tmp_path):
    chamadas, esperas = _prepara(monkeypatch, tmp_path, [200])
    _roda_a_thread()
    assert len(chamadas) == 1 and esperas == []


def test_sem_rede_no_arranque_tenta_em_60s_e_5min(monkeypatch, tmp_path):
    chamadas, esperas = _prepara(monkeypatch, tmp_path, [
        OSError("sem rede"), OSError("sem rede"), 200])
    _roda_a_thread()
    assert esperas == [60, 300]
    assert len(chamadas) == 3
    assert all(c["fn"] == "ativavid_open" for c in chamadas)


def test_desiste_depois_da_terceira(monkeypatch, tmp_path):
    chamadas, esperas = _prepara(monkeypatch, tmp_path, [
        OSError("x"), OSError("x"), OSError("x"), OSError("x")])
    _roda_a_thread()
    assert len(chamadas) == 3 and esperas == [60, 300]


def test_servidor_recusou_conta_como_falha(monkeypatch, tmp_path):
    # 401 de JWT vencido: o jeito antigo (sem e-mail) roda no mesmo turno;
    # se tambem falhar, e retentativa — nao silencio.
    chamadas, esperas = _prepara(monkeypatch, tmp_path, [401, 401, 200])
    monkeypatch.setattr(reg, "dados_da_maquina", lambda: {
        "device": "D", "versao": "5.0.40", "maquina": "M", "email": "a@b.c"})
    _roda_a_thread()
    assert esperas == [60]
    assert [c.get("p_email") for c in chamadas] == ["a@b.c", None, "a@b.c"]


def test_sem_supabase_configurado_nao_e_falha(monkeypatch, tmp_path):
    chamadas, esperas = _prepara(monkeypatch, tmp_path, [])
    monkeypatch.setattr(lic, "configured", lambda: False)
    _roda_a_thread()
    assert chamadas == [] and esperas == []


def test_avisar_devolve_verdade_ou_falha(monkeypatch):
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_http_rpc", lambda *a, **k: (204, {}))
    assert reg._avisar_servidor({"device": "D"}) is True
    monkeypatch.setattr(lic, "_http_rpc", lambda *a, **k: (500, {}))
    assert reg._avisar_servidor({"device": "D"}) is False
    monkeypatch.setattr(lic, "_http_rpc", lambda *a, **k: 1 / 0)
    assert reg._avisar_servidor({"device": "D"}) is False
