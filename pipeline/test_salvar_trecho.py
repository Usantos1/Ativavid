# -*- coding: utf-8 -*-
"""Salvar um trecho do vídeo na Biblioteca, como clipe de b-roll.

A 4.31/4.32 fizeram o vídeo de humor USAR os clipes da Biblioteca, em tela
cheia. Só que a única forma de pôr um clipe lá era recortar arquivo na mão,
fora do app — foi o que eu mesmo tive de fazer para testar. Buraco aberto
por quem entregou as duas versões.

Agora a marcação que ele já usa para apontar legenda errada (M no começo,
M no fim) ganha uma segunda saída no mesmo balão.

Dois defeitos que só o teste AO VIVO achou:

  1. `self._read_json()` não existe no `DesktopHandler` — o editor roda
     sob ele e herda este arquivo. A tela disse "Failed to fetch" e o log,
     o AttributeError.
  2. O nome vinha de `n.text` (a nota JÁ SALVA) e não da caixa de texto:
     quem clica em "Salvar na Biblioteca" acabou de digitar e nunca passou
     pelo "Aplicar". O arquivo saía `humor--asset.mp4`.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import broll_library as bl  # noqa: E402

JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")


@pytest.fixture()
def video(tmp_path, monkeypatch):
    from app.ffmpeg_tools import ffmpeg_bin

    f = tmp_path / "cut.mp4"
    subprocess.run(
        [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=540x960:rate=30:duration=6",
         "-c:v", "libx264", "-crf", "30", "-preset", "ultrafast", str(f)],
        check=True, capture_output=True, timeout=90)
    monkeypatch.setattr(bl, "library_root",
                        lambda *_a, **_k: _prep(tmp_path / "Biblioteca"))
    return f


def _prep(raiz: Path) -> Path:
    (raiz / "clips").mkdir(parents=True, exist_ok=True)
    return raiz


def test_recorta_e_guarda_com_a_categoria_no_nome(video, tmp_path):
    out = bl.salvar_trecho(video, inicio=1.0, fim=3.0, categoria="reacao",
                           nome="cliente rindo do preço", altura=320)
    assert out["ok"] and out["categoria"] == "reacao"
    assert out["arquivo"] == "reacao--cliente-rindo-do-preco.mp4"
    f = tmp_path / "Biblioteca" / "clips" / out["arquivo"]
    assert f.is_file() and f.stat().st_size > 1000


def test_o_clipe_sai_no_quadro_do_video(video, tmp_path):
    """9:16 — o insert desenha nesse quadro; fora dele entraria esticado."""
    from app.ffmpeg_tools import ffprobe_bin

    out = bl.salvar_trecho(video, inicio=1.0, fim=2.2, categoria="humor",
                           altura=320)
    f = tmp_path / "Biblioteca" / "clips" / out["arquivo"]
    r = subprocess.run([ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(f)], capture_output=True, text=True, timeout=30)
    larg, alt = [int(x) for x in r.stdout.strip().split(",")[:2]]
    assert (larg, alt) == (180, 320), (larg, alt)


def test_nome_repetido_nao_apaga_o_anterior(video, tmp_path):
    a = bl.salvar_trecho(video, inicio=1.0, fim=2.0, categoria="humor",
                         nome="igual", altura=320)
    b = bl.salvar_trecho(video, inicio=3.0, fim=4.0, categoria="humor",
                         nome="igual", altura=320)
    assert a["arquivo"] != b["arquivo"]
    clips = tmp_path / "Biblioteca" / "clips"
    assert len(list(clips.glob("humor--igual*.mp4"))) == 2


@pytest.mark.parametrize("ini,fim", [(1.0, 1.2), (0.0, 40.0)])
def test_trecho_fora_do_tamanho_e_recusado(video, ini, fim):
    with pytest.raises(ValueError):
        bl.salvar_trecho(video, inicio=ini, fim=fim, categoria="humor",
                         altura=320)


def test_video_que_nao_existe_avisa(tmp_path, monkeypatch):
    monkeypatch.setattr(bl, "library_root",
                        lambda *_a, **_k: _prep(tmp_path / "Biblioteca"))
    with pytest.raises(ValueError):
        bl.salvar_trecho(tmp_path / "nao-existe.mp4", inicio=0, fim=2,
                         categoria="humor")


# ------------------------------------------------------- as duas pontas

def test_a_rota_le_o_corpo_como_as_vizinhas():
    """`self._read_json()` e do outro handler: o editor roda sob o
    `DesktopHandler`, que herda este arquivo e nao tem esse metodo."""
    import re

    i = PS.index("def _salvar_trecho(")
    bloco = PS[i:PS.index("\n    def ", i + 10)]
    # Sem os comentários: o comentário CONTA a história e cita o nome do
    # método errado — ancorar no texto cru acusaria a própria explicação.
    codigo = re.sub(r"#[^\n]*", "", bloco)
    assert "self._read_json()" not in codigo
    assert "json.loads(self.rfile.read(length)" in codigo


def test_a_rota_nao_deixa_sair_do_projeto():
    i = PS.index("def _salvar_trecho(")
    bloco = PS[i:PS.index("\n    def ", i + 10)]
    assert "alvo.relative_to(self.root.resolve())" in bloco


def test_o_botao_usa_o_relogio_do_arquivo_que_toca():
    """A nota e do RASCUNHO; sem converter, o clipe sairia deslocado por
    tudo que foi removido antes dele."""
    i = JS.index("async function guardarTrechoNaBiblioteca()")
    bloco = JS[i:i + 1600]
    assert "draftToRendered(n.start)" in bloco
    assert "draftToRendered(n.end)" in bloco


def test_o_nome_vem_da_caixa_e_nao_da_nota_salva():
    i = JS.index("async function guardarTrechoNaBiblioteca()")
    bloco = JS[i:i + 2000]
    assert "$('noteText') || {}).value" in bloco


def test_o_balao_oferece_as_categorias_de_humor():
    from app.broll_library import CATEGORIAS_HUMOR

    i = HTML.index('id="noteCategoria"')
    bloco = HTML[i:HTML.index("</select>", i)]
    for cat in CATEGORIAS_HUMOR:
        assert f'value="{cat}"' in bloco, cat
