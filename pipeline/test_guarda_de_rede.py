# -*- coding: utf-8 -*-
"""A guarda de rede da suíte (conftest.py) funciona — e deixa o loopback.

Nasceu em 04/09: um teste que caía no ramo do GitHub do `check_update`
passou numa versão e quebrou na seguinte porque o "latest" real tinha
andado. Foram treze releases num dia; teste que lê o estado de um servidor
não prova nada.
"""
import socket

import pytest


def test_conectar_para_fora_levanta():
    # `RedeNoTeste` e RuntimeError; o conftest nao e importavel pelo nome
    # em todo modo de import do pytest, entao casa pela mensagem.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="tentou conectar em"):
            s.connect(("93.184.216.34", 80))
    finally:
        s.close()


def test_loopback_continua_livre():
    """A suíte sobe servidores locais de verdade (preview, laboratórios)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    porta = srv.getsockname()[1]
    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cli.settimeout(3)
        cli.connect(("127.0.0.1", porta))   # não pode levantar
    finally:
        cli.close()
        srv.close()


@pytest.mark.rede
def test_quem_marca_rede_passa_pela_guarda():
    """Só prova que a marca desliga a guarda; não conecta de verdade."""
    assert socket.socket.connect.__name__ != "_connect"
