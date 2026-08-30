# -*- coding: utf-8 -*-
"""A nota do corte é a nota do corte que existe.

`score.json` é a nota do CORTE (gancho, clareza, ritmo, CTA) e as dicas
que o cartão e o editor mostram. O apply refaz o corte e não refazia a
nota: **13 dos 17 projetos do usuário que passaram por um "Aplicar
alterações" ficaram com a nota velha**, uma delas 90 horas velha.

Caso concreto: o `20260828-072440` foi corrigido às 09:08 e mostra a nota
das 07:33, com as dicas "Há pausas longas que dá para enxugar" e "O
fechamento está longo demais" — conselho sobre um corte que não existe.

Recalcular só passou a ser possível depois que o EDL parou de perder a
`quote` de cada trecho: a nota de clareza conta trechos com fala.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import app.apply_execute as ae  # noqa: E402

AE = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")

RANGES = [
    {"source": "SRC", "start": 0.0, "end": 4.0, "beat": "HOOK",
     "quote": "Procurando celular com a lanterna?"},
    {"source": "SRC", "start": 5.0, "end": 9.0, "beat": "B1",
     "quote": "A gente acha em cinco minutos, sem drama nenhum."},
    {"source": "SRC", "start": 10.0, "end": 14.0, "beat": "CTA",
     "quote": "Vem para a Prime Camp, a gente resolve hoje."},
]
CAPS = [{"text": p} for p in
        ("Procurando celular com a lanterna? A gente acha em cinco "
         "minutos, sem drama nenhum. Vem para a Prime Camp.").split()]


def _cut(d: Path) -> Path:
    """O `_refazer_nota` mede a duração com ffprobe; aqui ela é fingida."""
    import app.apply_execute as _ae

    _ae._probe_duration_real = lambda p: 12.0     # noqa: ARG005
    return d / "cut.mp4"


def _projeto(tmp_path: Path) -> Path:
    (tmp_path / "edl.json").write_text(json.dumps({"ranges": RANGES}),
                                       encoding="utf-8")
    (tmp_path / "job_intent.json").write_text(
        json.dumps({"editingIntent": "dynamic"}), encoding="utf-8")
    (tmp_path / "score.json").write_text(
        json.dumps({"overall": 1, "tips": ["dica do corte velho"]}),
        encoding="utf-8")
    (tmp_path / "verificacao.json").write_text(
        json.dumps({"silencioTotalS": 3.0}), encoding="utf-8")
    return tmp_path


def test_a_nota_e_refeita(tmp_path):
    d = _projeto(tmp_path)
    ae._refazer_nota(d, _cut(d), CAPS, lambda *_: None)
    nota = json.loads((d / "score.json").read_text(encoding="utf-8"))
    assert nota["overall"] != 1
    assert "dica do corte velho" not in (nota.get("tips") or [])


def test_a_clareza_usa_a_fala_dos_trechos(tmp_path):
    """Sem `quote` a nota diria "3 dos 3 takes entraram sem fala clara"."""
    d = _projeto(tmp_path)
    ae._refazer_nota(d, _cut(d), CAPS, lambda *_: None)
    nota = json.loads((d / "score.json").read_text(encoding="utf-8"))
    assert nota["clarity"] >= 70, nota


def test_o_diagnostico_do_corte_anterior_nao_sobrevive(tmp_path):
    """Ele descreve pausa e nível de um corte que não existe mais — o
    mesmo critério que o `run_fast` já aplica."""
    d = _projeto(tmp_path)
    ae._refazer_nota(d, _cut(d), CAPS, lambda *_: None)
    assert not (d / "verificacao.json").exists()


def test_sem_edl_nao_mexe_na_nota(tmp_path):
    d = _projeto(tmp_path)
    (d / "edl.json").unlink()
    ae._refazer_nota(d, _cut(d), CAPS, lambda *_: None)
    assert json.loads((d / "score.json").read_text(encoding="utf-8"))["overall"] == 1


def test_nunca_levanta(tmp_path):
    """A nota é um extra; o vídeo já está entregue."""
    recado = []
    ae._refazer_nota(tmp_path / "nao-existe", tmp_path / "x.mp4", None, recado.append)
    ae._refazer_nota(tmp_path, tmp_path / "vazio.mp4", CAPS, recado.append)


def test_o_apply_chama_so_quando_refaz_o_corte():
    i = AE.index("_refazer_nota(edit,")
    trecho = AE[i - 300:i]
    assert 'if plan.get("rebuildCut"):' in trecho
