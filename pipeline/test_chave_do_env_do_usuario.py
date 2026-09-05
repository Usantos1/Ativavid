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
    """5.0.54: a ordem passou a viver num lugar so (`chave_do_env`), porque
    as chaves ficaram CIFRADAS e cada helper que lia o arquivo cru recebia
    `dpapi:...` — 401 nas duas APIs, b-roll mudo. O que se cobra agora e
    que nenhum helper leia por conta propria e que a ordem la esteja certa.
    """
    import chave_do_env

    primeiro = chave_do_env.candidatos()[0]
    assert primeiro == Path.home() / "ATIVAVID" / ".env", primeiro
    for nome in HELPERS_COM_CHAVE:
        s = (HELPERS / nome).read_text(encoding="utf-8")
        assert "from chave_do_env import chave" in s, f"{nome} nao usa o leitor central"
        assert 'for candidate in [Path.home() / "ATIVAVID"' not in s, (
            f"{nome} voltou a ler o .env por conta propria — receberia `dpapi:...`")


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
