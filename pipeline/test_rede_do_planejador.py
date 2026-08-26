# -*- coding: utf-8 -*-
"""O planejador tem a mesma rede do gateway: Groq quando a sessão morre.

Em 23/08 as sessões Gemini e ChatGPT expiraram JUNTAS (mesmo navegador, mesma
extensão) e um vídeo real saiu com o título cru — com a chave do Groq parada no
.env o tempo todo. O gateway do editor sempre teve essa queda; o planejador
chamava `llm_session.chat` direto e ficava sem nenhuma.

Provado ao vivo com as sessões mortas de verdade: 4 de 4 projetos reais saíram
com plano e headline pelo Groq ("Salve seu celular molhado", 4,6-7,2s cada).

O que se trava aqui:
  - a queda só existe COM a chave (sem ela, o erro de sessão continua)
  - o pedido ao Groq exige JSON garantido — sem `response_format` o modelo
    devolveu um plano com vírgula faltando e o parse caiu (plano real)
  - a falha dupla mostra as DUAS causas, e resposta vazia não passa adiante
  - com a sessão viva, o Groq nem é tocado (custo por engano é bug)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))

import app.llm_gateway as gw  # noqa: E402
import app.llm_session as ls  # noqa: E402
from llm_cut_plan import _chat_com_rede  # noqa: E402

MSGS = [{"role": "user", "content": "plano"}]


def _sessao_morta(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("As sessões Gemini e ChatGPT expiraram.")
    monkeypatch.setattr(ls, "chat", explode)


def test_sessao_viva_nao_toca_o_groq(monkeypatch):
    monkeypatch.setattr(ls, "chat", lambda *a, **k: ("texto", "gemini-web"))
    def nunca(*a, **k):
        raise AssertionError("Groq chamado com a sessão viva — custo por engano")
    monkeypatch.setattr(gw, "_groq_chat", nunca)
    assert _chat_com_rede(MSGS) == ("texto", "gemini-web")


def test_sessao_morta_cai_para_o_groq(monkeypatch):
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    visto = {}
    def groq(messages, model, extras=None):
        visto["extras"] = extras
        return {"choices": [{"message": {"content": '{"ranges": []}'}}]}
    monkeypatch.setattr(gw, "_groq_chat", groq)
    texto, backend = _chat_com_rede(MSGS)
    assert backend == "groq" and texto == '{"ranges": []}'
    assert visto["extras"] == {"response_format": {"type": "json_object"}}, (
        "sem JSON garantido o parse já caiu num plano real")


def test_sem_chave_o_erro_de_sessao_continua(monkeypatch):
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "")
    with pytest.raises(RuntimeError, match="expiraram"):
        _chat_com_rede(MSGS)


def test_falha_dupla_mostra_as_duas_causas(monkeypatch):
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    def groq_morto(*a, **k):
        raise RuntimeError("HTTP 429 rate limit")
    monkeypatch.setattr(gw, "_groq_chat", groq_morto)
    with pytest.raises(RuntimeError) as e:
        _chat_com_rede(MSGS)
    assert "expiraram" in str(e.value) and "429" in str(e.value)


def test_resposta_vazia_do_groq_nao_passa(monkeypatch):
    """Texto vazio viraria 'plano' e cairia adiante com erro pior de ler."""
    _sessao_morta(monkeypatch)
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    monkeypatch.setattr(gw, "_groq_chat",
                        lambda *a, **k: {"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(RuntimeError, match="expiraram"):
        _chat_com_rede(MSGS)


# --- headline avulsa: o titulo dos videos de varias fontes ------------------
#
# `multi_take_concat` decide o corte sem IA (juncao dos takes) e por isso
# nunca teve titulo: 18 de 18 jobs desse caminho sairam com as primeiras
# palavras da fala como nome. `headline_apenas` pede SO o titulo, pela mesma
# rede do plano, e NUNCA levanta — titulo e enfeite, nao pode derrubar render.


def test_headline_avulsa_sai_da_rede(monkeypatch):
    import llm_cut_plan as lcp

    monkeypatch.setattr(lcp, "_chat_com_rede",
                        lambda m: ('{"headline": "Chip novo em 5 minutos", '
                                   '"headlineAlts": ["Outro angulo"]}', "groq"))
    r = lcp.headline_apenas("fala longa o bastante para valer uma chamada", {})
    assert r["headline"] == "Chip novo em 5 minutos"
    assert r["backend"] == "groq"
    assert r["headlineAlts"] == ["Outro angulo"]


def test_headline_avulsa_nunca_derruba_o_render(monkeypatch):
    import llm_cut_plan as lcp

    def explode(m):
        raise RuntimeError("tudo fora do ar")
    monkeypatch.setattr(lcp, "_chat_com_rede", explode)
    assert lcp.headline_apenas("fala longa o bastante para valer uma chamada", {}) == {}


def test_fala_curta_nao_gasta_chamada(monkeypatch):
    import llm_cut_plan as lcp

    def nunca(m):
        raise AssertionError("IA chamada para fala de 2 palavras — custo a toa")
    monkeypatch.setattr(lcp, "_chat_com_rede", nunca)
    assert lcp.headline_apenas("oi gente", {}) == {}


def test_resposta_sem_headline_devolve_vazio(monkeypatch):
    import llm_cut_plan as lcp

    monkeypatch.setattr(lcp, "_chat_com_rede", lambda m: ('{"headline": ""}', "groq"))
    assert lcp.headline_apenas("fala longa o bastante para valer uma chamada", {}) == {}


def test_o_multi_take_liga_a_headline_avulsa():
    """O run_fast chama no ramo certo — sem isso a funcao existe e nada muda."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(Path(__file__).resolve().parents[1] / "pipeline" / "run_fast.py")
    i = codigo.find('"backend": "multi_take_concat"')
    assert i > 0
    assert "headline_apenas" in codigo[i:i + 1500], (
        "o ramo multi_take_concat nao pede a headline avulsa")


