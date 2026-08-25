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


def test_a_guarda_nao_engole_o_take_de_outra_fonte():
    """Os tempos de cada take são LOCAIS do arquivo dele: o take 2 começa em
    0,0 de novo. Ordenar e fundir a lista inteira por `start`, ignorando
    `source`, intercalava os arquivos e engolia os ranges do take curto
    dentro de um range longo do take 1.

    Medido nos projetos do usuário: **5 projetos multi-take onde uma fonte
    inteira sumiu do EDL** — três deles o take de CTA que ele gravou e anexou,
    dois a `Parte_2` de uma gravação em duas partes. Sem erro nenhum: o take
    simplesmente não aparece no vídeo."""
    from app.editing_intent import _insert_range

    ranges = [
        {"source": "IMG_4046", "start": 0.0, "end": 40.0, "beat": "HOOK",
         "quote": "", "reason": "", "gain_db": 0.0},
        {"source": "IMG_4046", "start": 50.0, "end": 90.0, "beat": None,
         "quote": "", "reason": "", "gain_db": 0.0},
        {"source": "IMG_4048", "start": 0.4, "end": 3.0, "beat": "CTA",
         "quote": "", "reason": "", "gain_db": 0.0},
    ]
    out = _insert_range(ranges, 95.0, 98.0, "KEEP", "teste")
    assert {r["source"] for r in out} == {"IMG_4046", "IMG_4048"}
    # o CTA continua inteiro, no fim, com o beat dele
    cta = [r for r in out if r["source"] == "IMG_4048"]
    assert len(cta) == 1 and cta[0]["end"] == 3.0 and cta[0]["beat"] == "CTA"
    assert out[-1]["source"] == "IMG_4048", "a ordem do corte tem de valer"
    # e o beat do CTA não contamina o primeiro range da outra fonte
    assert out[0]["beat"] == "HOOK"


def test_a_fusao_dentro_da_mesma_fonte_continua_valendo():
    from app.editing_intent import _insert_range

    r = [{"source": "A", "start": 0.0, "end": 5.0, "beat": None,
          "quote": "", "reason": "", "gain_db": 0.0}]
    assert len(_insert_range(r, 5.05, 8.0, "KEEP", "t")) == 1     # encosta: funde
    assert len(_insert_range(r, 20.0, 25.0, "KEEP", "t")) == 2    # longe: não


def _r(**kw):
    return {"quote": "", "reason": "", "gain_db": 0.0, **kw}


def test_preserve_cta_nao_estica_um_take_de_outra_fonte():
    """`regions` e `duration_s` são da fonte de índice 0. Esticar o ÚLTIMO
    range da lista com um instante desse relógio só faz sentido se ele for
    dessa mesma fonte — senão pede um trecho que não existe.

    Medido num projeto real: `cta_IMG_0098 0.41-0.90` virava `0.41-84.2`, ou
    seja, 84 s de um arquivo de 7 s."""
    from app.editing_intent import guard_ranges

    ranges = [_r(source="IMG_1631", start=0.0, end=40.0, beat="HOOK"),
              _r(source="cta_IMG_0098", start=0.41, end=0.90, beat="CTA")]
    out = guard_ranges([dict(r) for r in ranges],
                       preset={"editingIntent": "dynamic"},
                       regions=[(0.0, 30.0), (60.0, 84.2)], duration_s=84.6)
    cta = [r for r in out if r["source"] == "cta_IMG_0098"]
    assert len(cta) == 1, out
    assert cta[0]["end"] <= 1.0, cta


def test_preserve_cta_continua_esticando_em_fonte_unica():
    """O comportamento que a guarda existe para ter, quando faz sentido."""
    from app.editing_intent import guard_ranges

    out = guard_ranges([_r(source="A", start=0.0, end=40.0, beat="HOOK")],
                       preset={"editingIntent": "dynamic"},
                       regions=[(0.0, 30.0), (60.0, 84.2)], duration_s=84.6)
    assert out[-1]["end"] == 84.2, out
    assert out[-1]["beat"] == "CTA"


def test_preserve_cta_nao_passa_da_duracao_da_fonte():
    from app.editing_intent import guard_ranges

    out = guard_ranges([_r(source="A", start=0.0, end=10.0, beat="HOOK")],
                       preset={"editingIntent": "dynamic"},
                       regions=[(0.0, 5.0), (20.0, 99.0)], duration_s=30.0)
    assert out[-1]["end"] <= 30.0, out


def test_rotulo_do_modelo_nao_carimba_fala_unica():
    """Um drop de 25s rotulado "repetition" carimbava TODA fala dentro dele.
    Caso real (24/08, "Cliente foi só pelo cafezinho"): o Vídeo completo
    entregou 56s de um vídeo de 2:01 — menos que a Edição leve — porque
    "Vou esperar o cafezinho ali sentada, tá bom?" herdou o rótulo da
    cantoria vizinha. Rótulo do modelo só vale com evidência na frase."""
    phrases = [
        {"start": 0.0, "end": 4.0, "text": "Abertura do vídeo com fala real"},
        {"start": 68.0, "end": 71.0, "text": "A sua mão que me sustenta."},
        {"start": 72.0, "end": 75.0, "text": "A sua mão que me sustenta."},
        {"start": 76.0, "end": 80.0,
         "text": "Vou esperar o cafezinho ali sentada, tá bom?"},
    ]
    drops = [{"start": 68.0, "end": 80.0, "class": "repetition"}]
    assert classify_complete_removal(phrases[2], phrases, drops=drops) \
        == "repetition"
    assert classify_complete_removal(phrases[3], phrases, drops=drops) is None


def test_rotulo_silence_nao_apaga_frase_com_palavras():
    phrases = [
        {"start": 0.0, "end": 4.0, "text": "Abertura do vídeo com fala real"},
        {"start": 6.0, "end": 9.0, "text": "É, chegou o cafezinho? Chegou."},
    ]
    drops = [{"start": 5.0, "end": 10.0, "class": "silence"}]
    assert classify_complete_removal(phrases[1], phrases, drops=drops) is None


def test_frase_que_contem_refrao_nao_e_repeticao():
    """`_near_dup` aceitava continência nos DOIS sentidos: a frase que
    CONTÉM o refrão repetido era marcada como repetição, e a fala única
    grudada nela morria junto ("A sua mão que me sustenta. Você tá feliz
    hoje, hein?"). Repetição removível é a frase cujo texto inteiro já
    existe em outro lugar — direcional."""
    phrases = [
        {"start": 0.0, "end": 3.0, "text": "A sua mão que me sustenta."},
        {"start": 4.0, "end": 8.0,
         "text": "A sua mão que me sustenta. Você tá feliz hoje, hein?"},
    ]
    # a mista NAO e repeticao (contem fala unica)...
    assert classify_complete_removal(phrases[1], phrases) is None
    # ...mas o refrao puro, contido na mista, continua sendo
    assert classify_complete_removal(phrases[0], phrases) == "repetition"
