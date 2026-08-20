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


def test_set_headline_answer_writes_hook_answer_lines(tmp_path):
    import json
    from app.quick_corrections import set_headline_answer

    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    ed_path = edit / "remotion" / "public" / "edit-data.json"
    ed_path.write_text(json.dumps({"hook": {"enabled": True, "lines": ["P?"]}}), encoding="utf-8")
    r = set_headline_answer(edit, "Aguenta sim olha isso")
    assert r["ok"] is True
    data = json.loads(ed_path.read_text(encoding="utf-8"))
    assert data["hook"]["answerLines"]
    assert data["hook"]["lines"] == ["P?"]  # pergunta intacta


# ------------------------------------------- posição da headline (arrastar) ----
def _projeto_com_hook(tmp_path, hook=None):
    import json

    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    p = edit / "remotion" / "public" / "edit-data.json"
    p.write_text(json.dumps({"hook": hook or {"enabled": True, "lines": ["Oi"]}}),
                 encoding="utf-8")
    return edit, p


def test_set_headline_pos_grava_padding_top(tmp_path):
    import json
    from app.quick_corrections import set_headline_pos

    edit, p = _projeto_com_hook(tmp_path)
    r = set_headline_pos(edit, 814)
    assert r["ok"] is True and r["paddingTop"] == 814
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["hook"]["paddingTop"] == 814
    assert data["hook"]["lines"] == ["Oi"]      # texto intacto


def test_set_headline_pos_pela_base(tmp_path):
    """A manchete se ancora pelo rodapé — arrastar tem de mexer no
    paddingBottom, não no paddingTop, senão ela ignora o valor."""
    import json
    from app.quick_corrections import set_headline_pos

    edit, p = _projeto_com_hook(tmp_path, {"enabled": True, "style": "manchete"})
    r = set_headline_pos(edit, 439, base="bottom")
    assert r["ok"] is True and r["paddingBottom"] == 439
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["hook"]["paddingBottom"] == 439
    assert "paddingTop" not in data["hook"]


def test_set_headline_pos_nao_deixa_sair_da_tela(tmp_path):
    """Fora do quadro a headline sumiria sem aviso nenhum."""
    from app.quick_corrections import set_headline_pos

    edit, _ = _projeto_com_hook(tmp_path)
    assert set_headline_pos(edit, -500)["paddingTop"] == 0
    assert set_headline_pos(edit, 99999)["paddingTop"] == 1560


def test_set_headline_pos_recusa_lixo(tmp_path):
    from app.quick_corrections import set_headline_pos

    edit, _ = _projeto_com_hook(tmp_path)
    for ruim in ("", None, "abc", float("nan"), float("inf")):
        assert set_headline_pos(edit, ruim)["ok"] is False, ruim


def test_op_set_headline_pos_no_dispatcher(tmp_path):
    import json
    from app.quick_corrections import handle

    edit, p = _projeto_com_hook(tmp_path)
    handle(edit, {"op": "set_headline_pos", "paddingTop": 700})
    assert json.loads(p.read_text(encoding="utf-8"))["hook"]["paddingTop"] == 700
    handle(edit, {"op": "set_headline_pos", "paddingBottom": 210})
    assert json.loads(p.read_text(encoding="utf-8"))["hook"]["paddingBottom"] == 210


def test_ancoras_cobrem_todos_os_estilos_de_headline():
    """O editor desenha a headline arrastável a partir desta tabela. Se um
    estilo novo ficar de fora, ele aparece no lugar errado no preview."""
    from app.render_proprio import Renderizador, ancoras_de_headline

    anc = ancoras_de_headline()
    assert set(anc) == set(Renderizador.HL_STYLES)
    for nome, a in anc.items():
        assert a["base"] in ("top", "bottom"), nome
        assert isinstance(a["px"], int) and 0 <= a["px"] <= 1920, nome
    # a manchete é a única que se ancora pela base
    assert anc["manchete"]["base"] == "bottom"
    assert [n for n, a in anc.items() if a["base"] == "bottom"] == ["manchete"]


# --------------------------------------------- posição da legenda (arrastar) ----
def test_set_caption_pos_stacked(tmp_path):
    """stacked guarda a altura como FRAÇÃO da altura, com o bloco centrado em
    h/2 + h*offset — é o que os dois motores leem."""
    import json
    from app.quick_corrections import set_caption_pos

    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    p = edit / "remotion" / "public" / "edit-data.json"
    p.write_text(json.dumps({"captions": {"style": "stacked"}}), encoding="utf-8")
    r = set_caption_pos(edit, 1259.5)          # o padrão 0.156
    assert r["ok"] is True
    assert abs(r["stackedOffsetY"] - 0.156) < 0.001
    assert json.loads(p.read_text(encoding="utf-8"))["captions"]["stackedOffsetY"]


def test_set_caption_pos_impacto_usa_a_base(tmp_path):
    import json
    from app.quick_corrections import set_caption_pos

    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    p = edit / "remotion" / "public" / "edit-data.json"
    p.write_text(json.dumps({"captions": {"style": "impacto"}}), encoding="utf-8")
    r = set_caption_pos(edit, 1490)            # 1920 - 430
    assert r["paddingBottom"] == 430
    assert "stackedOffsetY" not in json.loads(p.read_text(encoding="utf-8"))["captions"]


def test_set_caption_pos_recusa_estilo_sem_altura_livre(tmp_path):
    """A família `simples` posiciona por valor discreto — arrastar não teria
    onde gravar, e gravar num campo que ninguém lê seria mentira na tela."""
    import json
    from app.quick_corrections import set_caption_pos

    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    p = edit / "remotion" / "public" / "edit-data.json"
    p.write_text(json.dumps({"captions": {"style": "simples"}}), encoding="utf-8")
    r = set_caption_pos(edit, 900)
    assert r["ok"] is False and "simples" in r["error"]


def test_conversao_de_altura_da_legenda_ida_e_volta():
    from app.render_proprio import (
        ancoras_de_legenda, legenda_valor_para_y, legenda_y_para_valor,
    )

    for estilo, a in ancoras_de_legenda().items():
        y = legenda_valor_para_y(estilo, None)
        chave, valor = legenda_y_para_valor(estilo, y)
        assert chave == a["chave"], estilo
        assert abs(float(valor) - float(a["padrao"])) < 0.002, estilo
        # e uma altura arbitrária também tem de voltar
        chave2, v2 = legenda_y_para_valor(estilo, 700)
        assert abs(legenda_valor_para_y(estilo, v2) - 700) < 2.0, estilo
    assert legenda_y_para_valor("simples", 900) is None
