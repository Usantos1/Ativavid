# -*- coding: utf-8 -*-
"""O "Dispensar" do aviso de apply falho tem de valer — antes ele voltava sempre.

O cartaz REVISAR era decidido só por `qa.status === "failed"`. O clique em
Dispensar gravava `acknowledgedAt`, mas nada o lia para o cartaz — e o poll
seguinte trazia o aviso de volta, para sempre.

E `acknowledgedAt` NÃO pode ser o critério: a tela marca o ack sozinha ao
mostrar o toast da falha (`maybeToastApply` chama `markApplyAck` também no
`failed`). Se o cartaz sumisse pelo ack, ele sumiria junto com o toast e o
usuário nunca veria o aviso persistente. Por isso o Dispensar ganhou estado
próprio: `dismissedAt`, gravado só pelo clique.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture()
def falha(tmp_path):
    from app import apply_tasks as at

    edit = tmp_path / "proj1" / "edit"
    edit.mkdir(parents=True)
    at.register_task(edit, status=at.STATUS_QUEUED, stage="preparing")
    at.register_task(edit, status=at.STATUS_FAILED, stage="error")
    return at, tmp_path, edit


def test_o_ack_do_toast_nao_tira_a_falha_do_indice(falha):
    """O toast automático não é uma decisão do usuário."""
    at, root, edit = falha
    at.acknowledge_task(root, project_id="proj1")          # o toast
    at.prune_index(root)
    assert len(at._load_index(root)) == 1, (
        "o ack automático apagou o aviso que o usuário ainda não viu"
    )
    v = at.public_view(at.read_task(edit), edit)
    assert v.get("acknowledgedAt") and not v.get("dismissedAt")


def test_o_dispensar_explicito_tira_e_persiste(falha):
    at, root, edit = falha
    at.acknowledge_task(root, project_id="proj1", dismiss=True)
    assert len(at._load_index(root)) == 0, "o Dispensar não tirou do índice"
    v = at.public_view(at.read_task(edit), edit)
    assert v.get("dismissedAt"), "o dispensar não persistiu no projeto"


def test_um_apply_novo_zera_o_dispensar(falha):
    """Falhou de novo = aviso novo. O dispensar antigo não pode engolir a
    falha seguinte."""
    at, root, edit = falha
    at.acknowledge_task(root, project_id="proj1", dismiss=True)
    at.register_task(edit, status=at.STATUS_QUEUED, stage="preparing")
    at.register_task(edit, status=at.STATUS_FAILED, stage="error")
    v = at.public_view(at.read_task(edit), edit)
    assert not v.get("dismissedAt"), "a falha nova nasceu já dispensada"


def test_a_tela_decide_pelo_dismissed_e_nao_pelo_ack():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function applyFailed(")
    corpo = js[i:i + 600]
    assert "applyDismissed(qa)" in corpo, "o cartaz REVISAR ignora o Dispensar"
    assert "acknowledgedAt" not in corpo.replace("// `acknowledgedAt`", ""), (
        "o cartaz voltou a decidir pelo ack, que o toast grava sozinho"
    )
    k = js.index('act === "ackapply"')
    handler = js[k:k + 900]
    assert "dismiss: true" in handler, "o clique não grava o dispensar no servidor"
