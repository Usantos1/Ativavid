"""ETA a partir de fixtures de timing.json — sem processar vídeo."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.eta_estimate import collect_history, estimate_seconds, format_eta, label_for_job


def _sample(*, dur: float, cuts: int, total: float, hdr: bool = False, path: str = "FULL") -> dict:
    return {
        "sourceDuration": dur,
        "cuts": cuts,
        "wholeJobSec": total,
        "totalSec": total,
        "hdr": hdr,
        "renderPath": path,
    }


HIST = [
    _sample(dur=20, cuts=6, total=55, path="OVERLAY"),
    _sample(dur=22, cuts=7, total=62, path="OVERLAY"),
    _sample(dur=50, cuts=10, total=140, hdr=True, path="FULL"),
    _sample(dur=80, cuts=28, total=210, path="FULL"),
]


def test_no_eta_without_history():
    assert estimate_seconds({"sourceDuration": 20, "cuts": 6}, []) is None
    assert estimate_seconds({"sourceDuration": 20, "cuts": 6}, [HIST[0]]) is None
    assert format_eta(None) is None


def test_eta_against_fixtures():
    short = estimate_seconds({"sourceDuration": 20, "cuts": 6, "renderPath": "OVERLAY"}, HIST)
    long_hdr = estimate_seconds(
        {"sourceDuration": 50, "cuts": 10, "hdr": True, "renderPath": "FULL"}, HIST
    )
    many = estimate_seconds({"sourceDuration": 80, "cuts": 28, "renderPath": "FULL"}, HIST)
    assert short is not None and long_hdr is not None and many is not None
    assert short < long_hdr
    assert short < many
    # 20s 1080 overlay deve ficar perto do histórico ~1 min, não de 4 min
    assert 20 <= short <= 120
    # 50s 4K/HDR e 80s muitos cortes ficam acima do curto
    assert long_hdr >= 80
    label = format_eta(short)
    assert label and "restante" in label


def test_collect_history_from_fake_projects(tmp_path: Path):
    a = tmp_path / "job-a" / "edit"
    b = tmp_path / "job-b" / "edit"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "timing.json").write_text(json.dumps(HIST[0]), encoding="utf-8")
    (b / "timing.json").write_text(json.dumps(HIST[1]), encoding="utf-8")
    (a / "job_intent.json").write_text(
        json.dumps({"sourceDurationSec": 20}), encoding="utf-8"
    )
    hist = collect_history(tmp_path)
    assert len(hist) == 2
    assert label_for_job({"sourceDuration": 21, "cuts": 6}, hist)
