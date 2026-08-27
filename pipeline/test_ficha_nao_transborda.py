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


def test_valor_da_ficha_para_em_duas_linhas():
    """Com todos os avisos preenchidos o card chegava a 790px de altura e a
    grade de Recentes virava uma escada. Duas linhas por valor: 540px, com
    o essencial (que vem no comeco da frase) sempre visivel."""
    css = (RAIZ / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    i = css.index(".pc-ficha dd {")
    regra = css[i:css.index("}", i)]
    assert "-webkit-line-clamp: 2" in regra
    assert "overflow: hidden" in regra


def test_o_recado_essencial_cabe_nas_duas_primeiras_linhas():
    """Cada aviso tem de dizer o que importa ANTES de qualquer explicacao —
    o que passar de ~60 caracteres so aparece no title."""
    import json as _json
    from app.jobs_view import _qualidade_do_corte
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "verificacao.json").write_text(_json.dumps({
        "silenciosSobrando": [{"inicio": 22.0, "fim": 23.4}],
        "silencioTotalS": 1.4,
        "takesBaixos": [{"trecho": 3, "quedaDb": -9.0}],
        "emendasEstouradas": 0}), encoding="utf-8")
    job = {}
    _qualidade_do_corte(job, d)
    cabeca = job["corteQualidade"][:60]
    assert "pausa" in cabeca and "0:22" in cabeca, cabeca
