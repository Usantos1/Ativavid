"""Entrega com nome da headline (não só final.mp4)."""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.local_server import resolve_delivery_mp4


def test_headline_name_not_final_mp4():
    with tempfile.TemporaryDirectory() as raw:
        edit = Path(raw) / "edit"
        edit.mkdir()
        named = edit / "Transformando celular em iPhone 16.mp4"
        named.write_bytes(b"x" * 500)
        (edit / "cut.mp4").write_bytes(b"c" * 500)
        (edit / "state.json").write_text(json.dumps({
            "finalVideo": "Transformando celular em iPhone 16.mp4",
        }), encoding="utf-8")
        got = resolve_delivery_mp4(edit)
        assert got == named


def test_stale_final_pointer_finds_headline():
    with tempfile.TemporaryDirectory() as raw:
        edit = Path(raw) / "edit"
        edit.mkdir()
        named = edit / "Cabo magnetico.mp4"
        named.write_bytes(b"x" * 500)
        (edit / "cut.mp4").write_bytes(b"c" * 500)
        (edit / "cut_proxy.mp4").write_bytes(b"p" * 800)
        (edit / "state.json").write_text(json.dumps({
            "finalVideo": "final.mp4",
        }), encoding="utf-8")
        got = resolve_delivery_mp4(edit)
        assert got == named


if __name__ == "__main__":
    test_headline_name_not_final_mp4()
    test_stale_final_pointer_finds_headline()
    print("ok")
