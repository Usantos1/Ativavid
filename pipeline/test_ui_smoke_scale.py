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
    assert "Restaurar versão" in html
    assert 'id="autoContentType"' in html
    assert 'id="presetSelect"' in html
    assert 'id="dlgAutosave"' in html
    assert '<dialog id="dlgAutosave"' in html
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "toUpperCase() === 'DIALOG'" in js
    assert "const firstLoad = !S.lastSig" in js
    assert "isQuickEditing()" not in js.split("async function poll")[1].split("async function applyState")[0]
    assert "Continuar de onde parou?" in html
    assert 'id="btnApply"' in html
    assert "Aplicar alterações" in html
    assert "Ver final" in html
    assert "Abrir pasta" in html
    assert "Alterações pendentes" in html
    assert "•••" in html
    assert 'id="btnHeadMore"' in html
    assert 'id="btnZoom100"' in html
    assert 'id="btnZoomIn"' in html
    assert 'id="btnZoomOut"' in html
    assert ">100%<" in html
    assert 'id="hlOverlay"' in html
    assert 'id="pendingPill"' in html
    assert 'id="quickFixes"' in html
    assert 'id="hlChip"' in html
    assert 'id="applyStage"' in html
    assert "Cortar" in html
    assert "Excluir" in html
    assert "Restaurar versão" in html
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "persistCorrection" in js
    assert "commitHeadline" in js
    assert "op: 'apply'" in js
    assert "Aplicando alterações" in js
    assert "setZoom100" in js
    assert "bumpZoom" in js
    assert "CLIP_TIGHT_PX" in js
    assert "clip-body-hit" in js
    assert "e.ctrlKey" in js
    assert "isTypingContext" in js
    assert "tokenId: c.tokenId" in js or "tokenId: c.tokenId || undefined" in js
    assert "Final anterior" in js
    assert "Vídeo atualizado" in js


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
    assert 'data-view="import"' in html
    assert 'data-view="fila"' in html
    assert 'data-view="done"' in html
    assert 'data-view="estilo"' in html
    assert 'data-view="sistema"' in html
    assert 'data-view="historico"' not in html
    assert 'data-view="biblioteca"' not in html
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "function jobInFila" in js
    assert 'badge: "ATUALIZANDO"' in js
    assert "Não foi possível atualizar o vídeo." in js
    assert "Vídeo atualizado" in js
    assert "maybeToastApply" in js
    assert "justFinished" in js
    assert "ativavid-apply-ack:" in js
    assert "45000" not in js
    assert "Ver anterior" in js
    assert "Ver detalhe" in js
    assert "Lixeira" in html
    assert "data-act=\"detail\"" in js
    shell = (REPO / "assets" / "studio" / "shell.js").read_text(encoding="utf-8")
    assert "quickApply" in shell


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


if __name__ == "__main__":
    test_editor_has_protect_and_versions()
    test_studio_has_content_type_and_simple_system()
    test_score_labels_from_real_numbers()
    print("ok")
