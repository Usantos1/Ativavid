"""Correção de legenda — só JSON, sem render."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.caption_fixes import (
    apply_caption_fixes,
    apply_replacements_to_text,
    apply_replacements_to_words,
    normalize_cta_asr,
)
from app.ai_actions import apply_actions_to_edits, parse_deterministic_command


def test_replace_perico_and_sardelho():
    words = [
        {"text": "uma", "startMs": 100, "endMs": 200},
        {"text": "pericô...", "startMs": 200, "endMs": 400},
        {"text": "pro", "startMs": 400, "endMs": 500},
        {"text": "sardelho,", "startMs": 500, "endMs": 800},
    ]
    n = apply_replacements_to_words(words, [
        {"from": "uma pericô", "to": "uma Película"},
        {"from": "pro sardelho", "to": "pro celular dele"},
    ])
    assert n >= 2
    assert words[0]["startMs"] == 100
    joined = " ".join(w["text"] for w in words if w["text"])
    assert "Película" in joined
    assert "celular dele" in joined
    assert "pericô" not in joined.lower()
    assert "sardelho" not in joined.lower()


def test_apply_writes_files(tmp_path: Path):
    public = tmp_path / "remotion" / "public"
    public.mkdir(parents=True)
    (public / "captions.json").write_text(
        json.dumps([
            {"text": "pericô...", "startMs": 10, "endMs": 40},
            {"text": "sardelho,", "startMs": 40, "endMs": 80},
        ]),
        encoding="utf-8",
    )
    (public / "caption-cues.json").write_text(
        json.dumps([{"lines": [[{"text": "pericô..."}], [{"text": "sardelho,"}]]}]),
        encoding="utf-8",
    )
    out = apply_caption_fixes(tmp_path, [
        {"from": "pericô", "to": "Película"},
        {"from": "sardelho", "to": "celular dele"},
    ])
    assert out["changed"] >= 2
    caps = json.loads((public / "captions.json").read_text(encoding="utf-8"))
    texts = [c["text"] for c in caps]
    assert any("Película" in t for t in texts)
    assert any("celular dele" in t for t in texts)


def test_stores_fixes_for_later_jobs(tmp_path: Path):
    public = tmp_path / "remotion" / "public"
    public.mkdir(parents=True)
    (public / "captions.json").write_text(
        json.dumps([{"text": "pericô", "startMs": 10, "endMs": 40}]),
        encoding="utf-8",
    )
    apply_caption_fixes(tmp_path, [{"from": "pericô", "to": "Película"}])
    from app.caption_fixes import load_stored_fixes
    stored = load_stored_fixes(tmp_path)
    assert stored[0]["from"] == "pericô"
    assert stored[0]["to"] == "Película"


def test_cta_cursinho_becomes_percent():
    assert "1%" in normalize_cta_asr("Segue a gente pra ficar um cursinho mais feliz")
    assert "cursinho" not in normalize_cta_asr("ficar um cursinho mais").lower()
    assert "cursinho" in normalize_cta_asr("Você fez um cursinho?")
    assert "1%" in apply_replacements_to_text("ficar um curseto mais feliz")


def test_fix_also_updates_hook(tmp_path: Path):
    public = tmp_path / "remotion" / "public"
    public.mkdir(parents=True)
    (public / "captions.json").write_text(
        json.dumps([{"text": "cursinho", "startMs": 10, "endMs": 40}]),
        encoding="utf-8",
    )
    (public / "edit-data.json").write_text(
        json.dumps({"hook": {"enabled": True, "lines": ["Segue a gente pra", "ficar um cursinho mais"]}}),
        encoding="utf-8",
    )
    out = apply_caption_fixes(tmp_path, [{"from": "cursinho", "to": "1%"}])
    assert out["changed"] >= 1
    data = json.loads((public / "edit-data.json").read_text(encoding="utf-8"))
    joined = " ".join(data["hook"]["lines"])
    assert "cursinho" not in joined.lower()
    assert "1%" in joined


def test_ai_fix_captions_action():
    d = parse_deterministic_command("troca perico por Pelicula")
    assert d is not None
    assert d["actions"][0]["action"] == "fix_captions"
    patch = apply_actions_to_edits(d["actions"])
    ops = patch["timelineOps"]
    assert ops[0]["op"] == "fix_captions"
    assert ops[0]["replacements"][0]["to"]


if __name__ == "__main__":
    import tempfile

    test_replace_perico_and_sardelho()
    test_cta_cursinho_becomes_percent()
    test_ai_fix_captions_action()
    with tempfile.TemporaryDirectory() as d:
        test_apply_writes_files(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_stores_fixes_for_later_jobs(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_fix_also_updates_hook(Path(d))
    print("ok")
