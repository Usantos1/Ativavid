# -*- coding: utf-8 -*-
"""A primeira tela sem buraco, e o preview sem JavaScript velho.

**Recentes** era a única lista do app sem texto de vazio: quem acabava de
instalar via o título "Recentes", um botão "Ver fila" e meia tela em
branco. O usuário revende o app — a primeira tela dele é a primeira tela
dos clientes dele.

**Cache do preview**: o `index.html` pede
`studio.js?v=VERSION_PLACEHOLDER`. O app troca o placeholder pela digital
do arranque; o `local_server` servia a palavra literal, então a URL nunca
mudava e o navegador guardava a versão antiga para sempre. O sintoma é
cruel: o arquivo no disco está certo, o servidor entrega o arquivo certo
em `/assets/studio/studio.js`, e a tela continua a antiga.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
LOCAL = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


def test_recentes_tem_texto_de_vazio():
    assert 'id="emptyRecent"' in HTML
    assert 'renderInto("jobListRecent", "emptyRecent"' in JS


def test_o_texto_diz_o_que_vai_acontecer():
    i = HTML.index('id="emptyRecent"')
    assert "aparecem aqui" in HTML[i:i + 300]


def test_ver_fila_some_com_a_fila_vazia():
    """Botão que leva a outra tela vazia é pior que botão nenhum."""
    i = JS.index('verFila.textContent = busy')
    assert 'verFila.classList.toggle("hidden", !fila.length)' in JS[i:i + 400]


def test_ver_fila_e_declarado_uma_vez_so():
    """`const` repetido no mesmo escopo mata o arquivo INTEIRO — foi o que
    aconteceu ao escrever isto: SyntaxError e nenhuma tela funcionando."""
    assert JS.count('const verFila = $("#btnVerFila");') == 1


def test_o_preview_troca_a_digital_de_cache():
    i = LOCAL.index('if path in ("/", "/studio"):')
    bloco = LOCAL[i:i + 1600]
    assert 'html.replace("VERSION_PLACEHOLDER"' in bloco
    assert "st_mtime" in bloco, "a digital tem de vir do arquivo, nao fixa"


def test_a_digital_cobre_o_js_e_o_css():
    i = LOCAL.index('if path in ("/", "/studio"):')
    bloco = LOCAL[i:i + 1600]
    for nome in ("studio.js", "studio.css", "index.html"):
        assert f'"{nome}"' in bloco, nome


def test_o_placeholder_ainda_existe_no_html():
    """Se o HTML parar de pedir a digital, os dois servidores viram enfeite."""
    assert re.search(r"studio\.js\?v=VERSION_PLACEHOLDER", HTML)
