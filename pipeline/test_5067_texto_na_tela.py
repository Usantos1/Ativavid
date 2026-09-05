# -*- coding: utf-8 -*-
"""5.0.67: escrever um texto por cima do vídeo.

Era o maior buraco em relação ao CapCut: dava para pôr imagem, emoji e som
na linha do tempo, texto não. O `wordAccents` existia na régua do editor
mas nenhum motor de render o consumia — era uma faixa que não desenhava
nada.

A saída foi não ensinar desenho novo a ninguém. O texto vira um **PNG
transparente no próprio navegador** e entra como mídia manual. Com isso,
arrastar, redimensionar, enquadrar, escolher camada e animar entrada e
saída — tudo que já existe para mídia — passa a valer para o texto, e os
dois motores de render continuam sabendo só desenhar mídia. Nada novo para
manter igual entre eles (que é o defeito que a varredura de desenho existe
para pegar).

Conferido no laboratório, na porta 4894, com a raiz de projetos isolada:
os três estilos desenham, o texto longo quebra em até três linhas, o PNG
sai com fundo transparente e a rota de upload devolve
`used.src = library/<arquivo>.png` — o mesmo caminho que uma imagem colada
já usava.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")

ESTILOS = ("contorno", "caixa", "limpo")


def test_a_aba_existe_e_tem_os_controles():
    assert 'id="imgTabTexto"' in HTML
    assert 'id="imgTextoPane"' in HTML
    for campo in ("txtConteudo", "txtTamanho", "txtCor", "txtInserir", "txtPreview"):
        assert f'id="{campo}"' in HTML, campo
    for e in ESTILOS:
        assert f'data-txt-estilo="{e}"' in HTML, e
        # a pilula que ja existe, para os botoes nao nascerem sem estilo
        assert f'class="img-fonte txt-estilo{"" if e != "contorno" else " active"}"' \
            f' data-txt-estilo="{e}"' in HTML, e
    assert ".txt-preview" in CSS and ".txt-campo" in CSS


def test_a_aba_entra_no_rodizio_das_outras():
    """`setImgTab` escondia o painel da Biblioteca com `!== 'pexels'` — com
    uma aba nova essa conta passa a deixar dois paineis abertos."""
    bloco = PJS.split("function setImgTab(tab) {", 1)[1].split("\n}", 1)[0]
    for pane, chave in (("imgPexelsPane", "pexels"), ("imgLibraryPane", "library"),
                        ("imgTextoPane", "texto")):
        assert f"$('{pane}')?.classList.toggle('hidden', IMG_TAB !== '{chave}')" in bloco, pane
    assert "tab === 'texto'" in bloco, "a aba precisa ser aceita"


def test_o_desenho_e_o_MESMO_da_previa_e_do_arquivo():
    """A previa e o arquivo saem da mesma funcao — senao o que ele ve nao e
    o que entra no video."""
    assert PJS.count("desenharTexto(cv,") >= 2
    prev = PJS.split("function pintarTexto()", 1)[1][:400]
    ins = PJS.split("async function inserirTexto()", 1)[1][:900]
    assert "desenharTexto(" in prev and "desenharTexto(" in ins


def test_o_texto_nasce_com_a_cara_da_marca():
    fonte = PJS.split("function fonteDoTexto(", 1)[1][:400]
    assert "S.style && S.style.captionFont" in fonte, "a fonte das legendas dele"
    assert "'Poppins'" in fonte, "reserva quando a marca nao definiu fonte"
    cor = PJS.split("function corDaMarcaOuBranco()", 1)[1][:300]
    assert "S.style.accent" in cor


def test_o_contorno_aguenta_qualquer_fundo():
    """Texto branco sem contorno some num quadro claro — e o quadro por
    baixo e um video, nao um fundo escolhido."""
    corpo = PJS.split("function desenharTexto(", 1)[1][:2600]
    assert "strokeStyle = '#0b0d10'" in corpo
    assert "lineJoin = 'round'" in corpo, "canto agudo vira espinho no contorno"
    assert re.search(r"lineWidth = Math\.max\(6, tam \* 0\.1", corpo), corpo[:200]
    assert "c.strokeText(linha, x, y)" in corpo
    i_stroke = corpo.index("strokeText")
    i_fill = corpo.index("c.fillText(linha")
    assert i_stroke < i_fill, "o contorno vai por baixo da letra"


def test_a_caixa_escolhe_a_letra_pelo_contraste():
    corpo = PJS.split("function desenharTexto(", 1)[1][:2600]
    assert "luzDaCor(corCaixa) > 0.55 ? '#0b0d10' : '#ffffff'" in corpo, (
        "letra clara sobre caixa clara sumiria")
    luz = PJS.split("function luzDaCor(hex)", 1)[1][:600]
    assert "0.2126" in luz and "0.7152" in luz and "0.0722" in luz, "luminancia relativa"
    assert "0.03928" in luz, "a curva sRGB, nao a media dos canais"


def test_o_texto_longo_quebra_e_para_em_tres_linhas():
    q = PJS.split("function quebrarTexto(", 1)[1][:800]
    assert "ctx.measureText(tentativa).width > larguraMax" in q
    assert ".slice(0, 3)" in q, "sem teto, uma frase longa viraria uma coluna"


def test_entra_pelo_mesmo_cano_de_uma_imagem_colada():
    """Nada de rota nova: o PNG sobe pelo `/api/library/upload?use=1&folder=`
    que a imagem colada ja usava, e volta como `used.src`."""
    ins = PJS.split("async function inserirTexto()", 1)[1][:1100]
    assert "subirArquivoParaTimeline(" in ins
    assert "cv.toBlob(ok, 'image/png')" in ins, "PNG: o fundo tem de sair transparente"
    assert "new File([blob]" in ins
    sub = PJS.split("async function subirArquivoParaTimeline(", 1)[1][:900]
    assert "/api/library/upload" in sub and "pushInsertFromRef(" in sub


def test_nao_deixa_inserir_fora_da_edicao():
    ins = PJS.split("async function inserirTexto()", 1)[1][:1100]
    assert "S.tab !== 1 && S.tab !== 2" in ins
    assert "if (!texto)" in ins, "texto vazio nao vira arquivo"


def test_o_nome_do_arquivo_sobrevive_a_acento_e_emoji():
    ins = PJS.split("async function inserirTexto()", 1)[1][:1100]
    assert r"replace(/[^\p{L}\p{N}]+/gu, '-')" in ins, (
        "sem isso, `50% OFF!` viraria um nome de arquivo invalido")
    assert "|| 'livre'" in ins, "texto so de simbolos deixaria o nome vazio"
