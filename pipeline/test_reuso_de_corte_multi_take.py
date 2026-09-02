# -*- coding: utf-8 -*-
"""Reprocesso de MULTI-TAKE respeita o corte que o usuário aplicou.

Caso real (02/09): num filho do Multiplicador (3 takes) o usuário excluiu
um trecho, depois adicionou uma foto e refez — e o trecho excluído VOLTOU.
O reuso do EDL manual tinha a trava `len(sources) == 1` no chamador e
`src != source_key → None` no loader: todo reprocesso de multi-take
remontava o corte heurístico do zero.

Agora o reuso vale para multi-take, validando que as fontes do EDL são as
fontes DESTE job (reimport/estrutura diferente continua replanejando).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pipeline.run_fast import load_manual_edl_ranges  # noqa: E402

PRESET = {"rhythm": "dinamico", "intensity": "medio",
          "editingIntent": "complete", "contentType": "ad",
          "speechClean": "medio"}


def _projeto(tmp_path: Path, ranges: list[dict]) -> Path:
    edit = tmp_path / "edit"
    edit.mkdir(parents=True)
    # a marca de que houve edição manual antes
    (edit / "preview_edits.applied.json").write_text("{}", encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps({
        "ranges": ranges,
        "cutStyle": {k: PRESET[k] for k in PRESET},
    }), encoding="utf-8")
    return edit


RANGES_MULTI = [
    {"source": "g1_take", "start": 0.1, "end": 3.0, "beat": "HOOK"},
    {"source": "c2_take", "start": 0.0, "end": 5.0, "beat": "KEEP"},
    {"source": "a3_take", "start": 0.5, "end": 2.0, "beat": "CTA"},
]


def test_multi_take_reusa_o_corte_aplicado(tmp_path):
    edit = _projeto(tmp_path, RANGES_MULTI)
    out = load_manual_edl_ranges(
        edit, "g1_take", PRESET, fontes={"g1_take", "c2_take", "a3_take"})
    assert out is not None, "o corte manual do multi-take foi jogado fora"
    assert [r["source"] for r in out] == ["g1_take", "c2_take", "a3_take"]
    assert out[1]["end"] == 5.0


def test_fonte_que_o_job_nao_tem_replaneja(tmp_path):
    edit = _projeto(tmp_path, RANGES_MULTI)
    out = load_manual_edl_ranges(
        edit, "g1_take", PRESET, fontes={"g1_take", "c2_take"})   # sem a3
    assert out is None, "EDL com fonte estranha não pode ser reusado"


def test_sem_fontes_continua_estrito_como_antes(tmp_path):
    """Chamador antigo (sem `fontes`): só a fonte principal passa."""
    edit = _projeto(tmp_path, RANGES_MULTI)
    assert load_manual_edl_ranges(edit, "g1_take", PRESET) is None
    edit2 = _projeto(tmp_path / "b", [
        {"source": "unico", "start": 0.0, "end": 4.0, "beat": "HOOK"}])
    assert load_manual_edl_ranges(edit2, "unico", PRESET) is not None


def test_knob_mudado_segue_replanejando(tmp_path):
    edit = _projeto(tmp_path, RANGES_MULTI)
    preset2 = dict(PRESET, intensity="alto")
    out = load_manual_edl_ranges(
        edit, "g1_take", preset2, fontes={"g1_take", "c2_take", "a3_take"})
    assert out is None, "mudar knob de corte é pedido explícito de replanejar"


def test_chamador_nao_esta_mais_travado_em_fonte_unica():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "len(sources) == 1 and (manual :=" not in rf, (
        "a trava de fonte única voltou — multi-take perderia o corte manual")
    assert "fontes=set(sources_map.keys())" in rf
