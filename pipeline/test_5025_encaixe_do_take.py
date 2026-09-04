# -*- coding: utf-8 -*-
"""5.0.25: quadro de take que derrubava o motor rápido.

Achado lendo os dados do próprio app (04/09): de 303 projetos com
`timing.json`, 51 saíram pelo caminho LENTO. Os motivos mais recentes eram
três `OVERLAY_RENDER_FAILED exit=1` em 01/09, e o `pipeline.log` deles diz
a causa:

    UMA_PASSADA_FALLBACK erro: images do not match
    RENDER_PROPRIO_FALLBACK erro: images do not match

`_desenhar_insert` abria o quadro do take no tamanho em que o ffmpeg o
deixou e aplicava nele a máscara do CARTÃO. Tamanhos diferentes = Pillow
levanta "images do not match", e o motor rápido do vídeo INTEIRO cai: 88,9s
de Remotion no lugar de ~17s, três vezes naquele lote.

POR QUE os tamanhos divergiam, medido com ffmpeg (04/09): o insert daquele
projeto é um take de vídeo num cartão de 460x865 — e 865 é ÍMPAR. Pedindo
`crop=460:865` o ffmpeg devolve **460x864**: um pixel a menos, porque o
yuv420p trabalha em pares. A máscara continuava com 865.

    ffmpeg ... -vf "scale=460:865:...,crop=460:865:..." -> 460x864

Por isso o defeito só pegava alguns vídeos: depende de a altura do cartão
que o usuário desenhou cair num número ímpar.

A imagem parada já passava por um encaixe `cover`; o quadro do take não
passava por nenhum. Agora os dois usam a MESMA função.
"""
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.render_proprio import _encaixar_no_cartao  # noqa: E402

PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")


def test_o_quadro_de_qualquer_tamanho_cabe_na_mascara():
    """O caso real: take 16:9 num cartão 9:16."""
    for origem in ((1280, 720), (1080, 1920), (640, 640), (3840, 2160)):
        q = Image.new("RGBA", origem)
        r = _encaixar_no_cartao(q, 540, 960, 0.5, 0.5, 1.0)
        assert r.size == (540, 960), f"{origem} não coube"
        r.putalpha(Image.new("L", (540, 960), 255))   # era aqui que quebrava


def test_o_encaixe_nao_deforma():
    """`cover`: recorta o excedente, não estica."""
    q = Image.new("RGBA", (1000, 100))
    r = _encaixar_no_cartao(q, 500, 500, 0.5, 0.5, 1.0)
    assert r.size == (500, 500)
    # a escala é a MAIOR das duas (500/100 = 5), não a menor
    assert _encaixar_no_cartao(q, 500, 500, 0.0, 0.0, 1.0).size == (500, 500)


def test_o_enquadramento_e_o_zoom_continuam_valendo():
    q = Image.new("RGBA", (2000, 1000))
    for fx in (0.0, 0.5, 1.0):
        assert _encaixar_no_cartao(q, 400, 400, fx, 0.5, 1.0).size == (400, 400)
    assert _encaixar_no_cartao(q, 400, 400, 0.5, 0.5, 1.6).size == (400, 400)


def test_a_parada_e_o_take_usam_a_mesma_funcao():
    """Duas cópias do encaixe é como o defeito nasceu."""
    assert PROPRIO.count("def _encaixar_no_cartao(") == 1
    assert PROPRIO.count("_encaixar_no_cartao(") >= 3, (
        "alguém voltou a encaixar à mão em algum dos dois caminhos")


def test_o_take_so_e_reencaixado_quando_precisa():
    """Reescalar todo quadro custaria caro; o caso normal já vem no tamanho."""
    i = PROPRIO.index("q = Image.open(lista[idx]).convert(\"RGBA\")")
    bloco = PROPRIO[i:i + 500]
    assert "if q.size != masc.size:" in bloco
    assert "insert_encaixe" in bloco, "o enquadramento do cartão se perde"


def test_o_caso_real_de_um_pixel():
    """O que aconteceu em 01/09: cartao 460x865, quadro 460x864."""
    q = Image.new("RGBA", (460, 864))
    r = _encaixar_no_cartao(q, 460, 865, 0.5, 0.5, 1.0)
    assert r.size == (460, 865)
    r.putalpha(Image.new("L", (460, 865), 255))
