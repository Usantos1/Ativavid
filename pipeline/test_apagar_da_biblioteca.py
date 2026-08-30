# -*- coding: utf-8 -*-
""""quero deletar os efeitos que eu nao gostar por ali tambem" (30/08).

Dava para adicionar e reclassificar; para TIRAR era abrir a pasta no
Explorer. Com 233 efeitos importados de uma vez, escolher o que fica e
trabalho de lista.

O destino e a Lixeira do Windows (`SHFileOperationW` + `FOF_ALLOWUNDO`,
a mesma operacao do Explorer) — nao `unlink`. E um clique numa lista, o
acervo e dele, e clique numa lista nao pode ser definitivo. Testado com
arquivo de verdade: sai do disco e aparece na Lixeira.

E o seletor de categoria passou a oferecer TODAS as categorias da pasta,
nao so as 5 vagas do app: nao dava para reclassificar um arquivo para uma
categoria que ele mesmo criou e que estava ali do lado, nos chips.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import broll_library as bl  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    raiz = tmp_path / "Biblioteca"
    (raiz / "Efeitos").mkdir(parents=True)
    monkeypatch.setattr(bl, "library_root", lambda *_a, **_k: raiz)
    return raiz


def test_apaga_um_arquivo_da_biblioteca(lib):
    f = lib / "Efeitos" / "swoosh--001.mp3"
    f.write_bytes(b"som")
    r = bl.remover("Efeitos/swoosh--001.mp3")
    assert r["ok"] and not f.exists()


def test_nao_apaga_nada_fora_da_biblioteca(lib, tmp_path):
    fora = tmp_path / "importante.mp3"
    fora.write_bytes(b"nao me apague")
    for rel in ("../importante.mp3", "..\\importante.mp3",
                str(fora), "Efeitos/../../importante.mp3"):
        with pytest.raises(ValueError):
            bl.remover(rel)
    assert fora.exists(), rel


def test_arquivo_que_nao_existe_avisa(lib):
    with pytest.raises(ValueError):
        bl.remover("Efeitos/nao-existe.mp3")


def test_o_caminho_da_lixeira_e_o_do_explorer():
    """`FOF_ALLOWUNDO` e o que separa "foi para a Lixeira" de "sumiu", e o
    `pFrom` terminado em DOIS nulos e o que faz a API ler so o caminho."""
    src = (REPO / "app" / "broll_library.py").read_text(encoding="utf-8")
    i = src.index("def _para_a_lixeira(")
    bloco = src[i:src.index("\ndef ", i + 10)]
    assert "FOF_ALLOWUNDO = 0x0040" in bloco
    assert "FOF_ALLOWUNDO |" in bloco
    assert 'str(alvo) + "\\0\\0"' in bloco
    assert "SHFileOperationW" in bloco


def test_a_rota_existe_nos_dois_servidores():
    srv = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert '"/api/library/remover"' in srv
    app = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/library/remover"' in app, "rota nova nasce gateada"


def test_a_tela_pergunta_antes_e_nao_toca_o_som(lib):
    i = JS.index('e.target.closest("[data-libdel]")')
    bloco = JS[i:i + 900]
    assert "pedirConfirmacao(" in bloco
    assert "Lixeira" in bloco
    # a linha inteira e um player: sem parar a propagacao, apagar TOCA
    assert "e.stopPropagation()" in bloco


def test_arquivo_do_app_nao_tem_botao():
    i = JS.index("function libBotaoApagar(")
    assert 'if (it.origem === "app") return "";' in JS[i:i + 300]


# ------------------------------------------------------ as categorias

def test_o_seletor_oferece_as_categorias_que_existem():
    itens = [
        {"kind": "sfx", "categoria": "swoosh", "origem": "usuario"},
        {"kind": "sfx", "categoria": "impacto", "origem": "usuario"},
        {"kind": "sfx", "categoria": "relogio", "origem": "app"},
        {"kind": "sfx", "categoria": "", "origem": "usuario"},
        {"kind": "track", "categoria": "calma", "origem": "usuario"},
    ]
    out = bl._com_as_da_pasta(bl.SFX_VAGAS, itens, "sfx")
    assert out[:5] == list(bl.SFX_VAGAS), "as vagas do video vem primeiro"
    assert out[5:] == ["impacto", "relogio", "swoosh"], out
    assert "calma" not in out, "categoria de outro acervo nao entra"
    assert "" not in out
