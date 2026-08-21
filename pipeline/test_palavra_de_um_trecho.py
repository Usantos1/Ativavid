# -*- coding: utf-8 -*-
"""Uma palavra da fonte aparece UMA vez na legenda, não uma por trecho.

`_words_in_range` escolhe por SOBREPOSIÇÃO, então uma palavra que atravessa
dois trechos do EDL era emitida nos DOIS. Como a transcrição às vezes junta uma
fala inteira numa "palavra" só, isso não é raro.

MEDIDO nos 127 projetos do usuário: **93 (73%)** tinham pelo menos uma palavra
em mais de um trecho — 298 cópias extras, até 5x a mesma palavra.

E aparece na tela. Num projeto a fonte diz "bora" UMA vez (0,32 → 4,22 s — a
transcrição juntou tudo) e os três trechos guardados caem dentro dela: a
primeira legenda do vídeo desenhava `bora / bora / bora 32`.

Rodando o algoritmo velho contra o novo no MESMO edl: 298 cópias removidas e
**zero** textos perdidos.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def _projeto(tmp_path: Path, palavras: list[tuple[str, float, float]],
             ranges: list[tuple[float, float]]) -> tuple[dict, Path]:
    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "fonte.json").write_text(json.dumps({
        # `type: "word"` e o formato REAL (o `_word_items` filtra por ele);
        # sem isso o fixture nao produz legenda nenhuma e o teste falha por
        # motivo errado.
        "words": [{"type": "word", "text": t, "start": a, "end": b}
                  for t, a, b in palavras],
    }), encoding="utf-8")
    edl = {
        "ranges": [{"source": "fonte", "start": a, "end": b} for a, b in ranges],
    }
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    return edl, edit


def test_palavra_longa_sobre_varios_trechos_aparece_uma_vez(tmp_path):
    """O caso real: "bora" dura 3,9 s na fonte e os três trechos caem dentro."""
    from helpers.captions_for_remotion import build_captions

    edl, edit = _projeto(
        tmp_path,
        [("bora", 0.32, 4.22), ("32", 4.22, 5.34), ("vai", 5.34, 6.22)],
        [(0.93, 1.463), (3.03, 3.53), (3.76, 5.86)],
    )
    caps = build_captions(edl, edit)
    textos = [c["text"] for c in caps]
    assert textos.count("bora") == 1, f"bora saiu {textos.count('bora')}x: {textos}"


def test_a_palavra_fica_com_o_trecho_que_ela_mais_atravessa(tmp_path):
    """Critério: a maior sobreposição. O trecho que ficou com a maior parte da
    palavra é quem a mostra — senão ela apareceria fora do lugar da fala."""
    from helpers.captions_for_remotion import _dono_de_cada_palavra

    ranges = [{"source": "f", "start": 0.0, "end": 1.0},
              {"source": "f", "start": 1.0, "end": 5.0}]
    palavras = {"f": [{"text": "longa", "start": 0.8, "end": 4.0}]}
    dono = _dono_de_cada_palavra(ranges, palavras)
    assert dono[("f", 0)] == 1, "ficou com o trecho de menor sobreposição"

    # invertido: agora o primeiro trecho e quem cobre mais
    ranges = [{"source": "f", "start": 0.0, "end": 3.5},
              {"source": "f", "start": 3.5, "end": 5.0}]
    dono = _dono_de_cada_palavra(ranges, palavras)
    assert dono[("f", 0)] == 0


def test_empate_fica_com_o_primeiro(tmp_path):
    """Preserva a ordem da fala."""
    from helpers.captions_for_remotion import _dono_de_cada_palavra

    ranges = [{"source": "f", "start": 0.0, "end": 1.0},
              {"source": "f", "start": 1.0, "end": 2.0}]
    palavras = {"f": [{"text": "meio", "start": 0.5, "end": 1.5}]}
    assert _dono_de_cada_palavra(ranges, palavras)[("f", 0)] == 0


def test_nenhuma_palavra_se_perde(tmp_path):
    """A regra só escolhe QUAL trecho mostra — nunca joga a palavra fora."""
    from helpers.captions_for_remotion import build_captions

    edl, edit = _projeto(
        tmp_path,
        [("um", 0.0, 1.0), ("dois", 1.0, 2.0), ("tres", 2.0, 3.0),
         ("quatro", 3.0, 4.0)],
        [(0.0, 2.0), (2.0, 4.0)],
    )
    caps = build_captions(edl, edit)
    assert sorted(c["text"] for c in caps) == ["dois", "quatro", "tres", "um"]


def test_fontes_diferentes_nao_se_atrapalham(tmp_path):
    """O dono é por (fonte, palavra): dois takes distintos podem ter a mesma
    palavra no mesmo instante e as duas têm de aparecer."""
    from helpers.captions_for_remotion import build_captions

    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    for nome in ("a", "b"):
        (edit / "transcripts" / f"{nome}.json").write_text(json.dumps({
            "words": [{"type": "word", "text": "oi", "start": 0.0, "end": 1.0}],
        }), encoding="utf-8")
    edl = {"ranges": [{"source": "a", "start": 0.0, "end": 1.0},
                      {"source": "b", "start": 0.0, "end": 1.0}]}
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    caps = build_captions(edl, edit)
    assert [c["text"] for c in caps] == ["oi", "oi"], (
        "a palavra de outro take foi engolida"
    )


def test_a_transcricao_e_lida_uma_vez_por_fonte():
    """O laço relia o arquivo por TRECHO: um vídeo com 40 trechos abria a mesma
    transcrição 40 vezes."""
    src = (REPO / "helpers" / "captions_for_remotion.py").read_text(encoding="utf-8")
    i = src.index("def build_captions_with_provenance(")
    corpo = src[i:i + 3000]
    assert "por_fonte: dict[str, list] = {}" in corpo
    assert corpo.count("tr_path.read_text") == 0, (
        "voltou a ler a transcrição dentro do laço de trechos"
    )
