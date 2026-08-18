"""Default de estilo do app — uma constante, não seis cópias.

Cadeia de leitura do pacote: assets/brands/padrao.json, depois
assets/preview/default-style.json, por último APP_DEFAULT_STYLE.
O card final fica vazio de propósito: identidade de marca não se inventa.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

APP_DEFAULT_STYLE: dict[str, Any] = {
    "edit": "limpa",
    "headline": "realce",
    "captions": "stacked",
    "accent": "#e30004",
    "captionAccent": "#FFFFFF",
    "emphasisAccent": "#FF0000",
    "circleAccent": None,
    "elements": {
        "tracking": False,
        "zoomAuto": True,
        "zoomCuts": True,
        "flashCut": True,
        "musicAI": True,
        "endCard": True,
    },
    "fastMode": True,
    "oneClick": True,
    "rhythm": "calmo",
    "intensity": "medio",
    "speechClean": "leve",
    "videoGoal": "reels",
    "brollMode": "quando_necessario",
    "captionChunk": "frase_curta",
    "smartEmphasis": True,
    "endCardType": "seguir",
    "exportPreset": "reels",
    "colorGrade": "marca",
    "endCardCopy": {"line1": "", "line2": ""},
    "note": "",
    "brandId": "padrao",
    "brandName": "Padrão",
}

_SHIPPED_FILES = (
    REPO / "assets" / "brands" / "padrao.json",
    REPO / "assets" / "preview" / "default-style.json",
)


def load_shipped_style() -> dict[str, Any]:
    """Preset empacotado. Não lê o default-style.json do usuário."""
    for path in _SHIPPED_FILES:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict) or not data:
            continue
        out = dict(APP_DEFAULT_STYLE)
        out.update(data)
        if isinstance(data.get("elements"), dict):
            elems = dict(APP_DEFAULT_STYLE.get("elements") or {})
            elems.update(data["elements"])
            out["elements"] = elems
        return out
    return dict(APP_DEFAULT_STYLE)
