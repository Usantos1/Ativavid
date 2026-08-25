# -*- coding: utf-8 -*-
""""Trazer de volta": restaurar um trecho removido direto do relatório.

O caminho é o do corte do editor: o EDL atual ganha o trecho e vira
preview_edits.json — o próximo render entra como backend preview_edits e o
replanejo da IA não desfaz a decisão do usuário.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))


def _handler(tmp_path: Path):
    """Instância crua do Handler com root apontado — sem servidor de rede."""
    import preview_server as ps

    h = object.__new__(ps.Handler)
    h.root = tmp_path
    respostas: list[tuple[dict, int]] = []
    h._json = lambda data, code=200: respostas.append((data, code))
    return h, respostas


def _com_edl(tmp_path: Path) -> None:
    (tmp_path / "edl.json").write_text(json.dumps({
        "version": 1,
        "ranges": [
            {"source": "SRC", "start": 0.0, "end": 10.0, "beat": "HOOK"},
            {"source": "SRC", "start": 20.0, "end": 30.0, "beat": "CTA"},
        ],
    }), encoding="utf-8")


def _post(h, body: dict) -> None:
    import io

    raw = json.dumps(body).encode("utf-8")
    h.headers = {"Content-Length": str(len(raw))}
    h.rfile = io.BytesIO(raw)
    h._restaurar_trecho()


def test_restaurar_escreve_preview_edits(tmp_path):
    h, resp = _handler(tmp_path)
    _com_edl(tmp_path)
    _post(h, {"start": 12.0, "end": 15.0})
    data, code = resp[-1]
    assert code == 200 and data.get("ok") and data.get("changed"), data
    pe = json.loads((tmp_path / "preview_edits.json").read_text(encoding="utf-8"))
    spans = [(r["start"], r["end"]) for r in pe["edl"]["ranges"]]
    assert (12.0, 15.0) in spans, spans
    assert pe.get("origem") == "trazer-de-volta"


def test_trecho_ja_no_corte_nao_gera_edicao(tmp_path):
    h, resp = _handler(tmp_path)
    _com_edl(tmp_path)
    _post(h, {"start": 2.0, "end": 5.0})
    data, _ = resp[-1]
    assert data.get("ok") and not data.get("changed")
    assert not (tmp_path / "preview_edits.json").exists(), \
        "edicao vazia enfileiraria um refazer para nada"


def test_multi_take_e_recusado(tmp_path):
    h, resp = _handler(tmp_path)
    (tmp_path / "edl.json").write_text(json.dumps({"ranges": [
        {"source": "A", "start": 0.0, "end": 5.0},
        {"source": "B", "start": 0.0, "end": 5.0},
    ]}), encoding="utf-8")
    _post(h, {"start": 6.0, "end": 8.0})
    _, code = resp[-1]
    assert code == 409


def test_entrada_invalida_e_400(tmp_path):
    h, resp = _handler(tmp_path)
    _com_edl(tmp_path)
    _post(h, {"start": 8.0, "end": 3.0})
    assert resp[-1][1] == 400


def test_a_ui_tem_o_painel_e_a_acao():
    html = (RAIZ / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="saiuPanel"' in html and 'id="saiuList"' in html
    js = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "api/restaurar-trecho" in js, "a acao Trazer de volta sumiu"
    assert "renderSaiuPanel" in js
    assert "corteRelatorio" in js, "o estado nao guarda o relatorio"
    srv = (RAIZ / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert '"corteRelatorio": relatorio' in srv, \
        "/api/state deixou de expor o relatorio"
