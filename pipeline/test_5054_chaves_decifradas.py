# -*- coding: utf-8 -*-
"""5.0.54: TODO leitor da chave decifra o que a 5.0.47 cifrou.

A 5.0.47 passou a guardar as chaves de API com a DPAPI (`dpapi:...`) em
`~/ATIVAVID/.env`. O app lê por `load_env_keys`, que decifra — mas os
HELPERS de linha de comando liam o arquivo cru e passaram a mandar
`dpapi:AQAAA...` como chave. Medido em 05/09, com a chave real da máquina:
Pexels e Freepik responderam **401 Unauthorized**, e o b-roll automático
(`auto_broll`) parava CALADO — o vídeo saía sem imagem de apoio e nada na
tela dizia por quê.

O teste da 5.0.47 (`test_todo_leitor_passa_por_load_env_keys`) só olhava
`app/` e `pipeline/`. Este olha `helpers/` e `tools/`, que é onde o defeito
estava, e prova o caminho de leitura de cada helper com uma chave cifrada
de mentira.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

HELPERS_COM_CHAVE = {
    "pexels_search": ("load_api_key", "PEXELS_API_KEY"),
    "freepik_search": ("load_api_key", "FREEPIK_API_KEY"),
    "elevenlabs_music": ("load_api_key", "ELEVENLABS_API_KEY"),
    "auto_broll": ("_pexels_key", "PEXELS_API_KEY"),
}


@pytest.mark.parametrize("mod,par", sorted(HELPERS_COM_CHAVE.items()))
def test_helper_decifra_a_chave(monkeypatch, tmp_path, mod, par):
    fn_nome, env_nome = par
    (tmp_path / "ATIVAVID").mkdir()
    (tmp_path / "ATIVAVID" / ".env").write_text(
        f"{env_nome}=dpapi:cifrada\nOUTRA=1\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv(env_nome, raising=False)

    import chave_do_env
    monkeypatch.setattr(chave_do_env, "_decifrar",
                        lambda v: "CHAVE-DE-VERDADE" if v == "dpapi:cifrada" else v)

    m = __import__(mod)
    valor = getattr(m, fn_nome)()
    assert valor == "CHAVE-DE-VERDADE", f"{mod}.{fn_nome} devolveu {valor!r}"


def test_nenhum_helper_le_o_env_cru():
    """Um `read_text` do .env dentro de um helper volta a mandar `dpapi:...`."""
    culpados = []
    for arq in sorted((REPO / "helpers").glob("*.py")) + sorted((REPO / "tools").glob("*.py")):
        if arq.name == "chave_do_env.py":
            continue
        src = arq.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'^\s*for\s+\w+\s+in\s+\[?Path\.home\(\)\s*/\s*"ATIVAVID"\s*/\s*"\.env"', src, re.M):
            trecho = src[m.start():m.start() + 900]
            if "_API_KEY" in trecho or "_TOKEN" in trecho:
                culpados.append(f"{arq.name}:{src[:m.start()].count(chr(10)) + 1}")
    assert not culpados, f"leem o .env cru e receberiam `dpapi:...`: {culpados}"


def test_chave_do_env_cai_no_ambiente(monkeypatch, tmp_path):
    import chave_do_env

    monkeypatch.setattr(chave_do_env, "candidatos", lambda: (tmp_path / "nao-existe",))
    monkeypatch.setenv("PEXELS_API_KEY", "do-ambiente")
    assert chave_do_env.chave("PEXELS_API_KEY") == "do-ambiente"
    monkeypatch.delenv("PEXELS_API_KEY")
    assert chave_do_env.chave("PEXELS_API_KEY") == ""


def test_valor_em_texto_claro_continua_valendo(monkeypatch, tmp_path):
    """.env antigo (sem DPAPI, ou fora do Windows) tem de seguir funcionando."""
    import chave_do_env

    env = tmp_path / ".env"
    env.write_text("PEXELS_API_KEY=abc123\n", encoding="utf-8")
    monkeypatch.setattr(chave_do_env, "candidatos", lambda: (env,))
    assert chave_do_env.chave("PEXELS_API_KEY") == "abc123"
