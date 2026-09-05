# -*- coding: utf-8 -*-
"""5.0.63: lote 3 de legendas — seis fontes novas (45 no total).

"Mais estilos de legendas como tem no Captions e no CapCut... devemos
superar eles dois" (05/09). Este lote não inventa desenho nenhum: são seis
FONTES novas montadas sobre modos que já passaram na varredura. É o que o
usuário vê primeiro e o que menos arrisca — o desenho já é conhecido.

    elegante     Lora 700 ....... sem efeito, duas linhas (serifa editorial)
    cartaz       Titan One ...... sticker
    esportiva    Kanit 900 ...... contorno duplo
    estreita     Oswald 700 ..... sombra dura
    arredondada  Nunito 900 ..... pílula
    forte        Montserrat 900 . contorno da marca

Varredura contra o Remotion (razão de tinta): elegante 1,016 · cartaz 1,020
· esportiva 1,025 · estreita 1,029 · arredondada 1,003 · forte 1,027.

O `cartaz` reprovou na primeira passada (d_alfa 80,6): a Titan One é larga
e, a 84/800, os dois motores QUEBRAVAM A LINHA em pontos diferentes — o
Remotion cabia "EU PREFIRO ESTAR" e o motor próprio só "EU PREFIRO". Não é
defeito de desenho, é falta de folga: a medida de texto dos dois diverge
~1% e a decisão de corte estava no fio. Com 74/840 o d_alfa caiu para 13,1.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.caption_styles import (  # noqa: E402
    NOMES, USAM_COR_DA_ENFASE, USAM_COR_DA_LEGENDA,
)
from app.render_proprio import Renderizador  # noqa: E402

TSX = (REPO / "assets" / "shortform" / "src" / "SimpleCaptions.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")

LOTE = {
    "elegante": ("Lora[wght].ttf", "Lora", 700, ""),
    "cartaz": ("TitanOne-Regular.ttf", "TitanOne", 400, "sticker"),
    "esportiva": ("Kanit-Black.ttf", "Kanit", 900, "duplo"),
    "estreita": ("Oswald[wght].ttf", "Oswald", 700, "sombradura"),
    "arredondada": ("Nunito[wght].ttf", "Nunito", 900, "pilula"),
    "forte": ("Montserrat[wght].ttf", "Montserrat", 900, "contorno"),
}
FONTES = REPO / "assets" / "fonts-render"


def test_o_catalogo_cresceu_para_45():
    assert len(NOMES) == 45
    for e in LOTE:
        assert e in NOMES, e


def test_o_arquivo_da_fonte_existe_no_pacote():
    """Fonte que não vai no instalador vira legenda em Poppins sem avisar."""
    for e, (arq, _, _, _) in LOTE.items():
        assert (FONTES / arq).is_file(), f"{e}: falta {arq}"


def test_o_motor_proprio_e_o_template_pedem_a_MESMA_fonte():
    for e, (arq, familia, peso, modo) in LOTE.items():
        v = Renderizador.SIMPLE_VARIANTES[e]
        assert v[0] == arq, e
        assert v[10] == modo, e
        assert Renderizador.SIMPLE_PESO[e] == peso, e
        assert f"@remotion/google-fonts/{familia}" in TSX, familia
        assert f"  {e}: {{" in TSX, e


def test_o_tamanho_e_a_largura_batem_nos_dois_motores():
    """A conta de quebra de linha é a mesma dos dois lados: `size` e `maxW`
    diferentes fazem os motores agruparem palavras diferentes — foi o que
    reprovou o `cartaz` na primeira passada."""
    for e in LOTE:
        v = Renderizador.SIMPLE_VARIANTES[e]
        tam, max_p, lin, max_w = v[2], v[3], v[4], v[9]
        bloco = TSX.split(f"  {e}: {{", 1)[1][:300]
        assert f"size: {tam}," in bloco, f"{e}: tamanho divergente"
        assert f"maxWords: {max_p}," in bloco, f"{e}: palavras por cue"
        assert f"lines: {lin}," in bloco, f"{e}: linhas"
        assert f"maxW: {max_w}," in bloco, f"{e}: largura"
        # o editor desenha a demonstração com a MESMA geometria
        demo = PJS.split(f"  {e}: {{", 1)[1][:300]
        assert f"size: {tam}," in demo, f"{e}: tamanho no editor"
        assert f"maxWords: {max_p}," in demo, f"{e}: palavras no editor"
        assert f"maxW: {max_w}" in demo, f"{e}: largura no editor"


def test_o_cartaz_ficou_com_folga():
    """A folga que resolveu a divergência de quebra: 84/800 -> 74/840."""
    v = Renderizador.SIMPLE_VARIANTES["cartaz"]
    assert v[2] == 74 and v[9] == 840


def test_quem_pinta_superficie_sai_da_cor_da_legenda():
    # `elegante` não tem efeito nenhum: a cor pinta a linha inteira.
    assert "elegante" in USAM_COR_DA_LEGENDA
    assert "elegante" not in USAM_COR_DA_ENFASE
    # os modos com superfície colorida (duplo, pilula, contorno) usam a
    # cor na ÊNFASE, como os irmãos deles
    for e in ("esportiva", "arredondada", "forte"):
        assert e in USAM_COR_DA_ENFASE, e
        assert e not in USAM_COR_DA_LEGENDA, e
    # sticker e sombra dura são preto/branco fixos
    for e in ("cartaz", "estreita"):
        assert e not in USAM_COR_DA_ENFASE and e not in USAM_COR_DA_LEGENDA, e


def test_a_lista_de_MAIUSCULA_so_tem_MODO():
    """`SIMPLE_MAIUSCULA` é testada contra `modo`, não contra o id do
    estilo: pôr um id ali não faz nada e mente para quem lê."""
    modos = {v[10] for v in Renderizador.SIMPLE_VARIANTES.values()}
    for m in Renderizador.SIMPLE_MAIUSCULA:
        assert m in modos, f"`{m}` nao e modo de nenhum estilo"


def test_o_editor_e_o_hub_mostram_os_seis():
    for e in LOTE:
        assert f"id: '{e}', name: '{NOMES[e]}'" in PJS, e
    tela = SJS.split("legenda: {", 1)[1]
    tela = tela[:tela.index("},")]
    for e in LOTE:
        assert f'{e}: "{NOMES[e]}"' in tela, f"{e}: nome divergente da tela"
