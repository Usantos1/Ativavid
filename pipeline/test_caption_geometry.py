"""captionPosition/captionSize viram os knobs certos no edit-data."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))
from run_fast import _apply_caption_geometry  # noqa: E402


def _base_ed() -> dict:
    return {"captions": {"enabled": True, "style": "karaoke", "fontSize": 76,
                         "maxWords": 3, "safeWidth": 720, "paddingBottom": 420,
                         "windows": []}}


def test_default_baixo_medio_keeps_style_defaults():
    ed = _base_ed()
    _apply_caption_geometry(ed, {})
    cap = ed["captions"]
    assert cap["fontSize"] == 76
    assert cap["paddingBottom"] == 420
    assert cap["position"] == "baixo"
    assert "fontScale" not in cap
    assert "stackedOffsetY" not in cap


def test_centro_moves_every_style_knob():
    ed = _base_ed()
    _apply_caption_geometry(ed, {"captionPosition": "centro"})
    cap = ed["captions"]
    assert cap["paddingBottom"] == 900          # karaoke/estáticos/impacto
    assert cap["stackedOffsetY"] == -0.02       # stacked
    assert cap["scatterOffsetY"] == 0.5         # scatter
    assert cap["position"] == "centro"


def test_grande_scales_every_style_knob():
    ed = _base_ed()
    _apply_caption_geometry(ed, {"captionSize": "g"})
    cap = ed["captions"]
    assert cap["fontSize"] == 90                # 76 * 1.18 arredondado
    assert cap["fontScale"] == 1.18             # stacked
    assert cap["scatterFontSize"] == 85         # 72 * 1.18 arredondado
    assert cap["sizeScale"] == 1.18             # estáticos + impacto


def test_valores_invalidos_caem_no_padrao():
    ed = _base_ed()
    _apply_caption_geometry(ed, {"captionPosition": "diagonal", "captionSize": "xg"})
    cap = ed["captions"]
    assert cap["fontSize"] == 76
    assert cap["paddingBottom"] == 420
