"""Vídeo no fim da timeline: take novo (CTA), não overlay."""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.append_source import (
    append_cta,
    dest_cta_path,
    merge_source_paths,
    source_key_from_stem,
    validate_cta_clip,
    write_cta_file,
)
from pipeline.run_fast import load_preview_edit_ranges


def test_source_key_matches_run_fast():
    assert source_key_from_stem("cta_Qual_pelicula") == "cta_Qual_pelicula"
    assert source_key_from_stem("Qual pelicula!") == "Qual_pelicula_"
    used = {"cta_loja"}
    assert source_key_from_stem("cta_loja", used) == "cta_loja_2"


def test_dest_cta_unique_and_key():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        a = dest_cta_path(root, "Loja Centro.MOV")
        assert a.name == "cta_Loja_Centro.mov"
        a.write_bytes(b"x")
        b = dest_cta_path(root, "Loja Centro.MOV")
        assert b.name == "cta_Loja_Centro_2.mov"
        assert source_key_from_stem(a.stem) == "cta_Loja_Centro"


def test_write_rejects_photo():
    with tempfile.TemporaryDirectory() as raw:
        try:
            write_cta_file(Path(raw), "foto.jpg", b"abc")
        except ValueError as e:
            assert "MP4" in str(e) or "MOV" in str(e)
        else:
            raise AssertionError("foto não deveria entrar")


def test_merge_stays_inside_project():
    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw) / "proj"
        project.mkdir()
        primary = project / "IMG_1.MOV"
        extra = project / "cta_loja.mp4"
        outsider = Path(raw) / "outro.mp4"
        primary.write_bytes(b"a")
        extra.write_bytes(b"b")
        outsider.write_bytes(b"c")
        merged = merge_source_paths(
            [str(primary)],
            [str(extra), str(outsider), str(extra)],
            project,
        )
        assert merged == [str(primary.resolve()), str(extra.resolve())]


def test_validate_cta_rules():
    assert validate_cta_clip({"duration": 0.2, "width": 1080, "height": 1920})
    assert validate_cta_clip({"duration": 800, "width": 1080, "height": 1920})
    assert validate_cta_clip({"duration": 5, "width": 1920, "height": 1080}) is None
    assert validate_cta_clip({"duration": 5, "width": 1080, "height": 1920}) is None


def test_append_cta_from_path_uses_hint():
    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw) / "proj"
        project.mkdir()
        src = Path(raw) / "loja.mp4"
        src.write_bytes(b"not-a-real-video")
        got = append_cta(project, src_path=src, duration_hint=4.5)
        assert got["ok"] is True
        assert got["source"].startswith("cta_loja")
        assert got["duration"] == 4.5
        assert Path(got["path"]).is_file()


def test_preview_edits_keeps_other_source():
    with tempfile.TemporaryDirectory() as raw:
        edit = Path(raw)
        (edit / "preview_edits.json").write_text(json.dumps({
            "edl": {
                "ranges": [
                    {"source": "IMG_1659", "start": 0, "end": 12.5, "beat": "HOOK"},
                    {"source": "cta_loja", "start": 0, "end": 4.2, "beat": "CTA"},
                ],
            },
        }), encoding="utf-8")
        ranges = load_preview_edit_ranges(edit, "IMG_1659")
        assert ranges is not None
        assert [r["source"] for r in ranges] == ["IMG_1659", "cta_loja"]
        assert ranges[-1]["beat"] == "CTA"
        assert not (edit / "preview_edits.json").exists()
        assert (edit / "preview_edits.applied.json").exists()


if __name__ == "__main__":
    test_source_key_matches_run_fast()
    test_dest_cta_unique_and_key()
    test_write_rejects_photo()
    test_merge_stays_inside_project()
    test_validate_cta_rules()
    test_append_cta_from_path_uses_hint()
    test_preview_edits_keeps_other_source()
    print("ok")
