"""Apagar projeto vai para a Lixeira. Sem PowerShell, sem apagar de verdade."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.recycle import RecycleError, is_safe_project_dir, send_to_recycle_bin


def test_refuses_projects_root(tmp_path: Path):
    root = tmp_path / "Projetos"
    root.mkdir()
    assert is_safe_project_dir(root, root) is False
    nested = root / "20260818_video"
    nested.mkdir()
    assert is_safe_project_dir(nested, root) is True
    outsider = tmp_path / "outra"
    outsider.mkdir()
    assert is_safe_project_dir(outsider, root) is False


def test_runner_is_used_instead_of_erase(tmp_path: Path):
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "final.mp4").write_bytes(b"KEEP")
    seen: list[Path] = []

    def runner(path: Path) -> None:
        seen.append(path)
        dest = tmp_path / "lixeira" / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        path.rename(dest)

    send_to_recycle_bin(folder, runner=runner)
    assert seen == [folder.resolve()]
    assert not folder.exists()
    assert (tmp_path / "lixeira" / "proj" / "final.mp4").read_bytes() == b"KEEP"


def test_missing_folder_raises(tmp_path: Path):
    try:
        send_to_recycle_bin(tmp_path / "nao-existe", runner=lambda p: None)
    except RecycleError:
        return
    raise AssertionError("esperava RecycleError")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_refuses_projects_root(Path(d) / "a")
        test_runner_is_used_instead_of_erase(Path(d) / "b")
        test_missing_folder_raises(Path(d) / "c")
    print("ok")
