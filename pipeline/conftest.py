# -*- coding: utf-8 -*-
"""Guarda de rede da suíte: teste não sai da máquina.

Por que existe (04/09): `test_mesma_versao_continua_sem_atualizacao` passou
na 5.0.30 e quebrou na 5.0.31 sem ninguém tocar nele — ele caía no ramo do
GitHub do `check_update`, que consulta a internet DE VERDADE, e o "latest"
real tinha andado no meio (foram treze releases num dia). Teste que depende
do estado de um servidor não prova nada e apodrece sozinho.

O que a guarda faz: qualquer `socket.connect` para fora de loopback levanta
`RedeNoTeste`. Loopback continua livre porque a suíte sobe servidores
locais de verdade (preview, laboratórios com `--projects-root`).

Quem precisa da rede de propósito marca `@pytest.mark.rede` — e diz por que.
"""
from __future__ import annotations

import socket

import pytest

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


class RedeNoTeste(RuntimeError):
    """Um teste tentou falar com um host fora desta máquina."""


def _host_de(address) -> str:
    try:
        return str(address[0])
    except (TypeError, IndexError):
        return ""


@pytest.fixture(autouse=True)
def _sem_rede(request, monkeypatch):
    if request.node.get_closest_marker("rede"):
        yield
        return
    original = socket.socket.connect

    def _connect(self, address):
        host = _host_de(address)
        if host in _LOOPBACK or host.startswith("127."):
            return original(self, address)
        raise RedeNoTeste(
            f"o teste tentou conectar em {host!r}. Trave a chamada "
            "(monkeypatch) ou marque @pytest.mark.rede dizendo por que.")

    monkeypatch.setattr(socket.socket, "connect", _connect)
    yield


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "rede: o teste fala com um host de fora, de propósito")
