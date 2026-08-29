# -*- coding: utf-8 -*-
"""Atualizar é um clique: sem assistente e com aviso que aparece sozinho.

Pedido do usuário (29/08), comparando com o CapCut: "abrir o popup pedindo
pra atualizar sozinho... e atualizar só dando o Ok, sem ter estas etapas".
As etapas eram do instalador (idioma → pasta → avançar → concluir) e o
aviso só existia como uma pastilha colorida na barra de título, que ele
precisava descobrir que era clicável.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ISS = (REPO / "installer" / "ativa-vid.iss").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
UP = (REPO / "app" / "update_check.py").read_text(encoding="utf-8")


def test_o_instalador_roda_sem_perguntar_mas_com_barra():
    """`/SILENT`, não `/VERYSILENT`.

    Os dois não perguntam nada; a diferença é que `/VERYSILENT` esconde até
    a barra de progresso. O usuário testou a 3.43 e pediu o contrário:
    "quero ver a barra de progresso, sumir apenas quando terminar e for
    reabrir" — sem ela, entre o clique e o app voltar havia um buraco de
    segundos com a tela vazia.
    """
    i = UP.index("def baixar_e_instalar")
    trecho = UP[i:UP.index("\ndef ", i + 10)]
    assert '"/SILENT"' in trecho, trecho[-500:]
    assert '"/VERYSILENT"' not in trecho, "a barra some de novo"
    assert '"/SUPPRESSMSGBOXES"' in trecho


def test_o_app_volta_sozinho_depois_da_atualizacao_silenciosa():
    """`skipifsilent` no [Run] faria o app sumir: instala e nao reabre."""
    i = ISS.index('Description: "Abrir ATIVAVID"')
    linha_flags = ISS[i:i + 400].split('Flags:')[1].splitlines()[0]
    assert 'postinstall' in linha_flags, linha_flags
    assert 'skipifsilent' not in linha_flags, linha_flags


def test_o_instalador_nao_pergunta_idioma():
    assert "ShowLanguageDialog=no" in ISS


def test_a_pasta_so_e_perguntada_na_primeira_instalacao():
    assert "DisableDirPage=auto" in ISS


def test_o_aviso_aparece_sozinho_uma_vez_por_versao():
    i = JS.index("function avisarVersaoNova")
    trecho = JS[i:i + 700]
    assert "ativavid.updateAdiado" in trecho
    assert "adiada === nova" in trecho, "avisaria de novo a cada abertura"
    # e o "Agora nao" precisa GRAVAR a versao dispensada
    j = JS.index("btnUpdLater.onclick")
    assert "updateAdiado" in JS[j:j + 500]


def test_a_janela_diz_que_e_um_clique_so():
    i = JS.index("hint.textContent = upd.force")
    trecho = JS[i:i + 400]
    assert "reabre sozinho" in trecho and "autorização uma vez" in trecho
