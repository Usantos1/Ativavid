# -*- coding: utf-8 -*-
"""O aviso (toast) aparece no TOPO, centro — e nao no rodape.

"ali quase nunca da pra ver" (27/08): em pe embaixo, numa tela larga, o
aviso passava despercebido justo quando contava alguma coisa (chave
salva, motor trocado, erro do servidor).
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _regra_toast(css: str) -> str:
    i = css.find(".toast {")
    assert i > 0, "regra .toast sumiu"
    return css[i:css.find("}", i)]


def test_o_aviso_nasce_no_topo_nas_duas_telas():
    for arq in ("assets/studio/studio.css", "assets/preview/app.css"):
        regra = _regra_toast((RAIZ / arq).read_text(encoding="utf-8"))
        assert re.search(r"top:\s*\d+px", regra), f"{arq}: sem topo"
        assert not re.search(r"bottom:\s*\d+px", regra), \
            f"{arq}: ainda ancorado no rodape"


def test_fica_abaixo_da_barra_de_titulo_e_acima_do_resto():
    css = (RAIZ / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    regra = _regra_toast(css)
    topo = int(re.search(r"top:\s*(\d+)px", regra).group(1))
    barra = int(re.search(r"--tb-h:\s*(\d+)px", css).group(1))
    assert topo > barra, "o aviso cobriria a barra de titulo"
    z = int(re.search(r"z-index:\s*(\d+)", regra).group(1))
    z_barra = int(re.search(r"\.titlebar \{.*?z-index:\s*(\d+)", css,
                            re.S).group(1))
    assert z > z_barra, "a barra de titulo cobriria o aviso"


def test_a_mensagem_entra_como_texto_e_nunca_como_html():
    """Metade das chamadas passa recado vindo do SERVIDOR (erro, nome de
    arquivo). Se virasse innerHTML, um nome com < ou & quebraria a tela."""
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.find("function toast(")
    corpo = js[i:js.find("\n}", i)]
    assert "corpo.textContent = msg" in corpo
    assert "innerHTML = msg" not in corpo and "innerHTML = `" not in corpo


def test_avisos_seguidos_reanimam_a_entrada():
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.find("function toast(")
    corpo = js[i:js.find("\n}", i)]
    assert "void t.offsetWidth" in corpo, \
        "sem reiniciar a animacao, o 2o aviso aparece sem transicao"


def test_o_aviso_e_anunciado_para_leitores_de_tela():
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="toast"' in html and 'role="status"' in html


def test_no_preview_o_aviso_desce_abaixo_do_cabecalho():
    """A tela de preview tem barra de 72px MAIS a faixa das abas
    (Edicao/Estilo/Visual). Medido em 27/08 numa copia isolada da tela: o
    aviso a 52px cobria as abas (toast 52-95 x abas 92-127). Ele comeca
    abaixo do cabecalho e o app.js reajusta na hora de mostrar, porque o
    cabecalho quebra linha em tela estreita."""
    regra = _regra_toast(
        (RAIZ / "assets" / "preview" / "app.css").read_text(encoding="utf-8"))
    topo = int(re.search(r"top:\s*(\d+)px", regra).group(1))
    assert topo >= 140, f"o aviso voltaria a cobrir as abas (top {topo})"

    js = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.find("function toast(msg, ms)")
    corpo = js[i:js.find("\n}", i)]
    assert "header.glass" in corpo and "getBoundingClientRect" in corpo, \
        "sem medir o cabecalho, o aviso erra quando ele quebra linha"
