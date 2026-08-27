# -*- coding: utf-8 -*-
"""O Doutor le as chaves de onde o APP as guarda.

Caso real (27/08): rodar o diagnostico na maquina do usuario acusava "Sem
chave da ElevenLabs" e "Sem chave da Pexels" com as duas configuradas e
funcionando — ele lia o .env ao lado do codigo (Program Files, que e so
leitura e por isso NUNCA tem o arquivo), enquanto a tela de Integracoes
grava em %USERPROFILE%/ATIVAVID/.env. Diagnostico que mente e pior que
diagnostico nenhum: ensina o cliente a ignorar o relatorio.
"""
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "helpers") not in sys.path:
    sys.path.insert(0, str(RAIZ / "helpers"))


def _rodar(monkeypatch, home: Path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    for k in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "PEXELS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    import doutor
    importlib.reload(doutor)   # o modulo acumula em _itens (lista de modulo)
    doutor._itens.clear()
    doutor.checar_chaves()
    return [dict(i) for i in doutor._itens]


def test_acha_a_chave_no_env_do_usuario(monkeypatch, tmp_path):
    (tmp_path / "ATIVAVID").mkdir()
    (tmp_path / "ATIVAVID" / ".env").write_text(
        "ELEVENLABS_API_KEY=abc123\nPEXELS_API_KEY=xyz789\n",
        encoding="utf-8")
    itens = _rodar(monkeypatch, tmp_path)
    titulos = " | ".join(str(i.get("titulo")) for i in itens)
    assert "Sem chave da ElevenLabs" not in titulos, titulos
    assert "Sem chave da Pexels" not in titulos, titulos


def test_sem_chave_nenhuma_o_aviso_continua(monkeypatch, tmp_path):
    """O aviso VERDADEIRO nao pode sumir junto com o falso."""
    (tmp_path / "ATIVAVID").mkdir()
    itens = _rodar(monkeypatch, tmp_path)
    titulos = " | ".join(str(i.get("titulo")) for i in itens)
    assert "Sem chave da ElevenLabs" in titulos, titulos


def test_a_ordem_das_fontes_e_a_do_app():
    s = (RAIZ / "helpers" / "doutor.py").read_text(encoding="utf-8")
    i = s.find("def checar_chaves()")
    corpo = s[i:i + 1200]
    i_user = corpo.find('Path.home() / "ATIVAVID" / ".env"')
    i_skill = corpo.find('SKILL / ".env"')
    assert 0 < i_user < i_skill, \
        "o .env do usuario tem de ser lido ANTES do legado"
