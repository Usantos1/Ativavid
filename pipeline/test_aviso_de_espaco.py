# -*- coding: utf-8 -*-
"""68 GB para liberar, e o aviso só existia numa tela onde ele não entra.

Medido na máquina dele (30/08), com a própria função do app:

    190 projetos, 155,7 GB na pasta
    34,4 GB em cópias duplicadas (viram hardlink — nada é apagado)
    34,0 GB em intermediários de projetos entregues e parados
    -----------------------------------------------------------
    68,4 GB recuperáveis sem perder vídeo nenhum

O app media isso desde antes e escrevia numa dica dentro de Configurações
› Avançado. Ele não entra lá — foi hoje que pediu para TIRAR coisa de
Configurações. O aviso passa a aparecer em Projetos, com piso e com
silêncio quando dispensado.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")


def test_o_aviso_mora_em_projetos():
    i = HTML.index('id="view-projetos"')
    j = HTML.index('id="view-estilo"')
    bloco = HTML[i:j]
    assert 'id="projEspaco"' in bloco
    assert 'id="btnProjEspaco"' in bloco
    # nasce escondido: quem tem pouco a liberar nunca ve
    assert "hidden" in bloco[bloco.index('id="projEspaco"') - 60:
                             bloco.index('id="projEspaco"')]


def test_so_avisa_quando_o_numero_justifica():
    from_js = JS[JS.index("const ESPACO_PISO_GB"):][:120]
    assert "ESPACO_PISO_GB = 20" in from_js
    i = JS.index("async function avisarEspaco(")
    bloco = JS[i:i + 1200]
    assert "gb >= ESPACO_PISO_GB" in bloco
    assert "caixa.classList.remove(\"hidden\")" in bloco


def test_dispensar_cala_por_trinta_dias():
    """Aviso que volta todo dia vira paisagem."""
    assert "ESPACO_SILENCIO_DIAS = 30" in JS
    i = JS.index('const nao = $("#btnProjEspacoNao");')
    bloco = JS[i:i + 500]
    assert "ativavid-espaco-adiado" in bloco
    assert "ESPACO_SILENCIO_DIAS * 86400000" in bloco
    # e a leitura respeita o adiamento
    i = JS.index("async function avisarEspaco(")
    assert "ativavid-espaco-adiado" in JS[i:i + 500]


def test_liberar_usa_a_rota_que_ja_existia():
    i = JS.index('const btn = $("#btnProjEspaco");')
    bloco = JS[i:i + 900]
    assert '"/api/espaco/liberar"' in bloco
    assert 'caixa.classList.add("hidden")' in bloco, "sumir depois de liberar"


def test_a_conta_que_a_tela_mostra_e_a_do_servidor():
    """duplicatas + intermediarios = total; a tela nao pode inventar."""
    i = JS.index("async function avisarEspaco(")
    bloco = JS[i:i + 1400]
    assert "m.duplicatasGb" in bloco and "m.intermediariosGb" in bloco
    assert "m.totalGb" in bloco


def test_a_medicao_nao_apaga_nada():
    """`medir` so olha; quem apaga e `liberar`. Se um dia se cruzarem,
    abrir Projetos apagaria arquivo sem ninguem pedir."""
    src = (REPO / "helpers" / "liberar_espaco.py").read_text(encoding="utf-8")
    i = src.index("def medir(")
    corpo = src[i:src.index("\ndef ", i + 10)]
    for perigo in ("rmtree", "unlink", "os.remove", "os.link"):
        assert perigo not in corpo, f"medir() chama {perigo}"
