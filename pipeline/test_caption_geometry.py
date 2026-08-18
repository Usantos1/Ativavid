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


def test_brand_fonts_validated_against_catalog():
    from run_fast import _apply_brand_fonts

    ed = _base_ed()
    _apply_brand_fonts(ed, {"captionFont": "bebas", "headlineFont": "Archivo"})
    assert ed["captions"]["fontFamily"] == "bebas"
    assert ed["hook"]["fontFamily"] == "archivo"
    ed2 = _base_ed()
    _apply_brand_fonts(ed2, {"captionFont": "comic-sans", "headlineFont": ""})
    assert "fontFamily" not in ed2["captions"]
    assert "hook" not in ed2


def test_brand_emphasis_words_marks_line(tmp_path):
    """--emphasis da marca marca a linha (lineEmph) que a lista genérica não pega."""
    import json
    import subprocess
    import sys as _sys

    exe = _sys.executable
    cs = str(REPO / "helpers" / "caption_style.py")
    words = ["nossa", "loja", "tem", "pelicula", "blindada", "muito",
             "boa", "pra", "voce", "hoje", "mesmo", "viu"]
    caps = [{"text": w, "startMs": i * 450, "endMs": i * 450 + 380}
            for i, w in enumerate(words)]
    src = tmp_path / "captions.json"
    src.write_text(json.dumps(caps), encoding="utf-8")

    def run(extra):
        out = tmp_path / f"cues{len(extra)}.json"
        r = subprocess.run([exe, cs, "--captions", str(src), "-o", str(out), *extra],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-400:]
        return json.loads(out.read_text(encoding="utf-8"))

    def emph_texts(cues):
        """Texto das linhas marcadas como ênfase."""
        out = []
        for c in cues:
            for flag, line in zip(c.get("lineEmph") or [], c.get("lines") or []):
                if flag:
                    out.append(" ".join(t.get("text", "") for t in line))
        return out

    base = emph_texts(run([]))
    branded = emph_texts(run(["--emphasis", "pelicula, blindada"]))
    # a palavra da marca vira ênfase só quando declarada
    assert not any("pelicula" in t for t in base)
    assert any("pelicula" in t for t in branded)


def _broll_preset(edit, mode):
    return {"edit": edit, "brollMode": mode, "videoGoal": "reels"}


def test_broll_gate_respects_explicit_choice(monkeypatch, tmp_path):
    """Layout `limpa` com b-roll no padrão segue sem inserts; pedido explícito passa."""
    from run_fast import _attach_auto_broll

    # sem chaves de API a busca não roda, mas o GATE (inserts zerados ou não)
    # é o que importa aqui — o caminho de download é testado em outro lugar
    ed = {"inserts": [{"src": "x.jpg", "start": 1, "end": 3}]}
    out = _attach_auto_broll(dict(ed), tmp_path, _broll_preset("limpa", "quando_necessario"), "fala", 30)
    assert out["inserts"] == []  # padrão: quadro cheio limpo

    out = _attach_auto_broll(dict(ed), tmp_path, _broll_preset("limpa", "off"), "fala", 30)
    assert out["inserts"] == []  # desligado explicitamente

    # "sempre" em limpa NÃO zera mais os inserts — o pedido do usuário vale
    out = _attach_auto_broll(dict(ed), tmp_path, _broll_preset("limpa", "sempre"), "fala", 30)
    assert out["inserts"] != []
