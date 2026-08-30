# -*- coding: utf-8 -*-
"""Achar um vídeo pelo nome que está escrito nele.

O usuário tem 183 vídeos prontos. Dois buracos, achados em 30/08:

1. A busca de Projetos casava o NOME DA PASTA
   ("20260829-185156_Elizangela001_08291440_C039_1279ed7ca7") e o arquivo
   de câmera — nunca o TÍTULO, que é o que o cartão mostra e o que ele
   lembra. Digitar "lanterna" não achava "Celular na lanterna?".
2. Concluídos — a tela dos 183 — não tinha busca nenhuma.

Provado no navegador com três vídeos: "lanterna" acha pelo título,
"IMG_1678" pelo arquivo, "20260821" pela pasta, e um termo que não existe
devolve zero.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


def test_a_busca_olha_o_titulo():
    """O título é o que o cartão mostra — e o que ele nunca consultava."""
    i = JS.index("function casaBusca(")
    bloco = JS[i:i + 500]
    assert "j.title" in bloco
    assert "j.name" in bloco
    assert "jobFolderName(j)" in bloco
    # e o título existe em todo job desde o enrich
    assert 'job["title"] = _resolve_job_title(' in SRV


def test_as_duas_telas_usam_a_mesma_busca():
    """Duas buscas com regras diferentes na mesma lista seria pior que uma
    busca fraca."""
    assert JS.count("casaBusca(j, state.doneBusca)") == 1
    assert JS.count("casaBusca(j, state.projBusca)") == 1
    assert JS.count("function casaBusca(") == 1
    # a regra antiga não pode voltar
    assert 'String(j.name || "").toLowerCase().includes(busca)' not in JS


def test_concluidos_tem_campo_de_busca():
    i = HTML.index('data-view-panel="done"')
    bloco = HTML[i:HTML.index("</section>", i)]
    assert 'id="doneSearch"' in bloco
    assert "Buscar pelo título" in bloco
    assert '  doneBusca: "",' in JS
    assert '$("#doneSearch")' in JS


def test_o_texto_do_campo_diz_o_que_da_para_buscar():
    """"Buscar por nome…" não dizia QUAL nome — e o nome da pasta é um
    carimbo de data que ninguém decora."""
    assert "Buscar por nome…" not in HTML
    assert HTML.count("Buscar pelo título, pelo arquivo…") == 2
