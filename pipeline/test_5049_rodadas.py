# -*- coding: utf-8 -*-
"""5.0.49: lista de jobs esquentada no arranque; Diagnóstico vê as chaves cifradas.

1. `jobs_view.esquentar` monta a lista uma vez em segundo plano — a
   primeira `/api/jobs` pagava o build frio (4 s com 331 projetos).
2. O Doutor lia o `.env` cru; desde a 5.0.47 os segredos estão `dpapi:...`.
   Passa a decifrar com o `secret_store` do app e a dizer quantos estão
   protegidos. Lê o `.env` do usuário por `Path.home()` (como os testes
   antigos do Doutor patcham) e NÃO pelo `load_env_keys` do app — senão o
   Doutor de um teste lia as chaves reais desta máquina.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

CIFRADA = "dpapi:abc"


class _Store:
    def __init__(self):
        self.chamadas = 0

    def list(self):
        self.chamadas += 1
        return []


def test_esquentar_monta_a_lista_em_segundo_plano(tmp_path):
    from app import jobs_view

    store = _Store()
    t = jobs_view.esquentar(store, tmp_path)
    t.join(timeout=30)
    assert not t.is_alive() and t.daemon
    assert store.chamadas >= 1, "o build nao rodou"


def test_o_arranque_do_app_esquenta_os_jobs():
    src = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    i = src.index("ps.esquentar_painel(DesktopHandler.projects_roots)")
    assert "_esquentar_jobs(store, projects_root)" in src[i:i + 500]


def test_doutor_conta_chaves_cifradas_e_em_claro(monkeypatch, tmp_path):
    import doutor
    from app import secret_store

    env = tmp_path / ".env"
    linhas = ["GROQ_API_KEY=" + CIFRADA, "PEXELS_API_KEY=px-claro", "LLM_PROXY_MODE=session"]
    env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    monkeypatch.setattr(secret_store, "unprotect", lambda v: "gsk" if v == CIFRADA else v)
    valores, cifrados, claros = doutor._chaves_do_app(env)
    assert valores["GROQ_API_KEY"] == "gsk", "valor decifrado com o secret_store do app"
    assert valores["LLM_PROXY_MODE"] == "session"
    assert (cifrados, claros) == (1, 1)


def test_doutor_avisa_texto_claro_e_elogia_cifrado(monkeypatch, tmp_path):
    import doutor
    from app import secret_store

    (tmp_path / "ATIVAVID").mkdir()
    env = tmp_path / "ATIVAVID" / ".env"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(doutor, "SKILL", tmp_path / "skill-vazia")
    monkeypatch.setattr(secret_store, "unprotect", lambda v: "x")
    for k in ("GROQ_API_KEY", "ELEVENLABS_API_KEY", "PEXELS_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    env.write_text("PEXELS_API_KEY=x\n", encoding="utf-8")
    doutor._itens.clear()
    doutor.checar_chaves()
    titulos = [i["titulo"] for i in doutor._itens]
    assert any("texto claro" in t for t in titulos), titulos

    env.write_text("PEXELS_API_KEY=dpapi:zzz\n", encoding="utf-8")
    doutor._itens.clear()
    doutor.checar_chaves()
    titulos = [i["titulo"] for i in doutor._itens]
    assert "Chaves de API protegidas no disco" in titulos, titulos
    assert not any("Sem chave da Pexels" in t for t in titulos), "chave cifrada e chave presente"


def test_o_doutor_nao_le_as_chaves_reais_pelo_app():
    src = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")
    i = src.index("def _chaves_do_app(")
    assert "load_env_keys" not in src[i:i + 1500], (
        "pelo load_env_keys o Doutor de um teste leria o .env real desta maquina")
