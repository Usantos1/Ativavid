# -*- coding: utf-8 -*-
"""O traço de ênfase precisa de borda suave.

O `ImageDraw.line` do PIL desenha sem suavização: a borda sai em degraus, e
o círculo de ênfase é uma elipse deitada — justamente o ângulo onde o
serrilhado aparece. Medido em 29/08 contra o Remotion no mesmo quadro do
mesmo vídeo: o navegador tinha 649 pixels de meio-tom na borda do traço e o
motor próprio ZERO. Com o desenho em 3x reduzido por média de área: 541
(razão 0,18 contra 0,21 do navegador).
"""
import numpy as np

from app.render_proprio import _mascara_linha


def _meios_tons(mask) -> int:
    a = np.asarray(mask, dtype=np.int32)
    return int(((a > 10) & (a < 245)).sum())


def test_diagonal_tem_meio_tom_na_borda():
    pontos = [(10.0, 10.0), (190.0, 60.0)]
    m = _mascara_linha(pontos, 200, 80, 0, 0, 9)
    a = np.asarray(m, dtype=np.int32)
    assert a.max() > 240, "não desenhou o traço"
    assert _meios_tons(m) > 100, "borda dura: sem suavização"


def test_a_suavizacao_e_uma_fatia_de_verdade_do_traco():
    """Nao basta "ter algum meio-tom": a borda suave tem de ser uma parcela
    real do traco. No navegador a razao medida foi 0,21 (649 meio-tons para
    3099 de nucleo); abaixo de 0,05 o traco esta praticamente duro."""
    m = _mascara_linha([(10.0, 10.0), (190.0, 60.0)], 200, 80, 0, 0, 9)
    a = np.asarray(m, dtype=np.int32)
    nucleo = int((a >= 245).sum())
    assert nucleo > 500, "traco fino demais para julgar"
    assert _meios_tons(m) / nucleo > 0.05, "borda quase dura"


def test_traco_vazio_nao_quebra():
    m = _mascara_linha([], 50, 50, 0, 0, 9)
    assert np.asarray(m).max() == 0
    m = _mascara_linha([(1.0, 1.0)], 50, 50, 0, 0, 9)
    assert np.asarray(m).max() == 0


def test_caixa_minima_nao_quebra():
    m = _mascara_linha([(0.0, 0.0), (1.0, 1.0)], 0, 0, 0, 0, 9)
    assert m.size == (1, 1)


def test_os_dois_desenhos_usam_o_mesmo_caminho():
    """Traço (círculo) e marca-texto compartilham a rasterização — se um
    voltar a desenhar direto no PIL, o serrilhado volta só nele."""
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "app" / "render_proprio.py"
         ).read_text(encoding="utf-8")
    assert s.count("_mascara_linha(sub") == 2
    assert "dr.line(desl" not in s.split("def _mascara_linha")[1].split(
        "def ", 1)[1], "sobrou desenho sem suavização fora do ajudante"


def test_a_caixa_do_risco_usa_a_entrelinha_como_o_navegador():
    """A caixa do traço é "120% x 150% da palavra", e a palavra é medida
    pela ENTRELINHA (tam * 1,12) — como no navegador.

    Isto tem um teste porque eu mesmo "consertei" errado em 29/08: medindo
    a BASE do laço, o motor próprio parecia 36px mais baixo. Mas no
    navegador o arco de baixo passa ATRÁS das letras e some — a base
    visível não é a geometria. As PONTAS do laço, que o texto não esconde,
    batem com a entrelinha (esquerda 1281 e direita 1258, contra 1281 e
    1256 do Remotion) e erram 25px com qualquer outra referência."""
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "app" / "render_proprio.py"
         ).read_text(encoding="utf-8")
    i = s.index("esq, topo, larg_f, alt_f = TRACO_CAIXA")
    trecho = s[i:i + 260]
    assert "topo * alt_c" in trecho and "alt_f * alt_c" in trecho, trecho
    j = s.index("esq, topo, larg_f, alt_f = MARCADOR_CAIXA")
    trecho_m = s[j:j + 260]
    assert "topo * alt_c" in trecho_m and "alt_f * alt_c" in trecho_m


