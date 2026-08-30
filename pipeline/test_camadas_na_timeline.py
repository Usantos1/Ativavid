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
    Ctrl+Z imediato salvava. Tirar é selecionar o bloco e usar o Excluir de
    cima (ou Delete) — o ✕ colado no bloco saiu na 3.75 porque num bloco de
    24px ele comia o próprio bloco."""
    assert "function removerBlocoDaMao" in JS
    i = JS.index("function removerBlocoDaMao")
    bloco = JS[i:i + 700]
    # histórico ANTES: remover por engano não pode custar o trabalho
    assert bloco.index("pushHistory()") < bloco.index("splice(i, 1)")
    assert "if (!c || !c.isNew) return;" in bloco


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


def test_o_bloco_curto_nao_precisa_de_alvo_dentro_dele():
    """O bloco de som tem 0,6s (~24px). Qualquer botão desenhado dentro
    dele — o antigo ✕ — comia o bloco e ainda errava o alvo. Por isso a
    ação mora na barra de cima, que tem espaço."""
    assert "chip-x" not in JS
    i = JS.index("function refreshTransportActions")
    assert "S.blocoSel" in JS[i:i + 400]


def test_a_capa_fica_sozinha_na_coluna():
    """Como no CapCut: a capa é um botão na COLUNA da esquerda, fora da
    linha do tempo. Dentro da faixa (3.73) ela empurrava os clipes; com o
    ícone de vídeo ao lado (3.74) sobrava um enfeite que não dizia nada —
    "a capa deve ser apenas ela ali" (30/08)."""
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    i = html.index('class="track-label track-label-video"')
    coluna = html[i:html.index('id="laneVideo"')]
    assert 'id="capaChip"' in coluna
    assert 'data-icon="video"' not in coluna
    assert "$('capaChip')" in JS and "saveCoverFromPlayhead()" in JS


def test_a_barra_ficou_so_de_icones_nos_tres():
    """Marcar, Cortar e Excluir viraram ícone: o nome fica no passar do
    mouse e a barra devolve espaço — era ele que fazia os rótulos
    recolherem cedo na tela do usuário (125% de escala)."""
    assert "$('btnSplit').innerHTML = ICON.razor;" in JS
    assert "$('btnDeleteTake').innerHTML = ICON.trash;" in JS
    i = JS.index("const rotuloMarca =")
    assert "btn.title =" in JS[i:i + 400]


def test_clicar_no_bloco_acende_o_excluir_de_cima():
    """"quando clico na imagem deve ativar o delete que temos lá em cima,
    não aparecer um X" (30/08)."""
    i = JS.index("if (c.isNew && S.blocoSel === i) chip.classList.add('sel');")
    assert i > 0
    k = JS.index("function toggleSelectedTake")
    bloco = JS[k:k + 400]
    assert "S.blocoSel >= 0" in bloco and "removerBlocoDaMao(i);" in bloco
    # e o bloco selecionado vem ANTES do take, senão apagaria o take errado
    assert bloco.index("S.blocoSel >= 0") < bloco.index("S.selected < 0")


def test_clicar_fora_solta_a_selecao():
    i = JS.index("if (!chip && S.blocoSel >= 0) {")
    assert "S.blocoSel = -1;" in JS[i:i + 200]


def test_cortar_e_apagar_para_os_lados():
    """O Q e o W do CapCut. No nosso modelo o corte é uma lista de trechos:
    apagar à esquerda encurta o COMEÇO do trecho até a agulha, à direita o
    FIM. Não quebra o take em dois nem apaga o resto — mesmo resultado,
    feito com a peça que já existe (o trim), o que mantém o EDL válido."""
    assert "function apagarAteAAgulha" in JS
    i = JS.index("function apagarAteAAgulha")
    bloco = JS[i:i + 1800]
    assert "if (lado === 'esq') r.start = corte;" in bloco
    assert "else r.end = corte;" in bloco
    assert "persistEdl();" in bloco
    # sem take selecionado vale o que está SOB a agulha
    assert "layout.findIndex" in bloco
    # e as teclas
    assert "e.key === 'q'" in JS and "e.key === 'w'" in JS
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnCutLeft"' in html and 'id="btnCutRight"' in html


