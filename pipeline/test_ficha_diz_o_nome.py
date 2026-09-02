# -*- coding: utf-8 -*-
"""A ficha do card diz o NOME, nao a justificativa.

Pedido dele em 31/08, com o print de um card na frente: "nao precisa este
monte de justificativa apenas qual IA e trilha usada". As duas linhas
tinham virado paragrafo — a da trilha com 96 caracteres, a da IA com 104 —
e nas duas o que ele queria saber (MusicGen, Groq) estava afogado no meio.

O que muda: a linha carrega o nome e o motivo vai para o `title` (passar o
mouse). E as duas passam a aparecer em TODO video pronto, nao so quando
algo desviou do normal — antes, o caminho que dava certo nao se
identificava, entao "qual IA?" so tinha resposta quando dava errado.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

from app.jobs_view import _aviso_de_ia, _aviso_de_trilha  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")

# Cabe na coluna da ficha sem virar parede de texto. O valor antigo da
# trilha tinha 96 e o da IA 104.
TETO = 34


def _trilha(tmp_path: Path, timing: dict) -> dict:
    (tmp_path / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
    job: dict = {}
    _aviso_de_trilha(job, tmp_path)
    return job


def _ia(tmp_path: Path, llm: dict) -> dict:
    (tmp_path / "result.json").write_text(json.dumps({"llm": llm}),
                                          encoding="utf-8")
    job: dict = {"status": "done"}
    _aviso_de_ia(job, tmp_path)
    return job


@pytest.mark.parametrize("timing,nome", [
    ({"musicaFonte": "nuvem: ElevenLabs Music"}, "ElevenLabs Music"),
    ({"musicaFonte": "motor: MusicGen local"}, "IA local (MusicGen)"),
    ({"musicaFonte": "reuso: render anterior"}, "Reaproveitada"),
    ({"musicaFonte": "viral--x.mp3"}, "Sua biblioteca (viral)"),
    ({"musicaSkip": "créditos esgotados"}, "Sem trilha"),
])
def test_a_trilha_e_o_nome_de_quem_fez(tmp_path, timing, nome):
    job = _trilha(tmp_path, timing)
    assert job["trilhaNota"] == nome, job
    assert len(job["trilhaNota"]) <= TETO


@pytest.mark.parametrize("backend,nome", [
    ("gemini-web", "Gemini"),
    ("chatgpt-web", "ChatGPT"),
    ("groq", "Groq (plano B)"),
    ("heuristic_light", "edição leve (sem IA)"),
    ("preview_edits", "suas marcações (sem IA)"),
])
def test_a_ia_e_o_nome_de_quem_planejou(tmp_path, backend, nome):
    job = _ia(tmp_path, {"ok": True, "backend": backend})
    assert job["iaNota"] == nome, job
    assert len(job["iaNota"]) <= TETO


def test_o_motivo_nao_some_ele_vai_para_o_title(tmp_path):
    """Encurtar nao pode virar esconder: o que saiu da linha tem de estar
    no detalhe, senao a informacao morre."""
    job = _trilha(tmp_path, {"musicaFonte": "motor: MusicGen local",
                             "musicaMotivo": "reserva"})
    # "reserva" so existe em ficha ANTIGA (quando a nuvem ainda existia) —
    # o detalhe explica sem citar marca que saiu do produto
    assert "nuvem" in job["trilhaDetalhe"]
    job = _ia(tmp_path, {"ok": True, "backend": "groq", "groqVia": "parse"})
    assert "ilegível" in job["iaDetalhe"]


def test_sessao_boa_nao_ganha_detalhe(tmp_path):
    """"Gemini" nao precisa de explicacao — detalhe so quando houve desvio."""
    job = _ia(tmp_path, {"ok": True, "backend": "gemini-web"})
    assert not job.get("iaDetalhe")


def test_a_tela_poe_o_detalhe_no_title():
    i = JS.index('return `<dl class="pc-ficha">')
    bloco = JS[i:i + 700]
    assert "detalhe" in bloco and "title=" in bloco, bloco
    for linha in ('linhas.push(["IA", j.iaNota, j.iaDetalhe])',
                  'linhas.push(["Trilha", j.trilhaNota, j.trilhaDetalhe])'):
        assert linha in JS, linha


def test_o_card_repinta_quando_so_o_detalhe_muda():
    """A assinatura decide se o card e redesenhado; detalhe de fora fica
    preso na tela com o texto de outro video."""
    i = JS.index("function cardSig(")
    bloco = JS[i:JS.index("\nfunction ", i + 10)]
    assert "j.iaDetalhe" in bloco and "j.trilhaDetalhe" in bloco


def test_a_trilha_que_deu_certo_se_identifica():
    """Sem isto a linha da Trilha so existia quando algo desviou. Desde
    02/09 o unico compositor e o motor local — a rede de seguranca do
    rotulo aponta para ele, nunca inventa nuvem."""
    assert '_RENDER_META["musicaFonte"] = "motor: MusicGen local"' in RF
    assert '= "nuvem: ElevenLabs Music"' not in RF


def test_trilha_da_nuvem_continua_indo_para_o_acervo():
    """A guarda de arquivamento pulava tudo que tinha `musicaFonte` sem ser
    "motor:" — dar nome a nuvem faria a trilha nova parar de ser arquivada,
    calada. Um defeito criado pela propria melhoria."""
    i = RF.index("_veio_da_biblioteca = ")
    bloco = RF[i:i + 400]
    for prefixo in ('"motor:"', '"nuvem:"', '"reuso:"'):
        assert prefixo in bloco, prefixo
    assert "if not reuso and not _veio_da_biblioteca:" in RF
