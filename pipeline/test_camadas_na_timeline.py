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


def test_da_para_tirar_o_que_foi_posto_na_mao():
    """Somar sem tirar é armadilha: o emoji errado ficava no vídeo, e só o
    Ctrl+Z imediato salvava. O ✕ aparece só no que o usuário criou."""
    assert "function removerBlocoDaMao" in JS
    i = JS.index("function removerBlocoDaMao")
    bloco = JS[i:i + 700]
    # histórico ANTES: remover por engano não pode custar o trabalho
    assert bloco.index("pushHistory()") < bloco.index("splice(i, 1)")
    assert "if (!c || !c.isNew) return;" in bloco
    # e o ✕ só nasce no bloco do usuário — e só quando ele está selecionado
    j = JS.index("if (c.isNew && S.blocoSel === i) {")
    assert "chip-x" in JS[j:j + 400]


def test_o_gancho_nao_se_apaga_pela_linha_do_tempo():
    """Ele é parte do estilo — desliga-se no Estilo, não com um ✕ que
    apagaria a manchete do vídeo sem dizer isso."""
    i = JS.index("function removerBlocoDaMao")
    assert "!c.isNew" in JS[i:i + 300]


def test_o_bloco_da_mao_se_pega_tambem_na_edicao():
    """Print de 30/08: o usuário põe um som e não consegue apagá-lo —
    clicar no bloco só levava a agulha para o ponto. Mover e esticar eram
    coisas só do Visual; mas o que ele põe à mão nasce em tempo de rascunho,
    que é o relógio da Edição."""
    assert "const daMao = chip && S.insertsDraft[+chip.dataset.i]?.isNew;" in JS
    i = JS.index("const daMao =")
    bloco = JS[i:i + 700]
    assert "(S.tab === 2 || daMao)" in bloco
    # duas vezes: esticar (handle) e mover (corpo)
    assert bloco.count("S.tab === 2 || daMao") == 2


def test_o_x_do_bloco_curto_nao_depende_do_hover():
    """O bloco de som tem 0,6s (~24px): um ✕ escondido no hover, encostado
    na borda, é alvo pequeno demais."""
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    i = css.index(".chip .chip-x.sempre")
    assert "opacity: 0.75" in css[i:i + 120]
    # e a área de toque é maior que o desenho
    j = css.index(".chip .chip-x::after")
    assert "inset: -6px" in css[j:j + 160]
    assert "chip-x sempre" in JS


def test_a_capa_fica_na_coluna_e_nao_na_faixa():
    """Como no CapCut: a capa é um botão na COLUNA da esquerda, junto do
    ícone da faixa de vídeo — fora da linha do tempo. Dentro da faixa (a
    primeira tentativa, 3.73) ela empurrava os clipes e virava mais um
    bloco: "capa deve ser ali fora da timeline... onde mostra o icone de
    video na esquerda" (30/08).

    E JUNTO do ícone, não no lugar dele: os dois ficam na mesma coluna."""
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    i = html.index('class="track-label track-label-video"')
    fim = html.index('id="laneVideo"')
    coluna = html[i:fim]
    assert 'data-icon="video"' in coluna, "o ícone da faixa não pode sumir"
    assert 'id="capaChip"' in coluna, "a capa tem de morar na coluna"
    assert "$('capaChip')" in JS and "saveCoverFromPlayhead()" in JS


def test_a_barra_ficou_so_de_icones_nos_tres():
    """Marcar, Cortar e Excluir viraram ícone: o nome fica no passar do
    mouse e a barra devolve espaço — era ele que fazia os rótulos
    recolherem cedo na tela do usuário (125% de escala)."""
    assert "$('btnSplit').innerHTML = ICON.razor;" in JS
    assert "$('btnDeleteTake').innerHTML = ICON.trash;" in JS
    i = JS.index("const rotuloMarca =")
    assert "btn.title =" in JS[i:i + 400]


def test_o_x_so_aparece_no_bloco_selecionado():
    """"x ali atrapalha": colado num bloco de 24px ele comia o bloco e
    ainda errava o alvo. Em editor de vídeo se seleciona e se aperta
    Delete."""
    i = JS.index("if (c.isNew && S.blocoSel === i) {")
    assert "chip-x" in JS[i:i + 300]
    # e o Delete age no bloco selecionado ANTES do take
    k = JS.index("S.blocoSel >= 0) {")
    take = JS.index("S.selected >= 0 && S.tab === 1")
    assert k < take, "o bloco selecionado tem de vir antes do take no Delete"


def test_clicar_fora_solta_a_selecao():
    i = JS.index("if (!chip && S.blocoSel >= 0) {")
    assert "S.blocoSel = -1;" in JS[i:i + 200]
