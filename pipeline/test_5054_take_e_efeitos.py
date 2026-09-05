# -*- coding: utf-8 -*-
"""5.0.54: volume da voz e cor por TAKE selecionado; volume geral dos efeitos.

"Falta ... ajuste de cor manual no take selecionado, ajustar volume ... do
efeito sonoro, ajustar volume do áudio principal" (05/09, 05h).

- `gain_db` já existia no pipeline (render.py aplica `volume=+XdB` por
  segmento) mas o editor não o expunha. `grade` por trecho é novo: nome de
  look do grade.py ou filtro `eq=...` dos controles manuais; render.py aplica
  por cima do look global, inclusive na fonte preparada.
- `_norm_range` passa a ver os dois: mudar só o ganho ou só a cor conta como
  EDL diferente (senão o apply dizia "nada mudou").
- `captions.sfx.gain` multiplica todo efeito sonoro nos dois motores; vem do
  estilo (`sfxGain`, STYLE_KEYS).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

import pipeline.run_fast as rf  # noqa: E402
from app import quick_corrections as qc  # noqa: E402
from app.brand_presets import STYLE_KEYS  # noqa: E402

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
STACK = (REPO / "assets" / "shortform" / "src" / "StackedCaptions.tsx").read_text(encoding="utf-8")
PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")


# ------------------------------------------------------------ cor por take
def test_grade_do_trecho_aceita_look_e_filtro_seguro():
    assert rf._grade_do_trecho("vibrante") == "vibrante"
    assert rf._grade_do_trecho("teal_laranja") == "teal_laranja"
    cru = "eq=brightness=0.05:contrast=1.10:saturation=1.20"
    assert rf._grade_do_trecho(cru) == cru
    assert rf._grade_do_trecho("eq=contrast=1.1,curves=master='0/0 1/1'") != ""


def test_grade_do_trecho_recusa_o_que_derrubaria_o_ffmpeg():
    for ruim in ("nao_existe", "rm -rf /", "eq=contrast=1;drop", "auto", "", None, "x" * 300):
        assert rf._grade_do_trecho(ruim) == "", repr(ruim)


def test_leitor_do_editor_guarda_grade_e_gain(tmp_path):
    (tmp_path / "preview_edits.json").write_text(json.dumps({"edl": {"ranges": [
        {"source": "S", "start": 0, "end": 2, "beat": "HOOK", "gain_db": 3, "grade": "vibrante"},
        {"source": "S", "start": 3, "end": 5, "beat": "B1", "grade": "lixo qualquer"},
    ]}}), encoding="utf-8")
    fn = getattr(rf, "load_preview_edl_ranges", None) or getattr(rf, "_preview_edl_ranges", None) \
        or getattr(rf, "load_editor_ranges", None)
    if fn is None:
        # o leitor e o bloco que consome preview_edits.json: cobre pelo texto
        src = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
        assert src.count('_g = _grade_do_trecho(r.get("grade"))') == 2, "os dois leitores de EDL guardam a cor"
        return
    out = fn(tmp_path, "S")
    assert out[0]["gain_db"] == 3.0 and out[0]["grade"] == "vibrante"
    assert "grade" not in out[1]


def test_norm_range_ve_ganho_e_cor():
    base = {"source": "S", "start": 0, "end": 2, "beat": "HOOK"}
    assert qc._norm_range(base) == qc._norm_range(dict(base, gain_db=0))
    assert qc._norm_range(base) != qc._norm_range(dict(base, gain_db=3))
    assert qc._norm_range(base) != qc._norm_range(dict(base, grade="vibrante"))
    assert "grade" in qc._HERDAVEIS and "gain_db" in qc._HERDAVEIS


def test_render_aplica_a_cor_do_take_nos_dois_lacos():
    assert RENDER.count('extra_vf = resolve_grade_filter(str(r["grade"]))') == 2, "laco normal E laco do J-cut"
    assert "extra_vf: str = \"\"" in RENDER
    i = RENDER.index("if extra_vf and streams != \"a\":")
    assert 'vf_parts.append("format=yuv420p")' in RENDER[i:i + 200], "8 bits antes de qualquer eq/colorbalance"
    assert RENDER.count("extra_vf=extra_vf") == 2


# ------------------------------------------------------------- efeitos
def test_volume_dos_efeitos_vem_do_estilo():
    assert "sfxGain" in STYLE_KEYS
    src = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'ed["captions"]["sfx"] = {**(ed["captions"].get("sfx") or {}),' in src
    assert 'id="autoSfxGain"' in HTML
    assert "['autoSfxGain', 'sfxGain', '1']" in PJS and "['autoSfxGain', 'sfxGain']" in PJS
    assert PJS.count("sfxGain: S.style.sfxGain || '1'") == 3, "os tres payloads de estilo levam o campo"


def test_os_dois_motores_multiplicam_todo_efeito():
    assert "const SFX_GAIN = Math.max(0, Math.min(2, Number(D.captions?.sfx?.gain ?? 1) || 0));" in MAIN
    assert "volume={volume * SFX_GAIN}" in MAIN
    assert "* SFX_GAIN" in STACK and "SFX.gain ?? 1" in STACK
    assert 'self.sfx_gain = max(0.0, min(2.0, _pos(sfx, "gain", 1.0)))' in PROPRIO
    assert "vol * ganho" in PROPRIO


def test_motor_proprio_le_o_ganho(tmp_path):
    from app.render_proprio import _pos

    assert _pos({"gain": 0}, "gain", 1.0) == 0.0, "0 e mudo, nao 'padrao'"
    assert _pos({}, "gain", 1.0) == 1.0


# --------------------------------------------------------------- editor
def test_editor_leva_ganho_e_cor_no_trecho():
    assert "function camposDoTake(r)" in PJS
    assert PJS.count("...camposDoTake(r)") >= 5, "payload, salvar, split (2) e apagar-trecho (2)"
    i = PJS.index("function edlDirty()")
    assert "r.gain_db" in PJS[i:i + 400] and "r.grade" in PJS[i:i + 400], "mudar so ganho/cor tem de sujar o EDL"
    j = PJS.index("S.draft = ranges.map((r, srcIdx) => ({")
    assert "gain_db: +(r.gain_db || 0), grade: r.grade || ''" in PJS[j:j + 400]


def test_painel_do_take_tem_voz_e_cor():
    assert "function renderPainelDoTake(lane, r)" in PJS
    i = PJS.index("function renderPainelDoTake(lane, r)")
    corpo = PJS[i:PJS.index("\nfunction renderFxPanel()", i)]
    assert "GANHOS_DO_TAKE" in corpo and "LOOKS_DO_TAKE" in corpo
    looks = PJS[PJS.index("const LOOKS_DO_TAKE"):PJS.index("function gradeManualDoTake")]
    assert "eq=brightness=" in corpo and "saturation=" in corpo, "controles manuais geram o filtro"
    assert "persistEdl()" in corpo
    assert "renderPainelDoTake(lane, S.draft[S.selected])" in PJS, "o painel fx mostra o take quando nao ha bloco"
    for v in ("vibrante", "preto_branco", "teal_laranja", "pastel_suave", "manual"):
        assert f"'{v}'" in looks, v
