# -*- coding: utf-8 -*-
"""O SOM dos dois motores, comparado do mesmo jeito que o desenho.

Varri o desenho todo e depois o som. O som tem a mesma armadilha: o motor
próprio agenda os efeitos por conta própria e uma diferença ali é tão muda
quanto uma sombra faltando.

Achado em 30/08: o whoosh da manchete **não é o mesmo em todo estilo**. No
`Main.tsx`, quase todos têm `volume={0.1}`, o `carimbo` tem `{0.12}` e a
`pilula` **não tem `<Sfx>` nenhum**. O motor próprio tocava 0,1 em todos —
um som a mais na pilula, e um som fraco demais no carimbo.

O que bate e não precisa de conserto (conferido no mesmo dia): clique da
legenda (0,55), clique do empilhado (metade, teto 0,28), risco (0,28),
pop da bolha (0,12), whoosh do cartão de imagem (0,09, o padrão do `Sfx`)
e o clique do corte marcado (0,9).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

TSX = (REPO / "assets" / "shortform" / "src"
       / "Main.tsx").read_text(encoding="utf-8")


def _whoosh_do_template(estilo: str):
    """O volume que o template usa naquele ramo, ou None se não tem Sfx."""
    if estilo == "outline":          # o `return` final, sem `if`
        i = TSX.index("const stroke = H.strokePx ?? 12;")
        fim = i + 400
    else:
        i = TSX.index(f"if (styleId === '{estilo}')")
        seguinte = TSX.find("if (styleId ===", i + 20)
        fim = seguinte if seguinte > 0 else i + 2500
    m = re.search(r'<Sfx src="whoosh\.mp3"(?: volume=\{([0-9.]+)\})?',
                  TSX[i:fim])
    if not m:
        return None
    return float(m.group(1)) if m.group(1) else 0.09   # padrão do `Sfx`


def test_o_whoosh_da_manchete_bate_estilo_a_estilo():
    from app.render_proprio import WHOOSH_HL, WHOOSH_VOL, Renderizador

    for estilo in Renderizador.HL_STYLES:
        esperado = _whoosh_do_template(estilo)
        nosso = WHOOSH_HL.get(estilo, WHOOSH_VOL)
        assert nosso == esperado, (
            f"{estilo}: template {esperado}, motor próprio {nosso}")


def test_a_pilula_nao_toca_nada():
    """Ela é o único estilo sem `<Sfx>` — e um som a mais é tão errado
    quanto um som faltando."""
    from app.render_proprio import WHOOSH_HL

    assert _whoosh_do_template("pilula") is None
    assert WHOOSH_HL.get("pilula", "faltando") is None


def test_os_volumes_da_legenda_batem():
    """Estes são os sons que tocam em TODO vídeo do usuário (ele usa o
    empilhado em 114 de 114)."""
    from app.render_proprio import CLICK_VOL, SCRATCH_VOL, STACK_CLICK_VOL

    st = (REPO / "assets" / "shortform" / "src"
          / "StackedCaptions.tsx").read_text(encoding="utf-8")
    assert f"?? {CLICK_VOL}" in st.split("const CLICK_VOL")[1][:60]
    assert f"?? {SCRATCH_VOL}" in st.split("const SCRATCH_VOL")[1][:60]
    assert "Math.min(0.28, CLICK_VOL * 0.5)" in st
    assert STACK_CLICK_VOL == min(0.28, CLICK_VOL * 0.5)
