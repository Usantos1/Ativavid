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
    bloco = s[i:i + 2400]
    assert '"RECUSA da tarefa"' in bloco
    assert "consigo gerar texto" in bloco, "a frase real da recusa sumiu da deteccao"
