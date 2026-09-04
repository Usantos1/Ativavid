# -*- coding: utf-8 -*-
"""5.0.18: quatro estilos de legenda novos (neon, degradê, bandeira,
máquina de escrever).

Ele (04/09) escolheu "todos" da lista que propus. Cada estilo vive em
TRES motores — o template (SimpleCaptions.tsx), o motor proprio
(render_proprio) e a previa do editor — e um estilo que existe so em dois
sai diferente no video ou some da tela. Medido contra o Remotion em
04/09: neon 1,071 · degradê 1,007 · bandeira 0,998 · máquina 0,974.
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

NOVOS = ("neon", "degrade", "bandeira", "maquina")


def test_os_quatro_existem_nos_tres_motores():
    for e in NOVOS:
        assert e in caption_styles.NOMES, e
        # 5.0.23: neon, degrade e bandeira pintam uma SUPERFICIE -> cor da ENFASE;
        # a maquina de escrever pinta a LETRA -> cor da legenda
        alvo = (caption_styles.USAM_COR_DA_LEGENDA if e == "maquina"
                else caption_styles.USAM_COR_DA_ENFASE)
        assert e in alvo, f"{e}: a cor da marca tem de chegar nele"
        assert e in Renderizador.SIMPLE_VARIANTES, f"{e}: o motor proprio nao desenha"
        assert f"  {e}: {{" in TSX, f"{e}: sem variante no template"
        assert f"  {e}: {{family:" in PJS, f"{e}: sem variante na previa"
        assert f"{{id: '{e}'," in PJS, f"{e}: fora do catalogo da tela"
        assert f"'{e}'" in MAIN, f"{e}: fora do tipo de captions.style"


def test_a_medida_bate_nos_tres():
    """Fonte, tamanho, palavras por cue e largura: se divergirem, a QUEBRA
    de linha muda e o video sai com outro texto na tela."""
    esperado = {
        "neon": (74, 3, 1, 800),
        "degrade": (78, 3, 1, 800),
        "bandeira": (62, 4, 1, 760),
        "maquina": (56, 8, 2, 840),
    }
    for e, (tam, maxp, lin, maxw) in esperado.items():
        arq, eixo, t0, mp, nl, sx, sy, tr, bottom, mw, modo = Renderizador.SIMPLE_VARIANTES[e]
        assert (t0, mp, nl, mw) == (tam, maxp, lin, maxw), e
        assert modo == e and bottom == 430
        assert f"size: {tam}, maxWords: {maxp}, lines: {lin}" in TSX.replace("\n", " ").replace("    ", " "), e
        assert f"size: {tam}, maxWords: {maxp}, lines: {lin}" in PJS, e
        # `  <id>: {family:` e a entrada de STATIC_VARIANTS — o catalogo de
        # MANCHETES tambem tem um `neon`, e split solto pegava o dele
        assert f"maxW: {maxw}" in PJS.split(f"  {e}: {{family:")[1][:260], e


def test_a_caixa_alta_e_a_entrelinha_batem():
    """Quem desenha em CAIXA ALTA muda a MEDIDA das linhas: os tres motores
    tem de concordar sobre a lista (por pertencimento — ela cresce a cada
    estilo novo)."""
    from app.render_proprio import Renderizador
    tsx_set = TSX.split("const MAIUSCULA = new Set([")[1].split("]);")[0]
    pjs_set = PJS.split("const CAP_MAIUSCULA = new Set([")[1].split("]);")[0]
    for e in ("degrade", "bandeira"):
        assert e in Renderizador.SIMPLE_MAIUSCULA, e
        assert f"'{e}'" in tsx_set and f"'{e}'" in pjs_set, e
    for e in ("neon", "maquina"):
        assert e not in Renderizador.SIMPLE_MAIUSCULA, e
        assert f"'{e}'" not in tsx_set and f"'{e}'" not in pjs_set, e
    for e, lh in (("neon", 1.16), ("degrade", 1.14), ("bandeira", 1.2), ("maquina", 1.3)):
        assert f'"{e}": {lh}' in PY.replace("1.20", "1.2").replace("1.30", "1.3"), e
        assert f"{e}: {lh}" in TSX and f"{e}: {lh}" in PJS, e


def test_a_maquina_digita_no_mesmo_ritmo_nos_dois_motores():
    """Uma letra a cada `vel` quadros, teto de 2, cue digitado em 55% do
    tempo. Se os dois motores discordarem, a legenda termina de escrever em
    momentos diferentes — e a razao de tinta (mediana) esconderia isso."""
    assert "export function velocidadeMaquina(durFrames: number, nChars: number): number" in TSX
    assert "return Math.min(2, (0.55 * durFrames) / Math.max(1, nChars));" in TSX
    assert "def velocidade_maquina(dur_f: int, n_chars: int) -> float:" in PY
    assert "return min(2.0, 0.55 * dur_f / max(1, n_chars))" in PY
    f = Renderizador.velocidade_maquina
    assert f(60, 20) == 60 * 0.55 / 20
    assert f(600, 10) == 2.0, "o teto de 2 quadros por letra vale"
    assert f(30, 0) == min(2.0, 0.55 * 30)


def test_a_bandeira_inclina_a_fita_com_o_mesmo_angulo():
    assert "const BANDEIRA_SKEW = 8;" in TSX and "skewX(-${BANDEIRA_SKEW}deg)" in TSX
    assert "BANDEIRA_SKEW = 8.0" in PY
    assert "skewX(-8deg)" in PJS
    i = PY.index("def _bandeira(")
    bloco = PY[i:i + 3000]
    assert "math.tan(math.radians(self.BANDEIRA_SKEW))" in bloco
    assert "Image.AFFINE" in bloco, "o cisalhamento e da imagem inteira, texto junto"
    assert "self._tinta_na_caixa(fita)" in bloco, "a tinta sai da luminancia da fita, como inkOn"


def test_as_cores_padrao_sao_as_mesmas():
    for nome, valor in (("NEON_PADRAO", "#4de1ff"), ("DEGRADE_PADRAO", "#ff6a00"),
                        ("BANDEIRA_PADRAO", "#ff6a00")):
        assert f"const {nome} = '{valor}';" in TSX, nome
        assert f'{nome} = "{valor}"' in PY, nome
        assert f"const {nome} = '{valor}';" in PJS, nome
