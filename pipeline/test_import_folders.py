"""Importação por pasta: subpastas viram jobs; vários arquivos na mesma pasta juntam."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.local_server import _is_import_video, _walk_import_videos


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_walk_groups_like_skill():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        a1 = _touch(root / "Loja A" / "IMG_1.MOV")
        a2 = _touch(root / "Loja A" / "IMG_2.MOV")
        b1 = _touch(root / "Loja B" / "clip.mp4")
        _touch(root / "Loja A" / "edit" / "final.mp4")
        _touch(root / "Loja A" / "foto.jpg")
        found = _walk_import_videos(root)
        assert set(found) == {a1, a2, b1}
        groups: dict[str, list[Path]] = {}
        for src in found:
            groups.setdefault(src.parent.name, []).append(src)
        assert len(groups["Loja A"]) == 2
        assert len(groups["Loja B"]) == 1


def test_skips_outputs():
    assert _is_import_video(Path("final.mp4")) is False
    assert _is_import_video(Path("cut.mp4")) is False
    assert _is_import_video(Path("IMG_1.MOV")) is True


if __name__ == "__main__":
    test_walk_groups_like_skill()
    print("ok test_walk_groups_like_skill")
    test_skips_outputs()
    print("ok test_skips_outputs")
    print("ALL_OK")
