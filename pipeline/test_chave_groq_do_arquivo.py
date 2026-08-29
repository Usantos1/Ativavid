# -*- coding: utf-8 -*-
"""O plano B do planejador nao pode sumir por causa de COMO o processo subiu.

O app exporta as chaves para o ambiente ao iniciar, entao no uso normal
tudo funciona. Mas `_groq_key()` lia SO o ambiente: qualquer processo que
nao passe por esse arranque (pipeline chamado direto, um helper, um teste)
ficava sem chave — e o plano B de parse do planejador some CALADO, porque
ele so entra "se houver chave do Groq". Foi assim que um render de teste em
29/08 saiu sem IA com JSON quebrado e a chave boa no .env.
"""
import json
from pathlib import Path

from app import llm_gateway as gw

RAIZ = Path(__file__).resolve().parent.parent


def test_ambiente_vence_quando_existe(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "do-ambiente")
    assert gw._groq_key() == "do-ambiente"


def test_sem_ambiente_le_o_env_do_usuario(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.local_server as ls
    monkeypatch.setattr(ls, "load_env_keys",
                        lambda: {"GROQ_API_KEY": "do-arquivo"})
    assert gw._groq_key() == "do-arquivo"


def test_sem_chave_em_lugar_nenhum_devolve_vazio(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.local_server as ls
    monkeypatch.setattr(ls, "load_env_keys", lambda: {})
    assert gw._groq_key() == ""


def test_leitura_quebrada_nao_levanta(monkeypatch):
    """Sem chave e resposta valida; excecao aqui derrubaria o planejamento."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import app.local_server as ls

    def explode():
        raise OSError("disco fora")
    monkeypatch.setattr(ls, "load_env_keys", explode)
    assert gw._groq_key() == ""


def test_o_plano_b_de_parse_depende_dessa_chave():
    """Amarra o motivo: se alguem trocar a condicao, este teste explica."""
    s = (RAIZ / "helpers" / "llm_cut_plan.py").read_text(encoding="utf-8")
    i = s.index("except json.JSONDecodeError as e:")
    corpo = s[i:i + 500]
    assert "gw._groq_key()" in corpo
