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


def test_na_edicao_nao_entra_o_insert_da_ia():
    """Na Edição entra o que foi posto à mão E o gancho — nunca o insert que
    a IA colocou: ele está gravado no relógio do vídeo FINAL, e desenhá-lo
    sobre o corte em edição o poria no lugar errado.

    O gancho não tem esse problema: ele começa no segundo 0 nos dois
    relógios, e é clicando nele que se troca o texto da manchete."""
    i = JS.index("const soManuais = !phase2;")
    bloco = JS[i:i + 700]
    assert "c.isNew || c.kind === 'hook'" in bloco, bloco[:400]
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
    # a janela do app, e nao o editor de dentro do quadro: para quem esta na
    # linha do tempo, ser levado para o video e o mesmo que nao editar ali
    assert "editarManchetePelaLinhaDoTempo()" in bloco


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


def test_o_gancho_aparece_tambem_na_edicao():
    """A 3.58 pôs o clique no bloco GANCHO, mas o bloco só era desenhado no
    Visual: quem estava na Edição continuava sem editar a manchete pela
    linha do tempo (print do usuário em 29/08, já na 3.64)."""
    i = JS.index("const soManuais = !phase2;")
    bloco = JS[i:i + 700]
    assert "c.isNew || c.kind === 'hook'" in bloco, bloco[:400]
    j = JS.index("const temManual =")
    assert "c.kind === 'hook'" in JS[j:j + 200]


def test_projeto_sem_legenda_tambem_mostra_o_gancho():
    """`renderChips` saía cedo quando não havia legenda — e levava junto as
    faixas de gancho e de mídia, que nada têm com legenda."""
    assert "function desenharFaixasDeInsert" in JS
    i = JS.index("if (!showCaps) {")
    assert "desenharFaixasDeInsert(phase2);" in JS[i:i + 400]


def test_o_bloco_do_gancho_edita_ALI_e_nao_no_video():
    """A 3.65 abria o editor da manchete — que escreve DENTRO do quadro.
    Para quem estava na linha do tempo isso continuava sendo "só edita no
    vídeo" (print do usuário na 3.65). Agora o clique abre a janela do app
    com o texto atual."""
    assert "function editarManchetePelaLinhaDoTempo" in JS
    i = JS.index("function editarManchetePelaLinhaDoTempo")
    bloco = JS[i:i + 1200]
    assert "pedirTexto('Texto da manchete'" in bloco
    assert "persistHeadline([limpo])" in bloco
    # o editor de dentro do quadro continua existindo para o ajuste fino
    assert "function beginHeadlineEdit" in JS


def test_uma_linha_so_no_salvar_da_manchete():
    """Os dois motores reequilibram em duas linhas pela largura medida —
    mandar a quebra na mão só atrapalha."""
    i = JS.index("function editarManchetePelaLinhaDoTempo")
    assert "persistHeadline([limpo])" in JS[i:i + 1200]


def test_da_para_somar_pela_propria_linha_do_tempo():
    """Tudo já existia, mas cada coisa por um caminho: ícone na barra,
    pastilha ao lado da manchete. Quem olhava a linha do tempo não achava."""
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    for alvo in ("somarMidia", "somarSom", "somarEmoji", "somarLegenda"):
        assert f'id="{alvo}"' in html, alvo
        assert f"$('{alvo}')" in JS, alvo
    # e todos agem na agulha, pelos caminhos que já existiam
    i = JS.index("$('somarEmoji')")
    assert "setImgTab('emoji')" in JS[i:i + 200]
    j = JS.index("$('somarLegenda')")
    assert "escreverLegendaAqui()" in JS[j:j + 160]
