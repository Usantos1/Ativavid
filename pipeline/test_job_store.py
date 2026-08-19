# -*- coding: utf-8 -*-
"""Fila em SQLite: migração, isolamento e dois processos na mesma pasta."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.apply_tasks import _lookup_job  # noqa: E402
from app.job_store import SqliteJobStore  # noqa: E402


def _jobs_json(root: Path, jobs: list[dict]) -> None:
    meta = root / ".ativavid"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "jobs.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


# ---------------------------------------------------------------- migração
def test_migra_jobs_json_e_guarda_backup(tmp_path):
    _jobs_json(tmp_path, [
        {"id": "j1", "status": "done", "createdAt": "2026-08-01T00:00:00Z"},
        {"id": "j2", "status": "queued", "createdAt": "2026-08-02T00:00:00Z"},
    ])
    store = SqliteJobStore(tmp_path)
    assert [j["id"] for j in store.list()] == ["j2", "j1"], "mais recente primeiro"
    assert not (tmp_path / ".ativavid" / "jobs.json").exists()
    assert (tmp_path / ".ativavid" / "jobs.json.bak").exists(), "sem retorno possível"


def test_migracao_nao_repete_e_nao_ressuscita_apagado(tmp_path):
    _jobs_json(tmp_path, [{"id": "j1", "status": "done"}])
    SqliteJobStore(tmp_path).delete("j1")
    # o .bak continua lá; abrir de novo não pode trazer o job de volta
    assert SqliteJobStore(tmp_path).list() == []


def test_migracao_de_arquivo_corrompido_nao_derruba_o_app(tmp_path):
    meta = tmp_path / ".ativavid"
    meta.mkdir(parents=True)
    (meta / "jobs.json").write_text("{lixo", encoding="utf-8")
    assert SqliteJobStore(tmp_path).list() == []


# ------------------------------------------------- dois escritores (o bug)
def test_dois_processos_nao_se_sobrescrevem(tmp_path):
    """Era o defeito do jobs.json: cada store tinha o retrato inteiro e o
    último a gravar desfazia o outro — o job voltava de 'Editando' para 'Na
    fila'. Daí a regra de nunca subir um dev server na fila real."""
    a = SqliteJobStore(tmp_path)
    a.upsert({"id": "j1", "status": "queued"})
    a.upsert({"id": "j2", "status": "queued"})

    b = SqliteJobStore(tmp_path)          # segundo servidor, mesma pasta
    a.update("j1", status="processing", message="Editando...")
    b.update("j2", status="done", message="Pronto")

    estados = {j["id"]: j["status"] for j in SqliteJobStore(tmp_path).list()}
    assert estados == {"j1": "processing", "j2": "done"}


def test_escritor_novo_ve_o_que_o_outro_gravou(tmp_path):
    a = SqliteJobStore(tmp_path)
    a.upsert({"id": "j1", "status": "queued"})
    b = SqliteJobStore(tmp_path)
    a.update("j1", status="done")
    assert b.get("j1")["status"] == "done", "leitura ficou presa num retrato velho"


# ------------------------------------------------------------- isolamento
def test_listar_nao_da_alias_da_fila(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "status": "queued", "sources": ["a.mp4"]})
    vista = store.list()[0]
    vista["status"] = "done"
    vista["sources"].append("b.mp4")
    vivo = store.get("j1")
    assert vivo["status"] == "queued"
    assert vivo["sources"] == ["a.mp4"]


def test_quick_apply_nunca_e_gravado(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "status": "done", "quickApply": {"status": "failed"}})
    assert "quickApply" not in store.get("j1")


# ------------------------------------------------------------- ordenação
def test_empate_mantem_a_ordem_de_entrada(tmp_path):
    """13 vídeos importados no mesmo segundo não podem embaralhar: os ids são
    uuid, então desempatar por id sortearia a fila."""
    store = SqliteJobStore(tmp_path)
    for i in range(6):
        store.upsert({"id": f"j{i}", "createdAt": "2026-08-19T10:00:00Z"})
    assert [j["id"] for j in store.list()] == [f"j{i}" for i in range(6)]


def test_termino_manda_na_ordem(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "velho", "createdAt": "2026-08-01T00:00:00Z"})
    store.upsert({"id": "reeditado", "createdAt": "2026-07-01T00:00:00Z",
                  "finishedAt": "2026-08-19T00:00:00Z"})
    assert store.list()[0]["id"] == "reeditado"


# --------------------------------------------------------- outro processo
def test_apply_acha_o_job_lendo_o_banco(tmp_path):
    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    SqliteJobStore(tmp_path).upsert({
        "id": "abc", "title": "Meu vídeo", "status": "done",
        "projectDir": str(tmp_path / "proj"), "editDir": str(edit)})
    assert _lookup_job(edit, tmp_path) == ("abc", "Meu vídeo")


def test_apply_ainda_le_jobs_json_de_instalacao_antiga(tmp_path):
    """Quem abrir o Apply antes de o servidor migrar não pode ficar cego."""
    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    _jobs_json(tmp_path, [{"id": "abc", "title": "Antigo", "editDir": str(edit)}])
    assert _lookup_job(edit, tmp_path) == ("abc", "Antigo")


# ------------------------------------------------------------------ resto
def test_update_de_job_inexistente_devolve_none(tmp_path):
    assert SqliteJobStore(tmp_path).update("nao_existe", status="done") is None


def test_delete_devolve_o_job_removido(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "status": "done", "title": "X"})
    assert store.delete("j1")["title"] == "X"
    assert store.delete("j1") is None


def test_acentos_sobrevivem_ao_banco(tmp_path):
    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "title": "Promoção de Março — não é ação"})
    assert SqliteJobStore(tmp_path).get("j1")["title"] == "Promoção de Março — não é ação"


def test_uso_em_varias_threads(tmp_path):
    """O servidor é ThreadingHTTPServer: sqlite3 não deixa compartilhar
    conexão entre threads, então cada uma precisa da sua."""
    import threading

    store = SqliteJobStore(tmp_path)
    store.upsert({"id": "j1", "status": "queued"})
    erros: list[BaseException] = []

    def mexe(n: int) -> None:
        try:
            for _ in range(20):
                store.update("j1", progress=n)
                store.list()
        except BaseException as e:  # noqa: BLE001
            erros.append(e)

    ts = [threading.Thread(target=mexe, args=(i,)) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not erros, erros
    assert store.get("j1") is not None
