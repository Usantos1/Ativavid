# -*- coding: utf-8 -*-
"""Legenda DESLIGADA não pode ser desenhada.

Achado em 30/08 medindo o card final: o quadro do motor próprio trazia uma
bolha de legenda que o template não desenhava — e eu tinha desligado a
legenda no teste.

A causa: `_montar_tudo` checava `hook.enabled` (manchete) e `ec.enabled`
(card final), mas **nada** para a legenda. O template tem
`{D.captions.enabled ? ... : null}`.

Ponta a ponta: com o estilo "Nenhuma" o pipeline grava `enabled: false` e
`style: "karaoke"`, o portão manda para o motor rápido — que desenha ~79%
dos vídeos — e ele montava 6 camadas de legenda num vídeo em que o usuário
tinha pedido NENHUMA.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.render_proprio import Renderizador     # noqa: E402
from pipeline.run_fast import build_edit_data   # noqa: E402


def _projeto(tmp: Path) -> Path:
    pub = tmp / "remotion" / "public"
    pub.mkdir(parents=True)
    palavras = [{"text": f"p{i}", "startMs": i * 400, "endMs": i * 400 + 380}
                for i in range(12)]
    (pub / "captions.json").write_text(json.dumps(palavras), encoding="utf-8")
    (pub / "caption-cues.json").write_text("[]", encoding="utf-8")
    (tmp / "edl.json").write_text(
        json.dumps({"ranges": [{"start": 0.0, "end": 12.0}]}), encoding="utf-8")
    return pub


def _preset(captions: str) -> dict:
    return {"edit": "reels", "captions": captions, "headline": "manchete",
            "accent": "#e30004", "rhythm": "dinamico", "intensity": "medio",
            "elements": {}}


def _camadas(pub: Path, ed: dict) -> int:
    r = Renderizador(pub, ed, frames=200, fps=30.0, width=1080, height=1920)
    return len(r.camadas)


def test_nenhuma_nao_desenha_legenda(tmp_path):
    pub = _projeto(tmp_path)
    ed = build_edit_data(tmp_path / "cut.mp4", _preset("nenhuma"),
                         ["a", "b"], 12.0, 30.0)
    assert (ed["captions"] or {}).get("enabled") is False
    com = _camadas(pub, ed)
    ligada = build_edit_data(tmp_path / "cut.mp4", _preset("karaoke"),
                             ["a", "b"], 12.0, 30.0)
    assert _camadas(pub, ligada) > com, (
        "desligar a legenda tem de tirar camadas do desenho")
    # Sobram DUAS, e vale nomeá-las: a manchete (que tem o `enabled` dela) e
    # o CARD FINAL, que o `build_edit_data` liga por padrão. As duas eram
    # levadas junto pelo `return` da 3.87 — o card final some do vídeo é o
    # que mais dói ali.
    assert com == 2, com
    camadas = Renderizador(pub, ed, frames=200, fps=30.0,
                           width=1080, height=1920).camadas
    assert any(c.dim for c in camadas), "o card final tem de sobreviver"


def test_o_estilo_ligado_continua_desenhando(tmp_path):
    pub = _projeto(tmp_path)
    for estilo in ("karaoke", "stacked", "metal"):
        ed = build_edit_data(tmp_path / "cut.mp4", _preset(estilo),
                             ["a", "b"], 12.0, 30.0)
        assert (ed["captions"] or {}).get("enabled") is True
        assert _camadas(pub, ed) >= 1, estilo


def test_edit_data_antigo_sem_o_campo_continua_desenhando(tmp_path):
    """`is not False`, e não `if enabled`: um projeto antigo pode não ter o
    campo, e ali o certo é continuar desenhando."""
    pub = _projeto(tmp_path)
    ed = build_edit_data(tmp_path / "cut.mp4", _preset("karaoke"),
                         ["a", "b"], 12.0, 30.0)
    ed["captions"].pop("enabled", None)
    assert _camadas(pub, ed) > 1


def test_desligar_a_legenda_nao_leva_o_resto_junto(tmp_path):
    """A primeira versão desta guarda (3.87) era um `return` — e depois dela
    o montador ainda faz o contador de lista, os inserts, o card final e o
    som dos cortes. Um projeto com legenda "Nenhuma" perdia o b-roll.

    Achado na medição do contador, que veio com ZERO camadas.
    """
    pub = _projeto(tmp_path)
    base = {"hook": {"enabled": False}, "endCard": {"enabled": False},
            "transitions": [], "elements": {},
            "listMarkers": [{"n": 1, "atSec": 1.0}, {"n": 2, "atSec": 3.0}]}
    desligada = dict(base, captions={"enabled": False, "style": "karaoke",
                                     "fontSize": 76, "maxWords": 3,
                                     "safeWidth": 720, "paddingBottom": 420})
    assert _camadas(pub, desligada) == 2, (
        "o contador de lista tem de sobreviver à legenda desligada")


def test_a_guarda_nao_e_um_return():
    """O código depois dela é que desenha contador, inserts e card final."""
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = py.index('if caps_cfg.get("enabled") is False:')
    bloco = py[i:i + 200]
    assert "return" not in bloco, "voltou o return que matava o resto"
    assert "self.cues = []" in bloco
    # e o despachante de estilo fica atrás da guarda
    assert "legenda_ligada = caps_cfg.get(\"enabled\") is not False" in py
