# -*- coding: utf-8 -*-
"""Ler o CÓDIGO de um arquivo, sem comentários e sem docstrings.

Existe porque três testes desta base já casaram com o comentário que explica a
decisão em vez do código que a implementa. Um teste assim passa mesmo com o
código errado, desde que o comentário continue certo — e comentários costumam
continuar certos, porque ninguém os apaga ao mudar a linha de baixo.

O caso concreto: um teste exigia `"elevenlabs"` perto da chamada de
transcrição. O bloco de comentário logo acima dela explica *por que* o backend
é explícito e cita o nome — então o teste passava com a chamada sem o
argumento.

O resto do arquivo sai IDÊNTICO: os trechos ignorados são apagados no lugar,
preservando posições. Remontar a partir dos tokens normalizaria o espaçamento
(`def f(` viraria `def f (`) e quebraria toda busca escrita do jeito natural.
"""
from __future__ import annotations

import io
import tokenize
from pathlib import Path

_ASPAS_TRIPLAS = ('"""', "'''")


def apenas_codigo(caminho: Path | str) -> str:
    """Devolve o texto do arquivo com comentários e docstrings em branco.

    Aspas triplas caem junto: nesta base elas são sempre docstring ou texto
    longo, nunca argumento de linha de comando.
    """
    linhas = Path(caminho).read_text(encoding="utf-8").splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO("".join(linhas)).readline):
        apagar = tok.type == tokenize.COMMENT or (
            tok.type == tokenize.STRING
            and tok.string.lstrip("rbfuRBFU")[:3] in _ASPAS_TRIPLAS)
        if not apagar:
            continue
        (l0, c0), (l1, c1) = tok.start, tok.end
        for n in range(l0 - 1, l1):
            linha = linhas[n]
            ini = c0 if n == l0 - 1 else 0
            fim = c1 if n == l1 - 1 else len(linha.rstrip("\n"))
            linhas[n] = linha[:ini] + " " * (fim - ini) + linha[fim:]
    return "".join(linhas)
