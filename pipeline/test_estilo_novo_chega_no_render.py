# -*- coding: utf-8 -*-
"""O elo preset -> edit-data -> portao, com os estilos novos.

O desenho ja foi conferido quadro a quadro contra o Remotion, e o portao do
motor rapido ja foi exercitado. O que faltava era o pedaco do meio: o
`build_edit_data` pega o preset que a tela salvou e escreve o `edit-data`
que o render le. Se a cor ou o estilo se perdessem AQUI, os dois testes de
cima continuariam verdes e o video sairia errado — foi assim que o
`newInserts` ficou meses sendo salvo e nunca lido.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import caption_styles                      # noqa: E402
from app.render_proprio import motivo_nao_suportado  # noqa: E402
from pipeline.run_fast import build_edit_data        # noqa: E402


def _public(tmp_path: Path) -> Path:
    """Um projeto mínimo: o `build_edit_data` lê o `edl.json` ao lado do
    corte para contar os segmentos (é ele que decide a câmera)."""
    import json
    pub = tmp_path / "remotion" / "public"
    pub.mkdir(parents=True)
    (pub / "captions.json").write_text("[]", encoding="utf-8")
    (pub / "caption-cues.json").write_text("[]", encoding="utf-8")
    (tmp_path / "edl.json").write_text(
        json.dumps({"ranges": [{"start": 0.0, "end": 12.0}]}), encoding="utf-8")
    return pub


def _preset(estilo: str) -> dict:
    return {
        "edit": "reels", "captions": estilo, "headline": "manchete",
        "accent": "#e30004", "captionAccent": "#ffffff",
        "emphasisAccent": "#ffd166", "rhythm": "dinamico",
        "intensity": "medio", "contentType": "informational",
        "elements": {},
    }


def test_estilo_e_cor_chegam_no_edit_data(tmp_path):
    pub = _public(tmp_path)
    cut = tmp_path / "cut.mp4"
    for estilo in ("metal", "vidro", "traco", "moldura", "eco"):
        ed = build_edit_data(cut, _preset(estilo), ["Linha 1", "Linha 2"],
                             12.0, 30.0)
        caps = ed.get("captions") or {}
        assert caps.get("style") == estilo, f"{estilo}: {caps.get('style')}"
        # a cor da legenda tem de atravessar: o seletor da tela guarda a cor
        # no preset, e sem esta passagem o render nunca a receberia
        assert caps.get("accent") == "#ffffff", estilo


def test_o_que_sai_do_preset_passa_no_portao(tmp_path):
    """Fecha o circuito: o `edit-data` que o pipeline escreve de verdade é
    aceito pelo motor rápido, sem cair no Chrome calado."""
    pub = _public(tmp_path)
    cut = tmp_path / "cut.mp4"
    for estilo in sorted(caption_styles.TODOS):
        ed = build_edit_data(cut, _preset(estilo), ["Linha 1", "Linha 2"],
                             12.0, 30.0)
        motivo = motivo_nao_suportado(ed, pub)
        assert motivo is None, f"{estilo} cairia no caminho lento: {motivo}"


def test_a_enfase_nao_rouba_a_cor_da_legenda(tmp_path):
    """Cada estilo consome UMA das duas cores. Um estilo em ambas as listas
    receberia as duas e a tela ficaria sem saber qual está mostrando."""
    assert not (caption_styles.USAM_COR_DA_LEGENDA
                & caption_styles.USAM_COR_DA_ENFASE)
    pub = _public(tmp_path)
    cut = tmp_path / "cut.mp4"
    for estilo in ("metal", "stacked"):
        ed = build_edit_data(cut, _preset(estilo), ["a", "b"], 12.0, 30.0)
        caps = ed.get("captions") or {}
        if estilo in caption_styles.USAM_COR_DA_LEGENDA:
            assert caps.get("accent") == "#ffffff"
            assert "emphasisAccent" not in caps
        else:
            assert caps.get("emphasisAccent") == "#ffd166"
            assert "accent" not in caps
