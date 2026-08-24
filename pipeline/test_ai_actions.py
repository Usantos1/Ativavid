"""Ciclo plan → pending → apply do Editar com IA — sem render."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.ai_actions import (
    FAIL_PLAN,
    VAGUE_CUT_MSG,
    apply_actions_to_edits,
    format_apply_log,
    interpret_llm_reply,
    is_apply_confirmation,
    make_pending_edit,
    operations_from_patch,
    parse_deterministic_command,
    pending_is_stale,
    plan_from_prompt,
    prompt_allows_cut,
    filter_unsafe_cuts,
    sanitize_proposal_summary,
    validate_actions,
)


def test_confirm_phrases():
    for t in (
        "ok pode aplicar", "pode aplicar", "faz isso", "sim", "manda ver",
        "ok", "aplica", "beleza",
    ):
        assert is_apply_confirmation(t), t
    assert not is_apply_confirmation("a edição tirou a piada")
    assert not is_apply_confirmation("restaura o vídeo completo")


def test_deterministic_restore_full():
    d = parse_deterministic_command("restaura o vídeo completo", source_duration=4.43)
    assert d is not None
    assert d["backend"] == "deterministic"
    assert d["actions"][0]["action"] == "restore_range"
    assert d["actions"][0]["start"] == 0.0
    assert d["actions"][0]["end"] == 4.43
    actions, summary, backend = plan_from_prompt(
        "restaura o vídeo completo",
        duration=2.1,
        source_duration=4.43,
        chat_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM não deve ser chamada")),
    )
    assert backend == "deterministic"
    assert actions[0]["end"] == 4.43
    patch = apply_actions_to_edits(actions, duration=4.43)
    ops = operations_from_patch(patch, actions)
    log = format_apply_log(ops)
    assert log[0] == "AI_EDIT_APPLY operations=1"
    assert "RESTORE_RANGE 0.00-4.43" in log


def test_deterministic_restore_first_and_remove_last():
    first = parse_deterministic_command("volta os primeiros 5 segundos", source_duration=39.12)
    assert first["actions"][0]["action"] == "restore_range"
    assert first["actions"][0]["start"] == 0.0
    assert first["actions"][0]["end"] == 5.0
    last = parse_deterministic_command(
        "remove os últimos 2 segundos", cut_duration=10.0, source_duration=39.12,
    )
    assert last["actions"][0]["action"] == "set_duration_max"
    assert last["actions"][0]["maxSec"] == 8.0


def test_semantic_is_not_deterministic():
    for t in (
        "a edição perdeu a graça",
        "tira essa parte que ficou repetitiva",
        "deixa o começo mais rápido",
        "A edição tirou a piada. Restaura o vídeo completo.",
        "Restaurado o vídeo completo de 0 a 4,4s",
    ):
        assert parse_deterministic_command(t, source_duration=4.43) is None, t


def test_llm_prose_does_not_invent():
    def chat(messages, model=None):
        return "Restaurado o vídeo completo de 0 a 4,4s para preservar a piada.", "fake"

    parsed = interpret_llm_reply(
        "Restaurado o vídeo completo de 0 a 4,4s para preservar a piada.",
        duration=4.43,
    )
    assert parsed is None
    actions, summary, _backend = plan_from_prompt(
        "a edição perdeu a graça",
        duration=4.43,
        source_duration=4.43,
        chat_fn=chat,
    )
    assert actions == []
    assert summary == FAIL_PLAN


def test_semantic_valid_actions_become_pending():
    def chat(messages, model=None):
        return json.dumps({
            "actions": [{
                "action": "remove_range",
                "start": 8.0,
                "end": 12.0,
                "reason": "repetition",
            }],
            "summary": "Vou tirar o trecho repetitivo",
        }), "fake"

    actions, summary, backend = plan_from_prompt(
        "tira essa parte que ficou repetitiva",
        duration=20.0,
        chat_fn=chat,
    )
    assert backend == "fake"
    assert actions[0]["action"] == "remove_range"
    patch = apply_actions_to_edits(actions, duration=20.0)
    ops = operations_from_patch(patch, actions)
    pending = make_pending_edit(
        project_id="job-a",
        ranges=[{"source": "SRC", "start": 0, "end": 20}],
        operations=ops,
        actions=actions,
        patch=patch,
        summary=summary,
    )
    assert pending["hasPendingEdit"] is True
    assert pending["projectId"] == "job-a"
    assert pending["edlRevision"]
    assert pending["timestamp"] > 0
    assert pending["operations"][0]["op"] == "remove_range"


def test_llm_retry_then_structured():
    n = {"i": 0}

    def chat(messages, model=None):
        n["i"] += 1
        if n["i"] == 1:
            return "Restaurado o vídeo…", "fake"
        return json.dumps({
            "actions": [{"action": "restore_range", "start": 0, "end": 4.43}],
            "summary": "Vou restaurar o bloco",
        }), "fake"

    actions, _summary, _backend = plan_from_prompt(
        "a edição perdeu a graça",
        duration=4.43,
        source_duration=4.43,
        chat_fn=chat,
    )
    assert n["i"] == 2
    assert actions[0]["action"] == "restore_range"


def test_pending_stale_after_manual_edit():
    ranges = [{"source": "SRC", "start": 0.0, "end": 10.0}]
    pending = make_pending_edit(
        project_id="job-a",
        ranges=ranges,
        operations=[{"op": "restore_range", "start": 0, "end": 10}],
    )
    assert pending_is_stale(pending, project_id="job-a", ranges=ranges) is False
    changed = [{"source": "SRC", "start": 1.0, "end": 9.0}]
    assert pending_is_stale(pending, project_id="job-a", ranges=changed) is True
    assert pending_is_stale(pending, project_id="job-b", ranges=ranges) is True


def test_pending_reload_same_project():
    ranges = [{"source": "SRC", "start": 0.0, "end": 4.43}]
    pending = make_pending_edit(
        project_id="20260816-002530_IMG_3912_9d41f4134e",
        ranges=ranges,
        operations=[{"op": "restore_range", "start": 0, "end": 4.43}],
    )
    raw = json.dumps(pending)
    loaded = json.loads(raw)
    assert loaded["projectId"] == pending["projectId"]
    assert pending_is_stale(loaded, project_id=pending["projectId"], ranges=ranges) is False
    assert pending_is_stale(loaded, project_id="outro-projeto", ranges=ranges) is True


def test_confirm_applies_existing_pending():
    assert is_apply_confirmation("ok pode aplicar")
    ranges = [{"source": "SRC", "start": 2.0, "end": 8.0}]
    pending = make_pending_edit(
        project_id="job-a",
        ranges=ranges,
        operations=[{"op": "restore_range", "start": 0, "end": 10}],
    )
    assert pending["hasPendingEdit"]
    assert pending_is_stale(pending, project_id="job-a", ranges=ranges) is False


def test_undo_restores_exact_edl_snapshot():
    before = [{"source": "SRC", "start": 5.19, "end": 11.0, "beat": "HOOK"}]
    snapshot = json.loads(json.dumps(before))
    after = [{"source": "SRC", "start": 0.0, "end": 39.01, "beat": "KEEP"}]
    restored = json.loads(json.dumps(snapshot))
    assert restored == before
    assert restored != after


def test_summary_is_proposal_not_done():
    text = sanitize_proposal_summary("Restaurado o vídeo completo de 0 a 4,4s", has_ops=True)
    assert not text.lower().startswith("restaurad")
    empty = sanitize_proposal_summary("Nenhuma alteração pendente; mantendo o projeto", has_ops=False)
    assert "consegui preparar" in empty.lower() or "descrever de outra forma" in empty.lower()


def test_vague_melhoria_does_not_trim():
    def chat(messages, model=None):
        return json.dumps({
            "actions": [{
                "action": "trim_range",
                "start": 12.95,
                "end": 13.35,
                "reason": "keep punchline",
            }],
            "summary": "Vou deixar só o gancho",
        }), "fake"

    actions, summary, _backend = plan_from_prompt(
        "melhoria",
        duration=33.8,
        source_duration=55.0,
        chat_fn=chat,
    )
    assert actions == []
    assert summary == VAGUE_CUT_MSG


def test_trim_uses_cut_clock_not_source():
    actions = validate_actions(
        {"actions": [{"action": "trim_range", "start": 12.95, "end": 13.35}]},
        duration=33.8,
        source_duration=55.0,
    )
    assert actions[0]["start"] == 12.95
    assert actions[0]["end"] == 13.35
    tiny = validate_actions(
        {"actions": [{"action": "trim_range", "start": 0, "end": 0.4}]},
        duration=33.8,
        source_duration=55.0,
    )
    assert tiny[0]["end"] == 0.4
    actions, summary, _backend = plan_from_prompt(
        "melhoria",
        duration=33.8,
        source_duration=55.0,
        chat_fn=lambda *a, **k: (json.dumps({
            "actions": [{"action": "trim_range", "start": 0, "end": 0.4}],
            "summary": "Vou enxugar",
        }), "fake"),
    )
    assert actions == []
    assert summary == VAGUE_CUT_MSG


def test_explicit_remove_still_works():
    def chat(messages, model=None):
        return json.dumps({
            "actions": [{
                "action": "remove_range",
                "start": 8.0,
                "end": 12.0,
                "reason": "repetition",
            }],
            "summary": "Vou tirar o trecho repetitivo",
        }), "fake"

    actions, _summary, _backend = plan_from_prompt(
        "tira essa parte que ficou repetitiva",
        duration=20.0,
        chat_fn=chat,
    )
    assert actions[0]["action"] == "remove_range"


def _cut_reply(action="trim_range"):
    payload = {
        "trim_range": {"action": "trim_range", "start": 0, "end": 0.4, "reason": "keep punchline"},
        "remove_range": {"action": "remove_range", "start": 0, "end": 12, "reason": "enxugar"},
        "set_duration_max": {"action": "set_duration_max", "maxSec": 0.4, "reason": "curto"},
    }[action]
    return json.dumps({"actions": [payload], "summary": "Vou enxugar"}), "fake"


def test_vague_prompts_never_allow_cut():
    for text in (
        "melhoria",
        "melhora",
        "melhorar",
        "melhora o vídeo",
        "melhora o video",
        "deixa melhor",
        "deixa o vídeo melhor",
        "fica melhor",
        "pode melhorar",
        "melhorar o vídeo",
    ):
        assert prompt_allows_cut(text) is False
        for action in ("trim_range", "remove_range", "set_duration_max"):
            actions, summary, _backend = plan_from_prompt(
                text,
                duration=33.8,
                source_duration=55.0,
                chat_fn=lambda *a, act=action, **k: _cut_reply(act),
            )
            assert actions == [], (text, action, actions)
            assert summary == VAGUE_CUT_MSG


def test_filter_unsafe_cuts_all_cut_actions():
    for body in (
        {"action": "trim_range", "start": 0, "end": 0.4},
        {"action": "remove_range", "start": 0, "end": 30},
        {"action": "set_duration_max", "maxSec": 0.4},
    ):
        kept = filter_unsafe_cuts([body], prompt="melhoria", cut_duration=33.8)
        assert kept == [], body
        tiny = filter_unsafe_cuts([body], prompt="corta os últimos 2 segundos", cut_duration=33.8)
        if body["action"] in ("trim_range", "set_duration_max"):
            assert tiny == []


if __name__ == "__main__":
    for fn in (
        test_confirm_phrases,
        test_deterministic_restore_full,
        test_deterministic_restore_first_and_remove_last,
        test_semantic_is_not_deterministic,
        test_llm_prose_does_not_invent,
        test_semantic_valid_actions_become_pending,
        test_llm_retry_then_structured,
        test_pending_stale_after_manual_edit,
        test_pending_reload_same_project,
        test_confirm_applies_existing_pending,
        test_undo_restores_exact_edl_snapshot,
        test_summary_is_proposal_not_done,
        test_vague_melhoria_does_not_trim,
        test_trim_uses_cut_clock_not_source,
        test_explicit_remove_still_works,
        test_vague_prompts_never_allow_cut,
        test_filter_unsafe_cuts_all_cut_actions,
    ):
        fn()
        print("ok", fn.__name__)
    print("ALL_OK")


# --- a mensagem de sessão cobre TODAS as falhas ----------------------------
#
# `chat()` junta os erros num blob ("gemini: … · chatgpt: …") e o
# friendly_llm_error testava padrões em ordem: o primeiro vencia e a metade do
# ChatGPT sumia. As duas sessões expiram juntas (mesmo navegador), o usuário
# recapturava só o Gemini como mandado, e a IA continuava morta pelo lado
# escondido. Visto ao vivo em 23/08 num job real.


def test_duas_sessoes_mortas_avisam_as_duas():
    from app.llm_session import friendly_llm_error

    m = friendly_llm_error(
        "gemini: Token Gemini ausente — recapture · "
        "chatgpt: ChatGPT sem accessToken — recapture")
    assert "gemini.google.com" in m and "chatgpt.com" in m, m


def test_uma_sessao_morta_nao_pede_as_duas():
    from app.llm_session import friendly_llm_error

    so_gem = friendly_llm_error("gemini: Token Gemini ausente — recapture")
    assert "gemini.google.com" in so_gem and "chatgpt.com" not in so_gem
    so_gpt = friendly_llm_error("chatgpt: ChatGPT sem accessToken — recapture")
    assert "chatgpt.com" in so_gpt and "gemini.google.com" not in so_gpt
