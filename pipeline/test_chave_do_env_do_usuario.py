# -*- coding: utf-8 -*-
"""As chaves são lidas de onde a tela de Integrações grava.

Numa instalação normal o código fica em Program Files, que é só leitura:
a tela grava em `%USERPROFILE%/ATIVAVID/.env`, e o `.env` ao lado do
código só existe na máquina de quem desenvolve. Helper que olhava apenas
para o segundo dependia inteiramente de o app injetar a variável no
ambiente do processo.

Quando essa dependência se rompe o sintoma é MUDO: em 27/08 o plano B do
Groq sumiu num processo iniciado fora do app (corrigido na 3.26) e a
trilha da ElevenLabs falha igual — o vídeo sai sem música e a ficha diz
"geração falhou", mandando procurar defeito numa chave que está certa.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "helpers"
sys.path.insert(0, str(HELPERS))

HELPERS_COM_CHAVE = ("auto_broll.py", "elevenlabs_music.py",
                     "google_images.py", "pexels_search.py", "transcribe.py")


def test_todo_helper_olha_o_env_do_usuario_primeiro():
    for nome in HELPERS_COM_CHAVE:
        s = (HELPERS / nome).read_text(encoding="utf-8")
        i = s.find("for candidate in [")
        assert i >= 0, nome
        while i >= 0:
            trecho = s[i:i + 200]
            assert 'Path.home() / "ATIVAVID" / ".env"' in trecho, (
                f"{nome}: a lista de .env nao comeca pelo do usuario")
            i = s.find("for candidate in [", i + 10)


def test_acha_a_chave_so_com_o_env_do_usuario(monkeypatch):
    """Sem variavel de ambiente e sem .env ao lado do codigo."""
    casa = Path(tempfile.mkdtemp())
    try:
        (casa / "ATIVAVID").mkdir()
        (casa / "ATIVAVID" / ".env").write_text(
            "# comentario\nELEVENLABS_API_KEY=\"chave-de-teste-123\"\n"
            "PEXELS_API_KEY=pex-456\n", encoding="utf-8")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: casa))
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        monkeypatch.delenv("PEXELS_API_KEY", raising=False)
        import importlib

        em = importlib.import_module("elevenlabs_music")
        assert em.load_api_key() == "chave-de-teste-123"
        ps = importlib.import_module("pexels_search")
        assert ps.load_api_key() == "pex-456"
    finally:
        shutil.rmtree(casa, ignore_errors=True)


def test_o_ambiente_continua_valendo_de_reserva(monkeypatch):
    """Quem roda pelo app recebe a chave no ambiente — isso nao pode
    quebrar por causa da ordem nova."""
    casa = Path(tempfile.mkdtemp())
    try:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: casa))
        monkeypatch.setenv("PEXELS_API_KEY", "veio-do-ambiente")
        import importlib

        ps = importlib.import_module("pexels_search")
        assert ps.load_api_key() == "veio-do-ambiente"
    finally:
        shutil.rmtree(casa, ignore_errors=True)
