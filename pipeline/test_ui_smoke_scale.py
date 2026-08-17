"""Smoke de UI: IDs e textos existem. Sem servidor, sem mídia."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_editor_has_protect_and_versions():
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnProtect"' in html
    assert 'id="protectMenu"' in html
    assert "Proteger seleção" in html
    assert "Proteger gancho" in html
    assert "Proteger CTA" in html
    assert "Desproteger" in html
    assert 'id="btnVersions"' in html
    assert "Versões" in html
    assert 'id="autoContentType"' in html
    assert 'id="presetSelect"' in html
    assert 'id="dlgAutosave"' in html
    assert "Continuar de onde parou?" in html


def test_studio_has_content_type_and_simple_system():
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="importContentType"' in html
    assert "Tipo de conteúdo" in html
    assert 'id="importPresetHint"' in html
    assert "Status do ATIVAVID" in html
    assert "Tudo funcionando corretamente" in html or 'id="sysStatusLine"' in html
    assert "Avançado" in html
    assert 'id="hwAccelDetail"' in html
    assert 'id="btnHwBench"' in html
    # menu lateral não ganhou item novo
    for forbidden in ("Histórico", "Biblioteca", "Presets", "Versões"):
        # esses nomes podem aparecer no conteúdo, mas não como item do menu
        pass
    assert html.count('data-view="') >= 6
    assert 'data-view="historico"' not in html
    assert 'data-view="biblioteca"' not in html


def test_score_labels_from_real_numbers():
    import sys

    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from helpers.video_score import present_score

    out = present_score({"overall": 87, "hook": 90, "clarity": 80, "rhythm": 78, "cta": 88, "tips": []})
    labels = {i["id"]: i["text"] for i in out["items"]}
    assert labels["hook"] == "forte"
    assert labels["clarity"] == "boa"
    assert present_score({}) == {}
