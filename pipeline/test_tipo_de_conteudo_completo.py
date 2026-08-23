# -*- coding: utf-8 -*-
"""Todo tipo oferecido na tela tem que funcionar de ponta a ponta.

Este arquivo nasce de um prejuízo medido. "Viral" aparecia na tela de Estilos e
tinha rótulo, mas ficou sem regra de prompt — e `prompt_rules` acessava o dicionário
direto. Resultado: `KeyError: 'viral'` dentro do planejamento por IA, que o
pipeline engole por desenho (`try_plan_cut` nunca levanta) e substitui pelo corte
heurístico.

O sintoma, então, não foi mensagem de erro nenhuma: foi o título do vídeo virar
as primeiras palavras da fala. Entre 18 e 22/08 saíram 65 vídeos assim, e o único
registro estava numa linha de log que ninguém abre.

O que se trava aqui não é o caso "viral" — é a classe: lista, rótulo e regra
precisam andar juntos, e um tipo desconhecido nunca mais pode derrubar o corte.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import content_type as ct  # noqa: E402


@pytest.mark.parametrize("tipo", ct.CONTENT_TYPES)
def test_todos_os_tipos_tem_regra(tipo):
    regra = ct.prompt_rules(tipo)
    assert regra.strip(), f"{tipo!r} está na tela mas não tem regra de prompt"
    assert tipo in regra, f"a regra de {tipo!r} não diz de que tipo ela é"


@pytest.mark.parametrize("tipo", ct.CONTENT_TYPES)
def test_todos_os_tipos_tem_rotulo(tipo):
    assert ct.LABELS.get(tipo, "").strip(), f"{tipo!r} apareceria sem nome na tela"


def test_tipo_desconhecido_nao_derruba_o_corte():
    """A blindagem: um tipo novo, ou lixo salvo num preset antigo, vira "" —
    corte genérico, não corte nenhum."""
    for lixo in ("tipo-que-nao-existe", "", None, "VIRAL!!!", 123):
        assert ct.prompt_rules(lixo) == ""


def test_o_planejador_monta_o_prompt_com_qualquer_tipo():
    """Sobe uma camada: é em `_rhythm_rules` que o KeyError estourava de fato.

    Testar só `prompt_rules` deixaria passar uma regressão em quem a chama —
    e quem a chama é o caminho que produz o título do vídeo.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
    from llm_cut_plan import _rhythm_rules, _system_prompt  # type: ignore

    for tipo in (*ct.CONTENT_TYPES, "tipo-que-nao-existe", ""):
        # O preset que estava congelado no edl.json do vídeo que quebrou.
        preset = {"rhythm": "dinamico", "intensity": "medio", "speechClean": "medio",
                  "editingIntent": "dynamic", "contentType": tipo, "videoGoal": "reels"}
        texto = _rhythm_rules(preset)
        assert "RITMO=" in texto and "TIPO_CONTEUDO=" in texto
        assert _system_prompt(preset).strip()
