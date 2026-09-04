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
}
TIPOS = tuple(NOMES) + ("nenhuma",)

# Quem usa a cor da marca em vez de branco/preto
USAM_A_COR_DA_MARCA = frozenset({"faixa"})
