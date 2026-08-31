# -*- coding: utf-8 -*-
"""O atributo `hidden` tem de esconder — inclusive o card do suporte.

Print dele em 31/08, no PC em TRIAL: o bloco "Suporte Prime Camp" estava
na tela. Ele pediu o contrário em 30/08 — "pode deixar bem escondido esse
número, apenas pra quem for pagar ou contratar a licença" — e o
`renderSuporte` marcava `hidden` certinho.

A causa não era o JS: `[hidden]` do navegador é `display:none` na folha do
AGENTE, e qualquer regra de autor com `display` ganha dela. Então todo
componente com `display:flex` continuava visível com `hidden` ligado.

Não era caso isolado: o CSS já tinha três remendos individuais
(`.lic-admin[hidden]`, `.lic-admin-sub[hidden]`, `.dlg-lic-adv-section
[hidden]`) — o mesmo defeito reaparecendo a cada componente novo. Uma
regra global resolve a família.

Medido depois do conserto, com o app servindo uma máquina em trial:
`display:none`, altura 0. E com licença ativa: volta a aparecer, com o
número e o link do WhatsApp levando a máquina junto.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STUDIO = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
EDITOR = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_hidden_manda_nas_duas_folhas():
    for nome, css in (("studio.css", STUDIO), ("app.css", EDITOR)):
        assert "[hidden] { display: none !important; }" in css, nome


def test_a_regra_vem_antes_dos_componentes():
    """Sem `!important` a ordem importaria; com ele, não — mas a regra
    ainda tem de existir ANTES para quem for ler o arquivo entender que é
    política, não remendo."""
    i = STUDIO.index("[hidden] { display: none !important; }")
    assert i < STUDIO.index(".lic-suporte {")


def test_o_suporte_so_aparece_para_quem_paga():
    i = JS.index("function renderSuporte(")
    bloco = JS[i:JS.index("\nfunction renderLicense", i)]
    assert 'modo === "licensed" || modo === "account"' in bloco
    assert "box.hidden = !pago" in bloco
    assert "if (!pago) return" in bloco, "sem isto o numero seria escrito mesmo escondido"


def test_o_numero_nao_fica_no_html():
    """Se o número estivesse no HTML, escondê-lo seria só cosmético — quem
    abrisse o arquivo do app leria."""
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert "98768" not in html
    i = JS.index("const SUPORTE")
    assert "98768" in JS[i:i + 200], "o numero vive no JS, escrito so quando paga"
