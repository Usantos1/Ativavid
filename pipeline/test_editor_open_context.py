"""Abertura de projeto existente: escopo /p/<pasta> acha o cut. Sem FFmpeg."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
HELPERS = REPO / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import preview_server as ps  # noqa: E402


def test_scope_miss_does_not_use_hub_dummy(tmp_path: Path):
    projects = tmp_path / "Projetos"
    hub = projects / ".ativavid" / "hub" / "edit"
    hub.mkdir(parents=True)
    (hub / "state.json").write_text(
        json.dumps({"project": "Estilo padrão da marca", "awaitingStyle": True}),
        encoding="utf-8",
    )
    real = projects / "proj_real" / "edit"
    real.mkdir(parents=True)
    (real / "cut.mp4").write_bytes(b"CUT" * 20)
    (real / "state.json").write_text(
        json.dumps({"project": "Real", "video": "cut.mp4", "awaitingStyle": False}),
        encoding="utf-8",
    )
    (real / "preset-used.json").write_text(
        json.dumps({"brandId": "padrao", "brandName": "Prime Camp"}),
        encoding="utf-8",
    )
    ps.Handler.root = hub
    ps.Handler.projects_roots = [projects]
    h = ps.Handler.__new__(ps.Handler)
    rest = h._scope("/p/proj_real/api/state")
    assert rest == "/api/state"
    assert h.scoped is True
    assert h.scope_miss is False
    assert h.root == real.resolve()
    assert (h.root / "cut.mp4").is_file()
    video = h._current_video()
    assert video is not None
    assert video.name == "cut.mp4"

    miss = h._scope("/p/nao_existe/api/state")
    assert miss == "/api/state"
    assert h.scope_miss is True
    assert h.scoped is False


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_scope_miss_does_not_use_hub_dummy(Path(d))
    print("ok")
