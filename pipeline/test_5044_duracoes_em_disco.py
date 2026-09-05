# -*- coding: utf-8 -*-
"""5.0.44: o cache de duração dos vídeos sobrevive ao fechar o app.

Era só memória: cada abertura refazia ~190 `ffprobe` (31 s de CPU num
notebook de cliente, todo dia) para medir arquivos que não mudaram. Agora
vai para `~/ATIVAVID/duracoes-cache.json`, com mtime e tamanho na chave —
arquivo regravado mede de novo sozinho; arquivo igual, nunca mais.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

import preview_server as ps  # noqa: E402


def _arma(monkeypatch, tmp_path, respostas):
    monkeypatch.setattr(ps, "_DUR_DISCO", tmp_path / "duracoes-cache.json")
    monkeypatch.setattr(ps, "_dur_cache", {})
    monkeypatch.setattr(ps, "_dur_disco_lido", False)
    monkeypatch.setattr(ps, "_dur_sujo", 0)
    chamadas = []

    def _probe(p):
        chamadas.append(str(p))
        return respostas.get(Path(p).name, 0.0)

    monkeypatch.setattr(ps, "probe_duration", _probe)
    return chamadas


def test_segunda_abertura_nao_mede_de_novo(monkeypatch, tmp_path):
    v = tmp_path / "a.mp4"
    v.write_bytes(b"x" * 100)
    chamadas = _arma(monkeypatch, tmp_path, {"a.mp4": 12.5})
    assert ps.probe_duration_cached(v) == 12.5
    ps._dur_gravar()
    assert (tmp_path / "duracoes-cache.json").is_file()
    # "fechou o app": memoria zerada, disco fica
    monkeypatch.setattr(ps, "_dur_cache", {})
    monkeypatch.setattr(ps, "_dur_disco_lido", False)
    assert ps.probe_duration_cached(v) == 12.5
    assert chamadas == [str(v)], "mediu de novo um arquivo que nao mudou"


def test_arquivo_regravado_mede_de_novo(monkeypatch, tmp_path):
    v = tmp_path / "a.mp4"
    v.write_bytes(b"x" * 100)
    resp = {"a.mp4": 12.5}
    chamadas = _arma(monkeypatch, tmp_path, resp)
    assert ps.probe_duration_cached(v) == 12.5
    v.write_bytes(b"y" * 200)
    t = time.time() + 10
    os.utime(v, (t, t))
    resp["a.mp4"] = 30.0
    assert ps.probe_duration_cached(v) == 30.0
    assert len(chamadas) == 2


def test_zero_continua_none_e_persiste(monkeypatch, tmp_path):
    v = tmp_path / "quebrado.mp4"
    v.write_bytes(b"x")
    _arma(monkeypatch, tmp_path, {"quebrado.mp4": 0.0})
    assert ps.probe_duration_cached(v) is None
    ps._dur_gravar()
    dados = json.loads((tmp_path / "duracoes-cache.json").read_text(encoding="utf-8"))
    assert list(dados.values()) == [None]


def test_grava_de_25_em_25_e_o_esquentar_grava_o_resto(monkeypatch, tmp_path):
    resp = {}
    for i in range(26):
        (tmp_path / f"v{i}.mp4").write_bytes(b"x")
        resp[f"v{i}.mp4"] = 1.0 + i
    _arma(monkeypatch, tmp_path, resp)
    for i in range(24):
        ps.probe_duration_cached(tmp_path / f"v{i}.mp4")
    assert not (tmp_path / "duracoes-cache.json").exists()
    ps.probe_duration_cached(tmp_path / "v24.mp4")
    assert (tmp_path / "duracoes-cache.json").exists()
    src = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    i = src.index("def esquentar_painel")
    assert "_dur_gravar()" in src[i:i + 1500], "o aquecimento do arranque tem de gravar o resto"


def test_disco_corrompido_nao_derruba(monkeypatch, tmp_path):
    (tmp_path / "duracoes-cache.json").write_text("{lixo", encoding="utf-8")
    v = tmp_path / "a.mp4"
    v.write_bytes(b"x")
    _arma(monkeypatch, tmp_path, {"a.mp4": 3.0})
    assert ps.probe_duration_cached(v) == 3.0
