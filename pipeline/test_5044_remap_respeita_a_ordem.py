# -*- coding: utf-8 -*-
"""5.0.44: troca pequena de posição depois do remap volta à ordem original.

Caso real (cliente, 04/09): uma correção de palavra deixou três palavras
com tempo sintético de +1 ms cada ("A" 19440, "parte" 19441, "da" 19442).
Remapeadas por provenance saíram "da" 19209 e "parte" 19240; o sort por
início trocou as duas, o validador recusou ("ordem das palavras
invertida") e o app refez o vídeo inteiro — 2,5 min no lugar de 1, sem
ninguém saber por quê. Reproduzido com o snapshot `versions/v3.json` do
projeto: antes `'ordem das palavras invertida'`, depois `None`.

A ordem das palavras é o que o vídeo mostra; dezenas de ms no início
ninguém vê. Então as PALAVRAS trocam de lugar e os TEMPOS ficam. Troca
grande é reordenação de verdade: fica, e o validador decide.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import caption_remap as cr  # noqa: E402


def _w(texto, s, e, ordem):
    return {"text": texto, "startMs": s, "endMs": e, "timestampMs": (s + e) // 2,
            cr._ORDEM: ordem}


def test_troca_pequena_volta_a_ordem_e_mantem_os_tempos():
    # ordem original: A(0) parte(1) da(2) Shopee(3); o sort por inicio pos
    # "da" antes de "parte" por 31 ms
    r = [_w("A", 19140, 19240, 0), _w("da", 19209, 19307, 2),
         _w("parte", 19240, 19620, 1), _w("Shopee.", 19307, 19687, 3)]
    cr._respeitar_ordem_original(r, "ms")
    assert [x["text"] for x in r] == ["A", "parte", "da", "Shopee."]
    assert [x["startMs"] for x in r] == [19140, 19209, 19240, 19307], "os tempos ficam no lugar"
    assert [x["endMs"] for x in r] == [19240, 19307, 19620, 19687]
    assert r[1]["timestampMs"] == (19209 + 19307) // 2


def test_troca_grande_e_reordenacao_de_verdade_e_fica():
    r = [_w("depois", 1000, 1400, 5), _w("antes", 3000, 3400, 1)]
    cr._respeitar_ordem_original(r, "ms")
    assert [x["text"] for x in r] == ["depois", "antes"]


def test_tres_fora_de_ordem_voltam():
    r = [_w("c", 100, 150, 2), _w("b", 120, 170, 1), _w("a", 140, 190, 0)]
    cr._respeitar_ordem_original(r, "ms")
    assert [x["text"] for x in r] == ["a", "b", "c"]
    assert [x["startMs"] for x in r] == [100, 120, 140]


def test_unidade_em_segundos_tambem():
    r = [{"text": "da", "start": 1.209, "end": 1.307, cr._ORDEM: 2},
         {"text": "parte", "start": 1.24, "end": 1.62, cr._ORDEM: 1}]
    cr._respeitar_ordem_original(r, "s")
    assert [x["text"] for x in r] == ["parte", "da"]
    assert [x["start"] for x in r] == [1.209, 1.24]


def test_sem_indice_nao_mexe():
    r = [{"text": "x", "startMs": 10, "endMs": 20}, {"text": "y", "startMs": 12, "endMs": 22}]
    cr._respeitar_ordem_original(r, "ms")
    assert [x["text"] for x in r] == ["x", "y"]


def test_o_remap_chama_e_nao_vaza_a_chave():
    src = (REPO / "app" / "caption_remap.py").read_text(encoding="utf-8")
    i = src.index("result.sort(key=lambda c: _item_span(c)[0])")
    trecho = src[i:i + 200]
    assert "_respeitar_ordem_original(result, unit)" in trecho
    assert "item.pop(_ORDEM, None)" in trecho
