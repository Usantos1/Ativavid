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
    replace_caption_tokens,
    tokens_match,
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
    joined = " ".join(t for t in texts if t)
    assert any("Película" in t for t in texts)
    assert "celular dele" in joined


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


def _line(*parts):
    words = []
    t = 0
    for text in parts:
        words.append({"text": text, "startMs": t, "endMs": t + 200})
        t += 200
    return words


def test_tokens_match_word_boundary():
    assert tokens_match("amassa.", "amassa")
    assert tokens_match("Amassa", "amassa")
    assert tokens_match("AMASSA!", "amassa")
    assert not tokens_match("amassado", "amassa")
    assert not tokens_match("desamassa", "amassa")
    assert not tokens_match("a", "amassa")
    assert not tokens_match("A", "amassa")
    assert not tokens_match("massa", "amassa")


def test_amassa_does_not_hit_neighbors():
    words = _line("essa", "película", "amassa", "muito", "a", "amassado", "desamassa")
    n = apply_replacements_to_words(words, [{"from": "amassa", "to": "TESTELEG"}])
    assert n == 1
    assert [w["text"] for w in words] == [
        "essa", "película", "TESTELEG", "muito", "a", "amassado", "desamassa",
    ]


def test_two_occurrences_need_selected_cue():
    words = [
        {"text": "amassa", "startMs": 1000, "endMs": 1400, "id": "w1"},
        {"text": "depois", "startMs": 1400, "endMs": 1800},
        {"text": "amassa", "startMs": 4000, "endMs": 4400, "id": "w2"},
    ]
    untouched = [dict(w) for w in words]
    n = apply_replacements_to_words(words, [{"from": "amassa", "to": "TESTELEG"}])
    assert n == 0
    assert [w["text"] for w in words] == [w["text"] for w in untouched]
    out = replace_caption_tokens(words, [{"from": "amassa", "to": "TESTELEG"}])
    assert out["ambiguous"] is True
    assert out["matches"] == 2

    n = apply_replacements_to_words(words, [{"from": "amassa", "to": "TESTELEG", "tokenId": "w2"}])
    assert n == 1
    assert words[0]["text"] == "amassa"
    assert words[2]["text"] == "TESTELEG"


def test_clicked_token_id_skips_text_search():
    words = [
        {"text": "feliz.", "startMs": 8000, "endMs": 9100, "id": "cta9"},
        {"text": "feliz.", "startMs": 2000, "endMs": 2600, "id": "main3"},
    ]
    n = apply_replacements_to_words(words, [{"from": "feliz.", "to": "alegre", "tokenId": "cta9"}])
    assert n == 1
    assert words[0]["text"].startswith("alegre")
    assert words[1]["text"].startswith("feliz")


def test_two_occurrences_by_time_range():
    words = [
        {"text": "amassa.", "startMs": 1000, "endMs": 1400},
        {"text": "amassa.", "startMs": 4000, "endMs": 4400},
    ]
    n = apply_replacements_to_words(words, [{"from": "amassa", "to": "TESTELEG", "start": 3.9, "end": 4.5}])
    assert n == 1
    assert words[0]["text"] == "amassa."
    assert words[1]["text"] == "TESTELEG."


def test_whole_phrase_exact():
    words = _line("essa", "película", "amassa", "muito")
    n = apply_replacements_to_words(words, [{
        "from": "essa película amassa muito",
        "to": "essa película TESTELEG demais",
    }])
    assert n == 1
    assert [w["text"] for w in words] == ["essa", "película", "TESTELEG", "demais"]


def test_text_word_boundary():
    src = "essa película amassa muito"
    assert apply_replacements_to_text(src, [{"from": "amassa", "to": "TESTELEG"}]) == "essa película TESTELEG muito"
    assert apply_replacements_to_text("amassa.", [{"from": "amassa", "to": "TESTELEG"}]) == "TESTELEG."
    assert apply_replacements_to_text("Amassa", [{"from": "amassa", "to": "TESTELEG"}]) == "TESTELEG"
    assert apply_replacements_to_text("amassado", [{"from": "amassa", "to": "TESTELEG"}]) == "amassado"
    assert apply_replacements_to_text("desamassa", [{"from": "amassa", "to": "TESTELEG"}]) == "desamassa"
    assert apply_replacements_to_text("a película amassa", [{"from": "a", "to": "X"}]) == "X película amassa"
    assert apply_replacements_to_text("a película amassa", [{"from": "amassa", "to": "TESTELEG"}]) == "a película TESTELEG"


def test_fix_caption_ambiguous_does_not_write(tmp_path: Path):
    public = tmp_path / "remotion" / "public"
    public.mkdir(parents=True)
    original = [
        {"text": "amassa", "startMs": 10, "endMs": 40},
        {"text": "amassa", "startMs": 80, "endMs": 120},
    ]
    (public / "captions.json").write_text(json.dumps(original), encoding="utf-8")
    out = apply_caption_fixes(tmp_path, [{"from": "amassa", "to": "TESTELEG"}])
    assert out["ok"] is False
    assert out["ambiguous"] is True
    caps = json.loads((public / "captions.json").read_text(encoding="utf-8"))
    assert [c["text"] for c in caps] == ["amassa", "amassa"]


if __name__ == "__main__":
    import tempfile

    test_replace_perico_and_sardelho()
    test_cta_cursinho_becomes_percent()
    test_ai_fix_captions_action()
    test_tokens_match_word_boundary()
    test_amassa_does_not_hit_neighbors()
    test_two_occurrences_need_selected_cue()
    test_clicked_token_id_skips_text_search()
    test_two_occurrences_by_time_range()
    test_whole_phrase_exact()
    test_text_word_boundary()
    with tempfile.TemporaryDirectory() as d:
        test_apply_writes_files(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_stores_fixes_for_later_jobs(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_fix_also_updates_hook(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_fix_caption_ambiguous_does_not_write(Path(d))
    print("ok")
