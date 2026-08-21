# -*- coding: utf-8 -*-
"""Quem veste a fonte da marca e quem mantém a tipografia do template.

A regra está escrita em três lugares do projeto:

  Main.tsx:42   "CAP_FF veste o karaokê; HL_FF veste todas as headlines.
                 Elementos gráficos (contador, end card) e o stacked mantêm a
                 tipografia assinada do template."
  app.js:3614   `(style !== 'stacked' && FONT_CSS[captionFont]) || V.family`
  os imports    SimpleCaptions / ScatterCaptions / ImpactCaptions importam
                `capFamily`; ListCounter importa `hookFamily`; StackedCaptions
                não importa nenhum dos dois.

O motor próprio discordava dos três: vestia a fonte das legendas em TUDO —
inclusive no stacked (cuja família É o estilo: Poppins itálico 900 mais
Playfair laranja), no end card e no contador — e ao mesmo tempo IGNORAVA a
marca nos cinco estilos estáticos, que são justamente os que o template
veste.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.render_proprio import FONTES, Renderizador  # noqa: E402

# Duas fontes de marca que NENHUM estilo usa por conta própria: senão o
# teste passa dos dois lados. Inter, por exemplo, É a fonte da variante
# `classica` — com ela o teste dos estáticos não distinguia nada.
MARCA_CAP = "Montserrat[wght].ttf"
MARCA_HOOK = "ArchivoBlack-Regular.ttf"


def _public(tmp_path: Path, cues=None) -> Path:
    pub = tmp_path / "public"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "caption-cues.json").write_text(json.dumps(cues or []), encoding="utf-8")
    # impacto e scatter leem a transcricao, nao os cues
    (pub / "captions.json").write_text(json.dumps(
        [{"text": "Ola mundo inteiro", "startMs": 0, "endMs": 1200},
         {"text": "e outra frase aqui", "startMs": 1200, "endMs": 2400}]),
        encoding="utf-8")
    return pub


def _r(tmp_path: Path, estilo: str, *, cap=True, hook=True, cues=None,
       elements=None, hook_on=True, endcard_on=True,
       marcadores=None) -> Renderizador:
    """`hook_on`/`endcard_on` ISOLAM a camada em teste.

    `_familias` vê as fontes de TODO o render. Com headline e end card
    ligados, a fonte da marca aparecia na lista mesmo quando a legenda não a
    usava — e o teste dos estáticos passava dos dois lados, sem medir nada.
    """
    ed = {
        "width": 1080, "height": 1920, "fps": 30,
        "captions": {"style": estilo, **({"fontFamily": "montserrat"} if cap else {})},
        "hook": {"enabled": hook_on, "style": "outline", "lines": ["ola", "mundo"],
                 "endSec": 2.0, **({"fontFamily": "archivo"} if hook else {})},
        "endCard": ({"enabled": True, "lines": ["Segue @x", "direct"],
                     "lastSec": 1.0, "dim": 0.82} if endcard_on
                    else {"enabled": False}),
        "elements": elements or {},
        "listMarkers": marcadores or [],
    }
    return Renderizador(_public(tmp_path, cues), ed, frames=120, fps=30.0)


def _so_legendas(tmp_path: Path, estilo: str, cues=None) -> set[str]:
    r = _r(tmp_path, estilo, cues=cues, hook_on=False, endcard_on=False)
    return {Path(k[0]).name for k in r._fontes}


def _familias(r: Renderizador) -> set[str]:
    """Arquivos de fonte que este render carregou até agora."""
    return {Path(k[0]).name for k in r._fontes}


def test_catalogo_tem_as_duas_fontes_do_teste():
    for nome in (MARCA_CAP, MARCA_HOOK):
        assert (FONTES / nome).exists(), nome


def test_stacked_mantem_a_tipografia_do_template(tmp_path):
    """A família É o estilo aqui — trocar as quatro por uma só o destrói."""
    cues = [{"i": 0, "preset": "STACK_MIXED", "startMs": 0, "endMs": 900,
             "styleOffset": 0, "lines": [[{"text": "Olá", "fromMs": 0, "toMs": 400}]]}]
    assert MARCA_CAP not in _so_legendas(tmp_path, "stacked", cues)


def test_solo_big_e_recorte_tambem(tmp_path):
    """Os dois são presets do MESMO StackedCaptions.tsx."""
    for preset in ("SOLO_BIG", "SOLO_OUTLINE"):
        cues = [{"i": 0, "preset": preset, "startMs": 0, "endMs": 900,
                 "lines": [[{"text": "Olá", "fromMs": 0, "toMs": 400}]]}]
        assert MARCA_CAP not in _so_legendas(tmp_path, "stacked", cues), preset


def test_end_card_mantem_a_tipografia_do_template(tmp_path):
    r = _r(tmp_path, "stacked", hook_on=False)
    assert MARCA_CAP not in _familias(r)


def test_estilos_estaticos_vestem_a_marca(tmp_path):
    """`capFamily(base.family)` em SimpleCaptions.tsx:217 — o motor usava o
    arquivo fixo da variante e ignorava a marca."""
    cues = [{"i": 0, "preset": "STACK_MIXED", "startMs": 0, "endMs": 900,
             "lines": [[{"text": "Olá mundo", "fromMs": 0, "toMs": 400}]]}]
    for estilo in ("simples", "serifada", "classica", "bloco", "recorte"):
        assert MARCA_CAP in _so_legendas(tmp_path, estilo, cues), estilo


def test_impacto_e_scatter_vestem_a_marca(tmp_path):
    cues = [{"i": 0, "preset": "STACK_MIXED", "startMs": 0, "endMs": 900,
             "lines": [[{"text": "Olá mundo", "fromMs": 0, "toMs": 400}]]}]
    for estilo in ("impacto", "scatter"):
        assert MARCA_CAP in _so_legendas(tmp_path, estilo, cues), estilo


def test_contador_veste_a_fonte_da_HEADLINE(tmp_path):
    """ListCounter.tsx importa `hookFamily`, não `capFamily`. O motor usava a
    das legendas — com as duas marcas configuradas, saía a fonte errada."""
    r = _r(tmp_path, "stacked", elements={"listCounter": True},
           marcadores=[{"n": 1, "atSec": 0.5}, {"n": 2, "atSec": 2.0}],
           hook_on=False, endcard_on=False)
    fam = _familias(r)
    assert MARCA_HOOK in fam
    assert MARCA_CAP not in fam


def test_headline_sem_marca_propria_nao_pega_a_das_legendas(tmp_path):
    """`hookFamily(fontFamily)` cai no padrão do template, nunca em CAP_FF."""
    r = _r(tmp_path, "stacked", cap=True, hook=False, endcard_on=False)
    assert MARCA_CAP not in _familias(r)


def test_headline_veste_a_propria_marca(tmp_path):
    r = _r(tmp_path, "stacked", cap=False, hook=True, endcard_on=False)
    assert MARCA_HOOK in _familias(r)
