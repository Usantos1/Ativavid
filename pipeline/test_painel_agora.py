# -*- coding: utf-8 -*-
"""O painel "Agora" mostra a fila inteira.

Ele cortava em 3 e resumia o resto num botao "+2 na fila" — exatamente o
que o usuario quer ver quando manda varios videos de uma vez ("ali pode
mostrar todas as filas", 27/08). Agora lista todas, e a lista rola dentro
do painel para nao empurrar o hero de importar para fora da tela (medido
com 15 na fila: lista travada em 232px, hero ainda visivel).
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _funcao_agora() -> str:
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function renderHomeNow(")
    return js[i:js.index("\n}", i)]


def test_lista_todas_as_ativas():
    f = _funcao_agora()
    assert "actives.slice(0, 3)" not in f, "voltou a cortar em 3"
    assert re.search(r"actives\.map\(", f), "nao percorre todas as ativas"


def test_nao_ha_mais_o_botao_de_resumo():
    f = _funcao_agora()
    assert "home-now-more" not in f
    assert "na fila</button>" not in f


def test_o_titulo_conta_quantas_sao():
    f = _funcao_agora()
    assert "home-now-count" in f and "actives.length" in f


def test_a_lista_rola_em_vez_de_empurrar_a_tela():
    css = (RAIZ / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    i = css.index(".home-now-list {")
    regra = css[i:css.index("}", i)]
    assert re.search(r"max-height:\s*\d+px", regra), "sem teto, 20 na fila"
    assert "overflow-y: auto" in regra


def test_a_lista_existe_no_html_gerado():
    f = _funcao_agora()
    assert 'class="home-now-list"' in f
