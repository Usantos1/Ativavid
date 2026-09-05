# -*- coding: utf-8 -*-
"""5.0.41: o app só executa o instalador que confere com o publicado.

Até aqui "Atualizar agora" baixava o exe da `download_url` e o executava
sem conferir nada. Um instalador trocado no GitHub (conta invadida, release
editada) rodaria em toda máquina de cliente no próximo clique. Agora o
`publicar_versao.py` grava o SHA-256 do exe na política do Supabase, o RPC
devolve o hash junto com a URL, e o app confere o arquivo baixado ANTES de
executar. Para trocar o instalador seria preciso invadir os dois lugares.

Sem hash na política (versão antiga dela, ou o caminho do GitHub), segue
como antes — a proteção entra quando ele rodar o SQL, sem quebrar ninguém.
"""
from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import app.update_check as uc  # noqa: E402
from app import license as lic  # noqa: E402

CORPO = b"MZ" + b"x" * 2_000_000
SHA = hashlib.sha256(CORPO).hexdigest()
URL = "https://github.com/x/y/releases/download/v9/Instalar.ATIVAVID.9.99.exe"


def _preparar(monkeypatch, tmp_path, info: dict, corpo: bytes = CORPO):
    monkeypatch.setattr(uc, "check_update", lambda: info)
    monkeypatch.setattr(uc.sys, "platform", "win32")
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    import subprocess
    import urllib.request

    class _Resp(io.BytesIO):
        headers = {"Content-Length": str(len(corpo))}

        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda u, timeout=0: _Resp(corpo))
    executados: list[str] = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **k: executados.append(str(args[0])))
    monkeypatch.setattr(uc.os, "startfile", lambda p: executados.append(str(p)),
                        raising=False)
    return executados


def test_hash_certo_executa(monkeypatch, tmp_path):
    executados = _preparar(monkeypatch, tmp_path,
                           {"downloadUrl": URL, "downloadSha256": SHA})
    r = uc.baixar_e_instalar()
    assert r["ok"], r
    assert executados and executados[0].endswith("Instalar.ATIVAVID.9.99.exe")


def test_hash_errado_nao_executa_e_apaga(monkeypatch, tmp_path):
    executados = _preparar(monkeypatch, tmp_path,
                           {"downloadUrl": URL, "downloadSha256": "ab" * 32})
    r = uc.baixar_e_instalar()
    assert r["ok"] is False
    assert "não confere" in r["error"]
    assert executados == [], "executou um instalador que nao confere"
    assert not list(tmp_path.rglob("*.exe")), "o arquivo suspeito ficou no disco"
    assert uc._PROGRESSO["estado"] == "erro"


def test_hash_em_maiusculas_ou_com_espaco_confere(monkeypatch, tmp_path):
    executados = _preparar(monkeypatch, tmp_path,
                           {"downloadUrl": URL, "downloadSha256": "  " + SHA.upper() + " "})
    assert uc.baixar_e_instalar()["ok"]
    assert executados


def test_sem_hash_na_politica_segue_como_antes(monkeypatch, tmp_path):
    executados = _preparar(monkeypatch, tmp_path, {"downloadUrl": URL})
    assert uc.baixar_e_instalar()["ok"]
    assert executados


def test_a_politica_carrega_o_hash_ate_o_check_update(monkeypatch):
    monkeypatch.setattr(uc, "current_version", lambda: "1.0.0")
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "public_status", lambda: {"update": {
        "latestVersion": "9.99.0", "downloadUrl": URL,
        "downloadSha256": SHA.upper(), "force": False}})
    r = uc.check_update()
    assert r["source"] == "supabase" and r["updateAvailable"]
    assert r["downloadSha256"] == SHA


def test_normalize_update_guarda_o_hash():
    u = lic._normalize_update({"latestVersion": "9", "downloadSha256": " " + SHA.upper()})
    assert u["downloadSha256"] == SHA
    assert lic._normalize_update({"latestVersion": "9"})["downloadSha256"] is None


def test_sha256_do_arquivo_e_o_sha256(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(CORPO)
    assert uc._sha256_do_arquivo(f) == SHA


def test_o_sql_devolve_o_hash_e_o_publicador_grava():
    sql = (REPO / "supabase" / "hash_do_instalador.sql").read_text(encoding="utf-8")
    assert "add column if not exists download_sha256" in sql
    assert "'downloadSha256', nullif(lower(trim(coalesce(cfg.download_sha256, ''))), '')" in sql
    pub = (REPO / "tools" / "publicar_versao.py").read_text(encoding="utf-8")
    assert 'patch["download_sha256"] = sha' in pub
    assert "nao sao o mesmo arquivo" in pub, "hash de arquivo diferente do publicado nao pode subir"
    assert "hash_do_instalador.sql" in pub, "sem a coluna, o publicador tem de avisar e seguir"
