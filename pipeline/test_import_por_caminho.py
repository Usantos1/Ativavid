# -*- coding: utf-8 -*-
"""Importar por CAMINHO, e a regra de "cada subpasta vira um vídeo".

O usuário reclamou que escolher/arrastar uma pasta com subpastas só levava os
vídeos soltos. Parte era defeito no arrastar (já corrigido), parte é que o
botão principal — "Escolher vídeos" — abre um diálogo de ARQUIVOS, onde pasta
nem dá para marcar.

A saída é o diálogo NATIVO da janela do app, que devolve o caminho: o servidor
sempre soube importar por caminho e ninguém usava. De quebra acaba com o upload
— a tela subia 1,5 GB para 127.0.0.1 para importar arquivos que já estavam no
disco, ao lado.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    """A forma da pasta do usuário: soltos no topo + subpastas."""
    from app.overlay_compose import _ffmpeg

    raiz = tmp_path_factory.mktemp("SSD")
    (raiz / "Uma subpasta").mkdir()
    (raiz / "Outra subpasta").mkdir()
    (raiz / "vazia").mkdir()

    def mk(p: Path) -> None:
        subprocess.run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p),
        ], check=True, capture_output=True)

    for rel in ("solto_um.mp4", "solto_dois.mp4",
                "Uma subpasta/take1.mp4", "Uma subpasta/take2.mp4",
                "Outra subpasta/unico.mp4"):
        mk(raiz / rel)
    (raiz / "leiame.txt").write_text("nao e video", encoding="utf-8")
    return raiz


def test_cada_subpasta_vira_um_video_e_os_soltos_ficam_soltos(pasta):
    """A regra que a tela promete.

    Antes, os arquivos soltos dentro da pasta ESCOLHIDA eram colados num vídeo
    só, batizado com o nome da pasta: escolher `SSD` (9 soltos + 3 subpastas)
    dava um "SSD" de 9 takes emendados, que ninguém pediu. A pasta escolhida
    não é subpasta dela mesma.
    """
    from app.local_server import agrupar_import

    grupos = dict((t, len(fs)) for t, fs in agrupar_import([str(pasta)]))
    assert grupos == {
        "Uma subpasta": 2,
        "Outra subpasta": 1,
        "solto_um": 1,
        "solto_dois": 1,
    }, grupos


def test_pasta_vazia_e_arquivo_que_nao_e_video_nao_viram_projeto(pasta):
    from app.local_server import agrupar_import

    titulos = [t for t, _ in agrupar_import([str(pasta)])]
    assert "vazia" not in titulos
    assert "leiame" not in titulos


def test_arquivos_avulsos_viram_um_video_cada(pasta):
    """Escolher ARQUIVOS (não pasta) não pode colar tudo num vídeo só."""
    from app.local_server import agrupar_import

    escolhidos = [str(pasta / "solto_um.mp4"), str(pasta / "solto_dois.mp4")]
    grupos = agrupar_import(escolhidos)
    assert [t for t, _ in grupos] == ["solto_dois", "solto_um"]
    assert all(len(fs) == 1 for _, fs in grupos)


def test_juntar_de_proposito_faz_um_video_so(pasta):
    from app.local_server import agrupar_import

    grupos = agrupar_import([str(pasta)], merge=True)
    assert len(grupos) == 1
    assert len(grupos[0][1]) == 5


def test_o_preview_e_a_importacao_usam_o_mesmo_agrupador():
    """Eram duas cópias da regra — e duas cópias é como a tela passa a prometer
    uma coisa e o servidor fazer outra."""
    src = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = src.index("def _ingest_paths(")
    corpo = src[i:i + 2000]
    assert "agrupar_import(paths, merge=merge)" in corpo, (
        "a importação voltou a ter a sua própria regra"
    )
    j = src.index("def _planejar_import(")
    assert "agrupar_import(" in src[j:j + 400]


def test_o_preview_conta_o_que_seria_criado(pasta):
    from app.local_server import _planejar_import

    grupos, total = _planejar_import([str(pasta)])
    assert total == 5
    assert len(grupos) == 4
    assert {"titulo": "Uma subpasta", "n": 2} in grupos


def test_a_janela_do_app_oferece_o_seletor_nativo():
    """Sem isto não há como escolher pasta pelo botão principal: o
    `<input type=file>` do navegador não aceita pasta."""
    src = (REPO / "app" / "launcher.py").read_text(encoding="utf-8")
    assert "def escolher_pasta(self)" in src
    assert "def escolher_videos(self)" in src
    i = src.index("def _dialogo(self")
    corpo = src[i:i + 1200]
    assert "FOLDER_DIALOG" in corpo and "OPEN_DIALOG" in corpo
    assert "except Exception" in corpo, (
        "um diálogo que levanta derruba o clique do usuário"
    )


def test_a_tela_usa_o_nativo_e_cai_no_input_quando_nao_ha():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "function apiNativa()" in js
    i = js.index('$("#btnPick").onclick')
    trecho = js[i:i + 1200]
    assert "escolher_videos()" in trecho and "input.click();" in trecho, (
        "o botão de arquivos perdeu o nativo ou o caminho de queda"
    )
    assert "escolher_pasta()" in trecho and "folderInput.click();" in trecho


def test_importar_por_caminho_nao_sobe_bytes():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("async function importarPorCaminho(")
    corpo = js[i:i + 1600]
    assert "FormData" not in corpo, "voltou a subir os arquivos"
    assert '"/api/jobs"' in corpo and "paths: lista" in corpo


def test_nome_de_pasta_com_acento_atravessa_inteiro(tmp_path):
    """As pastas do usuário são todas assim — "Eu sei que você quer capinha
    rosa", "Quando o chefe chega sempre tá errado".

    O acento importa: o caminho de UPLOAD passa o nome por um cabeçalho
    multipart, onde não-ASCII é justamente onde parsers quebram, e um lote que
    falha ali some sem erro. Importar por CAMINHO não tem esse pedaço, mas o
    nome ainda vira título de job e nome de pasta de projeto — vale provar que
    chega inteiro, com o acento, até o outro lado.
    """
    import subprocess

    from app.local_server import agrupar_import
    from app.overlay_compose import _ffmpeg

    raiz = tmp_path / "SSD"
    nomes = ["Eu sei que você quer capinha rosa",
             "Quando o chefe chega sempre tá errado",
             "Fone ideial para academia"]
    for n in nomes:
        (raiz / n).mkdir(parents=True)
        subprocess.run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(raiz / n / "take.mp4"),
        ], check=True, capture_output=True)

    grupos = dict((t, len(a)) for t, a in agrupar_import([str(raiz)]))
    assert set(grupos) == set(nomes), (
        f"o acento se perdeu no caminho: {sorted(grupos)}"
    )
    assert all(v == 1 for v in grupos.values())
