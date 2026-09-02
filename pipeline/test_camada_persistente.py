# -*- coding: utf-8 -*-
"""Mídia posta à mão PERSISTE como camada editável depois do render.

Caso real (02/09, com print): "cadê o vídeo ali? após renderizar ele some
da timeline". Duas causas: o editor varria TODOS os inserts no estilo limpa
(inclusive os manuais) e só desenhava cartão de bloco `isNew`.

Protocolo novo: a tela manda o estado COMPLETO em `manualInserts` e o
pipeline SUBSTITUI o que há de manual — mover/apagar/reenquadrar um insert
já aplicado não duplica nem ressuscita. `newInserts` (preview antigo) segue
aceito, só acrescentando.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _cenario(tmp_path: Path, preview_ed: dict, edit_data: dict):
    from pipeline.run_fast import midia_do_editor

    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    for rel in ("foto.png", "take.mp4", "broll.jpg"):
        (public / rel).write_bytes(b"x")
    (edit / "preview_edits.json").write_text(
        json.dumps({"editData": preview_ed}), encoding="utf-8")
    midia_do_editor(edit, public, edit_data)
    return edit_data


def test_manual_substitui_mover_e_apagar_sem_duplicar(tmp_path):
    """O usuário MOVEU a foto (start 2→5) e APAGOU o take. A lista nova é a
    verdade: nada duplica, o apagado some, o b-roll automático fica."""
    ed = _cenario(
        tmp_path,
        {"manualInserts": [
            {"mid": "mfoto1", "src": "foto.png", "start": 5.0, "end": 7.5,
             "x": 0.3, "fx": 0.1, "entrada": "pop"},
        ]},
        {"inserts": [
            {"src": "broll.jpg", "start": 1.0, "end": 2.0, "auto": True},
            {"src": "foto.png", "start": 2.0, "end": 4.5, "manual": True,
             "mid": "mfoto1"},
            {"src": "take.mp4", "start": 8.0, "end": 10.0, "manual": True,
             "mid": "mtake1"},
        ]},
    )
    ins = ed["inserts"]
    assert [x["src"] for x in ins] == ["broll.jpg", "foto.png"], ins
    foto = ins[1]
    assert foto["start"] == 5.0 and foto["manual"] is True
    assert foto["x"] == 0.3 and foto["fx"] == 0.1 and foto["entrada"] == "pop"
    assert foto["mid"] == "mfoto1"
    assert not any(x.get("src") == "take.mp4" for x in ins), "o apagado voltou"


def test_lista_manual_vazia_apaga_tudo_que_era_manual(tmp_path):
    ed = _cenario(
        tmp_path,
        {"manualInserts": []},
        {"inserts": [
            {"src": "broll.jpg", "start": 1.0, "end": 2.0},
            {"src": "foto.png", "start": 2.0, "end": 4.0, "manual": True},
        ]},
    )
    assert [x["src"] for x in ed["inserts"]] == ["broll.jpg"]


def test_preview_antigo_newinserts_so_acrescenta(tmp_path):
    """Sem `manualInserts` vale o contrato velho: acrescenta e deduplica
    por src+start — projeto salvo por versão anterior não muda de regra."""
    ed = _cenario(
        tmp_path,
        {"newInserts": [
            {"src": "foto.png", "start": 2.0, "end": 4.5},   # duplicata
            {"src": "take.mp4", "start": 8.0, "end": 10.0},  # novo
        ]},
        {"inserts": [
            {"src": "foto.png", "start": 2.0, "end": 4.5, "manual": True},
        ]},
    )
    srcs = [x["src"] for x in ed["inserts"]]
    assert srcs == ["foto.png", "take.mp4"], srcs


def test_editor_nao_varre_mais_o_manual_no_limpa():
    """A causa nº 1 do sumiço: stripAutoInsertsIfLimpa apagava TUDO."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function stripAutoInsertsIfLimpa")
    corpo = js[i:i + 900]
    assert "it.manual" in corpo, "o limpa voltou a varrer a mídia manual"
    # e o desenho do cartão aceita manual, não só isNew (na Edição; na
    # Visual o final já tem a mídia queimada — ver a âncora naFinal abaixo)
    j = js.index("const agora = S.insertsDraft.filter")
    assert "c.isNew || (c.manual && !naFinal)" in js[j:j + 400], (
        "o cartão do insert aplicado sumiu do preview")
    # e o salvar manda o estado completo
    assert "manualInserts: S.insertsDraft" in js
    # na aba VISUAL o final ja tem a midia queimada: o cartao aplicado NAO
    # desenha por cima (imagem dupla com "a de tras se mexendo", 02/09)
    assert "c.manual && !naFinal" in js


def test_clipe_da_biblioteca_mostra_um_quadro():
    """No seletor 'Inserir imagem / B-roll' o clipe saia como cartao escuro
    com um play — sem miniatura nao da para saber qual video e (02/09). O
    capturador de quadro e UM so, com cache por URL, servindo o seletor e
    os blocos da timeline."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "function capturarQuadroDeVideo" in js
    i = js.index("if (it.kind === 'clip') {")
    assert "capturarQuadroDeVideo(thumb" in js[i:i + 700], (
        "o clipe da Biblioteca voltou a ficar sem miniatura")
    # e os blocos da timeline usam o MESMO capturador
    j = js.index("function miniaturaNoChip")
    assert "capturarQuadroDeVideo(url" in js[j:j + 600]
