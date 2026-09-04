# -*- coding: utf-8 -*-
"""Quando o trial deste PC começou, e quantos dias faltam.

Ele em 31/08: "eu tenho um PC com vários dias de instalação e ainda mostra
trial 4 dias". Nao havia como conferir: o painel listava maquinas a partir
do registro de ABERTURAS, e a tabela `trials` (a unica que sabe quando o
trial comecou) nao aparecia em lugar nenhum.

Com os dados dele na frente: o PC comecou o trial em 27/08 14:42, e em
31/08 faltam 4 dias — a conta esta certa. O trial comeca no PRIMEIRO
CONTATO com o servidor, nao na instalacao; um PC instalado antes e aberto
depois so comeca a contar quando abre.

O segundo defeito, este meu: o registro de aberturas so existe desde a
4.27, entao PC em versao anterior nao aparecia. Dos 3 trials da conta a
tela mostrava 1 maquina — um painel que esconde justamente quem esta em
trial nao serve para vigiar trial nenhum.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license_admin as la  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _iso(dias_atras: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat()


def _falso(monkeypatch, *, aberturas, trials, devices):
    def rest(_metodo, caminho, _corpo=None):
        if caminho.startswith("aberturas"):
            return 200, aberturas
        if caminho.startswith("trials"):
            return 200, trials
        if caminho.startswith("devices"):
            return 200, devices
        return 404, {}

    monkeypatch.setattr(la, "_rest_service", rest)


def test_a_conta_dos_dias_bate_com_a_do_servidor():
    """O SQL usa ceil((started_at + 7d - now())/86400). A tela tem de
    mostrar o MESMO numero que o PC do cliente mostra."""
    assert la._dias_de_trial(_iso(3.9)) == 4      # o caso real dele
    assert la._dias_de_trial(_iso(0)) == 7
    assert la._dias_de_trial(_iso(6.5)) == 1
    assert la._dias_de_trial(_iso(7.2)) == 0
    assert la._dias_de_trial(_iso(30)) == 0
    assert la._dias_de_trial(None) is None
    assert la._dias_de_trial("nao e data") is None


def test_maquina_com_trial_e_sem_abertura_aparece(monkeypatch):
    _falso(monkeypatch,
           aberturas=[{"device_id": "win-com-log", "host": "PC1",
                       "criado_em": _iso(1)}],
           trials=[{"device_id": "win-com-log", "started_at": _iso(2)},
                   {"device_id": "win-sem-log", "started_at": _iso(3.9)}],
           devices=[{"device_id": "win-sem-log", "last_seen": _iso(3.8),
                     "license_id": None, "blocked_at": None}])
    d = la.list_aberturas()
    achadas = {m["deviceId"]: m for m in d["maquinas"]}
    assert set(achadas) == {"win-com-log", "win-sem-log"}
    sem = achadas["win-sem-log"]
    assert sem["aberturas"] == 0
    assert sem["semRegistro"] is True
    assert sem["trialDias"] == 4, "e o PC da pergunta dele"
    assert sem["ultima"], "sem log de abertura, o last_seen do servidor conta"


def test_a_primeira_abertura_e_a_MAIS_ANTIGA(monkeypatch):
    """Comparar com a primeira e o que mostra se o PC ficou instalado sem
    ninguem abrir."""
    _falso(monkeypatch,
           aberturas=[{"device_id": "w", "criado_em": _iso(1)},
                      {"device_id": "w", "criado_em": _iso(9)},
                      {"device_id": "w", "criado_em": _iso(5)}],
           trials=[], devices=[])
    m = la.list_aberturas()["maquinas"][0]
    assert m["primeira"] < m["ultima"]
    assert m["primeira"].startswith(_iso(9)[:10])


def test_maquina_licenciada_nao_mostra_trial(monkeypatch):
    _falso(monkeypatch,
           aberturas=[{"device_id": "w", "criado_em": _iso(1)}],
           trials=[], devices=[{"device_id": "w", "license_id": "abc",
                                "last_seen": _iso(1), "blocked_at": None}])
    m = la.list_aberturas()["maquinas"][0]
    assert m["trialDias"] is None and m["temLicenca"] is True


def test_a_tela_mostra_as_duas_datas():
    """5.0.32: a coluna "Trial" virou "Status".

    A antiga so sabia falar de trial e dizia "acabou" para quem pagou um
    ano (print de 04/09). O plano agora vem decidido do servidor em
    `m.plano`; o inicio do trial continua na tela, mas so nas linhas em
    trial. A 1a abertura continua ao lado, para ler "instalado ha dias e
    ainda em trial".
    """
    i = JS.index("async function loadAberturas()")
    bloco = JS[i:JS.index("\nfunction wireAberturas", i)]
    for coluna in ("1ª abertura", "Status"):
        assert coluna in bloco, coluna
    assert "Trial</th>" not in bloco, "a coluna antiga voltou"
    assert "m.plano" in bloco and "m.trialInicio" in bloco
    assert "quando(m.primeira)" in bloco
