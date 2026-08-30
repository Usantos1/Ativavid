# -*- coding: utf-8 -*-
"""O varredor precisa continuar sabendo o que o catálogo tem.

Ele lê os ids direto do catálogo da tela (`STYLE_CATALOG` em app.js) e do
`video_layouts.CAMADA`. Se alguém acrescentar um estilo e o varredor não
enxergar, a varredura passa verde sem ter olhado o estilo novo — que é
justamente o buraco que ele existe para tapar.

Aqui não se roda o Remotion (precisa de GPU e de um projeto montado): o que
se guarda é que o varredor VÊ o catálogo inteiro, e as três lições que ele
carrega no código.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FONTE = (REPO / "tools" / "varrer_desenho.py").read_text(encoding="utf-8")


def test_o_varredor_enxerga_o_catalogo_inteiro():
    from app import caption_styles
    from app.render_proprio import Renderizador
    from app.video_layouts import CAMADA
    from tools.varrer_desenho import _catalogo

    assert set(_catalogo("captions")) == set(caption_styles.TODOS)
    assert set(_catalogo("headlines")) == set(Renderizador.HL_STYLES)
    assert set(CAMADA) == {"degrade", "vinheta", "cinema", "borda"}


def test_o_varredor_aplica_o_dim():
    """É um passo à parte do `desenhar`; sem ele o card final mede 0,087."""
    i = FONTE.index("def _monta(")
    bloco = FONTE[i:FONTE.index("def varrer(", i)]
    assert "if leg.dim:" in bloco and "_aplicar_dim" in bloco


def test_o_varredor_devolve_o_edit_data():
    """Ele mexe no `edit-data.json` de um projeto REAL para trocar o estilo."""
    assert "finally:" in FONTE
    i = FONTE.index("finally:")
    assert "write_text(backup" in FONTE[i:i + 300]


def test_o_varredor_avisa_que_a_razao_de_tinta_e_cega():
    """Quem ler o resultado tem de saber o que ele NÃO mede — o neon já saiu
    preto com a razão em 1,003."""
    assert "não vê forma nem cor" in FONTE
    assert "0,93 a 1,10" in FONTE
