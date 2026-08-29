# -*- coding: utf-8 -*-
"""Layouts e headlines: os três catálogos têm de dizer a mesma coisa.

Um estilo vive em três lugares — o cartão na tela (`app.js`), o desenho do
Remotion (`Main.tsx`) e o desenho do motor próprio (`render_proprio.py`).
Faltando em qualquer um deles nada quebra na hora: o job só sai diferente,
ou cai calado no caminho lento, ou o estilo simplesmente não acontece.

Foi o que estava acontecendo com o layout "Degradê": ele existia na tela e
no Remotion, e o motor próprio — que pega ~18 de cada 20 renders — nunca
olhou `videoLayout`. Quem escolhia recebia o vídeo sem degradê nenhum.

Provado contra o Remotion em 29/08, um quadro cada, tinta do quadro
inteiro (motor próprio ÷ Remotion):
  faixa 1,000 · fita 0,986 · neon 1,003 · vazado 0,883 · gradiente 0,817
  degradê 1,001 · vinheta 1,002 · cinema 0,998 · borda 0,994
(vazado e gradiente ficam abaixo por causa do alcance da sombra do Chrome,
que é mais larga; a forma e a cor foram conferidas olhando o par.)
"""
from __future__ import annotations

import re
from pathlib import Path

from app.render_proprio import Renderizador, camada_do_layout
from app.render_path import OVERLAY, classify_render_path
from app.video_layouts import CAMADA, QUADRO_CHEIO, TODOS, TRANSFORMAM

REPO = Path(__file__).resolve().parent.parent
APPJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")

NOVAS_HL = ("faixa", "fita", "neon", "vazado", "gradiente")
NOVOS_LAYOUTS = ("vinheta", "cinema", "borda")


def _ids_da_tela(grupo: str) -> list[str]:
    """Os ids do catálogo da tela, sem precisar de um motor de JS."""
    i = APPJS.index(f"  {grupo}: [")
    fim = APPJS.index("\n  ],", i)
    return re.findall(r"id: '([a-z0-9_]+)'", APPJS[i:fim])


# --------------------------------------------------------------- headline ---
def test_a_headline_nova_existe_nos_tres_lugares():
    tela = _ids_da_tela("headlines")
    for nome in NOVAS_HL:
        assert nome in tela, f"{nome}: falta o cartão na tela"
        assert f"styleId === '{nome}'" in MAIN, f"{nome}: falta desenho no Remotion"
        assert nome in Renderizador.HL_STYLES, f"{nome}: falta no motor próprio"


def test_toda_headline_do_catalogo_existe_nos_dois_motores():
    """Vale para o catalogo INTEIRO, nao so para os cinco de hoje: e assim
    que o proximo estilo nao nasce pela metade. Quem so existe no template
    faz o job cair no caminho lento calado; quem so existe no motor proprio
    sai diferente quando o job vai para o Remotion."""
    for nome in _ids_da_tela("headlines"):
        if nome == "nenhuma":            # opta por NAO ter headline
            continue
        assert nome in Renderizador.HL_STYLES, f"{nome}: falta no motor próprio"
        desenha = (f"styleId === '{nome}'" in MAIN
                   or f"HL_STYLES.{nome}" in MAIN)
        assert desenha, f"{nome}: falta desenho no Remotion"


def test_todo_layout_do_catalogo_tem_dono():
    """Cada layout ou TRANSFORMA o video (e vai para o Remotion) ou e so
    camada (e os dois motores desenham). Um id que nao seja nem um nem
    outro nao acontece em lugar nenhum — foi o caso do "degrade"."""
    from app.video_layouts import DIVIDEM

    for nome in _ids_da_tela("edits"):
        if nome in ("limpa", *DIVIDEM):
            continue
        camada = camada_do_layout(nome, 100, 100) is not None
        transforma = nome in TRANSFORMAM
        assert camada != transforma, f"{nome}: nem camada nem transformador"


def test_a_geometria_e_a_mesma_nos_tres():
    """Teto, largura segura e entrelinha diferentes = mesmo estilo em dois
    tamanhos, conforme o caminho que o job pegar."""
    for nome in NOVAS_HL:
        pesos, cap, safe_w, lh, _top = Renderizador.HL_STYLES[nome]
        m = re.search(rf"\n  {nome}: {{weights: \[(\d+), (\d+)\], cap: (\d+), "
                      rf"safeW: (\d+), lh: ([\d.]+)", MAIN)
        assert m, f"{nome}: sem geometria no Main.tsx"
        assert (int(m.group(3)), int(m.group(4))) == (cap, safe_w), nome
        assert float(m.group(5)) == lh, nome
        assert (int(m.group(1)), int(m.group(2))) == pesos, nome


