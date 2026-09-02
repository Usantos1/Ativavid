# -*- coding: utf-8 -*-
"""Atualizar com a fila ocupada avisa antes de fechar o app.

Caso real de 02/09: um vídeo de 11min estava há 55min renderizando; o
usuário clicou em atualizar e o app fechou sem aviso — o render recomeçou
do zero. Agora `instalarAtualizacao` consulta a fila e pede confirmação
(na janela do PRÓPRIO app — `pedirConfirmacao`, nunca o confirm() feio do
navegador, exigência de 29/08).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_instalar_confere_a_fila_antes_de_fechar():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("async function instalarAtualizacao")
    bloco = js[i:i + 1600]
    assert '"/api/jobs"' in bloco, "a guarda da fila sumiu do atualizar"
    assert "pedirConfirmacao" in bloco
    assert "recomeça do zero" in bloco
    # fila indisponível NÃO trava a atualização (o try engole)
    assert "fila indisponível não trava" in bloco
    # a guarda vem ANTES do download começar
    assert bloco.index("pedirConfirmacao") < bloco.index('"Baixando…"')
