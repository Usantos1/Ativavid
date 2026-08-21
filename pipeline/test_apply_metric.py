"""Métrica local do Apply — sem FFmpeg."""
from __future__ import annotations

import json
import sys
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import record_apply_metric


def test_record_apply_metric_appends(tmp_path: Path):
    edit = tmp_path / "edit"
    edit.mkdir()
    record_apply_metric(edit, {
        "type": "REUSE_CUT",
        "videoDuration": 9.97,
        "applyDuration": 79.7,
        "success": True,
    })
    record_apply_metric(edit, {
        "type": "REBUILD_CUT",
        "videoDuration": 9.27,
        "applyDuration": 206.1,
        "success": False,
        "error": "cut temporário tem 10 frames",
    })
    hist = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))
    assert len(hist) == 2
    assert hist[0]["type"] == "REUSE_CUT"
    assert hist[0]["success"] is True
    assert hist[0]["videoDuration"] == 9.97
    assert hist[0]["applyDuration"] == 79.7
    assert hist[1]["type"] == "REBUILD_CUT"
    assert hist[1]["success"] is False
    assert "error" in hist[1]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_record_apply_metric_appends(Path(d))
    print("ok")


def test_a_metrica_diz_qual_motor_desenhou(tmp_path: Path):
    """O log do apply só vai para a tela, então o motivo de uma queda se
    perdia — foi por isso que deu para diagnosticar o desperdício do RENDER
    (que grava `render-stats.json`) e não o do APPLY.

    Medido no histórico do usuário em 21/08/2026: o mesmo tipo de apply
    variou de 1,2x a 31,3x o tempo real, e não havia como saber qual foi
    pelo motor rápido e qual caiu no Remotion."""
    import json

    from app import apply_execute as ae

    edit = tmp_path / "edit"
    edit.mkdir()
    ae._motor(edit, "remotion", "TRUE_PEAK -0.9>-1.0")
    ae.record_apply_metric(edit, {"type": "REUSE_CUT", "videoDuration": 58,
                                  "applyDuration": 1806, "success": True})
    linha = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))[-1]
    assert linha["engine"] == "remotion"
    assert linha["fallbackReason"] == "TRUE_PEAK -0.9>-1.0"

    ae._motor(edit, "overlay")
    ae.record_apply_metric(edit, {"type": "REUSE_CUT", "videoDuration": 58,
                                  "applyDuration": 70, "success": True})
    linha = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))[-1]
    assert linha["engine"] == "overlay"
    assert "fallbackReason" not in linha


def test_dois_projetos_aplicando_juntos_nao_misturam_a_metrica(tmp_path: Path):
    """`is_apply_running` e POR PROJETO (le o apply_status.json daquele edit),
    entao dois projetos diferentes rodam apply ao mesmo tempo, cada um na sua
    thread "quick-apply", no MESMO processo.

    Guardadas num dicionario unico, as metricas se misturavam: o motor de um ia
    parar no historico do outro e os tempos por fase viravam a soma dos dois.
    Como e justamente esta medicao que decide o que otimizar, numero misturado
    e pior do que numero nenhum.
    """
    import json
    import time

    from app import apply_execute as ae

    a = tmp_path / "projeto_a" / "edit"
    b = tmp_path / "projeto_b" / "edit"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    # os dois intercalados, como aconteceria de verdade
    ae._motor(a, "overlay")
    ae._motor(b, "remotion", "classificado FULL: ['zoom']")
    t = time.time() - 12.0
    ae._fase(a, "render", t)
    ae._fase(b, "render", time.time() - 300.0)
    ae._fase(a, "promote", time.time() - 1.0)

    ae.record_apply_metric(a, {"type": "REUSE_CUT", "videoDuration": 40,
                               "applyDuration": 15, "success": True})
    ae.record_apply_metric(b, {"type": "REUSE_CUT", "videoDuration": 90,
                               "applyDuration": 310, "success": True})

    la = json.loads((a / "apply_history.json").read_text(encoding="utf-8"))[-1]
    lb = json.loads((b / "apply_history.json").read_text(encoding="utf-8"))[-1]

    assert la["engine"] == "overlay"
    assert "fallbackReason" not in la
    assert lb["engine"] == "remotion"
    assert lb["fallbackReason"].startswith("classificado FULL")

    assert sorted(la["phases"]) == ["promote", "render"]
    assert sorted(lb["phases"]) == ["render"], "a fase de A vazou para B"
    assert la["phases"]["render"] == pytest.approx(12.0, abs=1.0)
    assert lb["phases"]["render"] == pytest.approx(300.0, abs=1.0)


def test_colher_esvazia_o_mapa_e_nao_repete_na_proxima(tmp_path: Path):
    """Sem isto o mapa cresceria por projeto para sempre, e um apply seguinte
    que nao marcasse fase nenhuma herdaria os tempos do anterior."""
    import json

    from app import apply_execute as ae

    edit = tmp_path / "edit"
    edit.mkdir()
    ae._motor(edit, "overlay")
    ae._fase(edit, "render", 0.0)
    ae.record_apply_metric(edit, {"type": "REUSE_CUT", "videoDuration": 10,
                                  "applyDuration": 5, "success": True})
    ae.record_apply_metric(edit, {"type": "REUSE_CUT", "videoDuration": 10,
                                  "applyDuration": 5, "success": True})
    linhas = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))
    assert "phases" in linhas[-2] and "engine" in linhas[-2]
    assert "phases" not in linhas[-1], "as fases do apply anterior se repetiram"
    assert "engine" not in linhas[-1]


def test_sem_motor_registrado_a_metrica_nao_inventa_campo(tmp_path: Path):
    import json

    from app import apply_execute as ae

    edit = tmp_path / "edit"
    edit.mkdir()
    ae._ULTIMO_MOTOR.clear()
    ae.record_apply_metric(edit, {"type": "NOOP", "videoDuration": 1,
                                  "applyDuration": 1, "success": True})
    linha = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))[-1]
    assert "engine" not in linha and "fallbackReason" not in linha
