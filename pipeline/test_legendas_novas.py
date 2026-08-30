# -*- coding: utf-8 -*-
"""Os cinco estilos de legenda de 30/08, nos TRÊS motores.

"quero uns metalizados, outros tipo fonte glass que ofusca o efeito vidro
sobre o take, outros modelos com traço fino, nada grosso demais, e me
surpreenda."

Validados quadro a quadro contra o Remotion (140 quadros de fala contínua,
razão de tinta mediana):

    metal 1,007 · vidro 0,935 · traço 1,018 · moldura 1,003 · eco 1,023

O vidro fica 6,5% abaixo porque o `-webkit-text-stroke` do Chrome é um
traço REDONDO e o nosso é a união de 8 direções (um octógono, que perde os
vãos das diagonais). A diferença é menor que a de estilos já publicados
(o `simples` está em 1,059 e o `impacto` em 1,094) e o par lado a lado é o
mesmo desenho.

O que estes testes guardam é o que a razão de tinta NÃO pega: um estilo que
existe num motor e não no outro sai calado — foi assim que o `videoLayout`
ficou morto por meses no caminho rápido.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src"
       / "SimpleCaptions.tsx").read_text(encoding="utf-8")
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
NOVOS = ("metal", "vidro", "traco", "moldura", "eco")


def test_os_cinco_existem_nos_tres_motores():
    for e in NOVOS:
        assert f'"{e}":' in PY, f"{e} falta no motor próprio"
        assert f"  {e}: {{" in TSX, f"{e} falta no template"
        assert f"  {e}: {{family:" in JS, f"{e} falta na prévia"


def test_o_motor_rapido_aceita_os_cinco():
    """Sem isto o job cai no caminho lento (Chrome) calado — o estilo
    funcionaria, mas cada vídeo levaria 10x mais tempo."""
    import sys
    sys.path.insert(0, str(REPO))
    from app import caption_styles
    for e in NOVOS:
        assert e in caption_styles.TODOS, f"{e} não está na lista"
    # a lista literal virou `app/caption_styles.TODOS`; quem exercita
    # o portão de verdade é o test_estilos_de_legenda_fonte_unica.py
    assert "permitidos = CAPTION_STYLES.TODOS" in PY


def test_a_caixa_alta_e_a_mesma_nos_tres():
    """Caixa alta muda a MEDIDA das linhas: se os motores discordarem, a
    quebra de linha sai diferente e as legendas não casam mais."""
    assert 'SIMPLE_MAIUSCULA = ("sticker", "metal", "moldura", "eco")' in PY
    assert "const MAIUSCULA = new Set(['metal', 'moldura', 'eco']);" in TSX
    assert "const CAP_MAIUSCULA = new Set(['metal', 'moldura', 'eco']);" in JS


def test_o_tamanho_e_a_medida_batem():
    """Tamanho, palavras por cue e largura máxima decidem onde a linha
    quebra. Um número diferente entre motores = outra legenda."""
    esperado = {
        # estilo:    (tamanho, maxPalavras, linhas, larguraMax)
        "metal":     (76, 3, 1, 800),
        "vidro":     (72, 3, 1, 840),
        "traco":     (74, 3, 1, 820),
        "moldura":   (44, 6, 1, 700),
        "eco":       (78, 3, 1, 800),
    }
    for e, (tam, maxp, lin, maxw) in esperado.items():
        i = PY.index(f'"{e}":')
        linha = PY[i:PY.index("\n", i)]
        assert f", {tam}, {maxp}, {lin}," in linha, f"{e}: {linha}"
        assert f", {maxw}," in linha, f"{e} largura: {linha}"
        j = TSX.index(f"  {e}: {{")
        bloco = TSX[j:j + 260]
        assert f"size: {tam}," in bloco and f"maxWords: {maxp}," in bloco
        assert f"lines: {lin}," in bloco and f"maxW: {maxw}," in bloco
        k = JS.index(f"  {e}: {{family:")
        linha = JS[k:JS.index("\n", k)]
        assert f"size: {tam}," in linha and f"maxWords: {maxp}," in linha
        assert f"lines: {lin}," in linha and f"maxW: {maxw}" in linha


def test_a_cor_da_legenda_chega_nos_cinco():
    """O preset guardava a cor e o render nunca a recebia: sem os cinco
    nesta lista, o seletor da tela ficaria mentindo."""
    import sys
    sys.path.insert(0, str(REPO))
    from app import caption_styles
    for e in NOVOS:
        assert e in caption_styles.USAM_COR_DA_LEGENDA, e
    run = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "if ca and captions in USAM_COR_DA_LEGENDA:" in run
    for e in NOVOS:
        assert f"'{e}'" in JS[JS.index("const CAP_BASE_STYLES = ["):
                              JS.index("const CAP_EMPH_STYLES")]


def test_o_metal_e_prata_lisa_sem_risco_no_meio():
    """"a metalica é apenas uma cor metalica com uma certa transparencia
    puxando pro prata, e nao aquele risco no meio da fonte" (30/08).

    A primeira versão tinha uma parada escura em 50% com um estalo de luz
    logo abaixo — o cromado de catálogo. Numa legenda de 3 palavras aquilo
    corta o glifo no meio, e foi o que ele viu.
    """
    i = PY.index("paradas = ((0.00,")
    linha = PY[i:PY.index(chr(41) + chr(10), i)]
    assert "0.38" not in linha and "1.60" not in linha    # a faixa escura
    assert "(0.00, 1.38), (0.42, 1.06), (1.00, 0.74)" in linha
    assert "[[0, 1.38], [42, 1.06], [100, 0.74]]" in TSX
    assert "[[0, 1.38], [42, 1.06], [100, 0.74]]" in JS
    # e a prata deixa o take pulsar por baixo
    assert "METAL_OPACO = 0.88" in PY and "METAL_OPACO = 0.88;" in TSX
    assert "METAL_OPACO = 0.88;" in JS


def test_o_vidro_e_a_letra_e_nao_uma_caixa_atras_dela():
    """"apenas o estilo da fonte é tipo de vidro, com uma certa
    transparência, nao aquele fundo escroto" (30/08). A primeira versão era
    um PAINEL de vidro fumado — uma caixa, não uma letra de vidro."""
    assert 'SIMPLE_PAINEL = ("moldura",)' in PY      # o vidro saiu daqui
    assert "VIDRO_OPACO = 0.32" in PY and "VIDRO_FIO = 0.92" in PY
    for fonte in (TSX, JS):
        assert "VIDRO_OPACO = 0.32;" in fonte
        assert "VIDRO_FIO = 0.92;" in fonte
    # o fio é CENTRADO, como o `-webkit-text-stroke`: dilata E corrói
    i = PY.index('if modo == "vidro":')
    bloco = PY[i:i + 1200]
    assert "dentro = 1.0 - self._contorno(1.0 - pad_m, r)" in bloco
    assert "fio = np.clip(fora - dentro, 0.0, 1.0)" in bloco
    assert "WebkitTextStrokeWidth" in TSX


def test_o_metal_nao_deixa_o_contorno_tapar_o_degrade():
    """Com `background-clip: text` o fundo é pintado ANTES das sombras: uma
    cópia só faria a `text-shadow` do contorno cobrir o cromado."""
    i = TSX.index("if (V.modo === 'metal')")
    bloco = TSX[i:i + 1600]
    assert "position: 'relative'" in bloco
    assert "WebkitBackgroundClip: 'text'" in bloco
    assert bloco.count("{corpo}") == 2      # a de baixo e a de cima


def test_o_eco_pinta_na_mesma_ordem_nos_dois():
    """No CSS a PRIMEIRA sombra da lista fica por cima; no motor próprio
    quem pinta depois é que fica. Ciano em cima nos dois."""
    i = TSX.index("if (V.modo === 'eco')")
    bloco = TSX[i:i + 700]
    assert bloco.index("#28e0d8") < bloco.index("#ff2e88")
    j = PY.index("for desloc, cor_hex in ((")
    linha = PY[j:PY.index("\n", j)]
    assert linha.index("#ff2e88") < linha.index("#28e0d8")


def test_o_cartao_da_tela_usa_os_mesmos_numeros_do_render():
    """Um cartão que mente sobre o resultado é pior que não ter cartão — já
    aconteceu aqui (lápide branca com texto branco, invisível).

    Medido no navegador: o cartão do Metálico aplica o degradê com
    `background-clip: text` e opacidade 0,88; o do Vidro, preenchimento a
    0,32 com fio de 2px a 0,92. São os mesmos números do motor.
    """
    for fonte in (TSX, JS):
        assert "VIDRO_OPACO = 0.32;" in fonte
        assert "VIDRO_FIO = 0.92;" in fonte
        assert "METAL_OPACO = 0.88;" in fonte
    # e o metal do cartão é DUAS cópias, como no template: uma cópia só faria
    # o contorno tapar o degradê
    i = JS.index("if (V.modo === 'metal')")
    bloco = JS[i:i + 1400]
    assert "cima.style.webkitBackgroundClip = 'text';" in bloco
    assert "for (const alvo of [baixo, cima])" in bloco
    # e o vidro do cartão é fill + fio, como no template
    i = JS.index("if (V.modo === 'vidro')")
    bloco = JS[i:i + 1200]
    assert "fundo.style.opacity = String(VIDRO_OPACO);" in bloco
    assert "fio.style.webkitTextStrokeWidth" in bloco
