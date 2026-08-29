# -*- coding: utf-8 -*-
"""Camadas na linha do tempo: mídia na Edição e gancho clicável.

Dois pedidos do usuário em 29/08, com print:

* "adicionar imagens ali manual nas camadas ou vídeos" — a inserção já
  existia inteira (busca, biblioteca, upload; entra na agulha com 2,5s e é
  arrastável), mas só na aba Visual: na Edição o botão respondia "a busca
  de imagem é da aba Final".
* "não dá pra editar a headline pela timeline, apenas no vídeo" — o bloco
  GANCHO estava lá, mostrava o texto e o intervalo, e não fazia nada.

O que o teste protege é a divisão de relógios: na Edição só aparece o que
o usuário pôs à mão, porque isso nasce em tempo de rascunho
(`renderedToDraft`); os inserts da IA vêm do edit-data no relógio do vídeo
FINAL e desenhá-los sobre o corte em edição os poria no lugar errado.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_a_midia_pode_entrar_pela_edicao():
    assert "A busca de imagem é da aba Final" not in JS
    assert "S.tab !== 1 && S.tab !== 2" in JS


def test_na_edicao_so_aparece_o_que_foi_posto_na_mao():
    """Insert da IA está no relógio do vídeo final; desenhá-lo sobre o corte
    em edição o poria no lugar errado."""
    i = JS.index("const soManuais = !phase2;")
    bloco = JS[i:i + 420]
    assert "c.isNew" in bloco, bloco
    assert "if (soManuais && !visiveis.length) return;" in bloco


def test_a_faixa_aparece_na_edicao_quando_ha_midia():
    i = JS.index("const temManual =")
    bloco = JS[i:i + 260]
    assert "c.isNew" in bloco
    assert "!phase2 && !temManual" in bloco


def test_o_bloco_do_gancho_abre_o_editor_da_manchete():
    i = JS.index("O bloco GANCHO da linha do tempo")
    bloco = JS[i:i + 900]
    assert "c.kind !== 'hook'" in bloco
    assert "beginHeadlineEdit()" in bloco


def test_soltar_o_bloco_nao_abre_o_editor():
    """Todo arrasto termina em clique: sem a guarda, mover o gancho abriria
    o editor por cima do que acabou de ser movido."""
    i = JS.index("O bloco GANCHO da linha do tempo")
    assert "acabouDeArrastar" in JS[i:i + 900]
    j = JS.index("if (String(drag.type).startsWith('chip'))")
    assert "acabouDeArrastar = '1'" in JS[j:j + 300]


def test_a_marca_de_arrasto_e_limpa_depois_de_usada():
    """Marca que não se apaga trava o segundo clique — o editor nunca mais
    abriria naquele bloco."""
    i = JS.index("O bloco GANCHO da linha do tempo")
    bloco = JS[i:i + 900]
    assert re.search(r"acabouDeArrastar = '0'", bloco), bloco
