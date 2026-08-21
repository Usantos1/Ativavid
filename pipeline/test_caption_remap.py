"""Remap de legendas pelo timeline map. Sem FFmpeg, sem Whisper, sem Apply."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import (
    caption_timeline_edls,
    execute_apply_plan,
    pending_caption_remap,
    prepare_edl_apply,
)
from app.apply_plan import plan_apply_changes
from app.caption_remap import (
    OVERLAP_FAIL,
    apply_inferred_provenance,
    caption_to_provenance,
    provenance_error,
    remap_captions_between_timelines,
    remap_captions_through_edl,
    retime_captions_for_edl,
    validate_remapped_captions,
)
from app.quick_corrections import load, write_edl_ranges
from app.timeline_map import (
    build_timeline_map,
    encoded_video_frames,
    layout_jcut_spans,
    read_mp4_video_frames,
    validate_timeline_map,
)

SMOKE_EDIT = Path(r"E:\ATIVAVID\Projetos\_smoke_edl_IMG_1645\edit")

MAIN = "IMG_1645"
CTA = "cta_cta_mais_feliz"

OLD_RANGES = [
    {"source": MAIN, "start": 2.57, "end": 4.67, "beat": "HOOK"},
    {"source": MAIN, "start": 4.69, "end": 7.223, "beat": "B1"},
    {"source": MAIN, "start": 7.84, "end": 9.94, "beat": "B2"},
    {"source": MAIN, "start": 10.73, "end": 11.43, "beat": "KEEP"},
    {"source": CTA, "start": 0.0, "end": 3.4, "beat": "CTA"},
]
NEW_RANGES = [
    {**r} if r["source"] != CTA else {"source": CTA, "start": 0.0, "end": 2.7, "beat": "CTA"}
    for r in OLD_RANGES
]

OLD_JCUT = [
    {"beat": "HOOK", "source": MAIN, "video_start_in_output": 0.0,
     "video_duration": 2.033333, "audio_start_in_output": 0.0,
     "audio_duration": 2.033333, "tail_trim_frames": 2},
    {"beat": "B1", "source": MAIN, "video_start_in_output": 2.033333,
     "video_duration": 2.3, "audio_start_in_output": 1.866667,
     "audio_duration": 2.466666, "tail_trim_frames": 2},
    {"beat": "B2", "source": MAIN, "video_start_in_output": 4.333333,
     "video_duration": 1.866667, "audio_start_in_output": 4.166666,
     "audio_duration": 2.033333, "tail_trim_frames": 2},
    {"beat": "KEEP", "source": MAIN, "video_start_in_output": 6.2,
     "video_duration": 0.466667, "audio_start_in_output": 6.033333,
     "audio_duration": 0.633333, "tail_trim_frames": 2},
    {"beat": "CTA", "source": CTA, "video_start_in_output": 6.666666,
     "video_duration": 3.233333, "audio_start_in_output": 6.5,
     "audio_duration": 3.4, "tail_trim_frames": 0},
]


def _texts(caps: list) -> list[str]:
    return [str(c.get("text") or "") for c in caps if isinstance(c, dict)]


def test_layout_jcut_matches_recorded_timeline():
    spans = layout_jcut_spans(
        OLD_RANGES, fps=30.0, lead_frames=5, tail_frames=[2, 2, 2, 2, 0],
    )
    assert abs(spans[0]["audioEnd"] - 2.033333) < 0.002
    assert abs(spans[1]["outputStart"] - 1.866667) < 0.002
    assert abs(spans[-1]["outputStart"] - 6.5) < 0.002
    assert abs(spans[-1]["videoStart"] - 6.666666) < 0.002
    video = spans[-1]["videoEnd"]
    assert abs(video - 9.9) < 0.02


def test_encoded_frames_match_segments_quantization():
    assert encoded_video_frames(2.033333, 30) == 61
    assert encoded_video_frames(2.3, 30) == 69
    assert encoded_video_frames(1.866667, 30) == 57
    assert encoded_video_frames(0.466667, 30) == 15
    assert encoded_video_frames(3.233333, 30) == 97
    old_map = build_timeline_map(
        {"ranges": OLD_RANGES, "jcut_timeline": OLD_JCUT, "jcut": True, "fps": 30},
        fps=30.0,
    )
    assert old_map["outputFrames"] == 299
    assert abs(old_map["plannedDuration"] - 9.9) < 0.02
    assert abs(old_map["outputDuration"] - (299 / 30.0)) < 1e-6


def test_jcut_overlap_keeps_source_identity():
    old_map = {
        "spans": [
            {
                "source": "A", "sourceStart": 0.0, "sourceEnd": 2.0,
                "outputStart": 0.0, "outputEnd": 2.0,
                "videoStart": 0.0, "videoEnd": 2.0,
            },
            {
                "source": "B", "sourceStart": 0.0, "sourceEnd": 2.17,
                "outputStart": 1.83, "outputEnd": 4.0,
                "videoStart": 2.0, "videoEnd": 4.0,
            },
        ],
        "fps": 30, "jcut": True, "outputDuration": 4.0, "audioDuration": 4.0,
        "outputFrames": 120, "plannedDuration": 4.0,
    }
    new_map = {
        "spans": [
            {
                "source": "A", "sourceStart": 0.0, "sourceEnd": 2.0,
                "outputStart": 0.0, "outputEnd": 2.0,
                "videoStart": 0.0, "videoEnd": 2.0,
            },
            {
                "source": "B", "sourceStart": 0.0, "sourceEnd": 1.0,
                "outputStart": 1.83, "outputEnd": 2.83,
                "videoStart": 2.0, "videoEnd": 2.83,
            },
        ],
        "fps": 30, "jcut": True, "outputDuration": 2.83, "audioDuration": 2.83,
        "outputFrames": 85, "plannedDuration": 2.83,
    }
    caps = [
        {"text": "fromA", "start": 1.90, "end": 1.98,
         "source": "A", "sourceStart": 1.90, "sourceEnd": 1.98},
        {"text": "fromB", "start": 1.90, "end": 1.98,
         "source": "B", "sourceStart": 0.07, "sourceEnd": 0.15},
    ]
    out = remap_captions_between_timelines(caps, old_map, new_map)
    assert _texts(out) == ["fromA", "fromB"]
    a = next(c for c in out if c["text"] == "fromA")
    b = next(c for c in out if c["text"] == "fromB")
    assert a["source"] == "A"
    assert b["source"] == "B"
    assert abs(a["start"] - 1.90) < 0.02
    assert abs(b["start"] - 1.90) < 0.02
    bare = [
        {"text": "fromA", "start": 1.90, "end": 1.98},
        {"text": "fromB", "start": 1.90, "end": 1.98},
    ]
    assert provenance_error(bare, bare, old_map) == OVERLAP_FAIL


def test_same_source_jcut_overlap_is_not_fail():
    """J-cut da mesma fonte: overlap de áudio na saída não é ambiguidade A vs B."""
    old_map = {
        "spans": [
            {
                "source": "IMG_3935", "sourceStart": 4.0, "sourceEnd": 8.0,
                "outputStart": 0.0, "outputEnd": 4.0,
                "videoStart": 0.0, "videoEnd": 4.0,
            },
            {
                "source": "IMG_3935", "sourceStart": 8.3, "sourceEnd": 11.6,
                "outputStart": 3.7, "outputEnd": 7.0,
                "videoStart": 4.0, "videoEnd": 7.0,
            },
        ],
        "fps": 30, "jcut": True, "outputDuration": 7.0, "audioDuration": 7.0,
        "outputFrames": 210, "plannedDuration": 7.0,
    }
    cap = {"text": "E", "start": 3.80, "end": 4.10}
    assert provenance_error([cap], [cap], old_map) is None
    prov = caption_to_provenance(cap, old_map)
    assert prov is not None
    assert prov["source"] == "IMG_3935"


def test_same_source_unmatched_tokens_do_not_look_like_duplicates():
    """Token sem provenance no J-cut da mesma fonte não dispara duplicata falsa."""
    old_map = {
        "spans": [
            {
                "source": "IMG_3935", "sourceStart": 4.0, "sourceEnd": 8.0,
                "outputStart": 0.0, "outputEnd": 4.0,
                "videoStart": 0.0, "videoEnd": 4.0,
            },
            {
                "source": "IMG_3935", "sourceStart": 8.3, "sourceEnd": 11.6,
                "outputStart": 3.7, "outputEnd": 7.0,
                "videoStart": 4.0, "videoEnd": 7.0,
            },
        ],
        "fps": 30, "jcut": True, "outputDuration": 7.0, "audioDuration": 7.0,
        "outputFrames": 210, "plannedDuration": 7.0,
    }
    caps = [
        {"text": "hello", "start": 0.50, "end": 0.80,
         "source": "IMG_3935", "sourceStart": 4.50, "sourceEnd": 4.80},
        {"text": "E", "start": 3.80, "end": 4.10},
    ]
    filled = apply_inferred_provenance(caps, old_map)
    assert filled[1]["source"] == "IMG_3935"
    out = remap_captions_between_timelines(filled, old_map, old_map)
    assert _texts(out) == ["hello", "E"]
    assert validate_remapped_captions(filled, out, old_map) is None


def test_new_map_does_not_reuse_stale_cta_jcut():
    new_edl = {
        "ranges": NEW_RANGES,
        "jcut_timeline": OLD_JCUT,
        "jcut": True,
        "fps": 30,
    }
    new_map = build_timeline_map(new_edl, fps=30.0, prior_jcut=OLD_JCUT)
    cta = new_map["spans"][-1]
    assert cta["source"] == CTA
    assert abs(cta["sourceEnd"] - 2.7) < 0.02
    assert cta["sourceEnd"] < 3.3
    assert abs(new_map["plannedDuration"] - 9.2) < 0.05
    assert new_map["outputFrames"] == 278
    assert abs(new_map["outputDuration"] - (278 / 30.0)) < 1e-6


def test_identity_same_edl():
    edl = {"ranges": OLD_RANGES, "jcut_timeline": OLD_JCUT, "jcut": True, "fps": 30}
    caps = [
        {"text": "Mas", "startMs": 30, "endMs": 190},
        {"text": "ficar", "startMs": 7340, "endMs": 7580},
        {"text": "feliz.", "startMs": 8360, "endMs": 9100},
    ]
    out = retime_captions_for_edl(caps, edl, edl, fps=30.0)
    assert _texts(out) == _texts(caps)
    for a, b in zip(caps, out):
        assert abs(a["startMs"] - b["startMs"]) <= 2
        assert abs(a["endMs"] - b["endMs"]) <= 2
        assert a["text"] == b["text"]


def test_trim_cta_tail_keeps_main_and_feliz():
    old = {"ranges": OLD_RANGES, "jcut_timeline": OLD_JCUT, "jcut": True, "fps": 30}
    new = {"ranges": NEW_RANGES, "jcut": True, "fps": 30, "total_duration_s": 9.9}
    caps = [
        {"text": "Mas", "startMs": 30, "endMs": 190},
        {"text": "ficar", "startMs": 7340, "endMs": 7580},
        {"text": "feliz.", "startMs": 8360, "endMs": 9100},
        {"text": "cauda", "startMs": 9300, "endMs": 9800},
    ]
    out = retime_captions_for_edl(caps, old, new, fps=30.0, prior_jcut=OLD_JCUT)
    texts = _texts(out)
    assert texts.count("Mas") == 1
    assert "ficar" in texts
    assert "feliz." in texts
    assert "cauda" not in texts
    mas = next(c for c in out if c["text"] == "Mas")
    assert mas["startMs"] <= 50
    assert validate_remapped_captions(caps, out, build_timeline_map(new, fps=30, prior_jcut=OLD_JCUT)) is None


def test_cut_middle_shifts_later_only():
    old = {"ranges": [{"source": "SRC", "start": 0.0, "end": 10.0}], "jcut": False}
    new = {"ranges": [
        {"source": "SRC", "start": 0.0, "end": 4.0},
        {"source": "SRC", "start": 5.0, "end": 10.0},
    ], "jcut": False}
    caps = [
        {"text": "antes", "startMs": 2000, "endMs": 3000},
        {"text": "meio", "startMs": 4200, "endMs": 4800},
        {"text": "depois", "startMs": 8000, "endMs": 9000},
    ]
    out = retime_captions_for_edl(caps, old, new)
    texts = _texts(out)
    assert texts == ["antes", "depois"]
    assert out[0]["startMs"] == 2000
    assert abs(out[1]["startMs"] - 7000) <= 2
    assert out[1]["text"] == "depois"


def test_two_sources_same_clock_stay_independent():
    old = {"ranges": [
        {"source": "A", "start": 0.0, "end": 2.0},
        {"source": "B", "start": 0.0, "end": 2.0},
    ], "jcut": False}
    new = {"ranges": [
        {"source": "A", "start": 0.0, "end": 2.0},
        {"source": "B", "start": 0.0, "end": 1.0},
    ], "jcut": False}
    caps = [
        {"text": "alpha", "start": 0.5, "end": 0.8},
        {"text": "beta", "start": 2.2, "end": 2.5},
    ]
    out = retime_captions_for_edl(caps, old, new)
    assert _texts(out) == ["alpha", "beta"]
    assert abs(out[0]["start"] - 0.5) < 0.02
    assert abs(out[1]["start"] - 2.2) < 0.02
    assert out[0]["source"] == "A"
    assert out[1]["source"] == "B"
    # Trim B 1.0–2.0 would drop a word at source 1.5, not alpha.
    new2 = {"ranges": [
        {"source": "A", "start": 0.0, "end": 2.0},
        {"source": "B", "start": 0.0, "end": 1.0},
    ], "jcut": False}
    late = retime_captions_for_edl(
        caps + [{"text": "tailB", "start": 3.4, "end": 3.8}],
        old,
        new2,
    )
    assert "alpha" in _texts(late)
    assert "tailB" not in _texts(late)


def test_trim_b_does_not_steal_main_zero():
    """CTA 0–2.7 não casa com MAIN 0–2.7."""
    old = {
        "ranges": [
            {"source": MAIN, "start": 0.0, "end": 3.0},
            {"source": CTA, "start": 0.0, "end": 3.4},
        ],
        "jcut": False,
    }
    new = {
        "ranges": [
            {"source": MAIN, "start": 0.0, "end": 3.0},
            {"source": CTA, "start": 0.0, "end": 2.7},
        ],
        "jcut": False,
    }
    caps = [
        {"text": "Mas", "start": 0.03, "end": 0.19},
        {"text": "ficar", "start": 3.84, "end": 4.08},
        {"text": "feliz.", "start": 4.86, "end": 5.60},
        {"text": "silencio", "start": 5.80, "end": 6.30},
    ]
    out = retime_captions_for_edl(caps, old, new)
    texts = _texts(out)
    assert texts.count("Mas") == 1
    assert "ficar" in texts
    assert "feliz." in texts
    assert "silencio" not in texts
    assert len(out) <= len(caps)


def test_manual_text_is_sovereign():
    old = {"ranges": [{"source": "SRC", "start": 0.0, "end": 10.0}], "jcut": False}
    new = {"ranges": [
        {"source": "SRC", "start": 0.0, "end": 4.0},
        {"source": "SRC", "start": 6.0, "end": 10.0},
    ], "jcut": False}
    caps = [
        {"text": "Película", "startMs": 7000, "endMs": 9000,
         "source": "SRC", "sourceStart": 7.0, "sourceEnd": 9.0},
    ]
    out = retime_captions_for_edl(caps, old, new)
    assert out[0]["text"] == "Película"
    assert out[0]["startMs"] == 5000


def test_order_never_inverts():
    old = {"ranges": [{"source": "S", "start": 0.0, "end": 8.0}], "jcut": False}
    new = {"ranges": [{"source": "S", "start": 0.0, "end": 8.0}], "jcut": False}
    caps = [{"text": w, "start": i, "end": i + 0.4} for i, w in enumerate("abcde")]
    out = retime_captions_for_edl(caps, old, new)
    assert _texts(out) == list("abcde")


def test_legacy_through_edl_stays_naive():
    edl = [{"source": "SRC", "start": 0.0, "end": 4.0}, {"source": "SRC", "start": 6.0, "end": 10.0}]
    out = remap_captions_through_edl(
        [{"text": "cedo", "start": 2.0, "end": 4.0}, {"text": "tarde", "start": 7.0, "end": 9.0}],
        edl,
    )
    assert out[0]["start"] == 2.0
    assert out[1]["start"] == 5.0


def test_invariants_reject_duplicate_and_negative():
    bad_map = {"spans": [{"source": "", "sourceStart": 0, "sourceEnd": 1,
                          "videoStart": 0, "videoEnd": 1}], "outputDuration": 1}
    assert validate_timeline_map(bad_map) == "source ausente"
    neg = {"spans": [{"source": "A", "sourceStart": 2, "sourceEnd": 1,
                      "videoStart": 0, "videoEnd": 1}], "outputDuration": 1}
    assert validate_timeline_map(neg) == "segmento com duração negativa"
    good = build_timeline_map({"ranges": OLD_RANGES, "jcut_timeline": OLD_JCUT, "jcut": True}, fps=30)
    assert validate_timeline_map(good) is None
    orig = [{"text": "Mas", "startMs": 0, "endMs": 100}]
    dup = [
        {"text": "Mas", "startMs": 0, "endMs": 100, "source": MAIN, "sourceStart": 2.57},
        {"text": "Mas", "startMs": 9000, "endMs": 9100, "source": MAIN, "sourceStart": 2.57},
    ]
    assert validate_remapped_captions(orig, dup, good) == "token duplicado sem justificativa"


def test_smoke_edl_img_1645_pending_remap():
    if not SMOKE_EDIT.is_dir():
        return
    # Depois do Apply aprovado o EDL deixa de estar dirty; não reprocessa o projeto.
    if not load(SMOKE_EDIT).get("dirty", {}).get("edl"):
        return
    caps_path = SMOKE_EDIT / "remotion" / "public" / "captions.json"
    before = json.loads(caps_path.read_text(encoding="utf-8"))
    n_before = len(before)
    texts_before = _texts(before)
    assert n_before == 42
    assert texts_before.count("Mas") == 1
    assert "ficar" in texts_before
    assert "feliz." in texts_before
    pending = pending_caption_remap(SMOKE_EDIT)
    assert pending is not None
    texts = _texts(pending)
    assert texts.count("Mas") == 1
    assert "ficar" in texts
    assert "feliz." in texts
    assert len(pending) <= n_before + 2
    assert len(pending) >= n_before - 2
    err, new_map, remapped = prepare_edl_apply(SMOKE_EDIT)
    assert err is None
    assert remapped is not None
    assert new_map["outputFrames"] == 278
    assert abs(new_map["outputDuration"] - (278 / 30.0)) < 1e-6
    assert abs(new_map["plannedDuration"] - 9.2) < 0.05
    assert validate_remapped_captions(before, remapped, new_map) is None
    def _pick(word):
        return next(c for c in remapped if c["text"] == word)
    mas = _pick("Mas")
    ficar = _pick("ficar")
    feliz = _pick("feliz.")
    teste = _pick("TESTELEG.")
    assert mas["source"] == MAIN
    assert ficar["source"] == CTA
    assert feliz["source"] == CTA
    assert teste["source"] == MAIN
    eu = [c for c in remapped if c["text"] == "Eu"]
    assert len(eu) == 2
    assert {c["source"] for c in eu} == {MAIN}
    assert eu[0]["startMs"] != eu[1]["startMs"]
    cut_frames = read_mp4_video_frames(SMOKE_EDIT / "cut.mp4")
    old, _new, fps, _prior = caption_timeline_edls(SMOKE_EDIT)
    old_map = build_timeline_map(old, fps=fps, prior_jcut=old.get("jcut_timeline"))
    assert old_map["outputFrames"] == 299
    if cut_frames:
        assert abs(cut_frames - 299) <= 1
    # captions.json do cut atual permanece intacto
    after = json.loads(caps_path.read_text(encoding="utf-8"))
    assert after == before
    corr = load(SMOKE_EDIT)
    assert corr["dirty"]["edl"] is True


def test_prepare_fail_blocks_rebuild(tmp_path: Path):
    from pipeline.test_apply_execute import _hooks, _project

    edit = _project(tmp_path)
    write_edl_ranges(edit, [
        {"source": "SRC", "start": 0.0, "end": 4.0},
        {"source": "SRC", "start": 6.0, "end": 10.0},
    ])
    logs: list[str] = []
    with patch("app.apply_execute.validate_timeline_map", return_value="timeline não é monotônica"):
        out = execute_apply_plan(edit, plan_apply_changes(load(edit)), hooks=_hooks(logs))
    assert out["ok"] is False
    assert "Não foi possível preparar este corte" in out["message"]
    assert "rebuild" not in logs
    assert "QUICK_APPLY_INVARIANT" in " ".join(logs)


if __name__ == "__main__":
    test_layout_jcut_matches_recorded_timeline()
    test_encoded_frames_match_segments_quantization()
    test_jcut_overlap_keeps_source_identity()
    test_same_source_jcut_overlap_is_not_fail()
    test_same_source_unmatched_tokens_do_not_look_like_duplicates()
    test_new_map_does_not_reuse_stale_cta_jcut()
    test_identity_same_edl()
    test_trim_cta_tail_keeps_main_and_feliz()
    test_cut_middle_shifts_later_only()
    test_two_sources_same_clock_stay_independent()
    test_trim_b_does_not_steal_main_zero()
    test_manual_text_is_sovereign()
    test_order_never_inverts()
    test_legacy_through_edl_stays_naive()
    test_invariants_reject_duplicate_and_negative()
    test_smoke_edl_img_1645_pending_remap()
    with __import__("tempfile").TemporaryDirectory() as d:
        test_prepare_fail_blocks_rebuild(Path(d))
    print("ok")


def test_tail_gravado_zero_nao_vira_o_padrao():
    """Zero é um tail GRAVADO, não "vazio".

    `plan_jcut` devolve 0 sempre que o take termina em fala (o silêncio final
    não cobre nem um quadro). Medido nos projetos do usuário em 21/08/2026:
    **269 das 1047 entradas gravadas são 0 (26%)**, e **55 dos 111 projetos**
    têm um 0 num take que NÃO é o último.

    Com o `or`, esse 0 virava 2 e o take perdia 66,7 ms de áudio. Como
    `a_off += a_dur - lead` acumula, todos os spans seguintes ficavam cedo
    demais no mapa novo, e as legendas — carimbadas por `outputStart` —
    apareciam antes da palavra ser dita. A função irmã `_lead_frames_of` já
    fazia `is not None`."""
    from app.timeline_map import infer_tail_frames

    rs = [{"source": "A", "start": 0, "end": 1},
          {"source": "A", "start": 2, "end": 3},
          {"source": "A", "start": 4, "end": 5}]
    jt = [{"source": "A", "tail_trim_frames": 0},
          {"source": "A", "tail_trim_frames": 2},
          {"source": "A", "tail_trim_frames": 0}]
    assert infer_tail_frames(rs, prior_jcut=jt) == [0, 2, 0]
    # sem nada gravado, o padrão continua valendo (último take sempre 0)
    assert infer_tail_frames(rs, prior_jcut=None) == [2, 2, 0]


def test_o_zero_gravado_nao_desloca_os_spans_seguintes():
    """O sintoma que o usuário veria: legenda adiantada depois da emenda."""
    from app.timeline_map import build_timeline_map

    edl = {"fps": 30, "jcut": True,
           "ranges": [{"source": "A", "start": 0.0, "end": 2.0},
                      {"source": "A", "start": 5.0, "end": 7.0},
                      {"source": "A", "start": 9.0, "end": 11.0}]}
    jt = [{"source": "A", "tail_trim_frames": 0},
          {"source": "A", "tail_trim_frames": 0},
          {"source": "A", "tail_trim_frames": 0}]
    com = build_timeline_map(edl, fps=30, prior_jcut=jt)
    sem = build_timeline_map(edl, fps=30, prior_jcut=None)
    inicio_com = [s["outputStart"] for s in com["spans"]]
    inicio_sem = [s["outputStart"] for s in sem["spans"]]
    # o terceiro span é onde os dois cortes de 2 quadros teriam somado
    assert inicio_com[2] > inicio_sem[2], (inicio_com, inicio_sem)
    assert abs((inicio_com[2] - inicio_sem[2]) - 4 / 30) < 1e-6
