# -*- coding: utf-8 -*-
"""5.0.48: GET igual em voo é um pedido só; ordem dos Concluídos; POST no smoke.

1. `api()`: dois GETs iguais ao mesmo tempo compartilham a promessa (o
   arranque disparava /api/settings, /api/brands e /api/license repetidos).
2. Concluídos ordenam por recentes / nota / duração, guardado no navegador.
3. O smoke de rotas (5.0.45) ganha POST: `do_POST` de verdade nos dois
   handlers, com corpo JSON, para rotas que respondem 404 a id inexistente.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")


# ------------------------------------------------------------------ R7
def test_get_igual_em_voo_compartilha_a_promessa():
    i = JS.index("async function api(path, opts)")
    corpo = JS[i:i + 700]
    assert "_getEmVoo.get(path)" in corpo and "_getEmVoo.set(path, p)" in corpo
    assert ".finally(() => _getEmVoo.delete(path))" in corpo, "quando assenta, sai do mapa"
    assert 'metodo === "GET"' in corpo, "POST nunca e compartilhado"
    assert "async function _apiCru(path, opts)" in JS


# ------------------------------------------------------------------ R8
def test_concluidos_tem_ordem_e_guarda():
    assert 'id="doneSort"' in HTML
    for v in ("recentes", "nota", "duracao"):
        assert f'value="{v}"' in HTML
    assert "function ordemDosProntos()" in JS
    assert ".sort(ordemDosProntos())" in JS
    assert 'localStorage.setItem(DONE_SORT_KEY, state.doneSort)' in JS
    i = JS.index("function ordemDosProntos()")
    corpo = JS[i:i + 600]
    assert "nota(b) - nota(a) || byRecency(a, b)" in corpo, "empate na nota decide pela data"
    assert "dur(b) - dur(a) || byRecency(a, b)" in corpo


# ------------------------------------------------------------------ R10
def _handlers(tmp_path):
    from app import desktop_server as ds
    from app import local_server as ls
    import preview_server as ps

    root = tmp_path / "Projetos"
    root.mkdir()
    store = ls.JobStore(root)
    for cls in (ds.DesktopHandler, ls.StudioHandler):
        cls.store = store
        cls.projects_root = root
        cls.projects_roots = [root]
        cls.worker = None
    ps.Handler.root = root
    ps.Handler.projects_roots = [root]
    return [("app instalado", ds.DesktopHandler), ("studio", ls.StudioHandler)]


def _post(cls, caminho: str, corpo: dict) -> bytes:
    raw = json.dumps(corpo).encode("utf-8")
    h = cls.__new__(cls)
    h.rfile = io.BytesIO(
        f"POST {caminho} HTTP/1.1\r\nHost: 127.0.0.1:4850\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(raw)}\r\n\r\n".encode() + raw)
    h.wfile = io.BytesIO()
    h.client_address = ("127.0.0.1", 1)
    h.server = SimpleNamespace(server_name="127.0.0.1", server_port=4850)
    h.close_connection = True
    h.raw_requestline = h.rfile.readline(65537)
    assert h.parse_request()
    h.do_POST()
    return h.wfile.getvalue()


@pytest.mark.parametrize("rota", [
    "/api/jobs/srt", "/api/jobs/open-folder", "/api/jobs/rename",
    "/api/jobs/cancel", "/api/jobs/retry", "/api/jobs/delete",
])
def test_post_com_id_inexistente_responde_nos_dois_handlers(tmp_path, rota):
    for nome, cls in _handlers(tmp_path):
        saida = _post(cls, rota, {"id": "nao-existe", "name": "x"})
        assert saida.startswith(b"HTTP/1."), f"{nome}: {rota} nao respondeu nada"
        codigo = int(saida[9:12])
        # 403 = gate de licenca fechado (sem rede na suite) — tambem e resposta
        assert codigo in (400, 403, 404), f"{nome}: {rota} -> {codigo}"
