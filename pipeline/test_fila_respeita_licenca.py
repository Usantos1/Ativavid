# -*- coding: utf-8 -*-
"""A fila que JA EXISTE tambem para quando a licenca cai.

Pergunta dele em 31/08: "tu testou o bloqueio do trial? quem nao tem
login?". Testado por HTTP, com o veredito do servidor de licenca trocado
pelo que o `rpc_license.sql` devolve quando o trial acaba: as rotas que
produzem video respondem 403 `license_required` (criar, refazer, aplicar,
juntar CTA, publicar, previa da importacao), e as de sair do bloqueio
continuam livres (ativar chave, ver a licenca, abrir o app, abrir pasta).

O buraco que o teste achou: o gate cobre a rota que ENFILEIRA, e o Worker
nao olhava licenca nenhuma. Quem enfileirasse 30 videos no ultimo dia do
trial — ou tivesse a fila cheia na hora em que o computador fosse
bloqueado por pirataria — continuava produzindo, porque a fila e
retomada sozinha na abertura seguinte (`Worker.start` reenfileira tudo
que ficou em `queued`/`processing`).

O video ESPERA, nao vira erro: licenca renovada, ele sai sozinho. Marcar
erro puniria quem so ficou 10 minutos sem responder — e a janela offline
de 72h ja cobre esse caso antes de chegar aqui.
"""
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402
from app import local_server as ls  # noqa: E402
from app.job_store import SqliteJobStore  # noqa: E402

LS = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


@pytest.fixture()
def fila(tmp_path, monkeypatch):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "name": "teste", "status": "queued",
                  "message": "Na fila"})
    w = ls.Worker(store)
    rodou: list[str] = []
    monkeypatch.setattr(w, "_run_one", lambda job_id: rodou.append(job_id))
    # O timer de 60s nao pode segurar o teste; guarda que ele foi armado.
    armados: list[str] = []
    monkeypatch.setattr(w, "_tentar_de_novo_com_licenca", armados.append)
    return w, store, rodou, armados


def _veredito(monkeypatch, entitled: bool) -> None:
    monkeypatch.setattr(lic, "entitlement",
                        lambda **_k: {"ok": True, "entitled": entitled,
                                      "mode": "trial" if entitled else "blocked",
                                      "configured": True})


def _rodar(w) -> None:
    threading.Thread(target=w._loop, daemon=True).start()
    for _ in range(40):
        time.sleep(0.05)
        if w.q.empty():
            break
    time.sleep(0.3)


def test_com_licenca_o_video_sai(fila, monkeypatch):
    w, _store, rodou, _ = fila
    _veredito(monkeypatch, True)
    w.enqueue("j1")
    _rodar(w)
    assert rodou == ["j1"]


def test_sem_licenca_o_video_nao_sai(fila, monkeypatch):
    w, store, rodou, armados = fila
    _veredito(monkeypatch, False)
    w.enqueue("j1")
    _rodar(w)
    assert rodou == [], "a fila produziu video sem licenca"
    j = store.get("j1") or {}
    assert j.get("status") == "queued", "o video espera, nao vira erro"
    assert j.get("reason") == "license_required"
    assert "Sem licença" in str(j.get("message"))
    assert armados == ["j1"], "sem reagendar, o video nunca sairia depois de pagar"


def test_defeito_no_gate_nao_trava_quem_pagou(monkeypatch):
    """Erro aqui LIBERA: um defeito meu no gate nao pode parar a fila."""
    def explode(*_a, **_k):
        raise RuntimeError("supabase fora do ar de um jeito novo")

    monkeypatch.setattr(lic, "gate", explode)
    assert ls._licenca_libera_a_fila() is True


def test_a_checagem_vem_antes_de_ocupar_a_maquina():
    """Depois do `acquire_slot` o job ja tomou a vaga de quem pode rodar."""
    i = LS.index("def _loop(self)")
    bloco = LS[i:LS.index("\n    def ", i + 10)]
    assert bloco.index("_licenca_libera_a_fila()") < bloco.index("acquire_slot"), \
        "a licenca tem de ser olhada antes de pegar a vaga"


def test_a_espera_nao_gira_em_falso():
    """`continue` seco devolveria o job na hora: o loop giraria milhares de
    vezes por segundo com a maquina parada."""
    i = LS.index("def _tentar_de_novo_com_licenca(")
    bloco = LS[i:LS.index("\n    def ", i + 10)]
    assert "threading.Timer(60.0" in bloco
    assert "daemon = True" in bloco


def test_a_fila_usa_a_MESMA_regra_da_rota_que_enfileira():
    """Duas listas de rota livre viravam duas politicas — e a segunda
    envelhece calada."""
    i = LS.index("def _licenca_libera_a_fila(")
    bloco = LS[i:LS.index("\nclass Worker", i)]
    assert 'lic.gate("/api/jobs")' in bloco
