# -*- coding: utf-8 -*-
"""O aviso de versão nova diz O QUE muda.

"Nova versão disponível" não responde a pergunta que o usuário faz antes
de clicar — vale a pena agora? O corpo da release já vinha na resposta da
API e era jogado fora.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.update_check import _resumo_das_notas  # noqa: E402

CHANGELOG = """- **Atualizar virou um clique.** O aviso de versão nova agora
  aparece sozinho ao abrir o app, e a instalação roda em silêncio.
- Quem abrir o instalador na mão também não é mais perguntado
  sobre idioma.
- Terceira nota.
- Quarta nota, que não deve aparecer.
"""


def test_junta_a_linha_quebrada_do_changelog():
    """Sem juntar, a nota chega cortada no meio da frase."""
    notas = _resumo_das_notas(CHANGELOG)
    assert notas[0].startswith("Atualizar virou um clique.")
    assert "instalação roda em silêncio" in notas[0], notas[0]
    assert "**" not in notas[0], "marcação do markdown vazou"


def test_para_em_tres_notas():
    assert len(_resumo_das_notas(CHANGELOG)) == 3


def test_texto_sem_lista_nao_vira_nota():
    assert _resumo_das_notas("Só um parágrafo solto.") == []
    assert _resumo_das_notas(None) == []
    assert _resumo_das_notas("") == []


def test_a_janela_mostra_as_notas():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("const notas = $(\"#updDlgNotas\")")
    trecho = js[i:i + 400]
    assert "upd.notes" in trecho and "escapeHtml" in trecho, trecho
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="updDlgNotas"' in html
