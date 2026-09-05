# -*- coding: utf-8 -*-
"""5.0.55: banco de imagens DENTRO da Biblioteca.

"Ali em biblioteca deve deixar pesquisar no magnific ou pexels e salvar na
biblioteca pra usos futuros — o cliente montar a própria biblioteca
baixando do banco de imagens" (05/09).

Até aqui só o editor buscava foto/vídeo de banco, e o arquivo caía dentro
do projeto (`remotion/public/pexels|freepik/`): servia uma vez e sumia com
o projeto. Agora a mesma busca sai na tela da Biblioteca e o arquivo entra
no acervo, com empresa e categoria.

O que este arquivo trava é o contorno de segurança: a chave nunca sai do
servidor, o download da Freepik é por ID (o que a API conta como download)
e o da Pexels só aceita host da Pexels — senão a rota vira proxy aberto
gravando arquivo remoto na máquina do cliente.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app import banco_de_imagens as banco  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
LS = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
DS = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")


def test_rotas_nos_dois_servidores():
    assert 'path == "/api/library/buscar"' in LS
    assert 'path == "/api/library/salvar"' in LS
    assert '"/api/library/buscar",' in DS, "o app instalado precisa delegar a busca"
    assert '"/api/library/salvar",' in DS, "e o salvar (rota de POST)"


def test_pexels_so_aceita_host_da_pexels(monkeypatch):
    chamou = []
    monkeypatch.setattr(banco, "_pexels", lambda: (type("P", (), {
        "download": staticmethod(lambda url, dest: chamou.append(url)),
        "slugify": staticmethod(lambda s: "x"),
    })(), "chave"))
    for ruim in ("https://evil.com/a.jpg", "http://images.pexels.com/a.jpg",
                 "file:///C:/Windows/win.ini", "https://images.pexels.com.evil.com/a.jpg", ""):
        with pytest.raises(ValueError):
            banco.salvar_na_biblioteca(fonte="pexels", url=ruim, rid="1")
    assert not chamou, "baixou de um host que nao e da Pexels"


def test_freepik_baixa_por_id_e_recusa_id_invalido(monkeypatch):
    monkeypatch.setattr(banco, "_freepik", lambda: (type("F", (), {
        "download": staticmethod(lambda *a, **k: None),
        "download_video": staticmethod(lambda *a, **k: None),
        "slugify": staticmethod(lambda s: "x"),
    })(), "chave"))
    for ruim in ("", "abc", "12a", "../../etc/passwd"):
        with pytest.raises(ValueError):
            banco.salvar_na_biblioteca(fonte="freepik", rid=ruim)


def test_download_vazio_nao_entra_no_acervo(monkeypatch, tmp_path):
    monkeypatch.setattr(banco, "_pexels", lambda: (type("P", (), {
        "download": staticmethod(lambda url, dest: Path(dest).write_bytes(b"x")),
        "slugify": staticmethod(lambda s: "x"),
    })(), "chave"))
    with pytest.raises(RuntimeError):
        banco.salvar_na_biblioteca(fonte="pexels", url="https://images.pexels.com/a.jpg",
                                   rid="1", projects_root=tmp_path)


def test_salvar_entra_na_biblioteca_com_empresa(monkeypatch, tmp_path):
    grande = b"\xff\xd8\xff" + b"0" * 4000

    monkeypatch.setattr(banco, "_pexels", lambda: (type("P", (), {
        "download": staticmethod(lambda url, dest: Path(dest).write_bytes(grande)),
        "slugify": staticmethod(lambda s: "foto"),
    })(), "chave"))
    item = banco.salvar_na_biblioteca(
        fonte="pexels", url="https://images.pexels.com/photos/1/a.jpg", rid="1",
        query="loja", credit="Fulano", empresa="prime-camp", projects_root=tmp_path)
    assert item["ok"] and item["kind"] == "image"
    assert item["fonte"] == "pexels" and item["credit"] == "Fulano"
    destino = Path(item["path"])
    assert destino.is_file() and destino.read_bytes() == grande
    assert "prime-camp" in destino.as_posix(), "a imagem entra na pasta da empresa"


def test_busca_normaliza_e_valida():
    with pytest.raises(ValueError):
        banco.buscar("", "pexels")
    assert banco.FONTES == ("pexels", "freepik")


def test_a_tela_da_biblioteca_busca_e_salva():
    assert 'id="libraryBanco"' in HTML and 'id="libraryBancoQ"' in HTML
    assert 'value="pexels"' in HTML and 'value="freepik"' in HTML
    assert "function buscarNoBanco(termo, fonte)" in SJS
    assert "/api/library/buscar?q=" in SJS and '"/api/library/salvar"' in SJS
    i = SJS.index("async function salvarDoBanco(i)")
    corpo = SJS[i:i + 1200]
    assert "empresa" in corpo, "o arquivo entra na empresa ativa"
    assert "loadLibraryUi()" in corpo, "a lista se atualiza depois de guardar"
    assert "function bancoVisivel()" in SJS, "so nas abas de imagem e video"


def test_a_busca_so_aparece_onde_faz_sentido():
    i = SJS.index("function bancoVisivel()")
    corpo = SJS[i:i + 260]
    assert '"image"' in corpo and '"clip"' in corpo
    assert "track" not in corpo and "sfx" not in corpo, "banco de imagem nao serve para audio"
