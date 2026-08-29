# -*- coding: utf-8 -*-
"""Biblioteca separada por acervo e por categoria.

A tela juntava tudo numa lista so; com 171 trilhas nao dava para achar
nada. Aqui trava o que a separacao PRECISA garantir para nao virar
enfeite: a categoria e o nome do arquivo (o mesmo contrato que o pipeline
le), som nunca vira b-roll, e efeito do usuario troca o do app de verdade.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import app.broll_library as bl  # noqa: E402


def _raiz(tmp: Path) -> Path:
    raiz = tmp / "Projetos"
    raiz.mkdir(parents=True, exist_ok=True)
    bl.library_root(raiz)
    return raiz


def test_categoria_mora_no_nome_do_arquivo():
    """Trocar a categoria RENOMEIA — nao grava num json a parte.

    O plano B da musica escolhe a faixa pelo prefixo do nome
    (`_trilha_etiqueta` em run_fast). Uma categoria guardada em outro
    lugar seria uma segunda verdade, e sairia de sincronia na primeira vez
    que o usuario mexesse na pasta pelo Explorer.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        it = bl.add_bytes("minha musica.mp3", b"x" * 100, kind="track",
                          categoria="Humor", projects_root=raiz)
        assert it["name"] == "humor--minha-musica.mp3", it
        novo = bl.set_categoria(it["rel"], "viral", projects_root=raiz)
        assert novo["name"] == "viral--minha-musica.mp3", novo
        assert (bl.library_root(raiz) / "Trilhas"
                / "viral--minha-musica.mp3").is_file()
        solta = bl.set_categoria(novo["rel"], "", projects_root=raiz)
        assert solta["name"] == "minha-musica.mp3", solta
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_categoria_nao_escapa_da_biblioteca():
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        for rel in ("../fora.mp3", "/etc/passwd", ""):
            try:
                bl.set_categoria(rel, "viral", projects_root=raiz)
            except ValueError:
                continue
            raise AssertionError(f"aceitou {rel!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_som_nunca_vira_broll():
    """B-roll e imagem/clipe. Trilha e efeito sao AUDIO: se entrassem na
    escolha de b-roll, o video mostraria um mp3 como figura."""
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        bl.add_bytes("celular.jpg", b"i" * 80, projects_root=raiz)
        bl.add_bytes("viral--musica.mp3", b"m" * 80, kind="track",
                     projects_root=raiz)
        bl.add_bytes("whoosh--meu.mp3", b"s" * 80, kind="sfx",
                     projects_root=raiz)
        escolhas = bl.pick_for_query("celular", raiz, limit=5)
        assert escolhas and all(i["kind"] in ("image", "clip")
                                for i in escolhas), escolhas
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_efeito_do_usuario_troca_o_do_app():
    """A categoria do efeito e a VAGA que ele ocupa no video.

    Sem isto "Adicionar efeitos" seria um botao que guarda arquivo e nao
    muda video nenhum. Os dois motores tocam o som de
    `remotion/public/sfx`, entao a troca vale para os dois.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        bl.add_bytes("meu whoosh.mp3", b"MEU" * 40, kind="sfx",
                     categoria="whoosh", projects_root=raiz)
        public = tmp / "projeto" / "remotion" / "public"
        (public / "sfx").mkdir(parents=True)
        (public / "sfx" / "whoosh.mp3").write_bytes(b"APP" * 40)
        (public / "sfx" / "pop.mp3").write_bytes(b"APP" * 40)
        trocados = bl.aplicar_sfx_do_usuario(public, raiz)
        assert len(trocados) == 1, trocados
        assert (public / "sfx" / "whoosh.mp3").read_bytes().startswith(b"MEU")
        # vaga sem arquivo do usuario fica com o som do app
        assert (public / "sfx" / "pop.mp3").read_bytes().startswith(b"APP")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_efeitos_do_app_aparecem_e_nao_sao_editaveis():
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        pack = bl.list_assets(raiz)
        app_sfx = [i for i in pack["items"]
                   if i["kind"] == "sfx" and i["origem"] == "app"]
        assert len(app_sfx) >= 5, app_sfx
        # rel com prefixo proprio: a rota serve isso da pasta do template
        assert all(i["rel"].startswith(bl.SFX_APP_REL + "/") for i in app_sfx)
        assert bl.familia_sfx("cut-click.mp3") == "corte"
        assert bl.familia_sfx("caption-click.mp3") == "clique"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_clima_da_biblioteca_bate_com_o_do_pipeline():
    """A tela mostra o clima de cada categoria; se as duas tabelas
    discordarem, a tela promete uma escolha que o render nao faz."""
    import importlib
    rf = importlib.import_module("pipeline.run_fast")
    for rotulo, clima in bl.CLIMA_TRILHA.items():
        assert rf._TRILHA_CLIMA.get(rotulo) == clima, rotulo
