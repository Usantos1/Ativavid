# -*- coding: utf-8 -*-
"""5.0.25: quatro transições de corte, no lugar de uma.

Até a 5.0.24 existia UMA (`flash`) e ela era escrita à mão em quatro
arquivos; a tela nem perguntava. Ele pediu mais opções junto com os estilos
de manchete (04/09).

As quatro pintam SÓ no overlay — a camada que os dois motores sabem compor
igual. Transição que deforma a imagem (zoom, deslize) mexeria no vídeo por
baixo e não cabe neste desenho; por isso não estão aqui.

A armadilha que este arquivo guarda é a de sempre neste projeto: campo que
a tela salva e o render nunca recebe. `transicao` precisa estar em
STYLE_KEYS, senão morre na cadeia de presets — foi assim que a cor da
empresa se perdeu no mesmo dia.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.brand_presets import STYLE_KEYS  # noqa: E402
from app.transicoes import NOMES, TIPOS, USAM_A_COR_DA_MARCA  # noqa: E402

PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "CustomGraphics.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
FAST = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def test_o_campo_atravessa_a_cadeia_de_presets():
    assert "transicao" in STYLE_KEYS, (
        "o preset guarda a transição e o render nunca a recebe")


def test_a_tela_oferece_todas_as_do_catalogo():
    i = HTML.index('<select id="autoTransicao">')
    bloco = HTML[i:HTML.index("</select>", i)]
    for t in NOMES:
        assert f'value="{t}"' in bloco, f"`{t}` não aparece na tela"


def test_a_escolha_e_lida_e_gravada():
    assert "['autoTransicao', 'transicao', 'flash']" in PJS, "a tela não lê a escolha"
    assert "['autoTransicao', 'transicao']" in PJS, "mexer no seletor não salva"
    assert "transicao: S.style.transicao || 'flash'" in PJS, (
        "o estilo vai para o servidor sem a transição")


def test_o_pipeline_usa_o_tipo_escolhido():
    i = FAST.index('if elems.get("flashCut"):')
    bloco = FAST[i:i + 1200]
    assert 'preset.get("transicao")' in bloco, "o pipeline ignora a escolha"
    # 5.0.37: a forma virou `if tipo == "nenhuma": transitions = []` para
    # as escolhas por corte terem onde entrar; o que se cobra e a regra.
    assert 'if tipo == "nenhuma":' in bloco and "transitions = []" in bloco, (
        "`nenhuma` ainda escreveria transições")
    assert '"accent": accent' in bloco, (
        "a faixa sairia laranja de fábrica em vez da cor da empresa")


def test_o_motor_rapido_nao_recusa_as_novas():
    """Tipo desconhecido derruba o job no caminho LENTO, calado."""
    i = PROPRIO.index("for tr in edit_data.get(\"transitions\") or []:")
    bloco = PROPRIO[i - 200:i + 260]
    assert "from app.transicoes import NOMES" in bloco, (
        "a guarda voltou a aceitar só o flash — as outras três caem no lento")


def test_os_dois_motores_desenham_as_quatro():
    for t in ("brilho", "escurece", "faixa"):
        assert f'"{t}"' in PROPRIO or f"'{t}'" in PROPRIO, f"motor próprio sem `{t}`"
        assert f"'{t}'" in TSX, f"o template não desenha `{t}`"
    assert "tipo in (\"brilho\", \"escurece\")" in PROPRIO
    assert 'if (tipo === \'brilho\' || tipo === \'escurece\')' in TSX


def test_a_faixa_usa_a_cor_da_marca_e_o_resto_nao():
    assert USAM_A_COR_DA_MARCA == {"faixa"}
    i = PROPRIO.index('if tipo == "faixa":')
    # ate o fim do ramo, e nao uma janela de N caracteres: so de crescer um
    # comentario dentro dele o teste quebrava sem defeito nenhum
    marca = "est = f - (c - FLASH_LEAD)"
    dentro = PROPRIO.index(marca, i)
    fim = PROPRIO.index(marca, dentro + len(marca))
    bloco = PROPRIO[i:fim]
    assert "self._cor_transicao" in bloco, "a faixa não usa a cor da marca"
    volta = bloco.split("return a,")[1][:140]
    assert "_cor_transicao" in volta and "* 255" not in volta, (
        "`_cor` já devolve 0..255; multiplicar de novo estoura a cor")


def test_nenhuma_esta_no_catalogo_mas_nao_e_desenho():
    assert "nenhuma" in TIPOS and "nenhuma" not in NOMES, (
        "`nenhuma` é ausência de transição, não um desenho")


def test_a_intensidade_do_estilo_chega_na_transicao():
    """O template sempre leu `intensity`; o pipeline nunca escrevia o campo,
    então "sutil" e "forte" davam exatamente o mesmo flash."""
    i = FAST.index('if elems.get("flashCut"):')
    bloco = FAST[i:i + 1400]
    assert '"sutil": 0.6' in bloco and '"forte": 1.35' in bloco
    assert '"intensity": forca' in bloco, "a força não viaja com a transição"


def test_o_motor_rapido_obedece_a_intensidade():
    assert "def _flash_quadro(self, at_s: float, f: int, tipo: str = \"flash\"," in PROPRIO
    assert "k: float = 1.0)" in PROPRIO
    for trecho in ("0.62 * k", "0.92 * k", "np.float32(bloom)) * k"):
        assert trecho in PROPRIO, f"`{trecho}` sumiu — a força não é aplicada"


def test_todos_os_lugares_leem_a_tripla():
    """`flashes` virou (quando, tipo, força). Quem esquecer de desempacotar
    quebra o render inteiro — e são CINCO lugares, achados pela varredura."""
    import re
    alvos = {
        "app/render_proprio.py": PROPRIO,
        "app/emenda_legenda.py": (REPO / "app" / "emenda_legenda.py").read_text(encoding="utf-8"),
        "tools/varrer_desenho.py": (REPO / "tools" / "varrer_desenho.py").read_text(encoding="utf-8"),
    }
    for nome, txt in alvos.items():
        for m in re.finditer(r"for (.+?) in [\w.]*flashes", txt):
            assert m.group(1).count(",") == 2, (
                f"{nome}: `for {m.group(1)} in ...flashes` não desempacota a tripla")
