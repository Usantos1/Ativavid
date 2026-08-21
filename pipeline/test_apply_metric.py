"""Métrica local do Apply — sem FFmpeg."""
from __future__ import annotations

import json
import sys
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
    ae._ULTIMO_MOTOR.clear()
    ae._ULTIMO_MOTOR.update({"engine": "remotion",
                             "fallbackReason": "TRUE_PEAK -0.9>-1.0"})
    ae.record_apply_metric(edit, {"type": "REUSE_CUT", "videoDuration": 58,
                                  "applyDuration": 1806, "success": True})
    linha = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))[-1]
    assert linha["engine"] == "remotion"
    assert linha["fallbackReason"] == "TRUE_PEAK -0.9>-1.0"

    ae._ULTIMO_MOTOR.clear()
    ae._ULTIMO_MOTOR["engine"] = "overlay"
    ae.record_apply_metric(edit, {"type": "REUSE_CUT", "videoDuration": 58,
                                  "applyDuration": 70, "success": True})
    linha = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))[-1]
    assert linha["engine"] == "overlay"
    assert "fallbackReason" not in linha


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
