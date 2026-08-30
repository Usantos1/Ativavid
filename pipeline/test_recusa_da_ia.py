# -*- coding: utf-8 -*-
"""A recusa da IA não vira a legenda do post nem o título do vídeo.

Nos projetos do usuário, DOIS `legenda.txt` são isto por inteiro:

    "Sou apenas um modelo de linguagem. Não posso ajudar com isso."
    "Sou um modelo de linguagem. Isso está além das minhas habiliades."

É a legenda que ele copia para o Instagram. Um deles virou também o
TÍTULO do cartão na lista de prontos, porque o título saía da primeira
linha da legenda.

O polimento só conferia TAMANHO (12 a 900 caracteres) e hashtags — uma
recusa passa nos dois: tem 60 caracteres e nenhuma hashtag. E quando
passa, sobrescreve o rascunho montado do EDL, que estava certo.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.local_server import _corta_bonito, _manchete_do_edit  # noqa: E402
from pipeline.run_fast import _parece_recusa  # noqa: E402

RECUSAS = [
    "Sou apenas um modelo de linguagem. Não posso ajudar com isso.",
    "Sou um modelo de linguagem. Isso está além das minhas habiliades.",
    "Desculpe, não consigo ajudar com esse pedido.",
    "I'm sorry, I cannot help with that.",
]
LEGENDAS_BOAS = [
    "Quem nunca procurou o celular usando a própria lanterna dele? 😅\n\n"
    "Conserto de celular em Campinas é aqui. #PrimeCamp",
    "Nossa IA acha o defeito do aparelho antes de você perceber — "
    "traz aí que a gente resolve hoje mesmo na loja.",
]


def test_recusa_e_reconhecida():
    for t in RECUSAS:
        assert _parece_recusa(t), t


def test_legenda_de_verdade_passa():
    for t in LEGENDAS_BOAS:
        assert not _parece_recusa(t), t


def test_texto_longo_que_fala_de_ia_nao_e_recusa():
    """Uma legenda pode falar do produto; barrar isso jogaria fora
    legenda boa."""
    t = ("A gente usa modelo de linguagem para achar o defeito. " * 8)
    assert len(t) > 320 and not _parece_recusa(t)


def test_o_polimento_devolve_None_na_recusa():
    fonte = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = fonte.index("def _llm_polish_legenda(")
    corpo = fonte[i:fonte.index("\ndef write_legenda(", i)]
    assert "if _parece_recusa(text):" in corpo
    j = corpo.index("if _parece_recusa(text):")
    assert "return None" in corpo[j:j + 220]


def test_o_corte_respeita_a_palavra():
    t = "Quando o cliente tenta inventar qualquer desculpa pra não levar a capinha"
    out = _corta_bonito(t, 62)
    assert out.endswith("…") and not out.rstrip("…").endswith(" ")
    assert " lev…" not in out and "leva…" not in out
    assert out.rstrip("…") in t


def test_texto_curto_nao_e_cortado():
    assert _corta_bonito("Celular na lanterna?") == "Celular na lanterna?"


def test_a_manchete_vem_do_edit_data(tmp_path):
    import json

    pub = tmp_path / "remotion" / "public"
    pub.mkdir(parents=True)
    (pub / "edit-data.json").write_text(
        json.dumps({"hook": {"lines": ["Celular na lanterna?", "Você acredita"]}}),
        encoding="utf-8")
    assert _manchete_do_edit(tmp_path) == "Celular na lanterna? Você acredita"


def test_sem_manchete_devolve_None(tmp_path):
    assert _manchete_do_edit(tmp_path) is None
