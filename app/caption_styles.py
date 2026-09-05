# -*- coding: utf-8 -*-
"""Estilos de legenda (`captions.style`) num lugar só.

Mesmo remédio de `video_layouts.py`, pelo mesmo motivo: a lista vivia
repetida em quatro lugares (o portão do motor próprio, a passagem da cor no
run_fast, o catálogo da tela e o `SIMPLE_VARIANTS` do template), e o quarto
— a IA — não tinha lista NENHUMA.

O buraco da IA era o pior dos cinco. A ação `set_captions_style` aceitava
qualquer texto: um pedido como "põe legenda metálica" virava
`style="metalica"`, que não existe. Aí o vídeo saía com **karaokê** (o
`else` do template) e ainda pelo caminho LENTO, porque um estilo
desconhecido tira o job do motor próprio. Dois prejuízos, nenhum aviso.

`TODOS` é a lista canônica; `NOMES` é como cada um aparece na tela e é o
que se dá à IA para ela falar a mesma língua do usuário.
"""
from __future__ import annotations

# id -> nome que aparece na tela (e que a IA usa para reconhecer o pedido)
NOMES = {
    "karaoke": "Karaokê",
    "stacked": "Empilhado",
    "impacto": "Impacto",
    "scatter": "Disperso",
    "recorte": "Recorte",
    "bolha": "Bolha de conversa",
    "simples": "Simples",
    "serifada": "Serifada",
    "classica": "Clássica",
    "bloco": "Bloco",
    # os cinco de 30/08
    "metal": "Metálico",
    "vidro": "Vidro",
    "traco": "Contorno fino",
    "moldura": "Moldura",
    "eco": "Eco",
    # os quatro de 04/09 ("todos")
    "neon": "Neon",
    "degrade": "Degradê",
    "bandeira": "Bandeira",
    "maquina": "Máquina de escrever",
    # os quatro de fundo colorido (04/09, "pode implementar outros tipos")
    "pilula": "Pílula",
    "etiqueta": "Etiqueta",
    "fitadegrade": "Fita degradê",
    # os dois de 05/09 (pedido de 04/09: "fita dupla, etiqueta com canto recortado")
    "fitadupla": "Fita dupla",
    "etiquetacanto": "Etiqueta recortada",
    # lote 1 das 50 rodadas (05/09): "mais estilos como o Captions e o CapCut"
    "contorno": "Contorno da marca",
    "sombra3d": "Sombra longa",
    "beast": "Beast (amarelo)",
    "sublinhado": "Sublinhado",
    "gigante": "Gigante (Bebas)",
    "quadrinhos": "Quadrinhos (Bangers)",
    "divertida": "Divertida (Luckiest Guy)",
    "condensada": "Condensada (Anton)",
    # lote 2 das 50 rodadas (05/09)
    "duplo": "Contorno duplo",
    "sombradura": "Sombra dura",
    "retro": "Retrô (Righteous)",
    "minimal": "Minimalista",
    "grosso": "Grossa (Archivo)",
    "alerta": "Alerta (Bangers)",
    "marcador": "Marca-texto",
    # lote 3 das 50 rodadas (05/09): seis FONTES novas em modos que ja
    # existem. Nenhum desenho novo — o que muda e a letra, que e o que o
    # usuario ve primeiro.
    "elegante": "Elegante (Lora)",
    "cartaz": "Cartaz (Titan One)",
    "esportiva": "Esportiva (Kanit)",
    "estreita": "Estreita (Oswald)",
    "arredondada": "Arredondada (Nunito)",
    "forte": "Forte (Montserrat)",
}

TODOS = frozenset(NOMES)

# Estilos em que a cor escolhida pinta a LEGENDA (e não a ênfase). O
# `bolha` fica de fora de propósito: o verde de chat é fixo, é ele que faz
# a bolha ser reconhecível.
USAM_COR_DA_LEGENDA = frozenset({
    "karaoke", "simples", "serifada", "classica", "bloco", "recorte",
    "metal", "vidro", "traco", "moldura", "eco",
    "maquina",
    # lote 3: `elegante` nao tem efeito nenhum, entao a cor pinta a linha
    # (mesma regra do `minimal` e do `classica`).
    "elegante",
})

# Estilos em que a cor pinta a ÊNFASE (a palavra quente), não a linha toda.
# O `marcador` entra aqui, e nao na lista de cima, porque a faixa dele e um
# elemento de ENFASE (como a caixa do impacto): amarelo por padrao, e o que
# o usuario espera de um marca-texto.
# Os oito de 04/09 pintam uma SUPERFICIE (brilho, degrade, fita, capsula,
# barra, faixa), nao a letra — e superficie e ENFASE. Nasceram lendo a cor
# da legenda e, como quase todo preset tem legenda BRANCA (os tres do Prime
# Camp tem), o neon saia sem brilho e o degrade saia branco liso: a cor da
# marca nao aparecia em nenhum deles.
USAM_COR_DA_ENFASE = frozenset({"stacked", "scatter", "impacto", "marcador",
                                "neon", "degrade", "bandeira", "pilula",
                                "etiqueta", "fitadegrade",
                                "fitadupla", "etiquetacanto",
                                "contorno", "sombra3d", "sublinhado", "divertida",
                                "duplo", "retro", "alerta",
                                "esportiva", "forte", "arredondada"})


def valido(estilo: str | None) -> bool:
    """O id existe? Vale para o que vem da IA e para o que vem de um preset
    salvo por uma versão mais nova do app."""
    return str(estilo or "").strip().lower() in TODOS


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


# nome de tela -> id, sem acento e em caixa baixa ("metalico" -> "metal")
_POR_NOME = {_sem_acento(v).lower(): k for k, v in NOMES.items()}


def normalizar(estilo: str | None) -> str | None:
    """Devolve o id, ou None se não for um estilo conhecido.

    Aceita o id ("metal") e também o NOME DE TELA ("Metálico", "metalico"):
    quando o usuário pede à IA "põe legenda metálica", é o nome de tela que
    ele tem na frente, e é ele que a IA tende a devolver. Recusar o nome que
    a própria tela mostra seria recusar o vocabulário do usuário.

    Quem chama decide o que fazer com o None — o ponto é que ninguém siga
    adiante com um nome inventado achando que é um estilo.
    """
    e = str(estilo or "").strip().lower()
    if e in TODOS:
        return e
    return _POR_NOME.get(_sem_acento(e))


def lista_para_ia() -> str:
    """`id (Nome)` separados por vírgula — vai no prompt das ações."""
    return ", ".join(f"{k} ({v})" for k, v in NOMES.items())
