# -*- coding: utf-8 -*-
"""O player da Biblioteca — o do navegador saiu.

"se clicar em qualquer lugar do nome deve dar play e pausa, quero ver a
forma de onda do audio, ali tem muito espaco que pode ser usado do nome ate
o player, quero outro tipo de player melhor esse ta bem amador" (30/08).
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")


def test_o_audio_do_navegador_saiu_da_lista():
    # a linha da lista não monta mais um <audio> — a única menção que sobra
    # é o comentário que explica por que ele saiu
    i = JS.index("const linha = (it) => {")
    assert "<audio" not in JS[i:JS.index("if (state.libCat)", i)]
    assert 'class="lib-onda"' in JS and 'class="lib-play"' in JS


def test_a_linha_inteira_da_play():
    i = JS.index('linha.addEventListener("click"')
    bloco = JS[i:i + 400]
    # só o seletor de categoria e a própria onda têm ação própria
    assert 'e.target.closest("select, option, .lib-onda")' in bloco
    assert "tocarLinha(linha);" in bloco


def test_a_onda_ocupa_o_vao():
    """O vão entre o nome e o player ficava vazio: a onda é a única coisa
    da linha que cresce."""
    i = CSS.index(".lib-onda {")
    bloco = CSS[i:CSS.index("}", i)]
    assert "flex: 1 1 auto;" in bloco
    j = CSS.index(".lib-track-name { flex:")
    assert "flex: 0 1 auto;" in CSS[j:j + 60]


def test_um_audio_de_cada_vez():
    """Duas faixas juntas não ajudam a escolher nenhuma das duas."""
    i = JS.index("function tocarLinha(")
    assert "pararAudio();" in JS[i:i + 200]
    # e trocar de aba/filtro também para o que estava tocando
    assert "pararAudio();          // a lista mudou" in JS


def test_a_onda_so_decodifica_o_que_esta_na_tela():
    """242 efeitos decodificados de uma vez travariam a página."""
    assert "IntersectionObserver" in JS
    i = JS.index("function puxarFila()")
    assert "baixando < 4" in JS[i:i + 200]
    assert "PICOS.has(linha.dataset.rel)" in JS


def test_os_picos_sao_maximo_e_nao_media():
    """Um efeito de 0,2s viraria uma linha reta com média — e o pico é
    justamente o que se quer ver num efeito sonoro."""
    i = JS.index("async function picosDoArquivo(")
    bloco = JS[i:i + 1200]
    assert "if (v > m) m = v;" in bloco
    assert "out[i] /= teto;" in bloco       # normalizado
