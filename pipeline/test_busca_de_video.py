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


def test_vazio_por_busca_nao_mente_sobre_o_acervo():
    """Defeito que a PRÓPRIA busca criou, na 3.94: com 183 vídeos prontos,
    procurar algo inexistente mostrava "Nenhum vídeo pronto ainda."

    Provado no navegador: com resultado o aviso some; sem resultado ele diz
    «Nenhum resultado para “zzzz”» com um botão de limpar; sem vídeo nenhum
    volta o texto de fábrica.
    """
    i = JS.index("function renderInto(")
    bloco = JS[i:i + 2000]
    assert "Nenhum resultado para" in bloco
    assert "data-limpar-busca" in bloco
    # o texto de fábrica é guardado ANTES de ser escrito por cima
    assert "dataset.textoOriginal" in bloco
    assert bloco.index("dataset.textoOriginal =") < bloco.index("Nenhum resultado para")


def test_a_assinatura_do_vazio_inclui_o_termo():
    """Sem isso, trocar de termo não repinta: o `cardSig` continuaria
    "empty" e a mensagem ficaria com a busca anterior."""
    i = JS.index("function renderInto(")
    bloco = JS[i:i + 2000]
    # 5.0.12: o vazio por FILTRO DE EMPRESA tambem entra na assinatura
    assert "const sigVazio = termo ? `empty:${termo}` : (escondidos ? `empty:emp:${escondidos}:${state.brandActive.id}` : \"empty\");" in bloco
    assert 'box.dataset.cardSig = sigVazio;' in bloco


def test_limpar_a_busca_limpa_o_campo_e_o_estado():
    i = JS.index('const b = e.target.closest("[data-limpar-busca]");')
    bloco = JS[i:i + 500]
    assert 'campo.value = "";' in bloco
    assert 'state.doneBusca = "";' in bloco
    assert 'state.projBusca = "";' in bloco
    assert "renderJobs();" in bloco
