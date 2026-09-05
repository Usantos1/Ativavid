# -*- coding: utf-8 -*-
"""5.0.69: "Aulas 0" com uma aula publicada.

Print dele em 05/09: o menu mostrava **Aulas 0** e havia uma aula no ar
(`/api/aulas` devolvia "Introdução AtivaVid").

Não era um bug de contagem — era o selo respondendo outra pergunta. Ele
mostrava quantas aulas eram NOVAS desde a última visita, e portanto ficava
em 0 quase sempre. Ao lado de *Fila*, *Concluídos* e *Projetos*, que
mostram TOTAL, "Aulas 0" só podia ser lido como "não tem aula nenhuma".

Agora o número é o total, como os três vizinhos, e "tem aula nova" virou a
COR do selo (o mesmo verde-água de `.sb-badge`).

E mais dois detalhes que faziam o 0 aparecer mesmo depois disso:

- o selo era pintado depois de `refreshHealth`, `refreshAuthUi` e
  `loadBrandsUi`; agora sai na frente, sem `await` — é só um selo;
- o último total conhecido fica no `localStorage` e pinta ANTES de
  qualquer espera. No laboratório (navegador, sem a ponte do app) o
  `wireTitlebar` gasta os 3 s do próprio laço de tentativas, e o menu
  mostrava o 0 do HTML até lá. Conferido: com o cache, o selo mostra 1 aos
  150 ms.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")


def test_o_numero_do_selo_e_o_TOTAL():
    corpo = JS.split("function pintarSeloDeAulas(", 1)[1][:700]
    assert "const total = (lista || []).length;" in corpo
    assert 'setCount("#countAulas", total,' in corpo, "o numero e o total"
    assert "novo: novas > 0" in corpo, "o `novo` e so a cor"


def test_aula_nova_acende_em_vez_de_mudar_o_numero():
    assert '.sb-count[data-novo="1"]' in CSS
    bloco = CSS.split('.sb-count[data-novo="1"]', 1)[1][:200]
    assert "var(--teal)" in bloco, "o mesmo verde do selo de novidade"
    sc = JS.split("function setCount(sel, n, opcoes)", 1)[1][:420]
    assert 'el.dataset.novo = opcoes.novo ? "1" : "0"' in sc
    assert 'el.textContent = String(n);' in sc, "o numero nao muda com o realce"


def test_o_titulo_explica_o_numero():
    corpo = JS.split("function pintarSeloDeAulas(", 1)[1][:700]
    assert "Nenhuma aula publicada ainda" in corpo
    assert "nova${novas > 1" in corpo and "aula${total > 1" in corpo
    assert 'title="Aulas disponíveis"' in HTML, "o title do HTML dizia 'Aulas novas'"


def test_o_selo_nao_espera_saude_sessao_nem_marcas():
    """Ele ficava atras de tres `await` e o menu mostrava 0 enquanto isso."""
    boot = JS.split("async function boot() {", 1)[1]
    boot = boot[:boot.index("await refreshJobs()")]
    i_selo = boot.index("contarAulasNovas()")
    for antes in ("await refreshHealth()", "await refreshAuthUi()",
                  "await loadBrandsUi()"):
        assert i_selo < boot.index(antes), f"o selo tem de vir antes de {antes}"
    assert "contarAulasNovas().catch(() => {})" in boot, "sem `await`: e so um selo"


def test_o_ultimo_total_pinta_antes_de_qualquer_espera():
    boot = JS.split("async function boot() {", 1)[1][:600]
    assert boot.index("seloDeAulasDoCache()") < boot.index("wireDrop()"), (
        "o `wireTitlebar` la embaixo espera a ponte do app por ate 3 s")
    cache = JS.split("function seloDeAulasDoCache()", 1)[1][:600]
    assert "AULAS_TOTAL_KEY" in cache
    assert "Number.isFinite(n) && n > 0" in cache, (
        "cache vazio ou zerado nao pode pintar um 0 por cima do que a rede traz")
    assert "try {" in cache, "localStorage pode estar bloqueado"


def test_o_total_e_guardado_a_cada_pintura():
    corpo = JS.split("function pintarSeloDeAulas(", 1)[1][:700]
    assert "localStorage.setItem(AULAS_TOTAL_KEY, String(total))" in corpo


def test_a_primeira_visita_nao_pinta_tudo_de_novo():
    """Quem abre o app pela primeira vez nao pode ver todas as aulas
    marcadas como novidade — so o que chegar dali em diante."""
    corpo = JS.split("async function contarAulasNovas()", 1)[1][:800]
    assert "if (!vistas.size) { aulasMarcarVistas(lista); return; }" in corpo
    marcar = JS.split("function aulasMarcarVistas(lista)", 1)[1][:400]
    assert "pintarSeloDeAulas(lista, 0)" in marcar, (
        "marcar como visto zera o REALCE, nao o numero")


def test_os_quatro_contadores_do_menu_falam_a_mesma_lingua():
    ids = re.findall(r'class="sb-count" id="(\w+)"', HTML)
    assert set(ids) == {"countFila", "countDone", "countProjetos", "countAulas"}
    for i in ids:
        assert f'setCount("#{i}"' in JS, i
