# -*- coding: utf-8 -*-
"""Texto longo na ficha nao pode empurrar os botoes para fora do card.

Caso real (27/08): a nota da trilha trazia o NOME DO ARQUIVO
("anuncio--20260822-193504_a001_08221324_cf96c4.mp3") — uma palavra sem
espaco, que nao quebra linha. Num card de 220px o conteudo esticou para
258px e o botao "..." (apagar, abrir pasta) ficou fora do alcance: "como
vou apagar estes sem o menu?".
"""
import json
from pathlib import Path

from app.jobs_view import _aviso_de_trilha

RAIZ = Path(__file__).resolve().parent.parent


def test_o_css_deixa_a_palavra_longa_quebrar():
    css = (RAIZ / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    i = css.index(".pc-ficha dd {")
    regra = css[i:css.index("}", i)]
    assert "overflow-wrap: anywhere" in regra, regra
    assert "min-width: 0" in regra, "sem min-width a coluna do grid nao cede"


def test_a_nota_da_trilha_nao_mostra_nome_de_arquivo(tmp_path):
    (tmp_path / "timing.json").write_text(json.dumps(
        {"musicaFonte": "anuncio--20260822-193504_a001_08221324_cf96c4.mp3"}),
        encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    nota = job["trilhaNota"]
    assert ".mp3" not in nota, nota
    assert "anúncio" in nota, "o clima da faixa e o que interessa"
    assert len(nota) < 90, f"nota longa demais para a ficha: {len(nota)}"


def test_clima_desconhecido_nao_quebra(tmp_path):
    (tmp_path / "timing.json").write_text(json.dumps(
        {"musicaFonte": "musica-que-o-usuario-baixou.mp3"}), encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "biblioteca" in job["trilhaNota"]
    assert ".mp3" not in job["trilhaNota"]


def test_valor_longo_ganha_titulo_para_ler_inteiro():
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index('<dl class="pc-ficha">')
    trecho = js[i - 200:i + 400]
    assert "title=" in trecho, "sem title, texto longo so cortado na tela"
