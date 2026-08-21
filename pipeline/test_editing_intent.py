"""Guards de intenção — sem motor de render."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.editing_intent import (
    classify_complete_removal,
    detect_semantic_units,
    enforce_complete_edl,
    guard_ranges,
    looks_like_cta,
    normalize,
    suggest_intent,
)


def test_suggest_long_is_complete():
    assert suggest_intent(120) == "complete"
    assert suggest_intent(40) == "dynamic"


def test_shorts_defaults_relax_hook_cta():
    d = normalize({"editingIntent": "shorts"})
    assert d["preserveHook"] is False
    assert d["preserveCTA"] is False
    assert d["preserveCompleteSentences"] is True


def test_hook_is_restored():
    regions = [(0.2, 6.0), (8.0, 20.0), (40.0, 48.0)]
    ranges = [{"source": "SRC", "start": 8.0, "end": 20.0, "beat": "B1"}]
    out = guard_ranges(
        ranges,
        preset={"editingIntent": "complete", "preserveHook": True, "preserveCTA": True},
        regions=regions,
    )
    assert out[0]["start"] <= 0.3
    assert out[0]["beat"] == "HOOK"


def test_cta_is_extended():
    regions = [(0.2, 6.0), (8.0, 20.0), (40.0, 48.0)]
    ranges = [
        {"source": "SRC", "start": 0.2, "end": 6.0, "beat": "HOOK"},
        {"source": "SRC", "start": 8.0, "end": 20.0, "beat": "B1"},
        {"source": "SRC", "start": 40.0, "end": 42.5, "beat": "B2"},
    ]
    out = guard_ranges(
        ranges,
        preset={"editingIntent": "dynamic", "preserveHook": True, "preserveCTA": True},
        regions=regions,
    )
    assert out[-1]["end"] >= 47.9
    assert out[-1]["beat"] == "CTA"


def test_protected_range_kept():
    regions = [(0.0, 10.0), (20.0, 30.0)]
    ranges = [{"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"}]
    out = guard_ranges(
        ranges,
        preset={
            "editingIntent": "shorts",
            "preserveHook": False,
            "preserveCTA": False,
            "protectedRanges": [{"start": 20.0, "end": 30.0}],
        },
        regions=regions,
    )
    assert any(r["start"] <= 20.1 and r["end"] >= 29.8 for r in out)


def test_cta_phrase():
    full = "Se você gostou desse conteúdo, me segue para não perder os próximos vídeos."
    cut = "Se você gostou desse conteúdo, me segue para"
    assert looks_like_cta(full)
    assert looks_like_cta(cut)


def test_complete_restores_first_packed_block(tmp_path: Path | None = None):
    root = tmp_path or Path(tempfile.mkdtemp(prefix="complete_guard_"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "takes_packed.md").write_text(
        "## parte_1\n"
        "  [000.00-018.24] S0 Misericórdia. O que é isso? Não é, pai? Aham, é sim, filha.\n"
        "  [021.12-022.84] S0 Deixa eu ver de novo\n"
        "  [092.54-093.06] S0 Obrigado\n",
        encoding="utf-8",
    )
    regions = [(0.0, 18.24), (21.12, 22.84), (92.54, 93.06)]
    ranges = [
        {"source": "SRC", "start": 0.83, "end": 1.50, "beat": "HOOK", "reason": "punchline"},
        {"source": "SRC", "start": 2.54, "end": 11.24, "beat": "B1", "reason": "ritmo"},
        {"source": "SRC", "start": 21.12, "end": 22.84, "beat": "B2", "reason": "keep"},
        {"source": "SRC", "start": 92.54, "end": 93.06, "beat": "CTA", "reason": "cta"},
    ]
    out = guard_ranges(
        ranges,
        preset={"editingIntent": "complete", "preserveHook": True, "preserveCTA": True},
        regions=regions,
        edit_dir=root,
        source_stem="parte_1",
    )
    first_cov = sum(
        max(0.0, min(18.24, float(r["end"])) - max(0.0, float(r["start"])))
        for r in out
    )
    assert first_cov >= 17.0
    mid = sum(
        max(0.0, min(22.84, float(r["end"])) - max(21.12, float(r["start"])))
        for r in out
    )
    assert mid >= 1.5


def test_complete_rejects_rhythm_keeps_repetition_class():
    phrases = [
        {"start": 0.0, "end": 5.0, "text": "Primeiro bloco inteiro"},
        {"start": 6.0, "end": 8.0, "text": "espera um pouco espera um pouco"},
        {"start": 9.0, "end": 11.0, "text": "espera um pouco espera um pouco"},
        {"start": 12.0, "end": 14.0, "text": "e agora a conclusão"},
    ]
    ranges = [
        {"source": "SRC", "start": 0.0, "end": 5.0, "beat": "HOOK"},
        {"source": "SRC", "start": 6.0, "end": 8.0, "beat": "B1"},
        {"source": "SRC", "start": 12.0, "end": 14.0, "beat": "CTA"},
    ]
    regions = [(0.0, 5.0), (6.0, 8.0), (9.0, 11.0), (12.0, 14.0)]
    assert classify_complete_removal(phrases[2], phrases) == "repetition"
    assert classify_complete_removal(
        {"start": 9.0, "end": 11.0, "text": "frase unica de contexto"},
        phrases,
        drops=[{"start": 9.0, "end": 11.0, "class": "punchline"}],
    ) is None
    out = enforce_complete_edl(ranges, phrases=phrases, regions=regions)
    mid = sum(
        max(0.0, min(11.0, float(r["end"])) - max(9.0, float(r["start"])))
        for r in out
    )
    assert mid < 0.3


def _write_packed(root: Path, stem: str, phrases: list[dict]) -> None:
    lines = [f"## {stem}\n"]
    for p in phrases:
        lines.append(
            f"  [{p['start']:06.2f}-{p['end']:06.2f}] S0 {p['text']}\n"
        )
    (root / "takes_packed.md").write_text("".join(lines), encoding="utf-8")


def test_dynamic_short_joke_keeps_setup_payoff(tmp_path: Path | None = None):
    root = tmp_path or Path(tempfile.mkdtemp(prefix="dyn_joke_"))
    root.mkdir(parents=True, exist_ok=True)
    phrases = [
        {"start": 0.0, "end": 1.4, "text": "A senhora está tranquila?"},
        {"start": 1.6, "end": 2.8, "text": "Pode deixar que a gente avisa"},
        {"start": 3.0, "end": 4.43, "text": "Salbido, salbido"},
    ]
    _write_packed(root, "clip", phrases)
    ranges = [{"source": "SRC", "start": 3.0, "end": 4.43, "beat": "HOOK"}]
    regions = [(0.0, 1.4), (1.6, 2.8), (3.0, 4.43)]
    units = detect_semantic_units(phrases, duration_s=4.43)
    assert units and units[0]["preserveTogether"] is True
    out = guard_ranges(
        ranges,
        preset={"editingIntent": "dynamic", "preserveHook": True, "preserveCTA": True},
        regions=regions,
        duration_s=4.43,
        edit_dir=root,
        source_stem="clip",
    )
    for a, b in regions:
        cov = sum(max(0.0, min(b, float(r["end"])) - max(a, float(r["start"]))) for r in out)
        assert cov >= 0.85 * (b - a), (a, b, cov, out)


def test_dynamic_long_nonjoke_can_drop_middle(tmp_path: Path | None = None):
    root = tmp_path or Path(tempfile.mkdtemp(prefix="dyn_tut_"))
    root.mkdir(parents=True, exist_ok=True)
    phrases = [
        {"start": 0.0, "end": 5.0, "text": "Hoje vou ensinar o passo um do tutorial"},
        {"start": 8.0, "end": 12.0, "text": "Isso aqui e so um aparte sem funcao"},
        {"start": 20.0, "end": 30.0, "text": "Agora o passo dois da instalacao"},
        {"start": 40.0, "end": 48.0, "text": "Pronto, esse foi o tutorial"},
    ]
    _write_packed(root, "aula", phrases)
    ranges = [
        {"source": "SRC", "start": 0.0, "end": 5.0, "beat": "HOOK"},
        {"source": "SRC", "start": 20.0, "end": 30.0, "beat": "B1"},
        {"source": "SRC", "start": 40.0, "end": 48.0, "beat": "CTA"},
    ]
    regions = [(0.0, 5.0), (8.0, 12.0), (20.0, 30.0), (40.0, 48.0)]
    out = guard_ranges(
        ranges,
        preset={"editingIntent": "dynamic", "preserveHook": True, "preserveCTA": True},
        regions=regions,
        duration_s=50.0,
        edit_dir=root,
        source_stem="aula",
    )
    mid = sum(
        max(0.0, min(12.0, float(r["end"])) - max(8.0, float(r["start"])))
        for r in out
    )
    assert mid < 0.3


def test_dynamic_does_not_restore_mid_phrase():
    regions = [(0.2, 6.0), (8.0, 20.0), (21.0, 23.0), (40.0, 48.0)]
    ranges = [
        {"source": "SRC", "start": 0.2, "end": 6.0, "beat": "HOOK"},
        {"source": "SRC", "start": 8.0, "end": 20.0, "beat": "B1"},
        {"source": "SRC", "start": 40.0, "end": 48.0, "beat": "CTA"},
    ]
    out = guard_ranges(
        ranges,
        preset={"editingIntent": "dynamic", "preserveHook": True, "preserveCTA": True},
        regions=regions,
    )
    mid = sum(
        max(0.0, min(23.0, float(r["end"])) - max(21.0, float(r["start"])))
        for r in out
    )
    assert mid < 0.2


if __name__ == "__main__":
    tests = [
        test_suggest_long_is_complete,
        test_shorts_defaults_relax_hook_cta,
        test_hook_is_restored,
        test_cta_is_extended,
        test_protected_range_kept,
        test_cta_phrase,
        test_complete_restores_first_packed_block,
        test_complete_rejects_rhythm_keeps_repetition_class,
        test_dynamic_does_not_restore_mid_phrase,
        test_dynamic_short_joke_keeps_setup_payoff,
        test_dynamic_long_nonjoke_can_drop_middle,
    ]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print("ALL_OK")


# ------------------------------------ frases depois de 16min40s (bug real) ----
def test_frase_depois_de_1000s_continua_sendo_lida(tmp_path):
    r"""O escritor usa `f"{seconds:06.2f}"`, que preenche até 3 dígitos mas NÃO
    trunca: a partir de 1000,00s (16min40s) ele emite 4. A regex tinha
    `\d{3}` e parava de casar exatamente ali.

    Isso não falhava com erro — a frase só sumia da lista. E a lista alimenta
    a guarda que RESTAURA fala que a IA quis cortar, então a proteção parava
    de valer no resto de todo vídeo longo (podcast, "editar completo")."""
    from app.editing_intent import load_packed_phrases

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "takes_packed.md").write_text(
        "## IMG_1\n"
        "[012.30-015.80] S1 antes de dezesseis minutos\n"
        "[999.00-999.90] S1 no limite antigo\n"
        "[1000.00-1004.50] S1 logo depois do limite\n"
        "[3600.00-3605.00] S1 uma hora de video\n",
        encoding="utf-8")
    fr = load_packed_phrases(edit, "IMG_1")
    inicios = [p["start"] for p in fr]
    assert 1000.00 in inicios, "a frase de 16min40s tem de ser lida"
    assert 3600.00 in inicios, "e a de uma hora também"
    assert len(fr) == 4


def test_regex_da_frase_vive_num_lugar_so():
    r"""A cópia em pipeline/smoke_intent_report.py tinha o mesmo `\d{3}` e
    teria mascarado o conserto no smoke."""
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent
             / "smoke_intent_report.py").read_text(encoding="utf-8")
    assert "from app.editing_intent import PHRASE_RE" in fonte
    assert "PHRASE_RE = re.compile(" not in fonte
