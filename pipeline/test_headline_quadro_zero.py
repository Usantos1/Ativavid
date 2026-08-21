# -*- coding: utf-8 -*-
"""A headline tem de existir no quadro 0 — nos DEZ estilos, não só no `realce`.

O usuário viu o preview parado em 0:00.00 e a manchete não estava lá: ela
nascia com opacidade 0 e só ficava legível 8 quadros (0,27 s) depois, ainda
subindo 24 px. Como ela é a primeira coisa que o espectador lê, era exatamente
o momento em que ela faltava.

O conserto mexeu no `_opacidade` (que é COMPARTILHADO por headline, legenda,
cartão final, contador e inserts) e espalhou `enter_hl` por onze chamadas do
`_montar_headline`. Já introduzi duas regressões nesta noite exatamente assim —
mexendo num ponto comum achando que o template era uniforme. Por isso aqui cada
estilo é conferido sozinho.

`pop` e `deslizar` são entradas ESCOLHIDAS pelo usuário e continuam entrando do
zero: para elas o quadro 0 vazio é o certo, e isso também é testado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Os que usam a entrada COMPARTILHADA — os que o conserto tinha de acertar.
ESTILOS = ["outline", "realce", "card", "misto", "manchete",
           "pergunta", "sombra", "sublinhado", "pilula"]
# `carimbo` tem entrada PROPRIA no template (Main.tsx:884): um "slam" que
# comeca transparente e grande (`opacity: Math.min(slam, exit)`, slam de 0 a 7
# quadros) e aterrissa. Comecar vazio e o desenho dele, nao um defeito — e o
# motor ja faz igual. Medido contra a v2.38: carimbo saiu IDENTICO nos quadros
# 0, 12 e 60.


def _projeto(tmp_path: Path, estilo: str, animation: str | None = None) -> tuple[Path, dict]:
    pub = tmp_path / estilo / "remotion" / "public"
    pub.mkdir(parents=True)
    hook = {
        "enabled": True, "endSec": 4.0, "style": estilo,
        "text": "Eu precisava trocar a tela desse celular",
        "accent": "#ff5200",
    }
    if animation:
        hook["animation"] = animation
    if estilo == "pergunta":
        hook["answerLines"] = ["Trocamos na hora"]
        hook["answerAtSec"] = 2.5
    ed = {
        "durationSec": 6, "fps": 30, "width": 1080, "height": 1920,
        "hook": hook,
        "captions": {"enabled": False},
    }
    (pub / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    (pub / "captions.json").write_text("[]", encoding="utf-8")
    return pub, ed


def _tinta(pub: Path, ed: dict, quadro: int, total: int = 180) -> float:
    from app.render_proprio import Renderizador

    r = Renderizador(pub, ed, frames=total, fps=30.0)
    buf = np.zeros((r.h, r.w, 4), dtype=np.uint8)
    sujo, primeira = [0, 0, 0, 0], True
    for leg in r.camadas:
        if leg.inicio_f <= quadro <= leg.fim_f:
            if leg.dim:
                r._aplicar_dim(buf, sujo, leg.dim, quadro - leg.inicio_f, leg.dim_fade)
                primeira = False
            r.desenhar(leg, quadro - leg.inicio_f, buf, sujo, mesclar=not primeira)
            primeira = False
    return float(buf[..., 3].sum())


@pytest.mark.parametrize("estilo", ESTILOS)
def test_a_headline_desenha_no_quadro_zero(tmp_path, estilo):
    pub, ed = _projeto(tmp_path, estilo)
    assert _tinta(pub, ed, 0) > 1000, f"{estilo}: nada desenhado no quadro 0"


@pytest.mark.parametrize("estilo", ESTILOS)
def test_o_quadro_zero_ja_esta_no_tamanho_final(tmp_path, estilo):
    """Sem entrada significa PRONTA, não "quase pronta".

    Se o quadro 0 saísse mais leve que o quadro 12, a manchete ainda estaria
    chegando — só que mais rápido. Uma folga de 2% cobre o antialias.
    """
    pub, ed = _projeto(tmp_path, estilo)
    zero, assentado = _tinta(pub, ed, 0), _tinta(pub, ed, 12)
    assert zero == pytest.approx(assentado, rel=0.02), (
        f"{estilo}: quadro 0 tem {zero:.0f} de tinta contra {assentado:.0f} no 12"
    )


@pytest.mark.parametrize("animation", ["pop", "deslizar"])
def test_as_entradas_escolhidas_continuam_entrando(tmp_path, animation):
    """`pop` e `deslizar` são efeitos que o usuário escolhe: para eles o quadro
    0 vazio é o comportamento certo, e o conserto não pode tê-los achatado."""
    pub, ed = _projeto(tmp_path, "realce", animation=animation)
    zero, assentado = _tinta(pub, ed, 0), _tinta(pub, ed, 12)
    assert zero < assentado * 0.5, (
        f"{animation}: a entrada sumiu — quadro 0 já tem {zero:.0f} de {assentado:.0f}"
    )


def test_o_carimbo_mantem_o_slam_dele(tmp_path):
    """O `carimbo` não entra na regra: o template lhe dá uma entrada própria
    (Main.tsx:884), que começa transparente. Se um dia ele passar a desenhar no
    quadro 0, alguém achatou a entrada dele junto com as outras."""
    pub, ed = _projeto(tmp_path, "carimbo")
    zero, assentado = _tinta(pub, ed, 0), _tinta(pub, ed, 12)
    assert assentado > 1000, "o carimbo parou de desenhar"
    assert zero < assentado * 0.5, (
        f"o slam do carimbo foi achatado — quadro 0 com {zero:.0f} de {assentado:.0f}"
    )


def test_o_template_e_o_motor_concordam_em_quem_tem_entrada():
    """A regra vive nos DOIS lados. Se um mudar sozinho, o job cai no caminho
    lento com um desenho diferente e ninguém percebe."""
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert "anim === 'padrao'\n    ? 1" in tsx, "o template voltou a animar o padrao"
    assert 'enter_hl = 0 if anim == "padrao" else 8' in py, (
        "o motor proprio nao tem a mesma regra do template"
    )


def test_enter_zero_nao_vazou_para_a_legenda(tmp_path):
    """`_opacidade` é compartilhado. `enter <= 0` foi criado para a headline;
    nenhuma outra chamada do arquivo pode estar passando isso."""
    import re

    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    valores = re.findall(r"enter=(\d+)", py)
    assert valores, "nenhuma chamada com enter= literal — a busca quebrou"
    assert all(int(v) > 0 for v in valores), (
        f"alguma chamada literal usa enter<=0: {sorted(set(valores))}"
    )
