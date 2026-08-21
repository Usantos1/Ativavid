"""Diff de insumos do overlay incremental: só texto/gancho vira parcial."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from app.overlay_path import (  # noqa: E402
    _incremental_ranges,
    _texts_only_first_change_ms,
)

FPS = 30.0
FRAMES = 900  # 30s


def _snap(hook=None, caps=None, cues=None, template="t1", extra=None):
    ed = {"width": 1080, "height": 1920, "captions": {"style": "karaoke"}}
    if hook is not None:
        ed["hook"] = hook
    if extra:
        ed.update(extra)
    return {
        "_template": template,
        "edit-data.json": ed,
        "captions.json": caps if caps is not None else [],
        "caption-cues.json": cues,
    }


def test_texts_only_equal_returns_none():
    caps = [{"text": "oi", "startMs": 100, "endMs": 400}]
    assert _texts_only_first_change_ms(caps, caps) is None


def test_texts_only_change_returns_first_ms():
    a = [{"text": "perico", "startMs": 5000, "endMs": 5400},
         {"text": "bom", "startMs": 6000, "endMs": 6300}]
    b = [{"text": "película", "startMs": 5000, "endMs": 5400},
         {"text": "bom", "startMs": 6000, "endMs": 6300}]
    assert _texts_only_first_change_ms(a, b) == 5000


def test_timing_change_is_not_texts_only():
    a = [{"text": "oi", "startMs": 100, "endMs": 400}]
    b = [{"text": "oi", "startMs": 150, "endMs": 400}]
    assert _texts_only_first_change_ms(a, b) is None


def test_length_change_is_not_texts_only():
    a = [{"text": "oi", "startMs": 100, "endMs": 400}]
    assert _texts_only_first_change_ms(a, a + a) is None


def test_identical_snapshots_yield_empty_plan():
    s = _snap(hook={"lines": ["a", "b"], "endSec": 4})
    plano = _incremental_ranges(s, s, FPS, FRAMES)
    assert plano.ranges == []
    assert plano.audio_do_cache is True


def test_hook_only_change_yields_hook_window():
    old = _snap(hook={"lines": ["a", "b"], "endSec": 4})
    new = _snap(hook={"lines": ["c", "d"], "endSec": 4})
    plan = _incremental_ranges(old, new, FPS, FRAMES)
    assert plan.ranges == [(0, int(4 * FPS) + 12)]
    assert plan.audio_do_cache is True, "só o texto mudou: SFX segue no lugar"


def test_caption_text_fix_renders_from_change_to_end():
    caps_a = [{"text": "perico", "startMs": 12000, "endMs": 12400}]
    caps_b = [{"text": "película", "startMs": 12000, "endMs": 12400}]
    old = _snap(hook={"endSec": 4}, caps=caps_a)
    new = _snap(hook={"endSec": 4}, caps=caps_b)
    plan = _incremental_ranges(old, new, FPS, FRAMES)
    assert plan.ranges == [(int(12.0 * FPS) - 30, FRAMES)]
    assert plan.audio_do_cache is True


def test_hook_and_caption_changes_merge():
    old = _snap(hook={"lines": ["a"], "endSec": 4},
                caps=[{"text": "x", "startMs": 1000, "endMs": 1300}])
    new = _snap(hook={"lines": ["b"], "endSec": 4},
                caps=[{"text": "y", "startMs": 1000, "endMs": 1300}])
    plan = _incremental_ranges(old, new, FPS, FRAMES)
    # gancho (0-132) e legenda (0-900) se sobrepõem → um range só até o fim
    assert plan.ranges == [(0, FRAMES)]
    assert plan.audio_do_cache is True


def test_style_change_forces_full_render():
    old = _snap(hook={"endSec": 4})
    new = _snap(hook={"endSec": 4}, extra={"captions": {"style": "impacto"}})
    assert _incremental_ranges(old, new, FPS, FRAMES) is None


def test_template_change_forces_full_render():
    old = _snap(hook={"endSec": 4}, template="t1")
    new = _snap(hook={"endSec": 4}, template="t2")
    assert _incremental_ranges(old, new, FPS, FRAMES) is None


def test_cache_slots_are_per_project(tmp_path):
    """edit_dir.name é sempre "edit" — o slot tem que vir do PROJETO."""
    from app.overlay_path import _cache_dir_for

    a = _cache_dir_for(tmp_path / "Projetos" / "proj_A" / "edit")
    b = _cache_dir_for(tmp_path / "Projetos" / "proj_B" / "edit")
    assert a != b
    assert a == _cache_dir_for(tmp_path / "Projetos" / "proj_A" / "edit")


# ---------------------------------------------------------------- corte (EDL)
# Tirar 2 cortes do FIM refazia o overlay inteiro — e o overlay e 70-83% do
# tempo, ~22 min por video nesta maquina. Tudo antes do ponto de corte fica
# identico, cue por cue, e ja esta renderizado.
from app.overlay_path import _prefix_first_change_ms  # noqa: E402


def _cue(t: float, texto: str = "oi", dur: float = 400) -> dict:
    return {"startMs": t, "endMs": t + dur, "lines": [[{"text": texto, "fromMs": t}]]}


def test_prefixo_igual_devolve_o_ponto_de_divergencia():
    """Devolve o FIM da última cue igual, não o início da divergência.

    É de propósito: entre uma cue e a seguinte ainda corre a animação de
    saída, e redesenhar meio segundo a mais custa quase nada perto do risco
    de emendar no meio de um fade.
    """
    velho = [_cue(0), _cue(1000), _cue(2000)]
    novo = [_cue(0), _cue(1000), _cue(2500)]
    assert _prefix_first_change_ms(velho, novo) == 1400


def test_corte_no_fim_devolve_o_fim_da_ultima_cue_igual():
    """Nada de novo depois: o ponto de mudança é onde o antigo ainda tinha
    conteúdo e o novo não tem mais."""
    velho = [_cue(0), _cue(1000), _cue(2000)]
    novo = [_cue(0), _cue(1000)]
    assert _prefix_first_change_ms(velho, novo) == 1400  # fim da cue 1000+400


def test_mudanca_na_primeira_cue_nao_tem_o_que_reaproveitar():
    velho = [_cue(0), _cue(1000)]
    novo = [_cue(500), _cue(1000)]
    assert _prefix_first_change_ms(velho, novo) is None


def test_listas_iguais_nao_sao_mudanca():
    velho = [_cue(0), _cue(1000)]
    assert _prefix_first_change_ms(velho, list(velho)) is None


def test_corte_no_fim_rerenderiza_so_a_cauda_e_emenda_o_audio():
    velho = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(10000), _cue(20000)])
    novo = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(10000)])
    plan = _incremental_ranges(velho, novo, FPS, FRAMES)
    assert plan is not None, "corte no fim tem de virar parcial"
    (a, b), = plan.ranges
    assert b == FRAMES
    assert a == int(10.4 * FPS) - 30, "começa 30 quadros antes da divergência"
    assert plan.audio_do_cache is False, "os tempos mudaram: SFX tem de vir da emenda"


def test_corte_no_meio_reaproveita_o_comeco():
    velho = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(5000), _cue(9000)])
    novo = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(5000), _cue(8000)])
    plan = _incremental_ranges(velho, novo, FPS, FRAMES)
    (a, b), = plan.ranges
    # 5400 = fim da última cue igual; menos os 30 quadros de folga
    assert a == int(5.4 * FPS) - 30 and b == FRAMES
    assert plan.audio_do_cache is False


def test_corte_no_comeco_cai_no_render_completo():
    velho = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(5000)])
    novo = _snap(hook={"endSec": 4}, cues=[_cue(300), _cue(5000)])
    assert _incremental_ranges(velho, novo, FPS, FRAMES) is None


def test_mudanca_de_estilo_junto_com_corte_ainda_e_completo():
    velho = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(5000)])
    novo = _snap(hook={"endSec": 4}, cues=[_cue(0)],
                 extra={"captions": {"style": "impacto"}})
    assert _incremental_ranges(velho, novo, FPS, FRAMES) is None


def test_cobertura_grande_demais_nao_compensa():
    """Se quase tudo muda, o parcial nao vale o risco da emenda — o gate de
    cobertura de render_overlay_incremental derruba para o completo."""
    velho = _snap(hook={"endSec": 4}, cues=[_cue(0), _cue(500)])
    novo = _snap(hook={"endSec": 4}, cues=[_cue(0)])
    plan = _incremental_ranges(velho, novo, FPS, FRAMES)
    (a, b), = plan.ranges
    assert (b - a) / FRAMES > 0.85, "cobertura alta: o gate vai recusar"


# ------------------------------------------------------- duracao (o bloqueio)
# edit-data.json guarda durationSec, e cortar SEMPRE muda isso. Comparar esse
# campo derrubava tudo para render completo antes de olhar as legendas — o
# parcial de corte nunca dispararia.
def _snap_dur(dur, cues):
    s = _snap(hook={"endSec": 4}, cues=cues)
    s["edit-data.json"]["durationSec"] = dur
    return s


def test_corte_muda_a_duracao_e_ainda_vira_parcial():
    velho = _snap_dur(30.0, [_cue(0), _cue(10000), _cue(20000)])
    novo = _snap_dur(24.0, [_cue(0), _cue(10000)])
    plan = _incremental_ranges(velho, novo, FPS, FRAMES)
    assert plan is not None, "durationSec não pode bloquear o parcial"
    assert plan.ranges and plan.ranges[-1][1] == FRAMES
    assert plan.audio_do_cache is False


def test_duracao_diferente_sem_mudanca_grafica_nao_reusa_o_cache():
    """O cache tem o tamanho errado — copiá-lo inteiro entregaria um overlay
    com duração diferente da composição."""
    cues = [_cue(0), _cue(10000)]
    velho = _snap_dur(30.0, cues)
    novo = _snap_dur(24.0, list(cues))
    assert _incremental_ranges(velho, novo, FPS, FRAMES) is None


def test_mesma_duracao_e_mesmos_graficos_reusa_inteiro():
    s = _snap_dur(30.0, [_cue(0), _cue(10000)])
    plano = _incremental_ranges(s, s, FPS, FRAMES)
    assert plano.ranges == [] and plano.audio_do_cache is True


def test_medida_de_loudness_nao_abre_o_video():
    """`ebur128_summary` roda no vídeo FINAL e só lê áudio, mas não tinha
    `-vn`: sem ele o ffmpeg mapeia também o vídeo e decodifica o arquivo
    inteiro para o muxer nulo. O `measure_loudnorm`, no mesmo arquivo, já
    tinha — era inconsistência, não decisão.

    A medida não muda: conferido no mesmo clipe, I=-21,8 LUFS dos dois jeitos.
    """
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent.parent
             / "app" / "overlay_compose.py").read_text(encoding="utf-8")
    i = fonte.index("def ebur128_summary")
    corpo = fonte[i:fonte.index("\ndef ", i + 10)]
    assert '"-vn"' in corpo
    assert corpo.index('"-vn"') < corpo.index("ebur128=peak")


def test_duracao_mudou_com_range_so_no_comeco_recusa_o_incremental():
    """Se a duração mudou, o cartão final se move — e ele é desenhado a partir
    do FIM. Emendar uma cauda vinda do cache colocaria o cartão no lugar
    errado.

    O comentário no código afirmava que "o trecho novo sempre vai até o fim",
    sem conferir. O único range que não alcança o fim é o da headline
    (0..endSec); não consegui construir esse caso pelo app (mexer no corte
    muda a duração E as cues juntas), mas invariante afirmada e não conferida
    é o tipo de coisa que fura quando alguém mexe ao lado."""
    import json

    from app.overlay_path import _incremental_ranges

    base = {
        "_template": "t", "_engine": "proprio",
        "captions.json": [{"text": "oi", "startMs": 0, "endMs": 500}],
        "caption-cues.json": [{"i": 0, "startMs": 0, "endMs": 500}],
        "edit-data.json": {"durationSec": 10.0, "hook": {"enabled": True, "endSec": 3.0}},
    }
    novo = json.loads(json.dumps(base))
    novo["edit-data.json"]["durationSec"] = 9.0          # duração mudou
    novo["edit-data.json"]["hook"]["endSec"] = 3.5       # e só a headline mudou
    assert _incremental_ranges(base, novo, 30.0, 270) is None


def test_duracao_mudou_com_range_ate_o_fim_segue_valendo():
    """O outro lado da guarda: quando algum range ALCANÇA o fim, o
    incremental continua valendo. Aqui é uma troca de palavra na legenda, que
    propaga do ponto da mudança até o fim."""
    import json

    from app.overlay_path import _incremental_ranges

    base = {
        "_template": "t", "_engine": "proprio",
        "captions.json": [{"text": "oi", "startMs": 0, "endMs": 500}],
        "caption-cues.json": [{"i": 0, "startMs": 0, "endMs": 500}],
        "edit-data.json": {"durationSec": 10.0, "hook": {"enabled": True, "endSec": 3.0}},
    }
    novo = json.loads(json.dumps(base))
    novo["edit-data.json"]["durationSec"] = 9.0
    novo["captions.json"] = [{"text": "olá", "startMs": 0, "endMs": 500}]
    plano = _incremental_ranges(base, novo, 30.0, 270)
    assert plano is not None, "troca de palavra tem de continuar incremental"
    assert any(fim >= 270 for _, fim in plano.ranges), plano.ranges
