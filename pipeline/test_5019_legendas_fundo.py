# -*- coding: utf-8 -*-
"""5.0.19: quatro legendas de FUNDO colorido (pílula, etiqueta, fita
degradê, marca-texto).

Ele (04/09): "gostei desse fundo de laranja ali, mas pode implementar
outros tipos". A `bandeira` da 5.0.18 e a fita laranja; estes quatro sao
a mesma familia com outras formas.

Medido contra o Remotion no projeto real (04/09): pílula 1,024 ·
etiqueta 1,065 · fita degradê 1,018 · marca-texto 1,022 — todos dentro
de 0,93-1,10, e mais perto da referencia que `simples` (1,058) e `bloco`
(1,041), que estao em producao ha meses.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import caption_styles  # noqa: E402
from app.render_proprio import Renderizador  # noqa: E402

TSX = (REPO / "assets" / "shortform" / "src" / "SimpleCaptions.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
PY = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")

NOVOS = ("pilula", "etiqueta", "fitadegrade", "marcador")


def test_os_quatro_existem_nos_tres_motores():
    for e in NOVOS:
        assert e in caption_styles.NOMES, e
        assert e in Renderizador.SIMPLE_VARIANTES, f"{e}: o motor proprio nao desenha"
        assert f"  {e}: {{" in TSX, f"{e}: sem variante no template"
        assert f"  {e}: {{family:" in PJS, f"{e}: sem variante na previa"
        assert f"{{id: '{e}'," in PJS, f"{e}: fora do catalogo da tela"
        assert f"'{e}'" in MAIN, f"{e}: fora do tipo de captions.style"


def test_cada_um_puxa_a_cor_do_lugar_certo():
    """Os tres de painel usam a cor da LEGENDA; o marca-texto usa a de
    ÊNFASE (amarela por padrão), como a caixa do `impacto`."""
    # 5.0.23: os quatro pintam uma SUPERFICIE (capsula, barra, fita, faixa),
    # entao a cor sai da ENFASE — com a legenda branca de quase todo preset
    # a capsula saia branca e o degrade sumia.
    for e in ("pilula", "etiqueta", "fitadegrade", "marcador"):
        assert e in caption_styles.USAM_COR_DA_ENFASE, e
        assert e not in caption_styles.USAM_COR_DA_LEGENDA, e
        assert f"'{e}'" in PJS.split("const CAP_EMPH_STYLES")[1][:400], f"{e}: a tela nao oferece a cor da enfase"
    assert 'caps_cfg.get("emphasisAccent") or self.MARCADOR_PADRAO' in PY
    assert "C.emphasisAccent || MARCADOR_PADRAO" in TSX
    # os de painel leem a superficie pelo mesmo caminho
    assert 'superficie = caps_cfg.get("emphasisAccent") or accent' in PY
    assert "function corDaSuperficie(padrao: string): string {" in TSX


def test_a_medida_bate_nos_tres():
    esperado = {
        "pilula": (66, 4, 1, 720),
        "etiqueta": (52, 8, 2, 780),
        "fitadegrade": (62, 4, 1, 760),
        "marcador": (74, 3, 1, 800),
    }
    for e, (tam, maxp, lin, maxw) in esperado.items():
        arq, eixo, t0, mp, nl, sx, sy, tr, bottom, mw, modo = Renderizador.SIMPLE_VARIANTES[e]
        assert (t0, mp, nl, mw) == (tam, maxp, lin, maxw), e
        assert modo == e and bottom == 430
        assert f"size: {tam}, maxWords: {maxp}, lines: {lin}" in PJS, e
        assert f"maxW: {maxw}" in PJS.split(f"  {e}: {{family:")[1][:260], e
        bloco = TSX.split(f"  {e}: {{")[1][:300].replace("\n", " ")
        assert f"size: {tam}, maxWords: {maxp}, lines: {lin}" in " ".join(bloco.split()), e
        assert f"maxW: {maxw}" in " ".join(bloco.split()), e


def test_os_numeros_do_desenho_batem_nos_tres():
    """Barra da etiqueta, pé do degradê e faixa do marca-texto: um número
    diferente em um motor sai como outra legenda e ninguém percebe."""
    assert "const ETIQUETA_BARRA = 10;" in TSX and "ETIQUETA_BARRA = 10" in PY and "const ETIQUETA_BARRA = 10;" in PJS
    assert "const FITA_ESCURO = 0.55;" in TSX and "FITA_ESCURO = 0.55" in PY and "const FITA_ESCURO = 0.55;" in PJS
    for nome, valor in (("MARCADOR_PADY", 0.14), ("MARCADOR_PADX", 0.16)):
        assert f"const {nome} = {valor};" in TSX, nome
        assert f"const {nome} = {valor};" in PJS, nome
        assert f"{nome} = {valor}" in PY, nome
    assert "const MARCADOR_PADRAO = '#ffd400';" in TSX and 'MARCADOR_PADRAO = "#ffd400"' in PY


def test_a_pilula_e_capsula_e_a_etiqueta_tem_barra():
    i = PY.index("def _painel_colorido(")
    bloco = PY[i:i + 4200]
    assert 'ch // 2 if modo == "pilula"' in bloco, "raio da capsula = metade da altura"
    assert "borderRadius: 9999" in TSX and "borderRadius = '9999px'" in PJS
    # a barra fica POR CIMA do fundo e o texto centra depois dela, como o
    # `border-left` do CSS encolhe a caixa de conteudo
    assert "a_barra[:, folga:folga + barra]" in bloco
    assert "x = folga + barra + int((cw - barra - w_m) / 2)" in bloco
    assert "borderLeft: `${ETIQUETA_BARRA}px solid ${barra}`" in TSX


def test_a_faixa_do_marca_texto_cobre_a_letra_inteira():
    """5.0.20 — ele: "essa ultima esta cortando o fundo dela". A listra
    ficava DENTRO da caixa de linha e o pe do "p" e a ponta do "d" ficavam
    de fora; agora a faixa e a caixa de linha MAIS a folga."""
    i = PY.index("def _marca_texto(")
    bloco = PY[i:i + 3000]
    assert "alt_cx = int(round(alt_l)) + 2 * pad_y" in bloco
    assert "alpha[folga:folga + alt_cx, folga:L - folga] = 1.0" in bloco
    assert "ty = folga + pad_y + int((alt_l - (asc + desc)) / 2)" in bloco
    assert "self._tinta_na_caixa(faixa)" in bloco, "a tinta sai da luminancia da faixa"
    # a sombra parte do GLIFO, nao da faixa (senao vira lapide com halo)
    assert "sombra = self._sombra_de(glifo," in bloco
    assert "MARCADOR_TOPO" not in PY and "MARCADOR_TOPO" not in TSX, "a listra saiu"
    assert "background: faixa," in TSX and "padding: `${padY}px ${padX}px`" in TSX
    # a folga entra na altura empilhada, senao o CSS e o motor ancoram
    # a linha em alturas diferentes
    assert "alt_total = (alt_l * sq_y + 2 * pad_y_marc) * len(linhas)" in PY
    assert "marcador" not in Renderizador.SIMPLE_PAINEL, "e por LINHA, nao um painel do cue"


def test_a_faixa_cobre_a_caixa_do_glifo_da_fonte():
    """A folga de 0,14 do corpo tem de cobrir o que a fonte desenha: com
    entrelinha 1,16 a Poppins passa dos DOIS lados da caixa de linha."""
    from PIL import ImageFont
    tam, lh = 74, 1.16
    f = ImageFont.truetype(str(REPO / "assets" / "fonts-render" / "Poppins-ExtraBold.ttf"), tam)
    asc, desc = f.getmetrics()
    caixa = tam * lh
    pad_y = round(tam * 0.14)
    meia = (caixa - (asc + desc)) / 2
    topo_glifo = pad_y + meia            # dentro da caixa com folga
    base_glifo = topo_glifo + asc + desc
    assert topo_glifo >= 0, f"a faixa corta o topo da letra em {-topo_glifo:.1f}px"
    assert base_glifo <= caixa + 2 * pad_y, (
        f"a faixa corta o pe da letra em {base_glifo - (caixa + 2 * pad_y):.1f}px")
