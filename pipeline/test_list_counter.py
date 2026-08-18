"""Contador de lista: sequência ascendente, falsos positivos e mínimo de 2."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from app.list_counter import detect_list_markers  # noqa: E402


def _w(text, ms):
    return {"text": text, "startMs": ms, "endMs": ms + 400}


def test_detects_simple_enumeration():
    words = [_w("Primeiro,", 1000), _w("limpe", 1500), _w("a", 1800),
             _w("tela.", 2000), _w("Segundo,", 5000), _w("aplique.", 5600),
             _w("Terceiro,", 9000), _w("pronto!", 9500)]
    m = detect_list_markers(words)
    assert [x["n"] for x in m] == [1, 2, 3]
    assert m[0]["atSec"] == 1.0
    assert m[2]["atSec"] == 9.0


def test_segundo_de_tempo_nao_dispara():
    # "trinta segundos" sem um "primeiro" antes: nada
    words = [_w("leva", 0), _w("trinta", 500), _w("segundos", 1000)]
    assert detect_list_markers(words) == []


def test_primeiro_sozinho_nao_e_lista():
    words = [_w("primeiro", 0), _w("eu", 500), _w("limpo", 1000)]
    assert detect_list_markers(words) == []


def test_quarto_comodo_nao_dispara_fora_de_sequencia():
    words = [_w("la", 0), _w("no", 400), _w("quarto", 800)]
    assert detect_list_markers(words) == []


def test_numero_um_abre_sequencia():
    words = [_w("motivo", 0), _w("um", 500), _w("bla", 2000),
             _w("motivo", 6000), _w("dois", 6500)]
    m = detect_list_markers(words)
    assert [x["n"] for x in m] == [1, 2]


def test_um_sem_prefixo_nao_abre():
    # "um celular" não é enumeração
    words = [_w("comprei", 0), _w("um", 400), _w("celular", 800),
             _w("segundo", 3000)]
    assert detect_list_markers(words) == []
