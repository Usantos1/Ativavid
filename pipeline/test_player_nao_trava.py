# -*- coding: utf-8 -*-
"""O laco de reproducao do editor nao pode pedir layout no meio do quadro.

Relato dele em 31/08: "mesmo sem video na fila nosso player da umas
travadas e atrasadas no video, entao nao e CPU; se eu abrir a pasta e
abrir em outro player, mesmo com 10 videos na fila, nao trava".

Ele estava certo em descartar a CPU e o arquivo. Medido nesta maquina:

  * o servidor entrega faixas de 256 KB do `cut.mp4` em 2,3-2,9 ms
    (mediana de 120 faixas, duas rodadas), pior caso 24,6 ms — a entrega
    nao e o gargalo;
  * na PAGINA CARREGADA do editor (955 nos, 44 chips de legenda),
    `positionNeedle` custava 3,97 ms por chamada e rodava a cada quadro;
  * o par que custa: escrever `needle.style.left` custa 0,001 ms, mas
    escrever e ENTAO ler `panel.scrollLeft` custa 1,51 ms — a leitura
    obriga o navegador a refazer o layout da timeline ali mesmo, 60x por
    segundo, so para mover uma linha de 2 px;
  * `drawWave` custa 7,8 ms e uma unica rolagem agendava varios.

Nao consegui fechar o A/B tocando o video: os dois navegadores que tenho
aqui desenham em segundo plano, e nessa condicao o Chromium engasga o rAF
e pula o layout — qualquer numero de ponta a ponta sairia inventado. O que
este teste guarda e a FORMA que o laco tem de manter.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def _bloco(nome: str) -> str:
    i = JS.index(f"function {nome}(")
    return JS[i:JS.index("\nfunction ", i + 10)]


def test_a_agulha_le_a_rolagem_antes_de_escrever():
    b = _bloco("positionNeedle")
    esq = b.index("panel.scrollLeft")
    assert esq < b.index("needle.style.left"), \
        "ler scrollLeft depois de escrever forca o layout no meio do quadro"


def test_a_agulha_so_escreve_o_que_mudou():
    b = _bloco("positionNeedle")
    assert "if (x !== ultimoNeedleX)" in b
    assert "if (needle.style.visibility !== oculta)" in b
    assert b.count("textContent !== ") == 2, "os dois relogios sao condicionais"


def test_o_quadro_le_o_layout_uma_vez_so():
    b = _bloco("rafLoop")
    leitura = b.index("quadroEsq = panel.scrollLeft")
    assert leitura < b.index("updateCapOverlay()"), \
        "a leitura tem de vir antes de qualquer escrita do quadro"
    assert "panel.clientWidth" not in b.split("larguraPainel")[-1], \
        "a rolagem automatica reusa a largura ja lida"
    assert "quadroEsq = null" in b, "fora do quadro cada um le por conta"


def test_rolar_redesenha_a_onda_uma_vez_por_quadro():
    """`drawWave` custa 7,8 ms; uma rolagem dispara varios eventos."""
    i = JS.index("panel.addEventListener('scroll'")
    b = JS[i:i + 400]
    assert "redesenhoPendente" in b and "if (redesenhoPendente) return" in b
