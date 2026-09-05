# -*- coding: utf-8 -*-
"""5.0.79: o planejador repara a pontuação do JSON do Gemini antes de repetir.

Censo de 85 pipeline.log (03–05/09): 17 jobs com "resposta de gemini-web
com JSON quebrado" — vírgula faltando ("Expecting ',' delimiter"), vírgula
sobrando ("Expecting property name enclosed in double quotes"), aspas
curvas — e cada um custava uma repetição na sessão (~10 s) ou a queda para
o Groq. O reparo só mexe em pontuação entre elementos: nunca inventa
conteúdo, e o que continua quebrado levanta como antes (a amostra fica
em ~/ATIVAVID/ia-quebradas/ para melhorar o reparo com casos reais).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from llm_cut_plan import _extract_json, _reparar_json  # noqa: E402


@pytest.fixture(autouse=True)
def _amostras_no_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


BOM = {"ranges": [{"start": 1.0, "end": 2.5, "quote": "oi"}, {"start": 3.0, "end": 4.0, "quote": "tchau"}],
       "headline": "Titulo"}


def test_virgula_faltando_entre_objetos(capsys):
    ruim = ('{"ranges": [\n  {"start": 1.0, "end": 2.5, "quote": "oi"}\n'
            '  {"start": 3.0, "end": 4.0, "quote": "tchau"}\n], "headline": "Titulo"}')
    assert _extract_json(ruim) == BOM
    assert "[ia] JSON reparado" in capsys.readouterr().out


def test_virgula_faltando_entre_campos_em_linhas():
    ruim = '{"ranges": [{"start": 1.0, "end": 2.5, "quote": "oi"}, {"start": 3.0, "end": 4.0, "quote": "tchau"}]\n"headline": "Titulo"}'
    assert _extract_json(ruim) == BOM


def test_virgula_sobrando_antes_de_fechar():
    ruim = '{"ranges": [{"start": 1.0, "end": 2.5, "quote": "oi",}, {"start": 3.0, "end": 4.0, "quote": "tchau"},], "headline": "Titulo",}'
    assert _extract_json(ruim) == BOM


def test_aspas_curvas():
    ruim = '{“ranges”: [{“start”: 1.0, "end": 2.5, "quote": "oi"}, {"start": 3.0, "end": 4.0, "quote": "tchau"}], "headline": "Titulo"}'
    assert _extract_json(ruim) == BOM


def test_dentro_de_cerca_de_codigo_com_virgula_faltando():
    ruim = '```json\n{"ranges": [\n{"start": 1.0, "end": 2.5, "quote": "oi"}\n{"start": 3.0, "end": 4.0, "quote": "tchau"}\n], "headline": "Titulo"}\n```'
    assert _extract_json(ruim) == BOM


def test_json_bom_nao_e_tocado(capsys):
    import json

    assert _extract_json(json.dumps(BOM)) == BOM
    assert "reparado" not in capsys.readouterr().out


def test_quebra_de_linha_crua_dentro_da_fala_continua_valendo():
    """O reparo nao pode inserir virgula dentro de um "quote" com quebra."""
    ruim = '{"ranges": [{"quote": "linha um\nlinha dois", "start": 1}]}'
    assert _extract_json(ruim)["ranges"][0]["quote"] == "linha um\nlinha dois"


def test_lixo_continua_levantando_e_vira_amostra(tmp_path):
    with pytest.raises(Exception):
        _extract_json("isto nao tem json nenhum")
    with pytest.raises(Exception):
        _extract_json('{"ranges": [{"start": 1.0 "end": }}')   # nem o reparo salva
    amostras = list((tmp_path / "ATIVAVID" / "ia-quebradas").glob("*.txt"))
    assert amostras, "a resposta que nao deu para reparar fica guardada"
    assert amostras[-1].read_text(encoding="utf-8").startswith("# JSONDecodeError")


def test_o_reparo_nao_inventa_conteudo():
    s = '{"a": [1, 2,], "b": "x"\n"c": {"d": 1}}'
    assert _reparar_json(s) == '{"a": [1, 2], "b": "x",\n"c": {"d": 1}}'
