# -*- coding: utf-8 -*-
"""Renomear e aprovar o vídeo direto do cabeçalho do editor (03/09).

Ele abre o vídeo, aprova a edição e marca o nome com ✅ na mão. Agora o
nome do card no cabeçalho é clicável (renomear) e há um checkbox
"Aprovado" que põe/tira o ✅ na frente do nome. Tudo passa pelo
/api/jobs/rename do hub — o card mostra o mesmo nome. O editor precisa do
id do job: o resolvedor passa a devolver {id, title}.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class _Store:
    def __init__(self, jobs):
        self._jobs = jobs

    def list(self):
        return [dict(j) for j in self._jobs]


def test_ficha_do_card_traz_id_e_titulo(tmp_path):
    from app.jobs_view import ficha_do_card

    edit = tmp_path / "p" / "edit"
    job = {"id": "abc", "status": "done", "editDir": str(edit),
           "title": "G1 · C3 · CTA2", "titleLocked": True}
    assert ficha_do_card(_Store([job]), edit) == {"id": "abc", "title": "G1 · C3 · CTA2"}
    assert ficha_do_card(_Store([]), edit) is None


def test_o_estado_leva_id_e_titulo():
    ps = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert '"jobId"' in ps and '"jobTitle"' in ps
    ds = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert "ficha_do_card" in ds


def test_o_cabecalho_renomeia_e_aprova():
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "async function renomearVideoEditado" in js
    assert "async function alternarAprovado" in js
    i = js.index("async function gravarNomeDoVideo")
    bloco = js[i:js.index("\nasync function renomearVideoEditado", i)]
    assert "'/api/jobs/rename'" in bloco and "S.state.jobId" in bloco
    # o ✅ e o mesmo sinal que ele ja usa; marcar poe na frente, desmarcar tira
    assert "APROVADO_RE" in js and "✅ ${limpo}" in js
    j = js.index("const pintarMeta = ")
    corpo = js[j:j + 1400]
    assert "role', 'button'" in corpo and "proj-aprovado" in corpo
    assert "S.state.jobId" in corpo, "sem id nao ha o que renomear — controles so com job"
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    assert ".proj-aprovado" in css
