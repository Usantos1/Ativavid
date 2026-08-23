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


# --- qual motor desenhou o overlay ----------------------------------------
#
# O renderizador próprio desenha sem abrir o Chrome e é 3,3x mais rápido, mas
# ele se desliga sozinho quando encontra recurso de template que não suporta —
# e até aqui isso só aparecia num `print` do pipeline, que não é guardado.
#
# Conferido nos projetos reais em 22/08: 140 de 140 cobertos, nenhum pulado. O
# campo existe para o dia em que isso deixar de ser verdade, que é justamente o
# dia em que ninguém vai notar sozinho.


def test_o_motor_do_overlay_chega_ao_timing_json(tmp_path):
    import pipeline.run_fast as rf

    rf._TIMING.clear()
    rf._RENDER_META.clear()
    rf._TIMING["CUT"] = 9.0
    rf._RENDER_META["overlayEngine"] = "remotion"
    rf._RENDER_META["overlayEngineSkip"] = "legenda estilo-novo nao suportado"
    rf.write_timing(tmp_path)
    d = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    assert d.get("overlayEngine") == "remotion"
    assert "estilo-novo" in str(d.get("overlayEngineSkip"))


def test_motor_proprio_nao_grava_motivo_de_pulo(tmp_path):
    """Quando ele desenhou, não há o que explicar."""
    import pipeline.run_fast as rf

    rf._TIMING.clear()
    rf._RENDER_META.clear()
    rf._TIMING["CUT"] = 9.0
    rf._RENDER_META["overlayEngine"] = "proprio"
    rf._RENDER_META["overlayEngineSkip"] = None
    rf.write_timing(tmp_path)
    d = json.loads((tmp_path / "timing.json").read_text(encoding="utf-8"))
    assert d.get("overlayEngine") == "proprio"
    assert "overlayEngineSkip" not in d


def test_o_resultado_do_overlay_carrega_o_motor():
    """Gravar em run_fast não basta: quem sabe o motor é o overlay_path."""
    codigo = apenas_codigo(RAIZ / "app" / "overlay_path.py")
    assert '"engine"' in codigo, "o resultado do overlay não diz qual motor desenhou"
    assert '"engineSkip"' in codigo, "o motivo de pular o motor próprio não sai do módulo"
