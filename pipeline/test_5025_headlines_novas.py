# -*- coding: utf-8 -*-
"""5.0.25: quatro estilos de MANCHETE novos.

Ele (04/09), depois de oito estilos de legenda novos no mesmo dia: "tu não
criou os novos estilos ali de headline, tá igual estava". Estava mesmo — a
lista de manchete não mudava desde 29/08.

Os quatro reaproveitam peças que os três motores já sabem desenhar, que é o
que torna possível manter a mesma geometria nos três:

  recorte   caixa BRANCA com a letra na cor da marca (o realce invertido)
  etiqueta  caixa da marca com um fio branco por dentro da borda
  marcador  traço de marca-texto atrás do CORPO da letra
  linhas    dois fios finos, um acima e um abaixo do bloco todo

A tabela de geometria é a MESMA escrita em três lugares (`HL_STYLES` no
render_proprio.py, no Main.tsx e no app.js) — este arquivo compara os três.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

NOVAS = ("recorte", "etiqueta", "marcador", "linhas")

PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _geo_proprio(estilo):
    m = re.search(rf'"{estilo}":\s*\(\((\d+), (\d+)\), (\d+), (\d+), ([\d.]+), (\d+)\)',
                  PROPRIO)
    assert m, f"`{estilo}` não está na tabela do motor próprio"
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4]), float(m[5]))


def _geo_js(fonte, estilo):
    m = re.search(rf'{estilo}:\s*\{{weights:\s*\[(\d+), (\d+)\], cap: (\d+), '
                  rf'safeW: (\d+), lh: ([\d.]+)', fonte)
    if not m:
        m = re.search(rf'{estilo}:\s*\{{ weights: \[(\d+), (\d+)\], cap: (\d+), '
                      rf'safeW: (\d+), lh: ([\d.]+)', fonte)
    assert m, f"`{estilo}` não está na tabela"
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4]), float(m[5]))


def test_a_geometria_e_a_mesma_nos_tres_motores():
    for e in NOVAS:
        p, t, j = _geo_proprio(e), _geo_js(TSX, e), _geo_js(PJS, e)
        assert p == t == j, f"`{e}` tem geometrias diferentes: {p} {t} {j}"


def test_cada_motor_sabe_desenhar_os_quatro():
    for e in NOVAS:
        assert f'if estilo == "{e}":' in PROPRIO, f"motor próprio não desenha `{e}`"
        assert f"styleId === '{e}'" in TSX, f"o template não desenha `{e}`"
        assert f"styleId === '{e}'" in PJS, f"o cartão do editor não mostra `{e}`"


def test_o_template_aceita_os_quatro_no_tipo():
    i = TSX.index("style?: 'outline' | 'card'")
    bloco = TSX[i:i + 420]
    for e in NOVAS:
        assert f"'{e}'" in bloco, f"`{e}` fora do tipo — o tsc reprova o job"


def test_o_editor_lista_os_quatro_no_catalogo():
    i = PJS.index("  headlines: [")
    bloco = PJS[i:PJS.index("]", i)]
    for e in NOVAS:
        assert f"id: '{e}'" in bloco, f"`{e}` não aparece na tela de escolha"


def test_os_quatro_usam_a_cor_da_marca():
    i = PJS.index("const HL_ACCENT_USERS = [")
    bloco = PJS[i:PJS.index("];", i)]
    for e in NOVAS:
        assert f"'{e}'" in bloco, (
            f"`{e}` não entra na lista da cor — a tela some com o seletor")


def test_o_hub_tem_nome_para_os_quatro():
    for e, nome in (("recorte", "Recorte"), ("etiqueta", "Etiqueta"),
                    ("marcador", "Marca-texto"), ("linhas", "Entre linhas")):
        assert f'{e}: "{nome}"' in SJS, f"o cartão de preset mostraria o id cru de `{e}`"


def test_a_faixa_do_marcador_fica_atras_do_texto():
    """Mesma armadilha do sublinhado (corrigida em 29/08): com a faixa
    depois do texto na lista, ela cobre os descendentes das letras."""
    i = PROPRIO.index('if estilo == "marcador":')
    corpo = PROPRIO[i:PROPRIO.index('if estilo == "linhas":', i)]
    faixa = corpo.index("leg.palavras.append(Palavra(")
    texto = corpo.index("self._hl_bloco_texto(")
    assert faixa < texto, "a faixa do marca-texto passou por cima da letra"


def test_os_fios_do_linhas_envolvem_o_bloco_e_nao_cada_linha():
    i = PROPRIO.index('if estilo == "linhas":')
    corpo = PROPRIO[i:i + 1500]
    assert "alt_bloco = alt_cx * len(usadas)" in corpo, (
        "os fios voltaram a ser por linha")
