"""Executor do Apply 1.87 — mocks, sem FFmpeg/Remotion/Whisper."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import ApplyHooks, execute_apply_plan, pending_caption_remap
from app.apply_plan import plan_apply_changes
from app.quick_corrections import (
    fix_caption,
    load,
    read_headline_lines,
    set_headline,
    write_edl_ranges,
)


def _project(root: Path) -> Path:
    public = root / "remotion" / "public"
    public.mkdir(parents=True)
    (public / "edit-data.json").write_text(
        json.dumps({"hook": {"enabled": True, "lines": ["GANCHO"], "endSec": 4}, "durationSec": 10, "fps": 30}),
        encoding="utf-8",
    )
    words = [
        {"text": "uma", "startMs": 0, "endMs": 200},
        {"text": "perico", "startMs": 7000, "endMs": 9000},
        {"text": "boa", "startMs": 9000, "endMs": 10000},
    ]
    (public / "captions.json").write_text(json.dumps(words), encoding="utf-8")
    (root / "edl.json").write_text(
        json.dumps({"ranges": [{"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"}]}),
        encoding="utf-8",
    )
    (root / "cut.mp4").write_bytes(b"CUT" * 8000)
    (root / "final.mp4").write_bytes(b"OLD" * 8000)
    return root


def _hooks(logs: list[str], *, fail: str | None = None, expected_dur: float = 8.0) -> ApplyHooks:
    def rebuild(ed: Path, dest: Path) -> Path:
        logs.append("rebuild")
        if fail == "rebuild":
            raise RuntimeError("falha no corte")
        dest.write_bytes(b"CUT2" * 8000)
        return dest

    def render(ed: Path, *, cut: Path, captions, dest: Path) -> Path:
        logs.append("render")
        if captions is not None:
            logs.append("captions:" + " ".join(str(c.get("text")) for c in captions if isinstance(c, dict)))
        if fail == "render":
            raise RuntimeError("falha no visual")
        dest.write_bytes(b"NEW" * 8000)
        return dest

    def validate(path: Path, **kw) -> tuple[bool, dict]:
        logs.append("validate")
        if fail == "validate":
            return False, {"error": "arquivo inválido"}
        return True, {"durationSec": expected_dur, "audio": True, "ok": True}

    def promote(src: Path, dest: Path) -> None:
        logs.append(f"promote:{dest.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.resolve() != src.resolve():
            dest.unlink()
        src.replace(dest)

    def pack(ed: Path, final: Path) -> Path | None:
        logs.append("pack")
        for cand in (ed / "publicar" / "video", ed.parent / "publicar" / "video"):
            if cand.is_dir():
                dest = cand / "video.mp4"
                shutil.copy2(final, dest)
                return cand
        return None

    return ApplyHooks(
        rebuild_cut=rebuild,
        render_visual=render,
        validate_final=validate,
        promote_file=promote,
        sync_pack=pack,
        probe_duration=lambda p: expected_dur,
        log=logs.append,
        progress=lambda stage, msg: logs.append(f"progress:{msg}"),
    )


def test_reuse_cut_headline_and_caption(tmp_path: Path):
    edit = _project(tmp_path)
    set_headline(edit, "NOVA HEADLINE")
    fix_caption(edit, src="perico", dst="película")
    logs: list[str] = []
    plan = plan_apply_changes(load(edit))
    assert plan["mode"] == "REUSE_CUT"
    assert plan["runTranscription"] is False
    assert plan["runAI"] is False
    out = execute_apply_plan(edit, plan, hooks=_hooks(logs))
    assert out["ok"] is True
    assert "QUICK_APPLY_REUSE_CUT" in logs
    assert "QUICK_APPLY_RENDER_VISUAL" in logs
    assert "QUICK_APPLY_SUCCESS" in logs
    assert "rebuild" not in logs
    assert (edit / "final.mp4").read_bytes().startswith(b"NEW")
    assert (edit / "cut.mp4").read_bytes().startswith(b"CUT")
    assert read_headline_lines(edit) == ["NOVA HEADLINE"]
    words = json.loads((edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))
    assert "película" in " ".join(w["text"] for w in words).lower()
    assert "perico" not in " ".join(w["text"] for w in words).lower()
    corr = load(edit)
    assert corr["dirty"]["headline"] is False
    assert corr["dirty"]["captions"] is False
    assert corr["finalStale"] is False
    assert corr["captionsTimedTo"] is not None
    assert corr["captionsTimedTo"][0]["end"] == 10.0
    assert not (edit / "final.apply.tmp.mp4").exists()


def test_rebuild_cut_remaps_pelicula(tmp_path: Path):
    edit = _project(tmp_path)
    fix_caption(edit, src="perico", dst="película")
    write_edl_ranges(edit, [
        {"source": "SRC", "start": 0.0, "end": 4.0, "beat": "HOOK"},
        {"source": "SRC", "start": 6.0, "end": 10.0, "beat": "B1"},
    ])
    before = json.loads((edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))
    assert before[1]["text"] == "película"
    assert before[1]["startMs"] == 7000
    pending = pending_caption_remap(edit)
    assert pending is not None
    assert pending[1]["text"] == "película"
    assert pending[1]["startMs"] == 5000
    logs: list[str] = []
    plan = plan_apply_changes(load(edit))
    assert plan["mode"] == "REBUILD_CUT"
    assert plan["remapCaptions"] is True
    assert "REMAP_CAPTIONS" in plan["reasons"]
    assert plan["runAI"] is False
    out = execute_apply_plan(edit, plan, hooks=_hooks(logs, expected_dur=8.0))
    assert out["ok"] is True
    assert "MANUAL_EDL_REBUILD" in logs
    assert "CAPTIONS_REMAP_APPLIED" in logs
    assert "rebuild" in logs
    words = json.loads((edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))
    assert words[1]["text"] == "película"
    assert words[1]["startMs"] == 5000
    assert words[1]["endMs"] == 7000
    corr = load(edit)
    assert corr["dirty"]["edl"] is False
    assert corr["dirty"]["captions"] is False
    assert corr["captionsTimedTo"] is not None
    assert corr["captionsTimedTo"][0]["end"] == 4.0
    assert corr["captionsTimedTo"][-1]["start"] == 6.0
    assert corr["captionsTimedToFps"] == 30
    assert corr["finalStale"] is False
    assert (edit / "cut.mp4").read_bytes().startswith(b"CUT2")
    hist = json.loads((edit / "apply_history.json").read_text(encoding="utf-8"))
    assert hist[-1]["type"] == "REBUILD_CUT"
    assert hist[-1]["success"] is True


def test_failure_keeps_old_final_and_dirty(tmp_path: Path):
    edit = _project(tmp_path)
    set_headline(edit, "NOVA")
    old = (edit / "final.mp4").read_bytes()
    logs: list[str] = []
    plan = plan_apply_changes(load(edit))
    out = execute_apply_plan(edit, plan, hooks=_hooks(logs, fail="render"))
    assert out["ok"] is False
    assert "vídeo anterior foi mantido" in out["message"].lower()
    assert (edit / "final.mp4").read_bytes() == old
    assert not (edit / "final.apply.tmp.mp4").exists()
    corr = load(edit)
    assert corr["dirty"]["headline"] is True
    assert corr["finalStale"] is True
    assert read_headline_lines(edit) == ["NOVA"]


def test_validate_fail_keeps_dirty(tmp_path: Path):
    edit = _project(tmp_path)
    fix_caption(edit, src="perico", dst="película")
    logs: list[str] = []
    plan = plan_apply_changes(load(edit))
    out = execute_apply_plan(edit, plan, hooks=_hooks(logs, fail="validate"))
    assert out["ok"] is False
    assert (edit / "final.mp4").read_bytes().startswith(b"OLD")
    assert load(edit)["dirty"]["captions"] is True


def test_pack_updates_mp4_only(tmp_path: Path):
    edit = _project(tmp_path)
    pub = tmp_path / "publicar" / "video"
    pub.mkdir(parents=True)
    (pub / "video.mp4").write_bytes(b"STALE" * 100)
    (pub / "legenda.txt").write_text("não mexer", encoding="utf-8")
    (pub / "capa.jpg").write_bytes(b"capa")
    set_headline(edit, "NOVA HEADLINE")
    logs: list[str] = []
    out = execute_apply_plan(edit, plan_apply_changes(load(edit)), hooks=_hooks(logs))
    assert out["ok"] is True
    assert (pub / "video.mp4").read_bytes().startswith(b"NEW")
    assert (pub / "legenda.txt").read_text(encoding="utf-8") == "não mexer"
    assert (pub / "capa.jpg").read_bytes() == b"capa"


def test_noop():
    logs: list[str] = []
    plan = plan_apply_changes({"headline": False, "captions": False, "edl": False, "style": False})
    assert plan["mode"] == "NOOP"
    # execute_apply_plan precisa de um dir; NOOP sai antes dos hooks de mídia
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out = execute_apply_plan(Path(d), plan, hooks=_hooks(logs))
    assert out["ok"] is True
    assert out.get("noop") is True
    assert "rebuild" not in logs
    assert "render" not in logs


def test_progress_messages_reuse(tmp_path: Path):
    edit = _project(tmp_path)
    set_headline(edit, "X")
    logs: list[str] = []
    execute_apply_plan(edit, plan_apply_changes(load(edit)), hooks=_hooks(logs))
    msgs = [x for x in logs if x.startswith("progress:")]
    assert "progress:Preparando alterações..." in msgs
    assert "progress:Aplicando edição..." in msgs
    assert "progress:Finalizando vídeo..." in msgs


def test_progress_messages_rebuild(tmp_path: Path):
    edit = _project(tmp_path)
    write_edl_ranges(edit, [
        {"source": "SRC", "start": 0.0, "end": 4.0},
        {"source": "SRC", "start": 6.0, "end": 10.0},
    ])
    logs: list[str] = []
    execute_apply_plan(edit, plan_apply_changes(load(edit)), hooks=_hooks(logs))
    msgs = [x for x in logs if x.startswith("progress:")]
    assert "progress:Atualizando cortes..." in msgs
    assert "progress:Aplicando edição..." in msgs
    assert "progress:Finalizando vídeo..." in msgs


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_reuse_cut_headline_and_caption(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_rebuild_cut_remaps_pelicula(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_failure_keeps_old_final_and_dirty(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_validate_fail_keeps_dirty(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_pack_updates_mp4_only(Path(d))
    test_noop()
    with tempfile.TemporaryDirectory() as d:
        test_progress_messages_reuse(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_progress_messages_rebuild(Path(d))
    print("ok")
