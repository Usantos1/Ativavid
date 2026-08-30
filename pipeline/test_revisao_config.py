# -*- coding: utf-8 -*-
"""O interruptor: precedência, padrão, e o que ele NÃO é.

A revisão é um pós-processo do motor local, não um quarto backend. Este
arquivo tranca as duas coisas: que a chave funciona como as outras do
projeto, e que ela não virou um modo de transcrição por acidente.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.transcricao import modo, revisao


@pytest.fixture(autouse=True)
def sem_heranca(monkeypatch):
    monkeypatch.delenv("ATIVAVID_REVISAO", raising=False)
    monkeypatch.setattr(revisao, "PADRAO", revisao.DESLIGADA)


# ------------------------------------------------------------- precedência

def test_a_variavel_de_ambiente_ganha_da_configuracao(monkeypatch):
    """Canário e rollback de emergência não podem depender de editar arquivo."""
    monkeypatch.setattr("app.settings_store.load_settings",
                        lambda: {"revisao": "off"})
    monkeypatch.setenv("ATIVAVID_REVISAO", "gemini")
    assert revisao.modo() == revisao.LIGADA and revisao.ligada()

    monkeypatch.setattr("app.settings_store.load_settings",
                        lambda: {"revisao": "gemini"})
    monkeypatch.setenv("ATIVAVID_REVISAO", "off")
    assert revisao.modo() == revisao.DESLIGADA and not revisao.ligada()


def test_a_configuracao_ganha_do_padrao(monkeypatch):
    monkeypatch.setattr("app.settings_store.load_settings",
                        lambda: {"revisao": "gemini"})
    assert revisao.modo() == revisao.LIGADA


def test_valor_invalido_cai_no_padrao(monkeypatch):
    monkeypatch.setenv("ATIVAVID_REVISAO", "talvez")
    assert revisao.modo() == revisao.PADRAO


def test_configuracao_ilegivel_nao_derruba_nada(monkeypatch):
    def explode():
        raise OSError("settings.json corrompido")

    monkeypatch.setattr("app.settings_store.load_settings", explode)
    assert revisao.modo() == revisao.PADRAO


def test_o_padrao_de_hoje_e_ligado():
    """O padrão declarado, trancado no código.

    Nasceu ao contrário. Enquanto os commits estruturais entravam com a
    revisão dormindo, este teste cobrava `PADRAO = DESLIGADA` — para que
    ninguém ligasse a revisão de carona num commit que dizia não mexer em
    nada. Ele cumpriu o papel: falhou no instante em que o padrão virou, e
    virou de propósito, depois do canário de 49 PASS na máquina real.

    Agora guarda o outro lado. O padrão é `LIGADA`, e desligar a revisão em
    produção NÃO se faz editando esta constante: `ATIVAVID_REVISAO=off` já é
    rollback imediato, sem deploy e sem apagar arquivo (ver
    `test_revisao_cache.py`). Uma mudança aqui é decisão de produto e tem de
    ser deliberada, não efeito colateral de outro commit.
    """
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "app" / "transcricao" / "revisao.py")
    assert "PADRAO = LIGADA" in codigo


# ------------------------------------- não é um backend, e não pode virar um

def test_a_revisao_nao_e_um_modo_de_transcricao():
    """`backend_para_o_pipeline()` alimenta o `--backend` do `transcribe.py`.

    Um quarto valor teria de ser traduzido de volta em todo lugar que compara
    com `elevenlabs`, e a revisão é ortogonal ao motor.
    """
    assert set((modo.LOCAL, modo.SCRIBE, modo.AUTO)) == {"local", "elevenlabs", "auto"}
    assert modo.backend_para_o_pipeline() in (modo.LOCAL, modo.SCRIBE)
    assert not hasattr(modo, "LOCAL_MAIS_GEMINI")


def test_a_chave_da_revisao_nao_mexe_no_motor(monkeypatch):
    """Ligar a revisão não pode trocar o motor por baixo do pano."""
    monkeypatch.setenv("ATIVAVID_TRANSCRICAO", "local")
    monkeypatch.setenv("ATIVAVID_REVISAO", "gemini")
    assert modo.backend_para_o_pipeline() == modo.LOCAL

    monkeypatch.setenv("ATIVAVID_TRANSCRICAO", "elevenlabs")
    assert modo.backend_para_o_pipeline() == modo.SCRIBE


def test_o_sufixo_desejado_acompanha_o_interruptor(monkeypatch):
    monkeypatch.setenv("ATIVAVID_REVISAO", "off")
    assert revisao.sufixo_desejado() == ""
    monkeypatch.setenv("ATIVAVID_REVISAO", "gemini")
    assert revisao.sufixo_desejado() == revisao.SUFIXO
    # A FORMA e o contrato do cache; o numero sobe a cada mudanca de
    # prompt e nao pode ser pinado aqui.
    assert re.fullmatch(r"\+rev\d+", revisao.SUFIXO), revisao.SUFIXO


# ------------------------------------------------- os marcadores no pipeline

def test_o_run_fast_repassa_as_tres_linhas_da_revisao():
    """Revisão que falha em silêncio vira suspeita de regressão de qualidade
    sem nada no log para conferir."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(REPO / "pipeline" / "run_fast.py")
    for marcador in ("REVISAO_GEMINI", "REVISAO_GEMINI_PULADA",
                     "REVISAO_GEMINI_FALHOU"):
        assert f'"{marcador}"' in codigo, f"{marcador} não é repassado"
