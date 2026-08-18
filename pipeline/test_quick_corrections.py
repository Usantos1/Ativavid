"""Correções rápidas 1.87 — unitário, sem FFmpeg/Remotion/Whisper."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_plan import plan_apply_changes
from app.caption_remap import output_duration, remap_captions_through_edl
from app.caption_fixes import apply_replacements_to_words
from app.apply_execute import pending_caption_remap
from app.quick_corrections import (
    delete_range_index,
    fix_caption,
    handle,
    load,
    read_edl_ranges,
    read_headline_lines,
    set_headline,
    split_at_playhead,
    write_edl_ranges,
)


def _project(root: Path, *, headline: list[str], caption: str, ranges: list[dict] | None = None) -> Path:
    public = root / "remotion" / "public"
    public.mkdir(parents=True)
    (public / "edit-data.json").write_text(
        json.dumps({"hook": {"enabled": True, "lines": headline, "endSec": 4}}, ensure_ascii=False),
        encoding="utf-8",
    )
    words = []
    t = 0
    for w in caption.split():
        words.append({"text": w, "startMs": t, "endMs": t + 200})
        t += 200
    (public / "captions.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    (root / "edl.json").write_text(
        json.dumps({
            "ranges": ranges or [
                {"source": "SRC", "start": 0.0, "end": 8.0, "beat": "HOOK"},
                {"source": "SRC", "start": 8.0, "end": 20.0, "beat": "B1"},
            ]
        }),
        encoding="utf-8",
    )
    return root


def test_1_headline_persists_and_stale(tmp_path: Path):
    edit = _project(tmp_path, headline=["VOCÊ ESTÁ PAGANDO CARO"], caption="uma perico muito boa")
    out = set_headline(edit, "O BARATO PODE SAIR CARO")
    assert out["ok"]
    assert read_headline_lines(edit) == ["O BARATO PODE SAIR CARO"]
    disk = json.loads((edit / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8"))
    assert disk["hook"]["lines"] == ["O BARATO PODE SAIR CARO"]
    corr = load(edit)
    assert "headline" not in corr
    disk_corr = json.loads((edit / "corrections.json").read_text(encoding="utf-8"))
    assert "headline" not in disk_corr or disk_corr.get("headline") in (None, [], "")
    assert corr["dirty"]["headline"] is True
    assert corr["dirty"]["captions"] is False
    assert corr["finalStale"] is True
    # reload = ler de novo do disco
    assert load(edit)["dirty"]["headline"] is True
    assert read_headline_lines(edit) == ["O BARATO PODE SAIR CARO"]
    plan = plan_apply_changes(load(edit))
    assert plan["reuseCut"] is True
    assert plan["rebuildCut"] is False
    assert plan["runTranscription"] is False
    assert plan["runAI"] is False
    assert plan["execute"] is False


def test_2_caption_perico_to_pelicula(tmp_path: Path):
    edit = _project(tmp_path, headline=["GANCHO"], caption="uma perico muito boa")
    out = fix_caption(edit, src="uma perico muito boa", dst="uma película muito boa")
    assert out["ok"]
    words = json.loads((edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))
    joined = " ".join(w["text"] for w in words if w.get("text"))
    assert "película" in joined.lower()
    assert "perico" not in joined.lower()
    # timings das palavras originais seguem lá
    assert words[0]["startMs"] == 0
    corr = load(edit)
    assert corr["dirty"]["captions"] is True
    assert corr["finalStale"] is True
    # reload
    words2 = json.loads((edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))
    assert "película" in " ".join(w["text"] for w in words2 if w.get("text")).lower()


def test_3_split_and_delete_edl_math():
    ranges = [
        {"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"},
        {"source": "SRC", "start": 10.0, "end": 20.0, "beat": "B1"},
    ]
    # agulha em 4s da timeline = meio do primeiro take
    split = split_at_playhead(ranges, 4.0, min_seg=0.2)
    assert len(split) == 3
    assert split[0]["start"] == 0.0
    assert split[0]["end"] == 4.0
    assert split[1]["start"] == 4.0
    assert split[1]["end"] == 10.0
    assert split[2]["start"] == 10.0
    # excluir TAKE B (o segundo pedaço, índice 1)
    nxt = delete_range_index(split, 1)
    assert len(nxt) == 2
    assert nxt[0] == {"source": "SRC", "start": 0.0, "end": 4.0, "beat": "HOOK"}
    assert nxt[1]["start"] == 10.0
    assert nxt[1]["end"] == 20.0
    # duração da timeline: 4 + 10 = 14
    dur = sum(float(r["end"]) - float(r["start"]) for r in nxt)
    assert dur == 14.0


def test_3b_split_persists_without_ffmpeg(tmp_path: Path):
    edit = _project(tmp_path, headline=["H"], caption="oi", ranges=[
        {"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"},
    ])
    write_edl_ranges(edit, split_at_playhead(read_edl_ranges(edit), 3.0))
    got = read_edl_ranges(edit)
    assert len(got) == 2
    assert got[0]["end"] == 3.0
    assert got[1]["start"] == 3.0
    assert load(edit)["dirty"]["edl"] is True


def test_4_dirty_visual_only_plan():
    plan = plan_apply_changes({
        "headline": True,
        "captions": True,
        "edl": False,
        "style": False,
    })
    assert plan["reuseCut"] is True
    assert plan["rebuildCut"] is False
    assert plan["runTranscription"] is False
    assert plan["runAI"] is False
    assert plan["renderVisual"] is True
    assert plan["exportFinal"] is True
    assert plan["mode"] == "REUSE_CUT"
    assert plan["renderMode"] == "RENDER_VISUAL_ONLY"
    assert plan["reasons"] == ["HEADLINE_DIRTY", "CAPTIONS_DIRTY"]
    assert plan["remapCaptions"] is False
    assert plan["execute"] is False


def test_5_edl_dirty_rebuild_plan():
    plan = plan_apply_changes({"headline": False, "captions": False, "edl": True, "style": False})
    assert plan["reuseCut"] is False
    assert plan["rebuildCut"] is True
    assert plan["runTranscription"] is False
    assert plan["runAI"] is False
    assert plan["renderVisual"] is True
    assert plan["mode"] == "REBUILD_CUT"
    assert plan["renderMode"] == "RENDER_VISUAL"
    assert plan["reasons"] == ["EDL_DIRTY", "REMAP_CAPTIONS"]
    assert plan["remapCaptions"] is True
    assert plan["execute"] is False


def test_5b_cut_plus_caption_still_no_ai():
    plan = plan_apply_changes({"headline": False, "captions": True, "edl": True, "style": False})
    assert plan["rebuildCut"] is True
    assert plan["reuseCut"] is False
    assert plan["remapCaptions"] is True
    assert plan["runTranscription"] is False
    assert plan["runAI"] is False
    assert "CAPTIONS_DIRTY" in plan["reasons"]
    assert "EDL_DIRTY" in plan["reasons"]
    assert "REMAP_CAPTIONS" in plan["reasons"]


def test_5c_style_headline_captions_visual_only():
    for flags in (
        {"headline": True, "captions": False, "edl": False, "style": False},
        {"headline": False, "captions": True, "edl": False, "style": False},
        {"headline": False, "captions": False, "edl": False, "style": True},
    ):
        plan = plan_apply_changes(flags)
        assert plan["mode"] == "REUSE_CUT"
        assert plan["renderMode"] == "RENDER_VISUAL_ONLY"
        assert plan["remapCaptions"] is False
        assert plan["runTranscription"] is False
        assert plan["runAI"] is False
        assert plan["execute"] is False


def test_remap_remove_4_to_6():
    edl = [{"source": "SRC", "start": 0.0, "end": 4.0}, {"source": "SRC", "start": 6.0, "end": 10.0}]
    caps = [
        {"text": "cedo", "start": 2.0, "end": 4.0},
        {"text": "tarde", "start": 7.0, "end": 9.0},
    ]
    out = remap_captions_through_edl(caps, edl)
    assert output_duration(edl) == 8.0
    assert len(out) == 2
    assert out[0]["start"] == 2.0 and out[0]["end"] == 4.0
    assert out[1]["start"] == 5.0 and out[1]["end"] == 7.0


def test_remap_cue_crosses_removed_range():
    edl = [{"start": 0.0, "end": 4.0}, {"start": 6.0, "end": 10.0}]
    out = remap_captions_through_edl([{"text": "cruza", "start": 3.0, "end": 7.0}], edl)
    assert len(out) == 2
    assert out[0]["start"] == 3.0 and out[0]["end"] == 4.0
    assert out[1]["start"] == 4.0 and out[1]["end"] == 5.0
    gone = remap_captions_through_edl([{"text": "buraco", "start": 4.2, "end": 5.8}], edl)
    assert gone == []


def test_token_count_changes():
    def run(src, dst, words):
        w = [dict(x) for x in words]
        apply_replacements_to_words(w, [{"from": src, "to": dst}])
        return w

    one = run("perico", "película", [{"text": "perico", "startMs": 10, "endMs": 40}])
    assert one[0]["text"] == "película"
    assert one[0]["startMs"] == 10 and one[0]["endMs"] == 40

    two_to_three = run(
        "esse negócio",
        "essa película fosca",
        [
            {"text": "esse", "startMs": 0, "endMs": 600},
            {"text": "negócio", "startMs": 600, "endMs": 1200},
        ],
    )
    assert [x["text"] for x in two_to_three] == ["essa", "película", "fosca"]
    assert two_to_three[0]["startMs"] == 0
    assert two_to_three[-1]["endMs"] == 1200
    assert len(two_to_three) == 3

    four_to_two = run(
        "a b c d",
        "ok vai",
        [
            {"text": "a", "startMs": 0, "endMs": 100},
            {"text": "b", "startMs": 100, "endMs": 200},
            {"text": "c", "startMs": 200, "endMs": 300},
            {"text": "d", "startMs": 300, "endMs": 400},
        ],
    )
    assert [x["text"] for x in four_to_two] == ["ok", "vai"]
    assert four_to_two[0]["startMs"] == 0
    assert four_to_two[-1]["endMs"] == 400

    phrase = run(
        "uma perico muito boa",
        "película super fosca",
        [
            {"text": "uma", "startMs": 0, "endMs": 200},
            {"text": "perico", "startMs": 200, "endMs": 400},
            {"text": "muito", "startMs": 400, "endMs": 600},
            {"text": "boa", "startMs": 600, "endMs": 800},
        ],
    )
    assert phrase[0]["startMs"] == 0
    assert phrase[-1]["endMs"] == 800
    assert [x["text"] for x in phrase] == ["película", "super", "fosca"]


def test_6_reload_keeps_pending_and_stale(tmp_path: Path):
    edit = _project(tmp_path, headline=["Headline A"], caption="uma perico muito boa")
    set_headline(edit, "Headline B")
    fix_caption(edit, src="perico", dst="película")
    # "fechar e reabrir" = load() de novo
    corr = load(edit)
    assert read_headline_lines(edit) == ["Headline B"]
    joined = " ".join(
        w["text"]
        for w in json.loads((edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))
        if w.get("text")
    )
    assert "película" in joined.lower()
    assert corr["finalStale"] is True
    assert corr["dirty"]["headline"] is True
    assert corr["dirty"]["captions"] is True
    plan = handle(edit, {"op": "plan"})
    assert plan["execute"] is False
    assert plan["plan"]["reuseCut"] is True


def test_edl_does_not_rewrite_captions(tmp_path: Path):
    edit = _project(tmp_path, headline=["H"], caption="tarde", ranges=[
        {"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"},
    ])
    caps_p = edit / "remotion" / "public" / "captions.json"
    words = [
        {"text": "cedo", "startMs": 2000, "endMs": 4000},
        {"text": "tarde", "startMs": 7000, "endMs": 9000},
    ]
    caps_p.write_text(json.dumps(words), encoding="utf-8")
    before = caps_p.read_text(encoding="utf-8")
    write_edl_ranges(edit, [
        {"source": "SRC", "start": 0.0, "end": 4.0, "beat": "HOOK"},
        {"source": "SRC", "start": 6.0, "end": 10.0, "beat": "B1"},
    ])
    assert caps_p.read_text(encoding="utf-8") == before
    corr = load(edit)
    assert corr["dirty"]["edl"] is True
    assert corr["captionsTimedTo"]
    assert corr["captionsTimedTo"][0]["end"] == 10.0
    pending = pending_caption_remap(edit)
    assert pending is not None
    assert pending[0]["startMs"] == 2000
    assert pending[1]["startMs"] == 5000
    assert pending[1]["endMs"] == 7000
    assert pending[1]["text"] == "tarde"


def test_apply_handle_uses_executor_with_hooks(tmp_path: Path):
    from app.apply_execute import ApplyHooks
    from app.quick_corrections import plan_for_edit

    edit = _project(tmp_path, headline=["A"], caption="oi")
    (edit / "cut.mp4").write_bytes(b"cut" * 8000)
    (edit / "final.mp4").write_bytes(b"OLD" * 8000)
    set_headline(edit, "B")
    plan = plan_for_edit(edit)
    assert plan["execute"] is False
    logs: list[str] = []

    def rebuild(ed, dest):
        raise AssertionError("REUSE_CUT não reconstrói cut")

    def render(ed, *, cut, captions, dest):
        dest.write_bytes(b"NEW" * 8000)
        return dest

    def promote(src, dest):
        if dest.exists() and dest.resolve() != src.resolve():
            dest.unlink()
        src.replace(dest)

    hooks = ApplyHooks(
        rebuild_cut=rebuild,
        render_visual=render,
        validate_final=lambda path, **kw: (True, {"durationSec": 8, "audio": True}),
        promote_file=promote,
        sync_pack=lambda ed, final: None,
        probe_duration=lambda p: 8.0,
        log=logs.append,
        progress=lambda stage, msg: None,
    )
    out = handle(edit, {"op": "apply", "sync": True}, hooks=hooks)
    assert out["ok"] is True
    assert out["execute"] is True
    assert any("QUICK_APPLY_REUSE_CUT" in x for x in logs)
    assert (edit / "final.mp4").read_bytes().startswith(b"NEW")
    assert load(edit)["finalStale"] is False
    assert load(edit)["dirty"]["headline"] is False


def test_legacy_project_opens_without_new_fields(tmp_path: Path):
    """Projeto antigo: sem corrections/apply_history/captionsTimedTo ainda abre."""
    from app.project_versions import list_versions

    edit = _project(tmp_path, headline=["GANCHO ANTIGO"], caption="ola mundo")
    assert not (edit / "corrections.json").exists()
    assert not (edit / "apply_history.json").exists()
    corr = load(edit)
    assert corr["captionsTimedTo"] is None
    assert corr["captionsTimedToJcut"] is None
    assert corr["finalStale"] is False
    assert pending_caption_remap(edit) is None
    assert list_versions(edit) == []
    out = set_headline(edit, "GANCHO NOVO")
    assert out["ok"] is True
    assert (edit / "corrections.json").exists()
    saved = json.loads((edit / "corrections.json").read_text(encoding="utf-8"))
    assert saved["dirty"]["headline"] is True
    assert saved.get("captionsTimedTo") in (None, [], {})


def test_headline_does_not_touch_brand_preset(tmp_path: Path):
    edit = _project(tmp_path, headline=["A"], caption="oi")
    brand = tmp_path / "brands" / "loja.json"
    brand.parent.mkdir()
    brand.write_text(json.dumps({"aiHeadline": "NÃO MEXER"}), encoding="utf-8")
    set_headline(edit, "B")
    assert json.loads(brand.read_text(encoding="utf-8"))["aiHeadline"] == "NÃO MEXER"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_1_headline_persists_and_stale(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_2_caption_perico_to_pelicula(Path(d))
    test_3_split_and_delete_edl_math()
    with tempfile.TemporaryDirectory() as d:
        test_3b_split_persists_without_ffmpeg(Path(d))
    test_4_dirty_visual_only_plan()
    test_5_edl_dirty_rebuild_plan()
    test_5b_cut_plus_caption_still_no_ai()
    test_5c_style_headline_captions_visual_only()
    test_remap_remove_4_to_6()
    test_remap_cue_crosses_removed_range()
    test_token_count_changes()
    with tempfile.TemporaryDirectory() as d:
        test_6_reload_keeps_pending_and_stale(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_edl_does_not_rewrite_captions(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_apply_handle_uses_executor_with_hooks(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_headline_does_not_touch_brand_preset(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_legacy_project_opens_without_new_fields(Path(d))
    print("ok")
