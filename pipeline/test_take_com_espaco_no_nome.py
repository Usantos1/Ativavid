# -*- coding: utf-8 -*-
"""Nome de arquivo com espaço não pode trocar as frases de um take.

Caso real (29/08, job de 3 partes do usuário): `Parte 1.mov` tem 6,1s, mas
o EDL saiu com 12 trechos de `Parte_1` indo até 137,5s — tempos que só
existem na `parte 2`. O vídeo ficou mudo e travado por 23,4s e a ficha
acusou "1 pausa de 23,4s" e um trecho 64 dB abaixo.

A causa: o título da seção do `takes_packed.md` é o NOME DO ARQUIVO, e o
parser fazia `line[3:].split()[0]` — de `## Parte 1  (duration: ...)` ele
guardava a chave "Parte", que nunca casava com o stem "Parte 1". Sem
casar, o plano B pegava a seção MAIS LONGA (a da parte 2) e a guarda
restaurava aquelas frases como se fossem da Parte 1.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.editing_intent import load_packed_phrases, tirar_pausa_morta  # noqa: E402

PACOTE = """# Packed transcripts

## cut  (duration: 4.5s, 1 phrases)
  [000.00-004.50] S0 Fala turma.

## Parte 1  (duration: 4.8s, 1 phrases)
  [001.01-005.85] S0 Fala turma, se liga nesse programa.

## parte 2  (duration: 2m 15.6s, 2 phrases)
  [001.94-060.00] S0 Aqui vai a parte longa.
  [061.00-137.54] S0 E aqui o resto dela.

## parte 3  (duration: 5.0s, 1 phrases)
  [000.18-004.86] S0 Fechamento.
"""


def _pasta():
    d = Path(tempfile.mkdtemp())
    (d / "takes_packed.md").write_text(PACOTE, encoding="utf-8")
    return d


def test_cada_take_recebe_as_frases_dele():
    d = _pasta()
    try:
        p1 = load_packed_phrases(d, "Parte 1")
        assert len(p1) == 1 and p1[0]["end"] < 6.0, p1
        p2 = load_packed_phrases(d, "parte 2")
        assert len(p2) == 2 and p2[-1]["end"] > 100, p2
        p3 = load_packed_phrases(d, "parte 3")
        assert len(p3) == 1 and p3[0]["end"] < 5.0, p3
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_nome_que_nao_casa_nao_pega_frase_de_outro_take():
    """Antes devolvia a seção mais longa — e a guarda restaurava tempos que
    não existem no arquivo pedido."""
    d = _pasta()
    try:
        assert load_packed_phrases(d, "Take que nao existe") == []
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_uma_fonte_so_continua_com_plano_b():
    """Com um take só, casar pelo nome é dispensável: qualquer nome de
    seção serve, e tirar isso quebraria os projetos de fonte única."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "takes_packed.md").write_text(
            "# Packed\n\n## cut  (duration: 4.5s, 1 phrases)\n"
            "  [000.00-004.50] S0 A.\n\n"
            "## Meu Video Legal  (duration: 9.0s, 1 phrases)\n"
            "  [000.50-009.00] S0 B.\n", encoding="utf-8")
        ph = load_packed_phrases(d, "outro-nome-qualquer")
        assert len(ph) == 1 and ph[0]["text"] == "B."
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_casa_ignorando_espaco_acento_e_caixa():
    d = _pasta()
    try:
        assert load_packed_phrases(d, "parte_1")
        assert load_packed_phrases(d, "PARTE 1")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_pausa_morta_so_mexe_na_fonte_das_regioes():
    """As regiões de fala são de UMA fonte (a de índice 0) e o relógio de
    cada take começa do zero: dividir um trecho da parte 2 pelas pausas da
    Parte 1 cortaria no lugar errado."""
    regioes = [(0.0, 2.0), (2.6, 5.0)]
    ranges = [
        {"source": "Parte_1", "start": 0.0, "end": 5.0, "beat": "HOOK",
         "quote": "", "reason": "x", "gain_db": 0.0},
        {"source": "parte_2", "start": 0.0, "end": 5.0, "beat": "B1",
         "quote": "", "reason": "y", "gain_db": 0.0},
    ]
    out = tirar_pausa_morta(ranges, regioes, "dynamic")
    de_um = [r for r in out if r["source"] == "Parte_1"]
    de_dois = [r for r in out if r["source"] == "parte_2"]
    assert len(de_um) == 2, de_um          # dividido pela pausa de 0,6s
    assert len(de_dois) == 1, de_dois      # intocado
