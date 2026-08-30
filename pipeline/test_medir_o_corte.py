# -*- coding: utf-8 -*-
"""O corte diz onde gasta o tempo dele.

O corte é 30,8% do tempo de render — 12,6 horas somadas em 172 jobs,
mediana 263s — e era uma caixa preta: a fase `CUT` dava o total e mais
nada. Não dá para melhorar o que não se vê; foi medindo que saíram os nove
defeitos de 30/08.

As etapas estão no cabeçalho do próprio helper: extrair cada trecho (com
cor e fades), juntar sem reencodar, e a passada de filtro quando há
overlay. Agora cada uma se anuncia.
"""
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

HELPER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")


def test_o_helper_anuncia_as_etapas():
    assert "def _marco_corte(" in HELPER
    assert 'print(f"TIMING_CORTE {nome}={dt:.3f}", flush=True)' in HELPER
    assert '_marco_corte(f"extrair_{len(ranges)}_trechos", _t0)' in HELPER
    assert '_marco_corte("juntar", _t0)' in HELPER


def test_a_extracao_e_medida_mesmo_quando_falha():
    """Um corte que demora E quebra é o caso que mais interessa entender."""
    i = HELPER.index('_marco_corte(f"extrair_')
    assert "finally:" in HELPER[i - 400:i]


def test_as_etapas_viram_fases_do_timing():
    from pipeline.run_fast import _TIMING, _recolher_marcos_do_corte

    _TIMING.clear()
    proc = types.SimpleNamespace(
        stdout="concat ok\nTIMING_CORTE extrair_7_trechos=41.250\n"
               "TIMING_CORTE juntar=3.100\n",
        stderr="")
    _recolher_marcos_do_corte(proc)
    assert _TIMING["CUT_extrair_7_trechos"] == 41.25
    assert _TIMING["CUT_juntar"] == 3.1


def test_helper_mudo_nao_quebra_nada():
    """Versão antiga do helper, ou saída perdida: o total continua sendo
    gravado como antes."""
    from pipeline.run_fast import _TIMING, _recolher_marcos_do_corte

    _TIMING.clear()
    _recolher_marcos_do_corte(types.SimpleNamespace(stdout="", stderr=""))
    assert not _TIMING
    _recolher_marcos_do_corte(types.SimpleNamespace())
    assert not _TIMING


def test_as_subfases_nao_contam_duas_vezes():
    """Elas estão DENTRO do `CUT`: somá-las no total faria as porcentagens
    mentirem."""
    import json

    from pipeline.run_fast import _TIMING, write_timing

    _TIMING.clear()
    _TIMING.update({"CUT": 63.0, "ANALYZE": 20.0,
                    "CUT_extrair_7_trechos": 41.25, "CUT_juntar": 3.1})
    d = Path(tempfile.mkdtemp())
    write_timing(d)
    t = json.loads((d / "timing.json").read_text(encoding="utf-8"))
    assert t["totalSec"] == 83.0, t["totalSec"]
    assert t["stages"]["CUT"]["pct"] == 75.9
    assert "CUT_extrair_7_trechos" in t["stages"]
