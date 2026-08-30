# -*- coding: utf-8 -*-
"""Os cartoes da importacao: os tres novos e o orfao da ultima linha.

"quero mais 3 pra nao ficar apenas 1 ali sobrando" (30/08). Eram 7 numa
grade de 3 colunas — 3, 3 e um sozinho.

Os tres novos sao PACOTES (intencao de corte + tipo de conteudo), como o
"Viral" ja era. O que este arquivo guarda e a armadilha: um `data-intent`
que nao esteja nos pacotes NEM em `INTENTS` e descartado pelo servidor em
silencio — a escolha do usuario sumiria sem erro nenhum.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.content_type import CONTENT_TYPES  # noqa: E402
from app.editing_intent import INTENTS  # noqa: E402

HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")


def _cartoes() -> list[str]:
    i = HTML.index('id="intentGrid"')
    j = HTML.index("</div>", HTML.index('data-intent="depoimento"'))
    return re.findall(r'data-intent="([a-z]+)"', HTML[i:j])


def _pacotes() -> dict[str, str]:
    i = JS.index("const PACOTES_DE_MODO = {")
    bloco = JS[i:JS.index("};", i)]
    return dict(re.findall(r"(\w+): \{ intent: \"(\w+)\"", bloco))


def test_sao_dez_cartoes():
    assert len(_cartoes()) == 10, _cartoes()


def test_os_tres_novos_estao_la():
    c = _cartoes()
    for novo in ("tutorial", "anuncio", "depoimento"):
        assert novo in c, novo


def test_todo_cartao_chega_inteiro_no_servidor():
    """A armadilha: `data-intent` fora de INTENTS e sem pacote e trocado
    pelo recomendado, calado — a escolha do usuario evapora."""
    pac = _pacotes()
    for modo in _cartoes():
        assert modo in INTENTS or modo in pac, modo


def test_o_pacote_aponta_para_coisas_que_existem():
    i = JS.index("const PACOTES_DE_MODO = {")
    bloco = JS[i:JS.index("};", i)]
    for modo, intent, tipo in re.findall(
            r"(\w+): \{ intent: \"(\w+)\", tipo: \"(\w+)\" \}", bloco):
        assert intent in INTENTS, (modo, intent)
        assert tipo in CONTENT_TYPES, (modo, tipo)


def test_o_pacote_define_os_dois_lados():
    """Escolher o cartao tem de mexer no tipo de conteudo tambem — senao
    "Anuncio" corta igual a "Deixar mais dinamico"."""
    i = JS.index("function collectImportIntent(")
    assert "PACOTES_DE_MODO[mode]?.intent || mode" in JS[i:i + 400]
    i = JS.index("function applyIntentDefaults(")
    bloco = JS[i:i + 900]
    assert "const pacote = PACOTES_DE_MODO[mode];" in bloco
    assert 'value = pacote.tipo' in bloco


def test_o_ultimo_cartao_sozinho_ocupa_a_linha():
    assert ".intent-grid > .intent-card:last-child:nth-child(3n + 1)" in CSS
    i = CSS.index(".intent-grid > .intent-card:last-child:nth-child(3n + 1)")
    assert "grid-column: 1 / -1" in CSS[i:i + 120]
