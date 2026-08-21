"""Reprocesso não pode desfazer corte manual; lascas da IA não viram flash."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO / "pipeline"))

from run_fast import load_manual_edl_ranges  # noqa: E402


def _project(tmp_path: Path, *, applied: bool = True, preset_used: dict | None = None,
             cut_style: dict | None = None) -> Path:
    """`cut_style` = os knobs CONGELADOS no edl.json, que e o "antes" real.

    `preset_used` continua aceito de proposito: os testes que o usam provam que
    ele NAO decide mais nada. O worker reescreve o preset-used.json com o
    preset atual antes de rodar, entao le-lo era comparar o preset com ele
    mesmo — a guarda nunca disparava.
    """
    edit = tmp_path / "edit"
    edit.mkdir()
    if applied:
        (edit / "preview_edits.applied.json").write_text("{}", encoding="utf-8")
    edl: dict = {
        "ranges": [
            {"source": "IMG", "start": 1.0, "end": 5.0, "beat": "HOOK"},
            {"source": "IMG", "start": 7.0, "end": 12.0, "beat": "B1", "gain_db": 3.0},
        ],
    }
    if cut_style is not None:
        edl["cutStyle"] = cut_style
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    if preset_used is not None:
        (edit / "preset-used.json").write_text(json.dumps(preset_used), encoding="utf-8")
    return edit


PRESET = {"rhythm": "dinamico", "intensity": "medio", "editingIntent": "dynamic",
          "contentType": "humor", "speechClean": "medio"}


def test_reuses_manual_edl_when_cut_knobs_unchanged(tmp_path):
    edit = _project(tmp_path, cut_style=dict(PRESET))
    ranges = load_manual_edl_ranges(edit, "IMG", dict(PRESET))
    assert ranges is not None
    assert [(r["start"], r["end"]) for r in ranges] == [(1.0, 5.0), (7.0, 12.0)]
    assert ranges[1]["gain_db"] == 3.0


def test_replans_when_rhythm_changed(tmp_path):
    edit = _project(tmp_path, cut_style=dict(PRESET))
    changed = dict(PRESET, rhythm="muito_rapido")
    assert load_manual_edl_ranges(edit, "IMG", changed) is None


def test_replaneja_com_qualquer_knob_de_corte(tmp_path):
    for knob, novo_valor in (("intensity", "forte"), ("editingIntent", "complete"),
                             ("contentType", "viral"), ("speechClean", "agressivo")):
        base = tmp_path / knob
        base.mkdir(parents=True, exist_ok=True)
        edit = _project(base, cut_style=dict(PRESET))
        assert load_manual_edl_ranges(edit, "IMG", dict(PRESET, **{knob: novo_valor})) is None, (
            f"mudar {knob} nao replanejou o corte"
        )


def test_o_preset_used_nao_decide_mais_nada(tmp_path):
    """Ele e escrito com o preset ATUAL antes de rodar: le-lo era comparar o
    preset com ele mesmo, e a guarda nunca disparava. Aqui ele diz uma coisa e
    o corte congelado diz outra — quem manda e o congelado."""
    edit = _project(tmp_path, preset_used=dict(PRESET, rhythm="calmo"),
                    cut_style=dict(PRESET))
    assert load_manual_edl_ranges(edit, "IMG", dict(PRESET)) is not None


def test_edl_antigo_sem_knobs_mantem_o_corte(tmp_path):
    """Projeto de antes deste campo existir: recortar sozinho seria pior do que
    nao replanejar."""
    edit = _project(tmp_path, preset_used=dict(PRESET))
    assert load_manual_edl_ranges(edit, "IMG", dict(PRESET, rhythm="calmo")) is not None


def test_no_reuse_without_prior_manual_edit(tmp_path):
    edit = _project(tmp_path, applied=False, cut_style=dict(PRESET))
    assert load_manual_edl_ranges(edit, "IMG", dict(PRESET)) is None


def test_no_reuse_for_other_source(tmp_path):
    edit = _project(tmp_path, cut_style=dict(PRESET))
    assert load_manual_edl_ranges(edit, "OUTRO", dict(PRESET)) is None


def test_headline_only_change_still_reuses(tmp_path):
    # headline/estilo visual não são knobs de corte
    edit = _project(tmp_path, cut_style=dict(PRESET))
    preset = dict(PRESET, headline="pilula", headlineText="Nova headline")
    assert load_manual_edl_ranges(edit, "IMG", preset) is not None


def test_corrections_marker_allows_reuse(tmp_path):
    # quick apply não passa por preview_edits: a evidência de edição manual
    # fica em corrections.json (dirty.edl / appliedAt)
    edit = _project(tmp_path, applied=False, preset_used=dict(PRESET))
    (edit / "corrections.json").write_text(json.dumps({
        "dirty": {"edl": True}, "pending": {"edl": 2},
    }), encoding="utf-8")
    assert load_manual_edl_ranges(edit, "IMG", dict(PRESET)) is not None


def test_apply_fallback_requeues_and_clears_task(tmp_path, monkeypatch):
    # PrepareError não pode deixar o projeto travado: com fallback_full o
    # Apply delega ao rerun completo e a tarefa sai da frente do card.
    import app.apply_execute as ax

    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    monkeypatch.setattr(ax, "plan_apply_changes", lambda corr: {"mode": "RENDER_VISUAL"})
    monkeypatch.setattr(ax, "execute_apply_plan",
                        lambda e, plan, hooks=None: {"ok": False, "prepareFailed": True})
    calls = []
    res = ax.start_apply(edit, fallback_full=lambda: calls.append(1) or True)
    assert res.get("started")
    # A thread do Apply concorre com o resto da máquina: com a fila cheia,
    # 5s não bastam. Espera generosa, mas sai assim que o estado chega.
    import time as _t
    for _ in range(300):
        st = ax.read_apply_status(edit)
        if st.get("stage") == "queued" and not st.get("running") and calls:
            break
        _t.sleep(0.1)
    assert calls, "fallback_full não foi chamado"
    st = ax.read_apply_status(edit)
    assert st.get("stage") == "queued" and st.get("ok") is None
    assert not (edit / "apply_task.json").exists()


def test_requeue_fallback_finds_job_and_skips_running_one(tmp_path):
    import helpers.preview_server as ps

    proj = tmp_path / "20260818_projeto_abc"
    (proj / "edit").mkdir(parents=True)

    class FakeStore:
        def __init__(self):
            self.updates = []

        def list(self):
            return [{"id": "abc", "projectDir": str(proj), "status": "done"}]

        def update(self, jid, **kw):
            self.updates.append((jid, kw))

    class FakeWorker:
        busy_id = None

        def __init__(self):
            self.queued = []

        def enqueue(self, jid):
            self.queued.append(jid)

    h = ps.Handler.__new__(ps.Handler)
    h.root = proj / "edit"
    h.store, h.worker = FakeStore(), FakeWorker()
    assert h._requeue_full_fallback()() is True
    assert h.worker.queued == ["abc"]
    assert h.store.updates[0][1]["status"] == "queued"

    # job em andamento: não reenfileira por cima
    h.worker.busy_id = "abc"
    assert h._requeue_full_fallback()() is False


def test_requeue_fallback_absent_without_store(tmp_path):
    import helpers.preview_server as ps

    h = ps.Handler.__new__(ps.Handler)
    h.root = tmp_path
    assert h._requeue_full_fallback() is None


def test_llm_plan_drops_sliver_takes():
    from llm_cut_plan import MIN_TAKE_S, _normalize_ranges

    # região de fala minúscula: o snap não tem para onde expandir e o take
    # sai com ~0,2s — exatamente a lasca vista em produção (1.48→1.65)
    regions = [(1.48, 1.65), (3.0, 10.0)]
    data = {"ranges": [
        {"start": 1.48, "end": 1.65, "beat": "HOOK"},
        {"start": 3.5, "end": 9.5, "beat": "B1"},
    ]}
    out = _normalize_ranges(data, source_key="IMG", regions=regions, voice={})
    assert all(r["end"] - r["start"] >= MIN_TAKE_S for r in out)
    assert len(out) == 1


def test_mark_interrupted_unsticks_apply_status(tmp_path):
    from app.apply_tasks import INTERRUPTED_MSG, mark_interrupted

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "apply_status.json").write_text(json.dumps({
        "running": True, "ok": None, "message": "Aplicando edição...",
        "stage": "visual", "pid": 12345, "error": None,
    }), encoding="utf-8")
    mark_interrupted(edit, {"projectId": "p", "editDir": str(edit)})
    row = json.loads((edit / "apply_status.json").read_text(encoding="utf-8"))
    assert row["running"] is False
    assert row["ok"] is False
    assert INTERRUPTED_MSG in row["message"]
