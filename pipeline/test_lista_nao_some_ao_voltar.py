# -*- coding: utf-8 -*-
"""Voltar do preview não apaga a lista nem demora segundos.

Caso real de 02/09 ("quando estou visualizando um vídeo e volto pra
concluído, some todos e demora segundos pra carregar"): voltar recarrega a
página do hub — a lista nascia vazia ("Nenhum vídeo pronto", contadores 0)
até o /api/jobs responder, e ele levava 1-2 s (246 projetos × ~13 leituras
de arquivo). Dois consertos: a tela hidrata do último retrato e diz
"Carregando…" antes da primeira resposta; o servidor guarda o card dos
jobs concluídos (assinatura = registro + mtime da pasta edit e do
timing.json). Medido: 0,66 s → 0,14 s, card idêntico.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class _Store:
    def __init__(self, jobs):
        self._jobs = jobs

    def list(self):
        import copy
        return copy.deepcopy(self._jobs)

    def update(self, *a, **k):  # medir_duracao_em_fundo pode chamar
        pass


def _projeto(tmp_path: Path, nome: str) -> Path:
    edit = tmp_path / nome / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "timing.json").write_text('{"musicaFonte": "reuso: render anterior"}',
                                      encoding="utf-8")
    return edit


def test_card_pronto_vem_do_cache_e_invalida_quando_o_edit_muda(tmp_path, monkeypatch):
    from app import jobs_view

    jobs_view._CACHE_PRONTOS.clear()
    edit = _projeto(tmp_path, "p1")
    job = {"id": "j1", "status": "done", "editDir": str(edit),
           "projectDir": str(edit.parent), "title": "x",
           "sourceDurationSec": 10}
    store = _Store([job])
    chamadas = {"n": 0}
    real = jobs_view._montar_card

    def espiao(*a, **k):
        chamadas["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(jobs_view, "_montar_card", espiao)
    a = jobs_view.build(store, tmp_path)
    b = jobs_view.build(store, tmp_path)
    assert chamadas["n"] == 1, "a segunda chamada devia vir do cache"
    assert a[0]["trilhaNota"] == b[0]["trilhaNota"] == "Reaproveitada"

    # um "Aplicar" reescreve o timing.json: o card tem de ser remontado
    time.sleep(0.02)
    (edit / "timing.json").write_text('{"musicaSkip": "sem trilha"}',
                                      encoding="utf-8")
    os.utime(edit / "timing.json", None)
    c = jobs_view.build(store, tmp_path)
    assert chamadas["n"] == 2
    assert c[0]["trilhaNota"] == "Sem trilha"


def test_job_em_andamento_nunca_usa_cache(tmp_path, monkeypatch):
    from app import jobs_view

    jobs_view._CACHE_PRONTOS.clear()
    edit = _projeto(tmp_path, "p2")
    job = {"id": "j2", "status": "processing", "editDir": str(edit),
           "projectDir": str(edit.parent), "sourceDurationSec": 10}
    store = _Store([job])
    n = {"v": 0}
    real = jobs_view._montar_card
    monkeypatch.setattr(jobs_view, "_montar_card",
                        lambda *a, **k: (n.__setitem__("v", n["v"] + 1), real(*a, **k))[1])
    jobs_view.build(store, tmp_path)
    jobs_view.build(store, tmp_path)
    assert n["v"] == 2


def test_job_apagado_sai_do_cache(tmp_path):
    from app import jobs_view

    jobs_view._CACHE_PRONTOS.clear()
    edit = _projeto(tmp_path, "p3")
    job = {"id": "j3", "status": "done", "editDir": str(edit),
           "projectDir": str(edit.parent), "sourceDurationSec": 10}
    jobs_view.build(_Store([job]), tmp_path)
    assert "j3" in jobs_view._CACHE_PRONTOS
    jobs_view.build(_Store([]), tmp_path)
    assert "j3" not in jobs_view._CACHE_PRONTOS


def test_a_tela_hidrata_do_retrato_e_nao_mente_antes_da_resposta():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'localStorage.getItem("ativavid.jobs.cache")' in js
    assert 'localStorage.setItem("ativavid.jobs.cache"' in js
    assert "jobsLoaded: false" in js and "state.jobsLoaded = true" in js
    i = js.index("function renderInto")
    bloco = js[i:js.index("\nfunction ", i + 10)]
    assert "Carregando os vídeos…" in bloco
    # o "carregando" vem ANTES do texto de fabrica na cadeia de decisao
    assert bloco.index("!state.jobsLoaded") < bloco.index("empty.dataset.textoOriginal)")
