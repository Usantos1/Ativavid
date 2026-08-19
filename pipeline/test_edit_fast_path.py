"""Edição do dia a dia não pode custar um reprocessamento inteiro.

Problema real (19/08/2026): ajustar legenda/headline/corte de um vídeo já
pronto reenfileirava o pipeline COMPLETO (re-análise + re-corte + render),
~1h por vídeo, enquanto o Aplicar rápido reaproveita o cut.mp4 pronto.
Junto disso, o perfil contava THREADS como se fossem núcleos e abria 4
pipelines pesados num CPU de 4 núcleos reais.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_plan import plan_apply_changes  # noqa: E402
from app.performance import profile_settings  # noqa: E402

# i5-10300H do usuário: 8 threads, 4 núcleos reais
MAQUINA = {"cores": 8, "physicalCores": 4, "ramGb": 23.8,
           "accel": {"preferredEncoder": "h264_nvenc"}}


def _proj(**dirty):
    base = {"headline": False, "captions": False, "edl": False, "style": False}
    base.update(dirty)
    return {"dirty": base}


def test_legenda_reaproveita_o_corte_pronto():
    plan = plan_apply_changes(_proj(captions=True))
    assert plan["rebuildCut"] is False, "refez o corte só para trocar legenda"
    assert plan["renderVisual"] is True


def test_headline_reaproveita_o_corte_pronto():
    plan = plan_apply_changes(_proj(headline=True))
    assert plan["rebuildCut"] is False
    assert plan["renderVisual"] is True


def test_corte_manual_refaz_so_o_corte_e_remapeia_legenda():
    plan = plan_apply_changes(_proj(edl=True, captions=True))
    assert plan["rebuildCut"] is True
    assert plan["remapCaptions"] is True, "legenda ficaria fora de sincronia"


def test_nada_sujo_nao_faz_nada():
    assert plan_apply_changes(_proj())["mode"] == "NOOP"


def test_paralelismo_conta_nucleo_real_nao_thread():
    for prof in ("balanced", "performance"):
        s = profile_settings(prof, MAQUINA)
        assert s["parallelJobs"] <= 2, (
            f"{prof}: {s['parallelJobs']} pipelines pesados em 4 núcleos reais"
        )


def test_maquina_grande_ainda_usa_paralelismo():
    grande = {"cores": 32, "physicalCores": 16, "ramGb": 64,
              "accel": {"preferredEncoder": "h264_nvenc"}}
    s = profile_settings("performance", grande)
    assert s["parallelJobs"] >= 4
    assert s["renderSlots"] == 2


def test_sem_info_de_nucleo_fisico_assume_metade_das_threads():
    s = profile_settings("performance", {"cores": 8, "ramGb": 16})
    assert s["parallelJobs"] == 2