def test_a_agulha_na_borda_nao_apaga_o_take_inteiro():
    """Com a agulha na borda não há o que apagar daquele lado — e apagar o
    take todo seria destruir o que o usuário não pediu."""
    i = JS.index("function apagarAteAAgulha")
    bloco = JS[i:i + 1800]
    assert "const dentro = corte > r.start + MIN_SEG && corte < r.end - MIN_SEG;" in bloco
    assert "nada para apagar deste lado" in bloco


def test_a_coluna_da_capa_nao_tem_mais_o_icone():
    """"a capa deve ser apenas ela ali sem o icone de video" (30/08)."""
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    i = html.index('class="track-label track-label-video"')
    coluna = html[i:html.index('id="laneVideo"')]
    assert 'data-icon="video"' not in coluna
    assert 'id="capaChip"' in coluna


def test_o_excluir_de_cima_apaga_o_bloco_selecionado():
    """"quando clico na imagem deve ativar o delete que temos la em cima
    nao aparecer um X"."""
    assert "chip-x" not in JS, "o ✕ colado no bloco tinha de sair"
    i = JS.index("function refreshTransportActions")
    bloco = JS[i:i + 1200]
    assert "S.blocoSel >= 0 ? S.insertsDraft[S.blocoSel] : null" in bloco
    assert "const can = !!bloco ||" in bloco
    j = JS.index("function toggleSelectedTake")
    assert "removerBlocoDaMao(i);" in JS[j:j + 400]


def test_cortar_vale_para_a_imagem_e_o_emoji():
    """"não deixa cortar uma imagem, um áudio ou uma legenda" (30/08):
    Cortar/Q/W só olhavam os takes de vídeo e respondiam "selecione um
    take" com a imagem selecionada — resposta sobre outra coisa."""
    assert "function acaoNoBlocoSelecionado" in JS
    i = JS.index("function acaoNoBlocoSelecionado")
    bloco = JS[i:i + 1600]
    assert "S.insertsDraft.splice(S.blocoSel + 1, 0, b);" in bloco   # cortar
    assert "c.start = t;" in bloco and "c.end = t;" in bloco         # Q e W
    # e o bloco vem ANTES do take nos três caminhos
    for fn in ("function apagarAteAAgulha", "function splitAtPlayhead"):
        k = JS.index(fn)
        assert "acaoNoBlocoSelecionado" in JS[k:k + 400], fn


def test_o_efeito_sonoro_explica_em_vez_de_cortar():
    """Ele toca inteiro a partir de um instante: cortar não existe ali.
    Dizer isso é melhor que cortar de um jeito que o render ignora."""
    i = JS.index("function acaoNoBlocoSelecionado")
    bloco = JS[i:i + 1600]
    assert "Efeito é um ponto no tempo" in bloco
    assert "if (!blocoTemDuracao(c)) return false;" in bloco


def test_os_botoes_de_corte_existem_de_verdade():
    """Na 3.75 eles ficaram sem ícone e sem clique — um ramo do meu patch
    não rodou, e só as teclas Q/W funcionavam."""
    assert "$('btnCutLeft').innerHTML = ICON.cortarEsq;" in JS
    assert "$('btnCutRight').innerHTML = ICON.cortarDir;" in JS
    assert "$('btnCutLeft').addEventListener('click'" in JS
    assert "$('btnCutRight').addEventListener('click'" in JS
    # e o ícone é de forma PREENCHIDA: o CSS do app força fill=currentColor,
    # então ícone de traço vira mancha
    i = JS.index("cortarEsq:")
    assert 'fill="none"' not in JS[i:i + 400]
