# -*- coding: utf-8 -*-
"""Editar a linha do tempo não apaga a fala de cada trecho.

Medido nos projetos do usuário:

    passaram por "Aplicar alterações": 17 — **sem NENHUMA `quote`: 17 (100%)**
    nunca passaram:                   169 — sem nenhuma `quote`:  18 (11%)

`write_edl_ranges` montava cada trecho do zero com `source`, `start`,
`end` e, se viesse, `beat` — e o que chega da tela não tem `quote`. Tudo
o que o planejador escreveu (a fala do trecho, o motivo, o ganho) sumia
no primeiro salvamento.

Quem depende: a nota de clareza conta trechos com fala (sem `quote` ela
diria "25 dos 25 takes entraram sem fala clara", falso), o `post_brief`
monta o texto do post a partir das falas, e `guard_ranges` protege gancho
e CTA pelo `beat`.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.quick_corrections import write_edl_ranges  # noqa: E402

ANTIGO = [
    {"source": "SRC", "start": 0.0, "end": 5.0, "beat": "HOOK",
     "quote": "Procurando celular com a lanterna?", "reason": "gancho"},
    {"source": "SRC", "start": 6.0, "end": 12.0, "beat": "B1",
     "quote": "A gente acha em cinco minutos."},
]


def _projeto(tmp_path: Path, antigo=ANTIGO) -> Path:
    (tmp_path / "edl.json").write_text(
        json.dumps({"ranges": antigo}), encoding="utf-8")
    return tmp_path


def _escrever(tmp_path: Path, novos):
    return write_edl_ranges(tmp_path, novos, mark=False)["ranges"]


def test_trecho_igual_mantem_a_fala(tmp_path):
    d = _projeto(tmp_path)
    r = _escrever(d, [{"source": "SRC", "start": 0.0, "end": 5.0}])[0]
    assert r["quote"] == "Procurando celular com a lanterna?"
    assert r["beat"] == "HOOK" and r["reason"] == "gancho"


def test_trecho_encurtado_mantem_a_fala(tmp_path):
    """Aparar as pontas não muda o que é falado ali."""
    d = _projeto(tmp_path)
    r = _escrever(d, [{"source": "SRC", "start": 6.5, "end": 11.0}])[0]
    assert r["quote"] == "A gente acha em cinco minutos."


def test_trecho_novo_nao_inventa_fala(tmp_path):
    """Trecho trazido de volta não tem de quem herdar — inventar seria pior."""
    d = _projeto(tmp_path)
    r = _escrever(d, [{"source": "SRC", "start": 40.0, "end": 42.0}])[0]
    assert "quote" not in r and "beat" not in r


def test_encostar_de_raspao_nao_herda(tmp_path):
    """Herdar a fala do vizinho é pior que não herdar nada."""
    d = _projeto(tmp_path)
    # só 0,2s dos 4,0s caem dentro do trecho antigo
    r = _escrever(d, [{"source": "SRC", "start": 11.8, "end": 15.8}])[0]
    assert "quote" not in r


def test_o_que_a_tela_manda_ganha_do_antigo(tmp_path):
    d = _projeto(tmp_path)
    r = _escrever(d, [{"source": "SRC", "start": 0.0, "end": 5.0,
                       "beat": "CTA"}])[0]
    assert r["beat"] == "CTA"


def test_nao_herda_de_outra_fonte(tmp_path):
    """O relógio de cada take começa do zero: 0-5s da Parte 2 não é
    0-5s da Parte 1."""
    d = _projeto(tmp_path)
    r = _escrever(d, [{"source": "PARTE2", "start": 0.0, "end": 5.0}])[0]
    assert "quote" not in r


def test_os_tempos_continuam_sendo_os_da_tela(tmp_path):
    d = _projeto(tmp_path)
    r = _escrever(d, [{"source": "SRC", "start": 6.5, "end": 11.0}])[0]
    assert (r["start"], r["end"]) == (6.5, 11.0)