def test_supersampling_suficiente_para_a_diagonal():
    """3x deixava a diagonal do laço com 0,225 de meio-tom por núcleo
    contra 0,241 do navegador; 6x dá 0,239."""
    import app.render_proprio as rp
    assert rp.TRACO_SS >= 6


def test_ponta_do_marca_texto_e_elipse_e_nao_circulo():
    """A ponta da faixa do marca-texto acompanha o estica do SVG.

    O SVG do marca-texto usa `preserveAspectRatio="none"` e nao usa
    `vectorEffect`, entao o navegador estica a ponta arredondada na
    horizontal junto com a caixa. Com ponta redonda a faixa saia 65px
    curta de CADA lado contra o preview (tinta 0,838); com a elipse o erro
    caiu para 2px (tinta 0,986). O circulo continua com ponta redonda: la
    o SVG segura a espessura com `non-scaling-stroke`.
    """
    import numpy as np

    from app.render_proprio import _mascara_linha

    pontos = [(60.0, 40.0), (240.0, 40.0)]
    redonda = np.asarray(_mascara_linha(pontos, 300, 80, 0, 0, 30))
    elipse = np.asarray(_mascara_linha(pontos, 300, 80, 0, 0, 30, raio_x=60))

    def extremos(m):
        xs = np.nonzero((m > 127).any(axis=0))[0]
        ys = np.nonzero((m > 127).any(axis=1))[0]
        return int(xs.min()), int(xs.max()), int(ys.max() - ys.min())

    e_r, d_r, alt_r = extremos(redonda)
    e_e, d_e, alt_e = extremos(elipse)
    # a elipse estica so na horizontal: mesma espessura, mais larga
    assert abs(alt_e - alt_r) <= 2, (alt_r, alt_e)
    assert e_r - e_e >= 25 and d_e - d_r >= 25, (e_r, e_e, d_r, d_e)


def test_marca_texto_fica_na_tela_depois_de_entrar():
    """A faixa do marca-texto some depois da animacao de entrada?

    Ela era montada so como os pedacos da entrada (janelas de ~10 quadros)
    e nao tinha o estagio final de permanencia que o circulo ja tinha —
    entao o realce aparecia e sumia. Este teste le o codigo porque montar
    um render completo aqui custaria minutos.
    """
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "app" / "render_proprio.py"
         ).read_text(encoding="utf-8")
    i = s.index("esq, topo, larg_f, alt_f = MARCADOR_CAIXA")
    j = s.index("esq, topo, larg_f, alt_f = TRACO_CAIXA")
    trecho = s[i:j]          # so o bloco do marcador, antes do circulo
    assert "_faixa(1.0, (o_fim," in trecho, "sem o estagio de permanencia"


def test_preview_fecha_o_laco_do_risco():
    """O laço do preview tem que fechar, como o do vídeo final.

    `strokeDasharray={1}` com `non-scaling-stroke` faz o Chrome medir o
    tracejado na tela esticada: o traço aceso acabava antes do fim e o laço
    ficava aberto no arco de baixo (medido: o preview desenhava 0–0,42 e
    0,78–1,00 do caminho, tinta 9400 contra 15946 do motor próprio). Sem o
    tracejado depois que a animação termina, o preview passou a 16218 de
    tinta e 0,92 de sobreposição com o motor próprio.
    """
    from pathlib import Path
    s = (Path(__file__).resolve().parent.parent / "assets" / "shortform" /
         "src" / "PencilOutline.tsx").read_text(encoding="utf-8")
    assert "strokeDasharray={p >= 1 ? undefined : 1}" in s
    assert "strokeDashoffset={p >= 1 ? undefined : 1 - p}" in s
