# -*- coding: utf-8 -*-
"""As quatro headlines que estavam fora da faixa.

Varredura de 30/08, as 15 headlines contra o Remotion. Onze estavam entre
0,94 e 1,05; quatro não:

    sublinhado 1,152 · manchete 0,885 · vazado 0,856 · gradiente 0,815

Depois dos consertos, todas dentro da faixa. As causas, em ordem de quanto
ensinam:

1. `filter: drop-shadow` do CSS usa sigma = RAIO INTEIRO; `text-shadow` e
   `box-shadow` usam raio/2. O ajudante das headlines tem 0,5 como padrão, e
   `vazado` e `gradiente` — os dois com drop-shadow — ficaram com metade do
   borrão. (`BLUR_K` já documentava a regra; o que faltou foi usá-la.)
2. `manchete`: a barra de acento era desenhada FORA da lápide (30px à
   esquerda) e o texto ia centrado. No template ela é filha do flex, dentro,
   com `padding: 26px 44px` e `gap: 26` — e o texto é alinhado à esquerda.
3. `sublinhado`: a barra ficava ABAIXO da linha e POR CIMA do texto. O
   template diz o motivo de ser o contrário, em uma linha: "a bar clear of
   them reads as a separate rule rather than a highlight".
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src"
       / "Main.tsx").read_text(encoding="utf-8")


def _bloco(estilo: str) -> str:
    i = PY.index(f'if estilo == "{estilo}":')
    return PY[i:PY.index("return leg", i)]


def test_drop_shadow_usa_o_raio_inteiro():
    """Metade do borrão é o erro que `BLUR_K` existe para evitar."""
    for estilo in ("vazado", "gradiente"):
        assert "k_sombra=BLUR_K" in _bloco(estilo), estilo
        # e o template confirma que ali é drop-shadow, não text-shadow — o
        # ramo é o `if styleId === ...`, não a primeira menção do nome (que
        # aparece antes, na união de tipos e no teste de caixa alta)
        i = TSX.index(f"if (styleId === '{estilo}')")
        assert "drop-shadow" in TSX[i:i + 1600], estilo


def test_a_barra_da_manchete_fica_dentro_da_lapide():
    b = _bloco("manchete")
    assert "pad_lado, barra, vao = 44, 12, 26" in b
    assert "pad_esq = pad_lado + barra + vao" in b
    assert "larg_b = larg_max + pad_esq + pad_lado" in b
    assert "int(x_faixa + pad_lado)" in b, "a barra voltou para fora"
    assert "x_faixa - 30" not in b
    # e a barra é pintada DEPOIS da lápide, senão fica escondida atrás dela
    assert b.index("_hl_bloco_multi") < b.index("int(x_faixa + pad_lado)")
    # sombra do template
    assert "[(0, 14, 40, 0.45)]" in b


def test_a_barra_do_sublinhado_fica_atras_do_texto():
    b = _bloco("sublinhado")
    # a barra é a PRIMEIRA Palavra da linha: a ordem é a ordem de pintura
    assert b.index("leg.palavras.append") < b.index("_hl_bloco_texto")
    assert "barra_h = max(8, round(tam * 0.19))" in b
    assert "y_barra = int(y + alt_cx - round(tam * 0.06) - barra_h)" in b
    assert "[(0, 4, 16, 0.55)]" in b


def test_o_texto_da_manchete_alinha_a_esquerda_sem_mexer_nos_outros():
    """`_hl_bloco_multi` é compartilhado por três estilos: o alinhamento à
    esquerda entra como parâmetro OPCIONAL, e sem ele nada muda.

    (Medido: `carimbo` ficou em 1,034 antes e depois.)
    """
    i = PY.index("def _hl_bloco_multi")
    assinatura = PY[i:PY.index('"""', i)]
    assert "pad_esq=None" in assinatura
    corpo = PY[i:PY.index("def _montar_headline", i)]
    assert "larg_txt + (pad_x if pad_esq is None else pad_esq) + pad_x" in corpo
    assert "folga + pad_esq if pad_esq is not None" in corpo
