# -*- coding: utf-8 -*-
"""Layouts de vídeo (`videoLayout`) num lugar só.

Cada id vivia repetido em cinco lugares — run_fast (duas listas), ai_actions,
render_path e o catálogo da tela. Um layout novo que esquecesse uma delas não
dava erro: ele simplesmente não acontecia no vídeo, calado. Foi o que estava
acontecendo com o "degrade" no motor próprio (ver `CAMADA`).

Dois grupos importam:

  TRANSFORMAM  mexem no PRÓPRIO vídeo (escala, corte, fundo desfocado) — só o
               Remotion compõe isso, então o job vai pelo caminho lento.
  CAMADA       são só tinta POR CIMA do quadro cheio: os dois motores
               desenham, e o job continua no caminho rápido.

Quadro cheio (TRANSFORMAM + CAMADA + limpa) é também a lista de "sem b-roll
automático": nesses layouts o vídeo ocupa a tela toda e um insert entraria
tapando a fala, então ele só entra se o usuário pedir de propósito.
"""
from __future__ import annotations

# id -> nome que aparece na tela
TRANSFORMAM = {
    "moldura": "Moldura",
    "barra": "Barra inferior",
    "desfocado": "Fundo desfocado",
}

CAMADA = {
    "degrade": "Degradê",
    "vinheta": "Vinheta",
    "cinema": "Cinema",
    "borda": "Borda da marca",
}

# `split` e `split2` dividem a tela com uma mídia — não são quadro cheio.
DIVIDEM = {"split": "Tela dividida", "split2": "Tela dividida com mídia"}

TODOS = {"limpa": "Limpo", **DIVIDEM, **TRANSFORMAM, **CAMADA}

# Aceitos em `videoLayout`; qualquer outra coisa vira "limpa".
VALIDOS = frozenset(TODOS)

# Quadro cheio: o vídeo ocupa a tela inteira, com ou sem tinta por cima.
QUADRO_CHEIO = frozenset({"limpa", "clean", "limpo", *TRANSFORMAM, *CAMADA})


def normalizar(valor: object) -> str:
    """`videoLayout` de qualquer origem (preset, IA, arquivo antigo)."""
    v = str(valor or "limpa").strip().lower()
    if v in ("clean", "limpo"):
        return "limpa"
    return v if v in VALIDOS else "limpa"


def transforma_o_video(valor: object) -> bool:
    """True = precisa do Remotion compondo o vídeo (caminho lento)."""
    return normalizar(valor) in TRANSFORMAM


def e_so_camada(valor: object) -> bool:
    """True = tinta por cima; o motor próprio dá conta."""
    return normalizar(valor) in CAMADA
