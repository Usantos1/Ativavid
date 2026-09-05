# -*- coding: utf-8 -*-
"""5.0.70: desenho do overlay 1,32x mais rápido, e seis manchetes por fonte.

VELOCIDADE. Perfil de 900 quadros de um projeto real (30 s de vídeo,
40 camadas, 3 flashes): 16,33 s de desenho.

    `_aplicar_flash`  3,76 s  (21 chamadas, 0,18 s cada) — 23% do desenho
    `tobytes`         1,63 s  (687 cópias de 8,3 MB)     — 10%

O flash convertia o quadro INTEIRO para float32 e voltava, a cada quadro
de flash. Com a=0 a conta devolve o próprio pixel, então recortar pela
caixa onde a máscara é maior que zero não muda nada visível — e o feixe,
que varre o quadro, fica parcialmente fora dele em boa parte dos quadros.
A cópia para o cano some escrevendo o buffer direto (memoryview).

Depois: 12,39 s (1,32x). Provado quadro a quadro contra o código antigo:
nos pixels visíveis a diferença máxima é 1 em 255, e só onde a máscara é
exatamente zero — era o arredondamento do código antigo em pixels que ele
nem devia tocar. 681 dos 744 pixels diferentes estão com alfa zero dos
dois lados (o antigo zerava a cor por baixo da transparência).

MANCHETES. Nos 331 projetos do disco só `realce` (198) e `fita` (133)
foram usados; os outros vinte, nunca. O que muda a cara de um título é a
LETRA, então o lote são seis fontes já carregadas sobre pinturas que já
passaram na varredura — a fonte vem do id, a pintura de um alias.
"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.render_proprio import MARCA_FONTES, Renderizador  # noqa: E402

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
FONTS = (REPO / "assets" / "shortform" / "src" / "fonts.ts").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")

LOTE = {
    "gigante": ("bebas", "outline", True),
    "cartaz": ("titan", "card", True),
    "esportiva": ("kanit", "realce", False),
    "elegante": ("lora", "sublinhado", False),
    "estreita": ("oswald", "faixa", True),
    "quadrinhos": ("bangers", "sombra", False),
}


# ------------------------------------------------------------- o flash
def _flash_antigo(buf, a, cor):
    """Cópia literal do `_aplicar_flash` da 5.0.69 (quadro inteiro)."""
    b = buf.copy()
    a_b = b[..., 3].astype(np.float32) / 255.0
    a_o = a + a_b * (1.0 - a)
    peso = (a_b * (1.0 - a))[..., None]
    c3 = np.asarray(cor, dtype=np.float32)[None, None, :]
    rgb = (c3 * a[..., None] + b[..., :3].astype(np.float32) * peso) / np.maximum(a_o[..., None], 1e-6)
    b[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    b[..., 3] = (np.clip(a_o, 0, 1) * 255.0).astype(np.uint8)
    return b


def _quadro_de_prova():
    rng = np.random.default_rng(7)
    buf = np.zeros((120, 200, 4), dtype=np.uint8)
    # uma "legenda" opaca no meio e uma borda meio transparente
    buf[40:80, 50:150, :3] = rng.integers(0, 256, (40, 100, 3), dtype=np.uint8)
    buf[40:80, 50:150, 3] = 255
    buf[30:40, 50:150, :3] = 200
    buf[30:40, 50:150, 3] = 120
    # um feixe diagonal que cobre so parte do quadro
    a = np.zeros((120, 200), dtype=np.float32)
    xs = np.arange(200)[None, :] - np.arange(120)[:, None] * 0.6
    a[:, :] = np.clip(1.0 - np.abs(xs - 60) / 40.0, 0, 1) * 0.8
    return buf, a


def test_o_flash_recortado_da_o_mesmo_resultado_visivel():
    buf, a = _quadro_de_prova()
    r = Renderizador.__new__(Renderizador)
    novo = buf.copy()
    sujo = [0, 0, 0, 0]
    Renderizador._aplicar_flash(r, novo, sujo, a, (255.0, 255.0, 255.0))
    velho = _flash_antigo(buf, a, (255.0, 255.0, 255.0))
    vivo = a > (0.5 / 255.0)
    # dentro do feixe: identico
    assert np.array_equal(novo[vivo], velho[vivo])
    # fora do feixe, onde ha alfa: no maximo 1 de 255 (o arredondamento
    # do antigo); onde alfa e zero a cor por baixo nao conta
    fora = ~vivo & (novo[..., 3] > 0)
    d = np.abs(novo[fora].astype(int) - velho[fora].astype(int))
    assert d.max() <= 1, d.max()
    # o sujo cobre a caixa do feixe
    ys, xs = np.nonzero(vivo)
    assert sujo[0] <= xs.min() and sujo[2] >= xs.max() + 1
    assert sujo[1] <= ys.min() and sujo[3] >= ys.max() + 1


def test_mascara_vazia_nao_toca_no_quadro():
    """O antigo zerava a cor de todo pixel transparente mesmo sem feixe."""
    buf, _ = _quadro_de_prova()
    buf[0, 0, :3] = (9, 8, 7)          # cor "por baixo" de alfa zero
    novo = buf.copy()
    sujo = [0, 0, 0, 0]
    r = Renderizador.__new__(Renderizador)
    Renderizador._aplicar_flash(r, novo, sujo, np.zeros(buf.shape[:2], np.float32))
    assert np.array_equal(novo, buf), "mascara zero tem de ser um no-op"
    assert sujo == [0, 0, 0, 0]


def test_a_escrita_no_cano_nao_copia():
    src = inspect.getsource(Renderizador)
    assert 'memoryview(buf).cast("B")' in RP
    assert RP.count('bytes_ant = memoryview(buf).cast("B")') == 2, "os dois lacos de quadros"
    assert "bytes_ant = buf.tobytes()" not in RP
    assert "np.flatnonzero(vivo.any(axis=1))" in src, "o recorte pela caixa da mascara"


# -------------------------------------------------------- as manchetes
def test_as_seis_existem_nos_tres_motores():
    assert len(Renderizador.HL_STYLES) == 28
    for e in LOTE:
        assert e in Renderizador.HL_STYLES, e
        assert f"  {e}: {{weights:" in TSX, f"{e} fora do template"
        assert f"  {e}: {{ weights:" in PJS, f"{e} fora do editor"
        assert f"id: '{e}', name:" in PJS, f"{e} fora do seletor"
        assert f'{e}: "' in SJS.split("manchete: {", 1)[1][:1400], f"{e} fora do hub"


def test_fonte_e_pintura_batem_com_o_catalogo():
    for e, (fonte, pintura, maiuscula) in LOTE.items():
        assert Renderizador.HL_FONTE_DO_ESTILO[e] == fonte, e
        assert Renderizador.HL_PINTURA[e] == pintura, e
        assert pintura in Renderizador.HL_STYLES and pintura not in LOTE, e
        assert fonte in MARCA_FONTES, f"{e}: `{fonte}` nao e id do catalogo"
        assert (e in Renderizador.HL_MAIUSCULA) is maiuscula, e
        bloco = TSX.split(f"  {e}: {{weights:", 1)[1][:200]
        assert f"family: '{fonte}'" in bloco and f"paint: '{pintura}'" in bloco, e
        bloco_js = PJS.split(f"  {e}: {{ weights:", 1)[1][:220]
        assert f"paint: '{pintura}'" in bloco_js, e


def test_o_peso_pedido_e_o_que_a_fonte_tem():
    """Bebas, Titan e Bangers sao de peso unico: pedir 900 nelas daria
    negrito falso no Chrome e 400 no Pillow — os motores divergiriam."""
    for e, (fonte, _, _) in LOTE.items():
        teto = MARCA_FONTES[fonte][1]
        pesos = Renderizador.HL_STYLES[e][0]
        if teto is not None:
            assert max(pesos) <= teto, f"{e}: peso {pesos} acima do teto {teto} da {fonte}"


def test_os_numeros_da_tabela_sao_os_mesmos_nos_tres():
    for e in LOTE:
        (p0, p1), cap, safe, lh, top = Renderizador.HL_STYLES[e]
        t = TSX.split(f"  {e}: {{weights:", 1)[1][:160]
        assert f"[{p0}, {p1}], cap: {cap}, safeW: {safe}, lh: {lh:g}, top: {top}" in t.replace("1.10", "1.1").replace("1.02", "1.02"), (e, t)
        j = PJS.split(f"  {e}: {{ weights:", 1)[1][:160]
        assert f"[{p0}, {p1}], cap: {cap}, safeW: {safe}, lh: {lh:.2f}" in j or \
            f"[{p0}, {p1}], cap: {cap}, safeW: {safe}, lh: {lh:g}" in j, (e, j)


def test_a_fonte_vem_do_id_e_a_pintura_do_alias():
    assert "self._hl_estilo_id = estilo" in RP
    assert "estilo = self.HL_PINTURA.get(estilo, estilo)" in RP
    fonte = inspect.getsource(Renderizador._hl_fonte)
    assert "HL_FONTE_DO_ESTILO.get(getattr(self, \"_hl_estilo_id\"" in fonte
    assert fonte.index("if self.marca_hook:") < fonte.index("HL_FONTE_DO_ESTILO"), (
        "a fonte da MARCA continua mandando, como no template")
    # template
    assert "const paintId = S.paint ?? styleId;" in TSX
    assert "const hlFF = hookFamily(HLF?.family ?? fontFamily);" in TSX
    assert "if (styleId === '" not in TSX, "toda pintura compara com o alias"
    assert TSX.count("if (paintId === '") == 21
    assert "export function familyFor" in FONTS
    # editor
    assert "HL_FAMILIA_ATUAL = S.family || null;" in PJS
    assert "const paintId = S.paint || styleId;" in PJS
    assert "`hl-demo hl-${paintId}`" in PJS


def test_o_peso_inline_do_template_respeita_o_teto_da_fonte():
    comp = TSX.split("const HookInner: React.FC", 1)[1].split("\nexport const LayoutScrim", 1)[0]
    assert "const hlW = (w: number) =>" in comp
    # dentro do componente so a definicao do hlW chama hookWeight
    assert comp.count("hookWeight(") == 1, comp.count("hookWeight(")
    assert comp.count("hlW(") >= 20
