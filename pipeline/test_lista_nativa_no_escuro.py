# -*- coding: utf-8 -*-
"""A lista que abre num <select> tem de ser escura no tema escuro.

Ela e desenhada pelo SISTEMA, nao pelo CSS: sem `color-scheme` abre
BRANCA sobre o app preto. O hub ganhou a linha em 29/08, quando ele
mandou o print. O EDITOR ficou sem — e em 30/08 veio o print de novo,
desta vez do seletor de fonte da legenda, que so existe la ("esta cor
branca no tema dark que amadorismo").

Mesmo defeito, duas folhas de estilo, um ano de distancia entre os dois
consertos. Este teste cobre as DUAS, e qualquer folha nova com `:root`.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSS = sorted((REPO / "assets").rglob("*.css"))


def _folhas_com_root() -> list[Path]:
    return [f for f in CSS
            if "node_modules" not in str(f)
            and re.search(r"^:root\s*\{", f.read_text(encoding="utf-8"), re.M)]


def test_toda_folha_com_root_declara_o_esquema():
    faltam = [f.name for f in _folhas_com_root()
              if "color-scheme: dark" not in f.read_text(encoding="utf-8")]
    assert not faltam, faltam


def test_o_tema_claro_troca_o_esquema_junto():
    """Sem isto o tema claro herda a lista escura — o mesmo defeito,
    virado do avesso."""
    for f in _folhas_com_root():
        s = f.read_text(encoding="utf-8")
        if ':root[data-theme="light"]' not in s:
            continue
        i = s.index(':root[data-theme="light"]')
        assert "color-scheme: light" in s[i:i + 400], f.name


def test_ninguem_pinta_a_lista_de_branco_na_mao():
    """O `color-scheme` sozinho nao bastou.

    As duas folhas tinham uma regra EXPLICITA em `option` — `#121218`
    sobre `#ffffff` — que ganhava dele: a lista continuou branca no tema
    escuro por duas versoes depois do conserto de 4.21, e ele reclamou
    pela terceira vez. Cor de lista sai de token, nos dois temas.
    """
    import re as _re

    for f in _folhas_com_root():
        s = f.read_text(encoding="utf-8")
        for m in _re.finditer(r"option[^{}]*\{([^}]*)\}", s):
            bloco = m.group(1)
            achados = _re.findall(r"#[0-9a-fA-F]{3,8}", bloco)
            assert not achados, (f.name, bloco.strip()[:120], achados)


def test_as_duas_folhas_estao_na_conta():
    """Guarda o proprio teste: se um dia o `:root` sair de uma delas, o
    teste passaria vazio e o print voltaria."""
    nomes = {f.name for f in _folhas_com_root()}
    assert {"studio.css", "app.css"} <= nomes, nomes