# --- os dois gaps vistos nos jobs REAIS da 2.62 (24/08) ---------------------


def test_control_char_no_plano_nao_derruba():
    """O Gemini copiou uma quebra de linha crua para dentro do "quote" e o
    parser estrito derrubou o plano inteiro por um byte — 2x nos jobs reais."""
    from llm_cut_plan import _extract_json

    ruim = '{"ranges": [{"quote": "linha um\nlinha dois", "start": 1}]}'
    r = _extract_json(ruim)
    assert r["ranges"][0]["start"] == 1


def test_json_realmente_quebrado_ainda_levanta():
    """Tolerancia é para control char, não para lixo qualquer."""
    import pytest as _pt

    from llm_cut_plan import _extract_json

    with _pt.raises(Exception):
        _extract_json("isto nao tem json nenhum")


def test_ultima_rede_do_titulo_esta_ligada():
    """Projeto de antes da 2.62 nunca gravou headline_ia.json (o 1o render
    caiu no 'viral') — sem esta rede, o reprocesso sai cru PARA SEMPRE. Visto
    em dois manual_edl reais de 24/08."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(Path(__file__).resolve().parents[1] / "pipeline" / "run_fast.py")
    i = codigo.find("llm_meta = headline_preservada(edit_dir, llm_meta)")
    assert i > 0
    trecho = codigo[i:i + 1600]
    assert "headline_apenas" in trecho, "a ultima rede do titulo sumiu"
    # O modo leve ENTROU na rede: a tela promete "sem IA mexendo NO CORTE",
    # nao no titulo — a exclusao original leu a promessa errada e um job real
    # (24/08 17:10) saiu com titulo cru. O corte segue 100% heuristico.
    assert '!= "heuristic_light"' not in trecho, (
        "a exclusao do modo leve voltou — a promessa da tela e sobre o corte")


def test_json_quebrado_da_sessao_cai_para_o_groq(monkeypatch):
    """TRES planos reais (25-26/08) sairam 'sem IA' com o Groq parado: a
    sessao respondeu (rede nao cai) mas com JSON quebrado — virgula
    faltando — e o parse matava o plano. Parse quebrado agora tambem e
    plano B."""
    import llm_cut_plan as lcp
    from app import llm_gateway as gw

    monkeypatch.setattr(lcp, "_chat_com_rede",
                        lambda msgs: ('{"headline": "Oi" "sem virgula"}',
                                      "gemini-web"))
    monkeypatch.setattr(gw, "_groq_key", lambda: "chave")
    chamado = {}

    def _groq_falso(msgs, model, extras=None):
        chamado["extras"] = extras
        return {"choices": [{"message": {"content":
                '{"headline": "Consertado no plano B"}'}}]}

    monkeypatch.setattr(gw, "_groq_chat", _groq_falso)
    parsed, backend, bruto = lcp._chamar_e_parsear([{"role": "user",
                                                     "content": "x"}])
    assert backend == "groq"
    assert parsed["headline"] == "Consertado no plano B"
    assert chamado["extras"] == {"response_format": {"type": "json_object"}}, \
        "o retry PRECISA exigir json_object — e o que garante parse valido"

    # groq ja era o backend? nao ha proximo — o erro sobe
    monkeypatch.setattr(lcp, "_chat_com_rede",
                        lambda msgs: ('{quebrado', "groq"))
    import json as _json
    import pytest
    with pytest.raises(_json.JSONDecodeError):
        lcp._chamar_e_parsear([{"role": "user", "content": "x"}])
