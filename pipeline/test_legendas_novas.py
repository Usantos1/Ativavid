# -*- coding: utf-8 -*-
"""Os cinco estilos de legenda de 30/08, nos TRÊS motores.

"quero uns metalizados, outros tipo fonte glass que ofusca o efeito vidro
sobre o take, outros modelos com traço fino, nada grosso demais, e me
surpreenda."

Validados quadro a quadro contra o Remotion (140 quadros de fala contínua,
razão de tinta mediana):

    metal 1,007 · vidro 1,014 · traço 1,018 · moldura 1,003 · eco 1,023

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
    i = PY.index("permitidos = {")
    bloco = PY[i:i + 500]
    for e in NOVOS:
        assert f'"{e}"' in bloco, f"{e} não está na lista do motor rápido"


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
        "vidro":     (50, 12, 2, 700),
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
    run = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = run.index("if ca and captions in (")
    bloco = run[i:i + 320]
    for e in NOVOS:
        assert f'"{e}"' in bloco, f"{e} não recebe a cor da legenda"
    for e in NOVOS:
        assert f"'{e}'" in JS[JS.index("const CAP_BASE_STYLES = ["):
                              JS.index("const CAP_EMPH_STYLES")]


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
