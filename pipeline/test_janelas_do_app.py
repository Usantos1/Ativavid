# -*- coding: utf-8 -*-
"""Nenhuma janela do NAVEGADOR na frente do usuário.

`prompt()` e `confirm()` abrem a caixa do Chrome, com "127.0.0.1:4850 diz"
no topo e os botões do sistema: dentro de um app escuro parece outro
programa. O usuário mandou print em 29/08 ao criar um preset: "esse tipo
de janela feia não quero".
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TELAS = (REPO / "assets" / "preview" / "app.js",
         REPO / "assets" / "studio" / "studio.js")


def _sem_comentarios(js: str) -> str:
    """Comentário que CITA `prompt()` (o motivo da mudança mora lá) não é
    uma chamada — o teste estaria lendo a própria explicação."""
    js = re.sub(r"/\*.*?\*/", " ", js, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", linha) for linha in js.splitlines())


def test_nenhuma_caixa_nativa():
    for f in TELAS:
        s = _sem_comentarios(f.read_text(encoding="utf-8"))
        for padrao in (r"\bwindow\.(prompt|confirm|alert)\(",
                       r"(?<![\w.])(prompt|confirm|alert)\("):
            achou = [m.group(0) for m in re.finditer(padrao, s)]
            assert not achou, f"{f.name}: {achou[:3]}"


def test_as_janelas_do_app_existem_nas_duas_telas():
    for f in TELAS:
        s = f.read_text(encoding="utf-8")
        assert "function pedirTexto" in s, f.name
        assert "function pedirConfirmacao" in s, f.name
        assert "showModal()" in s


def test_o_texto_do_usuario_e_escapado():
    """Nome de preset com `<` nao pode virar HTML na janela."""
    s = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = s.index("function pedirTexto")
    assert "_escDlg(valor" in s[i:i + 500], s[i:i + 400]
