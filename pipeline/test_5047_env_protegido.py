# -*- coding: utf-8 -*-
"""5.0.47: as chaves de API do .env ficam cifradas com a DPAPI.

`~/ATIVAVID/.env` guardava ELEVENLABS/FREEPIK/GROQ/PEXELS em texto claro,
enquanto o `settings.json` já cifrava a service role e o `auth.json` o
refresh_token. Um backup ou uma sincronização de perfil levava tudo.

Regras: o que termina em _KEY/_TOKEN/_SECRET/_PASSWORD vai cifrado; o
resto (LLM_PROXY_BASE_URL, MODE, MODEL) fica legível; quem chama
`load_env_keys` continua recebendo texto claro; arquivo antigo migra na
primeira leitura; sem DPAPI (fora do Windows) nada muda.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import local_server as ls  # noqa: E402
from app import secret_store  # noqa: E402


def _arma(monkeypatch, tmp_path, *, dpapi=True):
    monkeypatch.setattr(ls, "USER_DIR", tmp_path)
    monkeypatch.setattr(ls, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(ls, "_LEGACY_ENV", tmp_path / "nao-existe" / ".env")
    if not dpapi:
        monkeypatch.setattr(secret_store, "available", lambda: False)
    else:
        # cifra de mentira, deterministica, para o teste nao depender do Windows
        monkeypatch.setattr(secret_store, "available", lambda: True)
        monkeypatch.setattr(secret_store, "protect",
                            lambda s: s if (not s or str(s).startswith("dpapi:")) else "dpapi:" + s[::-1])
        monkeypatch.setattr(secret_store, "unprotect",
                            lambda s: s[6:][::-1] if str(s).startswith("dpapi:") else s)


def test_segredo_cifrado_no_disco_e_claro_para_quem_le(monkeypatch, tmp_path):
    _arma(monkeypatch, tmp_path)
    ls.save_env_keys({"GROQ_API_KEY": "gsk_abc", "LLM_PROXY_MODE": "session",
                      "PEXELS_API_KEY": "px1", "ELEVENLABS_API_KEY": "sk_x"})
    bruto = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "gsk_abc" not in bruto and "px1" not in bruto and "sk_x" not in bruto
    assert "GROQ_API_KEY=dpapi:" in bruto and "LLM_PROXY_MODE=session" in bruto
    assert ls.load_env_keys() == {"GROQ_API_KEY": "gsk_abc", "LLM_PROXY_MODE": "session",
                                  "PEXELS_API_KEY": "px1", "ELEVENLABS_API_KEY": "sk_x"}


def test_arquivo_antigo_em_texto_claro_migra_na_primeira_leitura(monkeypatch, tmp_path):
    _arma(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("FREEPIK_API_KEY=MS3b\nLLM_PROXY_MODEL=gemini\n", encoding="utf-8")
    assert ls.load_env_keys()["FREEPIK_API_KEY"] == "MS3b"
    bruto = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FREEPIK_API_KEY=dpapi:" in bruto and "MS3b\n" not in bruto
    assert "LLM_PROXY_MODEL=gemini" in bruto
    assert ls.load_env_keys()["FREEPIK_API_KEY"] == "MS3b", "segunda leitura decifra"


def test_sem_dpapi_fica_como_esta(monkeypatch, tmp_path):
    _arma(monkeypatch, tmp_path, dpapi=False)
    ls.save_env_keys({"GROQ_API_KEY": "gsk_abc"})
    assert "GROQ_API_KEY=gsk_abc" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert ls.load_env_keys() == {"GROQ_API_KEY": "gsk_abc"}


def test_apagar_chave_e_gravar_vazio(monkeypatch, tmp_path):
    _arma(monkeypatch, tmp_path)
    ls.save_env_keys({"GROQ_API_KEY": "a", "PEXELS_API_KEY": "b"})
    ls.save_env_keys({"GROQ_API_KEY": ""})
    assert ls.load_env_keys() == {"PEXELS_API_KEY": "b"}


def test_o_que_e_segredo():
    assert ls._e_segredo("GROQ_API_KEY") and ls._e_segredo("x_token") and ls._e_segredo("A_SECRET")
    assert not ls._e_segredo("LLM_PROXY_BASE_URL") and not ls._e_segredo("LLM_PROXY_MODE")


def test_todo_leitor_passa_por_load_env_keys():
    """Se alguem ler o .env direto, recebe `dpapi:...` no lugar da chave."""
    for arq in ("app/desktop_server.py", "app/launcher.py", "app/llm_gateway.py",
                "app/llm_proxy.py", "pipeline/run_fast.py"):
        src = (REPO / arq).read_text(encoding="utf-8")
        assert 'ATIVAVID" / ".env"' not in src and "ENV_PATH.read_text" not in src, arq
