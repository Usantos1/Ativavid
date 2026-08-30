# -*- coding: utf-8 -*-
"""O corte não cai mais no meio de uma palavra.

Medido nos projetos do usuário (417 trechos mantidos, de 25/08 em diante):
**34% das bordas caíam dentro de uma palavra**, e 126 delas comiam mais de
0,05s — o que o ouvido pega. Duas vezes a palavra decepada era
`PrimeCamp.`, o nome da loja, na última frase do vídeo.

A culpa não era da IA: no `IMG_1772` o plano pede `end: 83.72` e a citação
dele é *"...você vai encontrar aqui na PrimeCamp."* — a palavra vai de
83,36 a 83,84. O modelo dá tempo aproximado; quem corta é que precisa
encaixar.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.editing_intent import encaixar_nas_palavras  # noqa: E402


def _fonte(tmp_path, palavras, stem="SRC"):
    d = tmp_path / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.json").write_text(
        json.dumps({"words": [{"start": a, "end": b, "text": t}
                              for t, a, b in palavras]}),
        encoding="utf-8")
    return tmp_path


def _r(a, b, source="SRC"):
    return {"start": a, "end": b, "beat": "KEEP", "source": source}


def test_o_caso_primecamp(tmp_path):
    """O caso real: a borda para 0,12s antes do fim do nome da loja."""
    ed = _fonte(tmp_path, [("Voce", 82.14, 82.52), ("vai", 82.52, 82.76),
                           ("encontrar", 82.76, 83.12), ("aqui", 83.12, 83.24),
                           ("na", 83.24, 83.36), ("PrimeCamp.", 83.36, 83.84)])
    out = encaixar_nas_palavras([_r(80.35, 83.72)], edit_dir=ed, stem="SRC")
    assert out[0]["end"] == 83.84, out


def test_caco_de_palavra_sai_inteiro(tmp_path):
    """Menos de um quarto dentro é clique, não fala: sai."""
    ed = _fonte(tmp_path, [("bom", 10.0, 10.4), ("cacando.", 10.5, 11.5)])
    out = encaixar_nas_palavras([_r(9.0, 10.6)], edit_dir=ed, stem="SRC")
    assert out[0]["end"] == 10.5


def test_a_borda_de_entrada_segue_a_mesma_regra(tmp_path):
    ed = _fonte(tmp_path, [("Nossa,", 1.0, 1.6), ("olha", 1.6, 1.9)])
    # 0,5s de 0,6s dentro -> a palavra entra inteira
    assert encaixar_nas_palavras([_r(1.1, 3.0)], edit_dir=ed,
                                 stem="SRC")[0]["start"] == 1.0
    # 0,1s de 0,6s dentro -> o caco sai
    assert encaixar_nas_palavras([_r(1.5, 3.0)], edit_dir=ed,
                                 stem="SRC")[0]["start"] == 1.6


def test_nao_mexe_em_outra_fonte(tmp_path):
    """O relógio de cada take começa do zero: encaixar a Parte 2 nas
    palavras da Parte 1 cortaria no lugar errado."""
    ed = _fonte(tmp_path, [("um", 1.0, 1.5)])
    outro = _r(1.2, 3.0, source="PARTE2")
    out = encaixar_nas_palavras([_r(0.0, 0.5), outro], edit_dir=ed, stem="SRC")
    assert out[1]["start"] == 1.2 and out[1]["end"] == 3.0


def test_palavra_longa_demais_e_artefato_e_nao_arrasta(tmp_path):
    """Timestamp de 4s numa palavra é erro do alinhador; encaixar por ele
    colaria a frase seguinte."""
    ed = _fonte(tmp_path, [("Ai", 1.0, 5.8)])
    out = encaixar_nas_palavras([_r(0.0, 1.01)], edit_dir=ed, stem="SRC")
    assert out[0]["end"] == 1.01


def test_trecho_nao_some(tmp_path):
    """Encaixar não pode engolir um trecho inteiro."""
    ed = _fonte(tmp_path, [("teste", 1.0, 2.0)])
    out = encaixar_nas_palavras([_r(1.4, 1.5)], edit_dir=ed, stem="SRC")
    assert len(out) == 1


def test_sem_transcricao_nada_muda(tmp_path):
    rs = [_r(1.0, 2.0)]
    assert encaixar_nas_palavras(rs, edit_dir=tmp_path, stem="SRC") == rs
    assert encaixar_nas_palavras(rs, edit_dir=None, stem=None) == rs


def test_a_guarda_chama_o_encaixe():
    """Sem isto o encaixe existe e nunca roda — o defeito continua."""
    fonte = (REPO / "app" / "editing_intent.py").read_text(encoding="utf-8")
    i = fonte.index("def guard_ranges(")
    corpo = fonte[i:fonte.index("def tirar_pausa_morta(")]
    assert "encaixar_nas_palavras(out" in corpo
