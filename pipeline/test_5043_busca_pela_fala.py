# -*- coding: utf-8 -*-
"""5.0.43: a busca dos Concluídos acha pelo que foi DITO no vídeo.

Título e nome de arquivo não são o que a pessoa lembra com 300 vídeos; a
frase é. A transcrição (`captions.json`) e a legenda do post (`legenda.txt`)
entram na busca, sem acento e sem maiúscula, com cache por mtime.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import busca_de_fala as bf  # noqa: E402


def _projeto(tmp_path: Path, nome: str, *, falas: list[str], legenda: str = "") -> dict:
    edit = tmp_path / nome / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "remotion" / "public" / "captions.json").write_text(json.dumps(
        [{"text": f, "startMs": i * 500, "endMs": i * 500 + 400} for i, f in enumerate(falas)]),
        encoding="utf-8")
    if legenda:
        (edit / "legenda.txt").write_text(legenda, encoding="utf-8")
    return {"id": nome, "editDir": str(edit), "title": "x"}


def test_acha_pela_fala_sem_acento_nem_maiuscula(tmp_path):
    bf._CACHE.clear()
    jobs = [_projeto(tmp_path, "a", falas=["testa", "outro", "CARREGADOR"]),
            _projeto(tmp_path, "b", falas=["nada", "a", "ver"])]
    assert bf.buscar(jobs, "carregador") == ["a"]
    assert bf.buscar(jobs, "Carregádor") == ["a"]
    assert bf.buscar(jobs, "outro carregador") == ["a"], "frase atravessa as cues"


def test_acha_pela_legenda_do_post(tmp_path):
    bf._CACHE.clear()
    jobs = [_projeto(tmp_path, "a", falas=["oi"], legenda="Promoção de verão #loja")]
    assert bf.buscar(jobs, "promocao de verao") == ["a"]


def test_termo_curto_nao_casa_tudo(tmp_path):
    bf._CACHE.clear()
    jobs = [_projeto(tmp_path, "a", falas=["oi"])]
    assert bf.buscar(jobs, "o") == []
    assert bf.buscar(jobs, "  ") == []


def test_cache_por_mtime_ve_a_correcao(tmp_path):
    bf._CACHE.clear()
    j = _projeto(tmp_path, "a", falas=["errado"])
    assert bf.buscar([j], "certo") == []
    caps = Path(j["editDir"]) / "remotion" / "public" / "captions.json"
    caps.write_text(json.dumps([{"text": "certo"}]), encoding="utf-8")
    t = time.time() + 5
    os.utime(caps, (t, t))
    assert bf.buscar([j], "certo") == ["a"]


def test_projeto_sem_arquivos_nao_derruba(tmp_path):
    bf._CACHE.clear()
    assert bf.buscar([{"id": "z", "editDir": str(tmp_path / "nao" / "existe")}, {"id": ""}, "lixo"], "abc") == []


def test_rota_e_tela():
    for arq in ("app/desktop_server.py", "app/local_server.py"):
        src = (REPO / arq).read_text(encoding="utf-8")
        assert '"/api/jobs/buscar"' in src, f"{arq} sem a rota"
        i = src.index('"/api/jobs/buscar"')
        assert src.index('.startswith("/api/jobs/")', i - 2000) > i or True
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "function buscarNaFala" in js
    assert js.count("buscarNaFala(") >= 3, "Concluidos E Projetos chamam a busca"
    assert "fala.ids.has(String(j.id))" in js
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert html.count("ou pelo que foi dito") == 2


def test_a_rota_vem_antes_do_prefixo_generico():
    # `/api/jobs/buscar` cairia em `/api/jobs/<id>` (404 "job not found") se
    # viesse depois do ramo `startswith("/api/jobs/")`.
    for arq in ("app/desktop_server.py", "app/local_server.py"):
        src = (REPO / arq).read_text(encoding="utf-8")
        assert src.index('"/api/jobs/buscar"') < src.index('.startswith("/api/jobs/")')
