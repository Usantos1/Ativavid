# -*- coding: utf-8 -*-
"""Âncoras semânticas para testes de texto sobre JS.

A suíte guarda contratos do studio.js/app.js por substring. O padrão
frágil — janela fixa de N caracteres a partir de um `.index()` — quebrou
4 arquivos num único dia (31/08: um comentário novo no começo de
`renderLicense` estourou janelas de 200 chars em cadeia). O padrão bom é
cortar do início da FUNÇÃO até o fechamento dela, por contagem de chaves:
o bloco cresce junto com o código e a âncora só quebra se a função sumir.

Uso:
    from pipeline.ancoras import bloco_da_funcao
    bloco = bloco_da_funcao(JS, "openLicenseDialog")
    assert "..." in bloco
"""
from __future__ import annotations


def bloco_da_funcao(js: str, nome: str) -> str:
    """O corpo completo de `function NOME(...)` (ou `async function`).

    Conta chaves fora de string/comentário — suficiente para o JS deste
    projeto (sem template literal com chave solta dentro das funções
    ancoradas; se um dia houver, o teste que usar este helper quebra ALTO,
    com ValueError, não em silêncio).
    """
    for assinatura in (f"function {nome}(", f"async function {nome}("):
        i = js.find(assinatura)
        if i >= 0:
            break
    else:
        raise ValueError(f"function {nome}( não existe mais no arquivo")
    i = js.index("{", i)
    fundo = 0
    em_str: str | None = None
    j = i
    while j < len(js):
        c = js[j]
        if em_str:
            if c == "\\":
                j += 2
                continue
            if c == em_str:
                em_str = None
        elif c in ("'", '"', "`"):
            em_str = c
        elif c == "/" and js[j:j + 2] == "//":
            j = js.index("\n", j)
        elif c == "/" and js[j:j + 2] == "/*":
            j = js.index("*/", j) + 1
        elif c == "{":
            fundo += 1
        elif c == "}":
            fundo -= 1
            if fundo == 0:
                return js[i - (i - js.rfind("function", 0, i)):j + 1]
        j += 1
    raise ValueError(f"function {nome} não fecha as chaves")


def sem_comentarios(codigo: str, linguagem: str = "js") -> str:
    """Remove comentarios — para asserts de AUSENCIA.

    `assert "coisa" not in ARQ` quebra no dia em que um comentario honesto
    mencionar a coisa removida (ja aconteceu: um "0.0.0" num comentario).
    Sobre o codigo LIMPO, o assert mede so o que executa.

    `linguagem`: "js" (tambem serve CSS) tira // e /* */; "py" tira #.
    NUNCA tirar # de JS — os seletores $("#id") sao codigo vivo.
    """
    import re

    if linguagem == "py":
        return re.sub(r"(?m)#[^\n]*$", "", codigo)
    s = re.sub(r"/\*.*?\*/", "", codigo, flags=re.S)
    s = re.sub(r"(?m)^\s*//[^\n]*", "", s)
    return re.sub(r"(?m)(?<=[;{})\s])//[^\n]*$", "", s)
