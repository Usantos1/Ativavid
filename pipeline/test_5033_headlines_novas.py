# -*- coding: utf-8 -*-
"""5.0.33: mais três manchetes — Riscado, Duas caixas e Quadro.

Continuação da linha de 04/09 ("pode continuar trazendo melhorias como
essa"). Os três reaproveitam peças que os motores já sabem desenhar:

  riscado  risco da marca atravessando a letra (a 52% da caixa de linha)
  caixas   linha 1 na caixa da marca, linha 2 na caixa branca — o realce e
           o recorte alternados
  quadro   moldura fina da marca em volta do BLOCO, fundo escuro translúcido;
           é o carimbo sem giro e com a letra branca

A tabela de geometria é a MESMA em três lugares; este arquivo compara os
três, como o `test_5025_headlines_novas`.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import re  # noqa: E402

NOVAS = ("riscado", "caixas", "quadro")
PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


# Copiados do `test_5025_headlines_novas`, e nao importados: modulo de teste
# nao e biblioteca, e o modo de import do pytest nao garante que um enxergue
# o outro (a coleta deste arquivo quebrou por isso na primeira rodada).
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


def test_cada_motor_sabe_desenhar_os_tres():
    for e in NOVAS:
        assert f'if estilo == "{e}":' in PROPRIO, f"motor próprio não desenha `{e}`"
        assert f"paintId === '{e}'" in TSX, f"o template não desenha `{e}`"
        assert f"paintId === '{e}'" in PJS, f"o cartão do editor não mostra `{e}`"


def test_o_template_aceita_os_tres_no_tipo():
    i = TSX.index("style?: 'outline' | 'card'")
    bloco = TSX[i:i + 520]
    for e in NOVAS:
        assert f"'{e}'" in bloco, f"`{e}` fora do tipo — o tsc reprova o job"


def test_o_editor_lista_e_pinta_com_a_cor_da_marca():
    i = PJS.index("  headlines: [")
    cat = PJS[i:PJS.index("]", i)]
    j = PJS.index("const HL_ACCENT_USERS = [")
    cor = PJS[j:PJS.index("];", j)]
    for e in NOVAS:
        assert f"id: '{e}'" in cat, f"`{e}` não aparece na tela de escolha"
        assert f"'{e}'" in cor, f"`{e}` sem a cor — a tela some com o seletor"


def test_o_hub_tem_nome_para_os_tres():
    for e, nome in (("riscado", "Riscado"), ("caixas", "Duas caixas"),
                    ("quadro", "Quadro")):
        assert f'{e}: "{nome}"' in SJS


def test_o_risco_fica_atras_do_texto():
    i = PROPRIO.index('if estilo == "riscado":')
    corpo = PROPRIO[i:PROPRIO.index('if estilo == "caixas":', i)]
    assert corpo.index("leg.palavras.append(Palavra(") < corpo.index("self._hl_bloco_texto("), (
        "o risco passou por cima da letra")


def test_a_moldura_do_quadro_envolve_o_bloco_com_a_borda_por_fora():
    i = PROPRIO.index('if estilo == "quadro":')
    corpo = PROPRIO[i:i + 2200]
    assert "larg_q = int(larg_max) + 2 * pad_x + 2 * fio" in corpo, (
        "a borda do CSS fica por FORA do padding (content-box)")
    assert "cheio * 0.28" in corpo, "o fundo translúcido sumiu"
