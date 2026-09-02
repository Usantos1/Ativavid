# -*- coding: utf-8 -*-
"""O planejador se apresenta como tarefa de TEXTO.

Job real de 02/09 (vídeo de YouTube, 15min): o Gemini Flash leu
"editor-chefe… monte um corte" como pedido para editar vídeo DE VERDADE e
recusou — "Não fui programado para fazer isso. Só consigo gerar texto." O
plano caiu no Groq (400 na transcrição gigante) e dali na heurística. O
prompt agora abre dizendo que a tarefa é devolver JSON, e o log distingue
RECUSA de JSON quebrado (a investigação começou pelo lado errado).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO, REPO / "helpers"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_o_prompt_abre_dizendo_que_e_texto():
    from llm_cut_plan import _system_prompt

    for intent in ("complete", "dynamic", "shorts"):
        s = _system_prompt({"editingIntent": intent})
        assert s.startswith("TAREFA DE TEXTO:"), intent
        assert "acessar arquivos de vídeo" in s


def test_o_log_distingue_recusa_de_json_quebrado():
    s = (REPO / "helpers" / "llm_cut_plan.py").read_text(encoding="utf-8")
    i = s.index("def _chamar_e_parsear")
    bloco = s[i:s.index("\ndef ", i + 10)]
    assert '"RECUSA da tarefa"' in bloco
    assert "consigo gerar texto" in bloco, "a frase real da recusa sumiu da deteccao"
    # a segunda recusa real ("sou só um modelo de linguagem") tambem conta
    assert "modelo de linguagem" in bloco


def test_recusa_repete_na_propria_sessao_antes_do_groq(monkeypatch):
    """Caso real de 02/09: o Flash recusou a 1ª chamada e entregou o plano
    completo na 2ª com o MESMO prompt — a repetição tem de vir ANTES do
    Groq (que engasga na transcrição longa)."""
    import llm_cut_plan as lcp
    from app import llm_gateway as gw

    respostas = iter([
        ("Não consigo te ajudar com isso. Sou só um modelo de linguagem.",
         "gemini-web"),
        ('{"headline": "Na segunda foi"}', "gemini-web"),
    ])
    chamadas = []

    def _rede(msgs):
        r = next(respostas)
        chamadas.append(r[1])
        return r

    monkeypatch.setattr(lcp, "_chat_com_rede", _rede)
    monkeypatch.setattr(gw, "_groq_chat", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("nao devia chegar ao groq")))
    parsed, backend, _ = lcp._chamar_e_parsear([{"role": "user", "content": "x"}])
    assert backend == "gemini-web" and parsed["headline"] == "Na segunda foi"
    assert len(chamadas) == 2
