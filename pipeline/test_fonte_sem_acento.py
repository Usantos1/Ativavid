# -*- coding: utf-8 -*-
"""Fonte que não desenha acento não passa calada.

Em 29/08 o usuário pediu a Integral CF (arquivo `Fontspring-DEMO-...`) no
app. É a versão de demonstração: no lugar de todo acento e da exclamação
ela carimba "DEMO". Sem checagem, "NÃO MORRE!" sairia "N[DEMO]O
MORRE[DEMO]" no vídeo pronto, na frente do cliente dele.

O erro que quase passou: a primeira versão comparava `mask.tobytes()`, um
método que o objeto do Pillow não tem, e o `except` engolia o
AttributeError — a checagem respondia "nenhum acento faltando" para
exatamente a fonte que carimbava tudo. Por isso o teste abaixo exige o
resultado NEGATIVO (fonte boa) e o POSITIVO (fonte ruim): só o negativo
passaria com a função quebrada.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.run_fast import _ACENTOS_PT, _acentos_que_faltam

REPO = Path(__file__).resolve().parent.parent
BOAS = sorted((REPO / "assets" / "fonts-render").glob("*.ttf"))


@pytest.mark.parametrize("arquivo", BOAS, ids=lambda p: p.name)
def test_fonte_boa_nao_da_alarme_falso(arquivo: Path):
    """Aviso errado é pior que aviso nenhum: ele ensina a ignorar o card."""
    assert _acentos_que_faltam(arquivo) == ""


# Fontes que comprovadamente NAO tem letra acentuada: as de simbolo do
# Windows (o app so roda no Windows). A demo do usuario entra na lista
# quando a maquina e a dele — o caso que originou a checagem.
SEM_ACENTO = [c for c in (
    Path("C:/Windows/Fonts/webdings.ttf"),
    Path("C:/Windows/Fonts/marlett.ttf"),
    Path.home() / "ATIVAVID" / "Fontes" / "Fontspring-DEMO-integralcf-bold.otf",
) if c.exists()]


@pytest.mark.parametrize("arquivo", SEM_ACENTO, ids=lambda p: p.name)
def test_fonte_sem_acento_e_apontada(arquivo: Path):
    """O caso POSITIVO. Sem ele o teste passaria com a funcao quebrada."""
    faltam = _acentos_que_faltam(arquivo)
    assert set(_ACENTOS_PT) <= set(faltam) | {"?"}, faltam


def test_arquivo_quebrado_nao_derruba_o_render(tmp_path: Path):
    ruim = tmp_path / "nao-e-fonte.ttf"
    ruim.write_bytes(b"isto nao e uma fonte")
    assert _acentos_que_faltam(ruim) == ""


def test_o_aviso_chega_no_card():
    """A ficha vira nota no card — senão a checagem morre no log."""
    from app import jobs_view

    fonte = jobs_view.__file__
    s = Path(fonte).read_text(encoding="utf-8")
    assert "fonteSemAcento" in s and "fonteNota" in s
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "j.fonteNota" in js
