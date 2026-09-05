# -*- coding: utf-8 -*-
"""5.0.45: toda rota GET com parâmetros RESPONDE — nos dois handlers de verdade.

Da 5.0.42 à 5.0.44, Empresas dizia "Não deu para ler os presets" e as
imagens (logos, miniaturas da Biblioteca) vinham quebradas. Causa: a rota
nova `/api/jobs/buscar` fez `from urllib.parse import parse_qs` DENTRO do
`do_GET`; o Python passa a tratar `parse_qs` como variável local da função
inteira, e toda rota acima que usa `parse_qs` estoura com UnboundLocalError
antes de mandar um byte (curl via 000). A suíte não tinha nenhum teste que
passasse por essas rotas no handler real — só pelas funções por baixo.

Este arquivo chama o `do_GET` de verdade (StudioHandler e DesktopHandler,
que é o do app instalado) para uma lista de rotas com query string e exige
uma resposta HTTP, seja 200 ou 404 — nunca exceção, nunca silêncio.
"""
from __future__ import annotations

import ast
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

ROTAS = [
    "/api/brands/logo?id=nao-existe&v=1",
    "/api/brand-presets?brandId=nao-existe",
    "/api/brand-presets",
    "/api/library?kind=image",
    "/api/jobs/buscar?q=teste",
    "/api/jobs/nao-existe/thumb",
    "/api/fontes",
    "/api/settings",
]


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


def _get(cls, caminho: str) -> bytes:
    h = cls.__new__(cls)
    h.rfile = io.BytesIO(f"GET {caminho} HTTP/1.1\r\nHost: 127.0.0.1:4850\r\n\r\n".encode())
    h.wfile = io.BytesIO()
    h.client_address = ("127.0.0.1", 1)
    h.server = SimpleNamespace(server_name="127.0.0.1", server_port=4850)
    h.close_connection = True
    h.raw_requestline = h.rfile.readline(65537)
    assert h.parse_request()
    h.do_GET()
    return h.wfile.getvalue()


@pytest.mark.parametrize("rota", ROTAS)
def test_rota_get_responde_nos_dois_handlers(tmp_path, rota):
    for nome, cls in _handlers(tmp_path):
        saida = _get(cls, rota)
        assert saida.startswith(b"HTTP/1."), f"{nome}: {rota} nao respondeu nada"
        codigo = int(saida[9:12])
        assert codigo in (200, 204, 400, 404), f"{nome}: {rota} -> {codigo}"


def _imports_locais_de_nome_global(arquivo: Path, funcao: str) -> list[str]:
    """Nomes importados DENTRO de `funcao` que tambem existem no topo do modulo."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    topo: set[str] = set()
    for no in arvore.body:
        if isinstance(no, ast.ImportFrom):
            topo |= {a.asname or a.name for a in no.names}
        elif isinstance(no, ast.Import):
            topo |= {(a.asname or a.name).split(".")[0] for a in no.names}
    achados: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == funcao:
            usos: dict[str, int] = {}  # nome -> primeira linha em que e LIDO
            for sub in ast.walk(no):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    usos[sub.id] = min(usos.get(sub.id, sub.lineno), sub.lineno)
            for sub in ast.walk(no):
                if isinstance(sub, ast.ImportFrom):
                    for a in sub.names:
                        nome = a.asname or a.name
                        # So e defeito quando o nome e LIDO antes da linha do
                        # import: o Python ja o trata como local ali e estoura.
                        if nome in topo and usos.get(nome, sub.lineno) < sub.lineno:
                            achados.append(f"{sub.module}.{a.name} (import na linha {sub.lineno}, "
                                           f"uso na {usos[nome]})")
    return achados


@pytest.mark.parametrize("arquivo,funcao", [
    ("app/local_server.py", "do_GET"),
    ("app/local_server.py", "_do_POST_rotas"),
    ("app/desktop_server.py", "do_GET"),
    ("app/desktop_server.py", "_do_POST_rotas"),
    ("helpers/preview_server.py", "do_GET"),
    ("helpers/preview_server.py", "do_POST"),
])
def test_nenhum_import_local_sombreia_nome_do_topo(arquivo, funcao):
    """Import local de um nome que ja existe no topo do modulo faz o nome
    virar local da funcao INTEIRA — e as linhas acima do import estouram."""
    achados = _imports_locais_de_nome_global(REPO / arquivo, funcao)
    assert not achados, f"{arquivo}:{funcao} sombreia nome do topo: {achados}"
