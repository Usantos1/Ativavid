# -*- coding: utf-8 -*-
"""O catalogo das transicoes de corte — a fonte unica dos quatro tipos.

Ate a 5.0.24 existia UMA transicao (`flash`) e ela era escrita a mao em
quatro arquivos. Ele (04/09) pediu mais opcoes; um catalogo em um lugar so
e o que impede a lista de sair de sincronia entre a tela, o pipeline, o
motor proprio e o template — o mesmo erro que os estilos de legenda ja
cobraram tres vezes.

Todas pintam SO no overlay (uma camada por cima do video), que e o que os
dois motores sabem compor igual. Transicao que deforma a imagem — zoom,
deslize — mudaria o video por baixo e nao cabe neste desenho.
"""
from __future__ import annotations

# id -> (nome na tela, o que faz)
NOMES: dict[str, str] = {
    "flash": "Flash (feixe de luz)",
    "brilho": "Brilho (clarao seco)",
    "escurece": "Escurece (piscada preta)",
    "faixa": "Faixa na cor da marca",
    # 5.0.51 — "QUERO MAIS TRANSICOES" (05/09). Todas desenham SO no overlay,
    # como as quatro de cima: nenhuma mexe no video por baixo.
    "cortina": "Cortina (fecha e abre)",
    "blocos": "Blocos (mosaico da marca)",
    "moldura": "Moldura (borda pisca)",
    "traco": "Traço de luz (fino)",
}
TIPOS = tuple(NOMES) + ("nenhuma",)

# Quem usa a cor da marca em vez de branco/preto
USAM_A_COR_DA_MARCA = frozenset({"faixa", "cortina", "blocos", "moldura"})

# A chave, no edit-data do projeto, das escolhas POR CORTE feitas no editor:
# {"<indice da emenda>": "<tipo>"}. Indice 0 = entre o 1o e o 2o trecho.
CHAVE_POR_CORTE = "transicoesPorCorte"


def aplicar_por_corte(transicoes: list, escolhas: dict | None) -> list:
    """As transicoes de um render com as escolhas do editor por cima.

    `transicoes` e a lista que o pipeline monta (uma por emenda, na ordem);
    `escolhas` e o que ele marcou na regua do editor. Quem nao foi marcado
    fica como o estilo manda; "nenhuma" tira a emenda; tipo desconhecido e
    ignorado (o motor rapido recusaria o job inteiro).
    """
    if not escolhas:
        return list(transicoes)
    fora = []
    for i, tr in enumerate(transicoes):
        tipo = str((escolhas or {}).get(str(i)) or "").strip().lower()
        if not tipo or tipo not in TIPOS:
            fora.append(dict(tr))
            continue
        if tipo == "nenhuma":
            continue
        fora.append(dict(tr, type=tipo))
    return fora