def test_o_motor_rapido_aceita_as_headlines_novas():
    """Sem isto o gate manda o job para o Remotion — calado, e ~5x mais
    devagar — só porque o estilo não existe aqui."""
    from app.render_proprio import motivo_nao_suportado

    for nome in NOVAS_HL:
        ed = {"hook": {"enabled": True, "style": nome},
              "captions": {"enabled": False}, "width": 1080, "height": 1920}
        motivo = motivo_nao_suportado(ed, REPO)
        assert motivo is None or "headline" not in motivo, f"{nome}: {motivo}"


def test_o_tipo_do_template_conhece_os_ids():
    """A união de tipos do `hook.style` — se um id novo não entra nela, o
    TypeScript trata o ramo como código morto."""
    i = MAIN.index("style?: 'outline'")
    bloco = MAIN[i:i + 400]
    for nome in NOVAS_HL:
        assert f"'{nome}'" in bloco, nome


# ----------------------------------------------------------------- layout ---
def test_o_layout_novo_existe_nos_tres_lugares():
    tela = _ids_da_tela("edits")
    for nome in NOVOS_LAYOUTS:
        assert nome in tela, f"{nome}: falta o cartão na tela"
        assert f"VIDEO_LAYOUT === '{nome}'" in MAIN, f"{nome}: falta no Remotion"
        assert camada_do_layout(nome, 1080, 1920) is not None, \
            f"{nome}: o motor próprio não desenha"


def test_a_tela_e_a_lista_do_app_batem():
    assert set(_ids_da_tela("edits")) == set(TODOS), \
        "cartão na tela sem id em video_layouts.py (ou o contrário)"


def test_camada_nao_transforma_e_transformador_nao_e_camada():
    for nome in CAMADA:
        assert camada_do_layout(nome, 200, 300) is not None, nome
    for nome in ("limpa", *TRANSFORMAM):
        assert camada_do_layout(nome, 200, 300) is None, nome
    assert not (set(CAMADA) & set(TRANSFORMAM))


def test_layout_de_camada_nao_perde_o_motor_rapido():
    """O motivo de todos os três novos serem só tinta: quem transforma o
    vídeo obriga o Remotion, e o render do usuário fica ~5x mais lento."""
    for nome in CAMADA:
        r = classify_render_path({"videoLayout": nome,
                                  "captions": {"enabled": True}})
        assert r["path"] == OVERLAY, f"{nome} caiu no caminho lento"
    for nome in TRANSFORMAM:
        r = classify_render_path({"videoLayout": nome,
                                  "captions": {"enabled": True}})
        assert r["path"] != OVERLAY, nome


def test_todo_quadro_cheio_dispensa_broll_automatico():
    """`QUADRO_CHEIO` é a lista de "não empurre insert por cima": o vídeo
    já ocupa a tela toda e o insert taparia a fala."""
    for nome in (*CAMADA, *TRANSFORMAM, "limpa"):
        assert nome in QUADRO_CHEIO, nome
    for nome in ("split", "split2"):
        assert nome not in QUADRO_CHEIO, nome


def test_a_camada_tem_a_forma_que_o_css_descreve():
    """Os números do `camada_do_layout` e do `LayoutScrim` são os mesmos."""
    deg = camada_do_layout("degrade", 100, 1000)[..., 3] / 255.0
    assert deg[0].max() < 0.01 and deg[510].max() < 0.02  # nada acima de 52%
    assert 0.72 < deg[999].max() < 0.76                   # 0,74 na base

    cin = camada_do_layout("cinema", 100, 1000)[..., 3] / 255.0
    assert cin[0].min() > 0.99 and cin[99].min() > 0.99   # tarja de 10%
    assert cin[500].max() < 0.01 and cin[999].min() > 0.99

    vin = camada_do_layout("vinheta", 100, 1000)[..., 3] / 255.0
    assert vin[500, 50] < 0.01                            # centro limpo
    assert 0.58 < vin[0, 0] < 0.66                        # canto 0,62
