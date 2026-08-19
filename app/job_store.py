"""Fila em SQLite — a fonte da verdade dos jobs.

Antes a fila era um jobs.json que cada JobStore carregava INTEIRO na memória e
reescrevia por completo a cada atualização. Isso tem um defeito silencioso: dois
processos com a mesma pasta de projetos (o app e um dev server, o app e um
segundo app) trabalham sobre retratos independentes, e quem grava por último
desfaz o trabalho do outro sem erro nenhum — um job que estava "Editando..."
voltava para "Na fila". A regra "nunca suba um dev server na fila real" existia
para contornar isto.

Aqui cada gravação toca UMA linha, dentro de uma transação, e nenhuma leitura
usa retrato em memória. Dois processos passam a se intercalar em vez de se
sobrescrever.

O job continua sendo um dicionário livre (o app carimba dezenas de campos): ele
mora em `data` como JSON. Só o que é usado para ordenar e procurar vira coluna.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    recency     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '',
    project_dir TEXT NOT NULL DEFAULT '',
    edit_dir    TEXT NOT NULL DEFAULT '',
    seq         INTEGER NOT NULL DEFAULT 0,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_recency ON jobs (recency DESC);
CREATE INDEX IF NOT EXISTS jobs_project ON jobs (project_dir);
"""

# Campos DERIVADOS de outra fonte (a tarefa de Apply). Nunca podem ser
# gravados: uma cópia velha aqui sobrevive à tarefa e o card fica preso em
# "REVISAR" para sempre — foi o que travou a fila do usuário na v2.13/v2.14.
DERIVED_KEYS = ("quickApply",)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def recency_of(job: dict) -> str:
    """Mais recente: término (reedição) > atualização > criação."""
    return str(job.get("finishedAt") or job.get("updatedAt") or job.get("createdAt") or "")


class SqliteJobStore:
    """Mesma interface do JobStore antigo: list/get/upsert/update/delete."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_dir = self.root / ".ativavid"
        self.meta_dir.mkdir(exist_ok=True)
        self.db_path = self.meta_dir / "jobs.db"
        self.jobs_path = self.meta_dir / "jobs.json"  # legado: migração e leitura externa
        self._local = threading.local()
        # executescript faz commit implícito: fica fora de qualquer transação.
        self._cx().executescript(SCHEMA)
        self._migrate_from_json()

    # ---------------- conexão ----------------
    def _cx(self) -> sqlite3.Connection:
        """Uma conexão POR THREAD — sqlite3 não permite compartilhar entre elas."""
        cx = getattr(self._local, "cx", None)
        if cx is None:
            cx = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
            cx.execute("PRAGMA journal_mode=WAL")   # leitor não bloqueia escritor
            cx.execute("PRAGMA synchronous=NORMAL")
            cx.execute("PRAGMA busy_timeout=15000")
            self._local.cx = cx
        return cx

    class _Tx:
        def __init__(self, cx: sqlite3.Connection, write: bool):
            self.cx, self.write = cx, write

        def __enter__(self) -> sqlite3.Connection:
            if self.write:
                # IMMEDIATE pega o lock de escrita na hora: dois processos
                # serializam em vez de descobrir o conflito no commit.
                self.cx.execute("BEGIN IMMEDIATE")
            return self.cx

        def __exit__(self, exc_type, exc, tb) -> None:
            if not self.write:
                return
            if not self.cx.in_transaction:
                return
            self.cx.execute("COMMIT" if exc_type is None else "ROLLBACK")

    def _tx(self, write: bool = True) -> "SqliteJobStore._Tx":
        return self._Tx(self._cx(), write)

    # ---------------- migração ----------------
    def _migrate_from_json(self) -> None:
        """Importa o jobs.json uma vez e o guarda como .bak (permite voltar)."""
        if not self.jobs_path.exists():
            return
        cx = self._cx()
        if cx.execute("SELECT 1 FROM jobs LIMIT 1").fetchone():
            return
        try:
            raw = json.loads(self.jobs_path.read_text(encoding="utf-8-sig"))
            jobs = [j for j in (raw.get("jobs") or []) if isinstance(j, dict) and j.get("id")]
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            return
        for job in jobs:
            self.upsert(job)
        try:
            self.jobs_path.replace(self.jobs_path.with_suffix(".json.bak"))
        except OSError:
            pass
        print(f"[fila] migrados {len(jobs)} job(s) de jobs.json para jobs.db", flush=True)

    # ---------------- leitura ----------------
    @staticmethod
    def _row(data: str) -> dict:
        return json.loads(data)

    def list(self) -> list[dict]:
        """Cada chamada desserializa do banco: ninguém recebe alias da fila.

        Os dois /api/jobs carimbam campos de visão (hasCut, stage, progress,
        message...) no que recebem daqui; com o dict vivo isso acabava gravado.
        """
        rows = self._cx().execute(
            "SELECT data FROM jobs ORDER BY recency DESC, seq ASC").fetchall()
        return [self._row(r[0]) for r in rows]

    def get(self, job_id: str) -> dict | None:
        r = self._cx().execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row(r[0]) if r else None

    # ---------------- escrita ----------------
    @staticmethod
    def _clean(job: dict) -> dict:
        job = dict(job)
        for k in DERIVED_KEYS:
            job.pop(k, None)
        return job

    def _write(self, cx: sqlite3.Connection, job: dict) -> None:
        job = self._clean(job)
        cx.execute(
            "INSERT INTO jobs (id, recency, status, project_dir, edit_dir, seq, data) "
            "VALUES (?,?,?,?,?,(SELECT COALESCE(MAX(seq),0)+1 FROM jobs),?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "recency=excluded.recency, status=excluded.status, "
            "project_dir=excluded.project_dir, edit_dir=excluded.edit_dir, "
            "data=excluded.data",
            (str(job["id"]), recency_of(job), str(job.get("status") or ""),
             str(job.get("projectDir") or ""), str(job.get("editDir") or ""),
             json.dumps(job, ensure_ascii=False)),
        )

    def upsert(self, job: dict) -> None:
        with self._tx() as cx:
            self._write(cx, job)
        self._bump()

    def update(self, job_id: str, **fields: Any) -> dict | None:
        """Lê e grava DENTRO da mesma transação.

        Ler fora dela é o que fazia o segundo processo escrever por cima de uma
        versão já vencida.
        """
        with self._tx() as cx:
            r = cx.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not r:
                return None
            job = self._row(r[0])
            job.update(fields)
            job["updatedAt"] = _utc()
            self._write(cx, job)
        self._bump()
        return job

    def delete(self, job_id: str) -> dict | None:
        """Tira da fila. Quem chamou apaga os arquivos, se quiser."""
        with self._tx() as cx:
            r = cx.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not r:
                return None
            cx.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        self._bump()
        return self._row(r[0])

    @staticmethod
    def _bump() -> None:
        try:
            from app.event_bus import bump

            bump()  # acorda o /api/events — a Fila atualiza sem poll cego
        except Exception:  # noqa: BLE001
            pass
