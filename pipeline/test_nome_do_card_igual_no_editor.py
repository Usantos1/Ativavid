# -*- coding: utf-8 -*-
"""O editor e o card mostram o MESMO nome.

03/09: o card dizia "G2 · C1 · CTA2" (título travado do Multiplicador) e o
editor "Bateria descarregando rápido pode ter conserto simples" (stem do
arquivo final) — regras diferentes. Agora o hub empresta ao preview o
resolvedor `titulo_do_card`, espelho do `displayTitle` da tela, e o estado
do projeto leva `jobTitle`; o editor prefere esse nome.
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


def test_titulo_travado_vence_o_arquivo_final(tmp_path):
    from app.jobs_view import titulo_do_card

    edit = tmp_path / "p" / "edit"
    job = {"id": "1", "status": "done", "editDir": str(edit),
           "title": "G2 · C1 · CTA2", "titleLocked": True,
           "final": str(edit / "Bateria descarregando rapido.mp4")}
    assert titulo_do_card(_Store([job]), edit) == "G2 · C1 · CTA2"


def test_sem_trava_vale_o_stem_do_final_menos_os_genericos(tmp_path):
    from app.jobs_view import titulo_do_card

    edit = tmp_path / "p" / "edit"
    base = {"id": "1", "status": "done", "editDir": str(edit), "title": "x"}
    assert titulo_do_card(
        _Store([dict(base, final=str(edit / "Demo completo.mp4"))]), edit
    ) == "Demo completo"
    # final.mp4 generico nao e nome: cai no titulo resolvido do job
    t = titulo_do_card(_Store([dict(base, final=str(edit / "final.mp4"))]), edit)
    assert t and t != "final"


def test_projeto_sem_job_nao_inventa_nome(tmp_path):
    from app.jobs_view import titulo_do_card

    assert titulo_do_card(_Store([]), tmp_path / "x" / "edit") is None


def test_o_caminho_compara_sem_ligar_para_barra_ou_caixa(tmp_path):
    from app.jobs_view import titulo_do_card

    edit = tmp_path / "P" / "edit"
    job = {"id": "1", "status": "done", "editDir": str(edit).replace("\\", "/").upper(),
           "title": "Travado", "titleLocked": True}
    assert titulo_do_card(_Store([job]), edit) == "Travado"


def test_o_estado_leva_o_titulo_e_o_editor_prefere_ele():
    ps = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert "titulo_do_card" in ps and '"jobTitle"' in ps
    ds = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert "ps.Handler.titulo_do_card = " in ds
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function nomeDoVideoEditado")
    bloco = js[i:js.index("\n}", i)]
    assert "S.state.jobTitle" in bloco
    assert bloco.index("jobTitle") < bloco.index("finalVideo"), \
        "o titulo do card tem de vir ANTES do stem do arquivo"
