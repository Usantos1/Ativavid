# -*- coding: utf-8 -*-
"""Quando o caminho rápido é pulado, o motivo tem que ficar gravado.

O caminho OVERLAY entrega o vídeo em cerca de 6 min; o FULL, em cerca de 25.
Nos projetos reais, 32 jobs foram pelo lento e o `timing.json` não dizia por
quê — `renderPath: "FULL"` e nada mais. O motivo existia só num `print` do
pipeline, e o log do pipeline não é guardado por projeto.

Para descobrir a causa eu tive que deduzi-la cruzando horários de arquivo: 91%
desses jobs rodaram junto com outro, e a vaga do caminho rápido é uma só. Foi
trabalho de investigação para recuperar um dado que existia no instante da
decisão e foi jogado fora.

Estes testes travam as duas metades: quem decide grava o motivo, e quem escreve
o `timing.json` carrega o motivo para o arquivo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))

from pipeline.leitura_de_codigo import apenas_codigo  # noqa: E402

# Cada porta que leva ao caminho lento, e o rótulo que ela precisa gravar.
PORTAS = {
    "longform": "vídeo longo não tenta o caminho rápido",
    "desligado": "o motor rápido está desligado neste install",
    "vaga_ocupada_apos_espera": "esperou a vaga até o teto e desistiu",
    "recurso:": "o vídeo usa recurso que exige o Remotion",
}


@pytest.mark.parametrize("rotulo", sorted(PORTAS))
def test_toda_porta_para_o_caminho_lento_grava_motivo(rotulo):
    codigo = apenas_codigo(RAIZ / "pipeline" / "run_fast.py")
    assert f'"{rotulo}' in codigo or f"'{rotulo}" in codigo, (
        f"a porta {rotulo!r} ({PORTAS[rotulo]}) não grava motivo")


def test_o_motivo_chega_ao_timing_json(tmp_path):
    """Gravar em `_RENDER_META` não basta: o arquivo é que sobrevive ao job."""
    import pipeline.run_fast as rf

    rf._TIMING.clear()
    rf._RENDER_META.clear()
    rf._TIMING["CUT"] = 12.0
    rf._RENDER_META["overlaySkip"] = "vaga_ocupada_apos_espera"
    rf.write_timing(tmp_path)
    d = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    assert d.get("overlaySkip") == "vaga_ocupada_apos_espera"


def test_sem_motivo_o_campo_nao_aparece(tmp_path):
    """Job que usou o caminho rápido não ganha um campo vazio para confundir."""
    import pipeline.run_fast as rf

    rf._TIMING.clear()
    rf._RENDER_META.clear()
    rf._TIMING["CUT"] = 12.0
    rf.write_timing(tmp_path)
    d = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    assert "overlaySkip" not in d
