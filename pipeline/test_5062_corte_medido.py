# -*- coding: utf-8 -*-
"""5.0.62: o corte passa a dizer onde gasta o tempo (e "aplicar a todos").

`_marco_corte` existe desde 30/08, mas só no caminho SEM J-cut — que quase
nunca roda. Em 133 projetos reais desde 01/09 o `timing.json` não tem UMA
fase `CUT_*`: o corte, que é a maior fatia do job (mediana 33,1 s de 114),
era uma caixa preta que a instrumentação já achava estar medindo.

Com as etapas no lugar, o primeiro corte medido de um projeto real disse
tudo em uma linha: planejar 0,00 s, preparar fontes 0,19 s, **extrair
33,52 s**, montar 1,42 s, compor 0,00 s, normalizar 3,96 s. A extração é
85% do corte — e dentro dela o `colorbalance` do ffmpeg sozinho custa mais
que o decode e o encode somados (a investigação está no cabeçalho do
`render.py`).

O "Aplicar a todos" vem junto porque nasceu da mesma leitura: quem acerta
o look num take quer o vídeo inteiro naquele look, e repetir take a take
num corte de vinte é o tipo de trabalho que devolve o cliente ao CapCut.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")

ETAPAS = ("planejar", "preparar_fontes", "extrair", "montar", "compor",
          "normalizar")


def test_todas_as_etapas_do_corte_se_medem():
    for etapa in ETAPAS:
        assert f'_marco_corte("{etapa}"' in RENDER, etapa


def test_as_etapas_do_caminho_PADRAO_estao_cobertas():
    """O caminho com J-cut é o normal; era ele que não tinha medição."""
    i = RENDER.index("def extract_and_assemble_jcut")
    corpo = RENDER[i:RENDER.index("# -------- Master SRT")]
    for etapa in ("planejar", "preparar_fontes", "extrair"):
        assert f'_marco_corte("{etapa}"' in corpo, f"{etapa} fora do J-cut"
    assert corpo.index('_marco_corte("extrair"') > corpo.index("finally:"), (
        "no `finally` a medição cobre também o corte que QUEBRA")
    i2 = RENDER.index("def assemble_jcut")
    assert '_marco_corte("montar"' in RENDER[i2:i2 + 1600]


def test_a_normalizacao_nao_fica_junto_com_a_composicao():
    """São dois encodes diferentes do vídeo inteiro: medir os dois juntos
    esconderia qual deles vale atacar."""
    i = RENDER.index('_marco_corte("compor"')
    j = RENDER.index('_marco_corte("normalizar"')
    assert i < j
    assert "_t_norm = _t_main.perf_counter()" in RENDER[i:j]


def test_o_run_fast_transforma_as_linhas_em_fases():
    assert '_recolher_marcos_do_corte(_helper("render.py"' in RF
    padrao = re.search(r'TIMING_CORTE \(\\w\+\)=\(\[0-9\.\]\+\)', RF)
    assert padrao, "o padrão que lê as linhas do helper"
    assert '_TIMING[f"CUT_{m.group(1)}"]' in RF
    # as sub-fases nao podem entrar no total: elas vivem DENTRO do CUT
    assert 'if not k.startswith("CUT_")' in RF


def test_o_nome_da_etapa_sobrevive_ao_padrao():
    """`\\w+` não casa acento nem hífen: um nome fora disso viraria uma fase
    que nunca aparece."""
    for etapa in ETAPAS:
        assert re.fullmatch(r"\w+", etapa), etapa


def test_aplicar_a_todos_copia_o_take_inteiro():
    assert "todos.textContent = 'Aplicar a todos';" in PJS
    bloco = PJS.split("todos.addEventListener", 1)[1][:900]
    assert "camposDoTake(r)" in bloco, "copia o mesmo pacote que vai no EDL"
    for campo in ("gain_db", "grade", "speed", "freeze", "reframe", "flip"):
        assert f"'{campo}'" in bloco, f"{campo} precisa ser LIMPO antes"
    assert "x !== r && !x.removed" in bloco, "não copia para o próprio nem para apagados"
    assert "JSON.parse(JSON.stringify(campos))" in bloco, (
        "o reframe é um objeto: sem cópia funda, todos os takes dividiriam "
        "o MESMO objeto e mexer num mexeria em todos")
    assert "pushHistory();" in bloco, "tem de dar para desfazer"
    assert "persistEdl();" in bloco
