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


def _tom(destino: Path, segundos: float) -> Path:
    """Um som de verdade, com duracao de verdade.

    `b"MEU" * 40` nao e audio: nao tem duracao para medir, e desde o teto
    de 4.19 e recusado — com razao. O tom sai a -6 dB para nao cair no
    filtro de distorcao (pico >= -0,1 dBFS).
    """
    import subprocess

    from app.ffmpeg_tools import ffmpeg_bin

    subprocess.run(
        [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"sine=frequency=900:duration={segundos}",
         "-af", "volume=-6dB", "-c:a", "libmp3lame", "-q:a", "5",
         str(destino)],
        check=True, capture_output=True, timeout=60)
    return destino


def test_efeito_do_usuario_troca_o_do_app():
    """A categoria do efeito e a VAGA que ele ocupa no video.

    Sem isto "Adicionar efeitos" seria um botao que guarda arquivo e nao
    muda video nenhum. Os dois motores tocam o som de
    `remotion/public/sfx`, entao a troca vale para os dois.
    """
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        curto = _tom(tmp / "curto.mp3", 0.40)
        bl.add_bytes("meu whoosh.mp3", curto.read_bytes(), kind="sfx",
                     categoria="whoosh", projects_root=raiz)
        public = tmp / "projeto" / "remotion" / "public"
        (public / "sfx").mkdir(parents=True)
        (public / "sfx" / "pop.mp3").write_bytes(b"APP" * 40)
        trocados = bl.aplicar_sfx_do_usuario(public, raiz)
        assert len(trocados) == 1, trocados
        assert "whoosh.mp3" in trocados[0]
        d = bl._dur_seg(public / "sfx" / "whoosh.mp3")
        assert d is not None and 0.3 < d < 0.6, d
        # vaga sem arquivo do usuario fica com o som do app
        assert bl._dur_seg(public / "sfx" / "pop.mp3") is not None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_efeito_longo_demais_nao_entra_na_vaga():
    """O defeito de 30/08: um `swoosh` de 10,78s no lugar do whoosh de
    0,45s do app — "saiu com um apito" no video dele. Um som de transicao
    longo toca por cima de tudo."""
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        longo = _tom(tmp / "longo.mp3", 6.0)
        bl.add_bytes("meu whoosh.mp3", longo.read_bytes(), kind="sfx",
                     categoria="whoosh", projects_root=raiz)
        public = tmp / "projeto" / "remotion" / "public"
        (public / "sfx").mkdir(parents=True)
        assert bl.aplicar_sfx_do_usuario(public, raiz) == []
        # e a vaga fica com o som do app, medido
        d = bl._dur_seg(public / "sfx" / "whoosh.mp3")
        assert d is not None and d < 1.0, d
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_o_som_do_app_volta_antes_da_troca():
    """Sem isto o arquivo ruim de um render anterior fica no projeto para
    sempre: a troca so grava quando ACHA candidato. Foi assim que o whoosh
    de 10,78s sobreviveu no projeto dele."""
    tmp = Path(tempfile.mkdtemp())
    try:
        raiz = _raiz(tmp)
        public = tmp / "projeto" / "remotion" / "public"
        (public / "sfx").mkdir(parents=True)
        _tom(public / "sfx" / "whoosh.mp3", 8.0)   # o erro de ontem
        bl.aplicar_sfx_do_usuario(public, raiz)    # biblioteca vazia
        d = bl._dur_seg(public / "sfx" / "whoosh.mp3")
        assert d is not None and d < 1.0, d
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


def test_video_tem_acervo_proprio_com_categoria_de_take():
    """Take de apoio (reação, meme, CTA) e foto de produto são coisas
    diferentes: ficavam na mesma aba e as categorias não serviam para
    nenhum dos dois."""
    from pathlib import Path
    RAIZ = Path(__file__).resolve().parent.parent
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'data-libtab="clip"' in html
    assert 'id="libraryVideoInput"' in html and 'id="libCountClip"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'kinds: ["clip"]' in js and 'kinds: ["image"]' in js
    assert "viral" in bl.CATEGORIAS_CLIPE and "meme" in bl.CATEGORIAS_CLIPE
    assert "cta" in bl.CATEGORIAS_CLIPE and "humor" in bl.CATEGORIAS_CLIPE


def test_so_um_som_toca_por_vez():
    """Tocar a terceira trilha deixava as duas anteriores tocando por cima
    (print do usuário com três ao mesmo tempo) — comparar duas músicas
    ficava impossível. `play` não borbulha: o listener é de captura."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "assets" / "studio"
          / "studio.js").read_text(encoding="utf-8")
    i = js.index('painel.addEventListener("play"')
    trecho = js[i:i + 400]
    assert "querySelectorAll(\"audio, video\")" in trecho, trecho
    assert "m.pause()" in trecho and "}, true)" in trecho, trecho
