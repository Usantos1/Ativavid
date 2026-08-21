# -*- coding: utf-8 -*-
"""Os quadros de "Identidade visual" abrem o editor NA SEÇÃO CERTA.

A tela de Marca prometia, com todas as letras, "abrem já na seção certa". Não
cumpria: os três quadros eram `data-view="estilo"` sem destino nenhum, e os
três caíam no topo de um editor de 3.073 pixels. Um texto que promete e não
entrega é pior que não prometer — o usuário procura o que foi dito que estaria
ali.

Agora o hub manda o destino por `postMessage` e o editor rola até ele. Por
`postMessage` e não pelo `src` de propósito: trocar o `src` recarrega o editor
e leva junto qualquer ajuste ainda não salvo.

Conferido no navegador, com os três destinos, contra o `main` (que é quem rola
de fato — `#styleSetup` tem `overflow: visible` e `scrollTop` sempre 0):

| destino | scrollTop | parou em | na vista |
|---|---|---|---|
| accent | 517 | "Cor da headline" | sim |
| fontes | 2142 | "Fonte da legenda" | sim |
| cartao | 2442 | "Elementos da marca" | sim |

E com os 4 blocos `<details>` fechados: abre só o do alvo, deixa os outros 3
fechados, e para em "Elementos da marca".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HUB_HTML = REPO / "assets" / "studio" / "index.html"
HUB_JS = REPO / "assets" / "studio" / "studio.js"
ED_HTML = REPO / "assets" / "preview" / "index.html"
ED_JS = REPO / "assets" / "preview" / "app.js"
ED_CSS = REPO / "assets" / "preview" / "app.css"


def _alvos_do_editor() -> dict[str, str]:
    js = ED_JS.read_text(encoding="utf-8")
    bloco = js[js.index("const IR_ALVOS = {"):]
    bloco = bloco[:bloco.index("}")]
    return dict(re.findall(r"(\w+)\s*:\s*'([^']+)'", bloco))


def test_cada_quadro_diz_para_onde_vai():
    """Sem `data-ident` o quadro cai no topo — que era o defeito."""
    html = HUB_HTML.read_text(encoding="utf-8")
    grid = html[html.index('id="identGrid"'):]
    grid = grid[:grid.index("</div>")]
    tiles = re.findall(r'<button[^>]*class="ident-tile"[^>]*>', grid)
    assert len(tiles) >= 3, tiles
    sem_destino = [t for t in tiles if 'data-view="estilo"' in t and "data-ident=" not in t]
    assert not sem_destino, ("quadro que abre o editor sem dizer onde parar", sem_destino)


def test_todo_destino_do_hub_existe_no_editor():
    alvos = _alvos_do_editor()
    html = HUB_HTML.read_text(encoding="utf-8")
    pedidos = set(re.findall(r'data-ident="([^"]+)"', html))
    assert pedidos, "nenhum quadro pede destino"
    assert pedidos <= set(alvos), (
        "o hub pede um destino que o editor não conhece", pedidos - set(alvos))


def test_todo_alvo_aponta_para_um_elemento_que_existe():
    """Um seletor com erro de digitação faz a função desistir calada, depois
    de tentar por 3s — o botão pareceria simplesmente não funcionar."""
    ed = ED_HTML.read_text(encoding="utf-8")
    for nome, sel in _alvos_do_editor().items():
        assert sel.startswith("#"), (nome, sel)
        assert f'id="{sel[1:]}"' in ed, (nome, sel, "não existe no editor")


def test_a_rolagem_nao_usa_smooth():
    """Medido neste iframe: o instantâneo leva o `main` a 2142 e o suave o
    deixa em 0. O app roda em Edge WebView2 — com `smooth` o quadro vira um
    botão que não faz nada, sem erro nenhum no console."""
    js = ED_JS.read_text(encoding="utf-8")
    i = js.index("function irParaSecao(")
    corpo = js[i:i + 1800]
    # Ancorado na CHAMADA, não no corpo: o comentário logo acima dela explica
    # por que não usar `smooth`, e a versão anterior deste teste casava com o
    # próprio comentário — passaria mesmo com a chamada errada.
    j = corpo.index("scrollIntoView")
    chamada = corpo[j:corpo.index(")", j) + 1]
    assert "smooth" not in chamada, ("o `behavior: 'smooth'` não rola neste contexto", chamada)
    assert "block: 'center'" in chamada, chamada


def test_abre_o_details_antes_de_rolar():
    """Num `<details>` fechado o alvo tem altura 0 e a rolagem para no lugar
    errado. Conferido: com os 4 fechados, abre só o do alvo."""
    js = ED_JS.read_text(encoding="utf-8")
    i = js.index("function irParaSecao(")
    corpo = js[i:i + 1800]
    assert ".open = true" in corpo
    assert corpo.index(".open = true") < corpo.index("scrollIntoView"), (
        "abrir o bloco DEPOIS de rolar não adianta")


def test_o_container_realcado_e_o_mais_proximo():
    """`.setup-group` antes de `.auto-field` pegava o grupo "Tipo de conteúdo
    e formato", de milhares de pixels: realçá-lo não aponta nada e
    centralizá-lo joga o campo para fora da tela. Aconteceu no primeiro teste."""
    js = ED_JS.read_text(encoding="utf-8")
    i = js.index("function irParaSecao(")
    corpo = js[i:i + 1800]
    assert "closest('.auto-field, .setup-group')" in corpo, (
        "voltou a escolher o contêiner por precedência em vez do mais próximo")


def test_o_hub_nao_recarrega_o_editor_para_mandar_o_destino():
    """Trocar o `src` levaria junto o ajuste ainda não salvo no editor."""
    js = HUB_JS.read_text(encoding="utf-8")
    i = js.index("function mandarAlvoAoEstilo(")
    corpo = js[i:js.index("function estiloFrameSrc(", i)]
    assert "postMessage" in corpo
    assert "estiloFrameSrc" not in corpo, "voltou a recarregar o editor"
    assert 'dataset.ok !== "1"' in corpo, (
        "sem esperar o load, a mensagem chega antes do editor existir")
    assert 'alvoNoEstilo = ""' in corpo, (
        "sem limpar, a próxima visita a Estilos rola sozinha")


def test_o_realce_existe_e_respeita_quem_pediu_menos_movimento():
    css = ED_CSS.read_text(encoding="utf-8")
    assert ".ir-piscou" in css, "a rolagem não diz onde parou"
    i = css.index("@media (prefers-reduced-motion: reduce)", css.index(".ir-piscou"))
    bloco = css[i:i + 320]
    assert "ir-piscou" in bloco and "animation: none" in bloco
    assert "box-shadow" in bloco, (
        "sem o pisca E sem borda, quem pediu menos movimento não vê onde parou")


def test_o_texto_da_tela_nao_promete_o_que_o_logo_nao_faz():
    """O quadro do Logo vai para a Biblioteca, não para o editor de estilo."""
    html = HUB_HTML.read_text(encoding="utf-8")
    grid = html[html.index('id="identGrid"'):]
    grid = grid[:grid.index("</div>")]
    logo = [t for t in re.findall(r"<button[^>]*>", grid) if "biblioteca" in t]
    assert logo, "o quadro do Logo deixou de apontar para a Biblioteca"
    hint = html[html.index("Identidade visual"):html.index('id="identGrid"')]
    assert "Estes itens vivem no editor de estilo da marca" not in hint, (
        "o texto voltou a dizer que TODOS abrem no editor de estilo")
