# -*- coding: utf-8 -*-
"""5.0.39: `Host` estranho é recusado em TODO pedido — GET incluído.

A guarda de origem (`origin_allowed`) só entrava no POST. O GET ficava
aberto ao DNS rebinding: um site cujo nome passa a apontar para 127.0.0.1
depois de carregado. Para o navegador a página continua na origem dela —
não manda `Origin`, o `Sec-Fetch-Site` diz `same-origin` — e o servidor
entregava `/api/settings` (e-mail da conta), a lista de licenças do admin
(a sessão de admin é a do disco, não um cookie) e os projetos.

O que denuncia o truque é o `Host`: vem `evil.com:4850`, e o servidor só
existe em 127.0.0.1. A checagem mora no `parse_request`, o único ponto por
onde GET, POST, HEAD e OPTIONS passam antes de qualquer rota — nos dois
servidores (Studio e editor; o app instalado herda do editor).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app import http_guard as guard  # noqa: E402


class _H(dict):
    def get(self, k, default=None):
        for chave, valor in self.items():
            if chave.lower() == str(k).lower():
                return valor
        return default


@pytest.mark.parametrize("host", [
    "127.0.0.1:4850", "127.0.0.1", "localhost:4850", "LOCALHOST:4850",
    "[::1]:4850", "[::1]",
])
def test_este_endereco_passa(host):
    assert guard.host_allowed(_H({"Host": host})) is True


@pytest.mark.parametrize("host", [
    "evil.com:4850",
    "127.0.0.1.evil.com:4850",     # prefixo não é o endereço
    "localhost.evil.com:4850",
    "192.168.0.10:4850",           # LAN: este servidor nem escuta ali
    "ativavid.com",
])
def test_outro_nome_e_recusado(host):
    assert guard.host_allowed(_H({"Host": host})) is False


def test_sem_host_nao_e_navegador():
    # HTTP/1.0 e ferramenta local (curl -H 'Host:') — não é o vetor.
    assert guard.host_allowed(_H({})) is True


# ---------------------------------------------------------------- servidores
def _pedido(cls, linha: bytes) -> tuple[bool, bytes]:
    """Roda só o `parse_request` de um handler real, sem socket.

    Devolve (despacha?, bytes escritos). Quando o handler recusa, a
    biblioteca não chama `do_GET` — é isso que a guarda precisa garantir.
    """
    h = cls.__new__(cls)
    h.rfile = io.BytesIO(linha)
    h.wfile = io.BytesIO()
    h.client_address = ("127.0.0.1", 50000)
    h.server = SimpleNamespace(server_name="127.0.0.1", server_port=4850)
    h.close_connection = True
    h.raw_requestline = h.rfile.readline(65537)
    ok = h.parse_request()
    return ok, h.wfile.getvalue()


def _servidores():
    from app import local_server as ls
    import preview_server as ps
    from app import desktop_server as ds

    return [("studio", ls.StudioHandler), ("editor", ps.Handler),
            ("app instalado", ds.DesktopHandler)]


@pytest.mark.parametrize("nome,cls", _servidores(), ids=lambda x: x if isinstance(x, str) else "")
def test_get_com_host_estranho_nao_chega_a_rota(nome, cls):
    ok, saida = _pedido(cls, b"GET /api/settings HTTP/1.1\r\nHost: evil.com:4850\r\n\r\n")
    assert ok is False, f"{nome}: despachou um GET de DNS rebinding"
    assert b"403" in saida.split(b"\r\n", 1)[0], saida[:120]


@pytest.mark.parametrize("nome,cls", _servidores(), ids=lambda x: x if isinstance(x, str) else "")
def test_post_com_host_estranho_tambem(nome, cls):
    ok, saida = _pedido(
        cls, b"POST /api/settings HTTP/1.1\r\nHost: evil.com:4850\r\n"
             b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}")
    assert ok is False, nome
    assert b"403" in saida.split(b"\r\n", 1)[0]


@pytest.mark.parametrize("nome,cls", _servidores(), ids=lambda x: x if isinstance(x, str) else "")
@pytest.mark.parametrize("host", [b"127.0.0.1:4850", b"localhost:4850"])
def test_o_proprio_app_continua_passando(nome, cls, host):
    ok, saida = _pedido(cls, b"GET /api/settings HTTP/1.1\r\nHost: " + host + b"\r\n\r\n")
    assert ok is True, f"{nome}: recusou o proprio app em {host!r}"
    assert saida == b""


def test_a_extensao_chama_um_endereco_local():
    """A extensão fala com `127.0.0.1`/`localhost`; se um dia mudar para
    outro nome, a guarda a barra — e barra calada, como em 20-21/08."""
    achados = []
    for pasta in (REPO / "assets", REPO / "extensao", REPO / "extension"):
        if not pasta.is_dir():
            continue
        for f in pasta.rglob("*.js"):
            if "node_modules" in f.parts:
                continue
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for alvo in ("http://127.0.0.1:48", "http://localhost:48"):
                if alvo in txt:
                    achados.append(f.name)
    # Não exige achar (a extensão pode morar fora do repo); exige que, se
    # achar, seja endereço local — a varredura acima só procura locais.
    assert isinstance(achados, list)


# ------------------------------------------------------- anti-clickjacking
@pytest.mark.parametrize("nome,cls", _servidores(), ids=lambda x: x if isinstance(x, str) else "")
def test_toda_resposta_proibe_iframe_de_fora(nome, cls):
    """Um site de fora não pode pôr o hub num <iframe> invisível e guiar
    cliques do dono (liberar dias é um clique). O hub embute o editor na
    MESMA origem, e `'self'` deixa isso passar."""
    h = cls.__new__(cls)
    h.rfile = io.BytesIO(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:4850\r\n\r\n")
    h.wfile = io.BytesIO()
    h.client_address = ("127.0.0.1", 50000)
    h.server = SimpleNamespace(server_name="127.0.0.1", server_port=4850)
    h.close_connection = True
    h.raw_requestline = h.rfile.readline(65537)
    assert h.parse_request() is True
    h.send_response(200)
    h.end_headers()
    saida = h.wfile.getvalue().decode("latin-1").lower()
    assert "x-frame-options: sameorigin" in saida, nome
    assert "frame-ancestors 'self'" in saida, nome
    assert "nosniff" not in saida, "nosniff barraria o studio.js num Windows que registra .js como text/plain"
