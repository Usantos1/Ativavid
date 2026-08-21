# -*- coding: utf-8 -*-
"""O ponteiro da pasta de entrega sobrevive ao fim do pipeline.

`ensure_delivery_pack` grava `state["deliveryPack"]` — o caminho de
`publicar/<nome>/`, que é o que o botão "Abrir pasta" usa (`read_pack_dir`).
Logo depois, `_write_preview_state` montava o state.json DO ZERO e o apagava.

MEDIDO nos projetos do usuário: 13 tinham a pasta `publicar/` criada e o
ponteiro perdido. Ele só sobrevivia quando um apply posterior o regravava —
por isso 105 de 128 tinham, e o defeito não era óbvio.

A correção preserva SÓ essa chave: o state continua sendo montado do zero, que
é o que impede chave velha de ressuscitar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_o_ponteiro_da_entrega_nao_e_apagado(tmp_path):
    from pipeline.run_fast import _write_preview_state

    (tmp_path / "state.json").write_text(
        json.dumps({"deliveryPack": "../publicar/meu_video"}), encoding="utf-8")
    _write_preview_state(tmp_path, "fonte.mov", phase=3, message="Pronto", fps=30)
    novo = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert novo.get("deliveryPack") == "../publicar/meu_video"


def test_o_state_continua_montado_do_zero(tmp_path):
    """Preservar tudo ressuscitaria chave velha — é justamente por isso que a
    função monta do zero. Só `deliveryPack` atravessa, porque ela não é dona
    dele."""
    from pipeline.run_fast import _write_preview_state

    (tmp_path / "state.json").write_text(
        json.dumps({"deliveryPack": "../publicar/x", "chaveVelha": 1,
                    "awaitingStyle": True}), encoding="utf-8")
    _write_preview_state(tmp_path, "f.mov", phase=3, message="Pronto", fps=30)
    novo = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "chaveVelha" not in novo
    assert novo["awaitingStyle"] is False, "chave velha sobreviveu por engano"
    assert novo["deliveryPack"] == "../publicar/x"


def test_sem_state_anterior_nao_inventa_ponteiro(tmp_path):
    from pipeline.run_fast import _write_preview_state

    _write_preview_state(tmp_path, "f.mov", phase=1, message="x", fps=30)
    novo = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "deliveryPack" not in novo


def test_state_ilegivel_nao_derruba_o_fim_do_pipeline(tmp_path):
    from pipeline.run_fast import _write_preview_state

    (tmp_path / "state.json").write_text("{ nao sou json", encoding="utf-8")
    _write_preview_state(tmp_path, "f.mov", phase=3, message="Pronto", fps=30)
    novo = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert novo["phase"] == 3


def test_o_botao_abrir_pasta_acha_a_entrega_pelo_ponteiro(tmp_path):
    """Fim a fim da leitura: gravado o ponteiro, `read_pack_dir` acha a pasta."""
    from app.delivery_pack import read_pack_dir

    edit = tmp_path / "projeto" / "edit"
    edit.mkdir(parents=True)
    pack = tmp_path / "projeto" / "publicar" / "meu_video"
    pack.mkdir(parents=True)
    (edit / "state.json").write_text(
        json.dumps({"deliveryPack": "../publicar/meu_video"}), encoding="utf-8")
    assert read_pack_dir(edit) == pack.resolve()
