# -*- coding: utf-8 -*-
r"""A lista de máquinas tem de caber na caixa.

"isso ta cortando e mal feito" (31/08), com o print da tela: a caixa
mostrava uma linha e meia de tres, o cabecalho vinha centralizado e sem
respiro, a data ocupava "30/08/2026, 21:59:13" em cada celula e o campo
de busca tinha uma SETA de menu que nao abre.

Tres defeitos, medidos no navegador com os dados reais dele:

  1. A 4.38 mandou a tabela para `.admin-tbl`, uma classe com UMA regra
     (`tr.is-bloqueado`) — o resto era tabela crua do navegador.
  2. A caixa media 87px para 191px de conteudo. Ela e item de uma coluna
     flex de altura fixa e era ela que cedia; a lista de contas tambem
     (114px para 250px). Quem tem de rolar e a pagina.
  3. `.ia-form input[type=text]` divide a regra com `select`, e junto ia
     a seta de dropdown desenhada no fundo e os 34px reservados para ela
     — em TODO campo de digitar do app.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _regra(seletor: str) -> str:
    i = CSS.index(seletor)
    return CSS[i:CSS.index("}", i)]


def test_a_caixa_da_lista_nao_encolhe():
    """Medido: 87px de caixa para 191px de conteudo, 3 maquinas virando
    'uma linha e um pedaco'."""
    assert "flex: 0 0 auto;" in _regra(".admin-access-table.wrap {")
    assert "max-height: 340px" in _regra(".admin-access-table.wrap {")
    assert "flex: 0 0 auto" in _regra(".lic-admin-list { ")


def test_a_tabela_tem_estilo_proprio():
    for prop in ("border-collapse", "table-layout: fixed"):
        assert prop in _regra(".admin-tbl {"), prop
    # cabecalho colado no topo enquanto rola, e alinhado a esquerda
    assert "position: sticky" in _regra(".admin-tbl thead th {")
    assert "text-align: left" in _regra(".admin-tbl th,")


def test_o_id_longo_nao_manda_na_largura():
    """40 caracteres de id esticavam a primeira coluna e empurravam o
    resto para fora."""
    r = _regra(".admin-tbl .maq-id {")
    assert "text-overflow: ellipsis" in r and "white-space: nowrap" in r


def test_campo_de_texto_nao_tem_seta_de_menu():
    r = _regra('.ia-form input[type="url"],\n.ia-form input[type="password"],\n'
               '.ia-form input[type="text"],\n.ia-form input[type="email"],\n'
               '.ia-form input[type="number"] {')
    assert "background-image: none" in r
    assert "padding-right: 12px" in r


def test_a_data_da_tabela_e_curta():
    i = JS.index("const anoAtual = new Date().getFullYear();")
    bloco = JS[i:i + 700]
    assert 'day: "2-digit", month: "2-digit"' in bloco
    assert 'hour: "2-digit", minute: "2-digit"' in bloco
    assert "year: \"2-digit\"" in bloco, "ano so quando nao e deste ano"


def test_busca_sem_resultado_avisa_em_vez_de_sumir():
    i = JS.index("async function loadAberturas()")
    bloco = JS[i:JS.index("\nfunction wireAberturas", i)]
    assert "Nenhum computador" in bloco
