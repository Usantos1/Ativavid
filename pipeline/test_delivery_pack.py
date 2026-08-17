"""Pasta para postar: vídeo + capa + legenda — só cópia, sem render."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.delivery_pack import ensure_delivery_pack, folder_to_open, read_pack_dir


def test_pack_has_video_cover_legenda(tmp_path: Path):
    proj = tmp_path / "job"
    edit = proj / "edit"
    edit.mkdir(parents=True)
    video = edit / "Roubou a venda no almoco!.mp4"
    video.write_bytes(b"video" * 80)
    (edit / "cover.jpg").write_bytes(b"jpeg" * 120)
    (edit / "legenda.txt").write_text("Gancho\n#loja\n", encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({
        "finalVideo": video.name,
    }), encoding="utf-8")

    dest = ensure_delivery_pack(edit)
    assert dest is not None
    assert dest.name == "Roubou a venda no almoco!"
    assert dest.parent.name == "publicar"
    assert (dest / "Roubou a venda no almoco!.mp4").is_file()
    assert (dest / "capa.jpg").is_file()
    assert (dest / "legenda.txt").read_text(encoding="utf-8").startswith("Gancho")
    assert read_pack_dir(edit) == dest
    assert folder_to_open(edit) == dest


def test_capa_update_replaces_pack_image(tmp_path: Path):
    proj = tmp_path / "job"
    edit = proj / "edit"
    edit.mkdir(parents=True)
    (edit / "Video.mp4").write_bytes(b"video" * 80)
    (edit / "cover.jpg").write_bytes(b"old" * 200)
    (edit / "state.json").write_text(json.dumps({"finalVideo": "Video.mp4"}), encoding="utf-8")
    dest = ensure_delivery_pack(edit)
    assert (dest / "capa.jpg").read_bytes().startswith(b"old")
    (edit / "cover.jpg").write_bytes(b"newcover" * 80)
    ensure_delivery_pack(edit)
    assert (dest / "capa.jpg").read_bytes().startswith(b"newcover")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as raw:
        test_pack_has_video_cover_legenda(Path(raw) / "a")
        test_capa_update_replaces_pack_image(Path(raw) / "b")
    print("ok")
