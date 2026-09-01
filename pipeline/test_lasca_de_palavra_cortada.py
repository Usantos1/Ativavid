# -*- coding: utf-8 -*-
"""Palavra que o corte removeu quase inteira NÃO vira legenda.

Caso real (C066, 01/09): o corte tirou 19,127→19,76s da fonte e a palavra
"né?" (19,119→19,699) ficou com só 8ms dentro do trecho mantido. O remap
emitia essa lasca — e como o EDL tinha J-cut (o áudio do trecho seguinte
começa ANTES do corte de vídeo), a lasca caiu DENTRO da fala seguinte: a
legenda na tela dizia "Prime né? Camp" no meio do nome da marca do usuário.

Regra: a palavra sai da legenda quando a parte audível no corte é menor que
60ms E menor que 25% da duração dela. Palavra curta INTEIRA dentro do trecho
continua aparecendo (a fração é 100%).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def _projeto(tmp_path: Path, palavras: list[tuple[str, float, float]],
             edl: dict) -> Path:
    edit = tmp_path / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "fonte.json").write_text(json.dumps({
        "words": [{"type": "word", "text": t, "start": a, "end": b}
                  for t, a, b in palavras],
    }), encoding="utf-8")
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    return edit


def test_lasca_de_8ms_nao_aparece_no_meio_da_marca(tmp_path):
    """O caso do C066, com os tempos reais e o J-cut do EDL."""
    from helpers.captions_for_remotion import build_captions

    edl = {"ranges": [
        {"source": "fonte", "start": 1.66, "end": 19.127},
        {"source": "fonte", "start": 19.76, "end": 20.527},
    ], "jcut_timeline": [
        {"audio_start_in_output": 0.0, "audio_duration": 17.467},
        {"audio_start_in_output": 17.300, "audio_duration": 0.767},
    ]}
    edit = _projeto(tmp_path, [
        ("assistência", 18.359, 18.840),
        ("né?", 19.119, 19.699),
        ("Prime", 19.76, 20.039),
        ("Camp.", 20.159, 20.52),
    ], edl)
    caps = build_captions(edl, edit)
    textos = [c["text"] for c in caps]
    assert "né?" not in textos, f"a lasca de 8ms voltou: {textos}"
    assert textos == ["assistência", "Prime", "Camp."], textos


def test_palavra_curta_inteira_dentro_do_trecho_fica(tmp_path):
    """"é" de 50ms inteiro dentro do corte é fala de verdade — fica."""
    from helpers.captions_for_remotion import build_captions

    edl = {"ranges": [{"source": "fonte", "start": 0.0, "end": 2.0}]}
    edit = _projeto(tmp_path, [
        ("isso", 0.2, 0.6),
        ("é", 0.65, 0.70),
        ("bom", 0.75, 1.2),
    ], edl)
    caps = build_captions(edl, edit)
    assert [c["text"] for c in caps] == ["isso", "é", "bom"]


def test_palavra_com_um_terco_audivel_na_borda_fica(tmp_path):
    """Fração razoável audível na borda do corte (>=25%) continua aparecendo,
    mesmo que a parte dentro seja menor que 60ms."""
    from helpers.captions_for_remotion import build_captions

    # "oi" de 150ms com 50ms dentro do trecho (33%).
    edl = {"ranges": [{"source": "fonte", "start": 0.0, "end": 1.05}]}
    edit = _projeto(tmp_path, [
        ("tudo", 0.2, 0.8),
        ("oi", 1.0, 1.15),
    ], edl)
    caps = build_captions(edl, edit)
    assert [c["text"] for c in caps] == ["tudo", "oi"]


def test_palavra_so_no_pad_fora_do_trecho_sai(tmp_path):
    """Palavra que só encosta no pad (fora do trecho mantido) não está no
    áudio do corte — não pode aparecer na legenda."""
    from helpers.captions_for_remotion import build_captions

    edl = {"ranges": [{"source": "fonte", "start": 0.0, "end": 1.0}]}
    edit = _projeto(tmp_path, [
        ("dentro", 0.2, 0.8),
        ("fora", 1.03, 1.4),
    ], edl)
    caps = build_captions(edl, edit)
    assert [c["text"] for c in caps] == ["dentro"]
