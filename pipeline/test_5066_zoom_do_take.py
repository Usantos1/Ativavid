# -*- coding: utf-8 -*-
"""5.0.66: o zoom deixa de ser decisão só do estilo e vira escolha por take.

O planejador já escrevia uma aproximação por trecho — em 317 projetos
reais, 313 usam `pushIn` 0,04 e as bases alternam entre 1,10 e 1,22. O que
faltava era o usuário poder discordar num take: segurar a imagem parada
num detalhe, ou fechar mais num take de reação.

São quatro opções, e a primeira é a de sempre:

    ""        automático — o que o estilo decidiu (nada muda)
    nenhum    o take fica parado
    suave     base 1,06 + 3% de aproximação
    forte     base 1,20 + 12%

`suave` fica abaixo da faixa que o planejador usa e `forte` acima, para as
duas serem visíveis ao lado do automático.

A escolha não mexe na classificação do render: quem decide OVERLAY ou FULL
lê `edit_data["camera"]`, não os trechos do EDL.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.ffmpeg_zoom import ZOOMS_DO_TAKE, zoom_do_range, zoom_for_index  # noqa: E402
from app.quick_corrections import _HERDAVEIS, _norm_range  # noqa: E402

PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")

EDL = {
    "ffmpegZoom": {"enabled": True, "zooms": [1.14, 1.2], "pushIn": 0.04,
                   "targetX": 0.5, "targetY": 0.4, "width": 1080, "height": 1920},
    "ranges": [{}, {"zoom": "nenhum"}, {"zoom": "forte"}, {"zoom": "suave"},
               {"zoom": "lixo"}],
}


def test_o_pedido_e_normalizado():
    assert zoom_do_range({}) == ""
    assert zoom_do_range({"zoom": "FORTE"}) == "forte"
    assert zoom_do_range({"zoom": "lixo"}) == "", "valor estranho vira automático"
    assert zoom_do_range(None) == ""


def test_sem_pedido_nada_muda():
    """A regra que protege os 317 projetos que já existem."""
    a = zoom_for_index(EDL, 0)
    assert a == {"base": 1.14, "push": 0.04, "cx": 0.5, "cy": 0.4,
                 "outW": 1080, "outH": 1920}
    # valor estranho cai no automático, e o índice continua alternando
    assert zoom_for_index(EDL, 4)["base"] == 1.14


def test_cada_opcao_faz_o_que_diz():
    assert zoom_for_index(EDL, 1) is None, "`nenhum` deixa o take parado"
    forte = zoom_for_index(EDL, 2)
    suave = zoom_for_index(EDL, 3)
    assert forte["base"] > 1.14 > suave["base"], "forte acima, suave abaixo"
    assert forte["push"] > 0.04 > suave["push"]
    # a âncora e o tamanho continuam vindo do estilo
    for z in (forte, suave):
        assert z["cx"] == 0.5 and z["cy"] == 0.4
        assert z["outW"] == 1080 and z["outH"] == 1920


def test_o_estilo_sem_zoom_manda_mais_que_o_take():
    """Se o estilo desligou o movimento, um pedido no take não pode ligar:
    sem `ffmpegZoom` não há largura, altura nem âncora de onde partir."""
    assert zoom_for_index({"ranges": [{"zoom": "forte"}]}, 0) is None
    assert zoom_for_index({"ffmpegZoom": {"enabled": False},
                           "ranges": [{"zoom": "forte"}]}, 0) is None


def test_indice_fora_da_lista_nao_derruba():
    assert zoom_for_index(EDL, 99) is not None
    assert zoom_for_index({"ffmpegZoom": EDL["ffmpegZoom"]}, 0) is not None


def test_o_campo_viaja_e_conta_como_mudanca():
    assert "zoom" in _HERDAVEIS
    a = {"source": "s", "start": 0, "end": 1}
    assert _norm_range(a) != _norm_range({**a, "zoom": "forte"})
    assert _norm_range({**a, "zoom": "forte"}) != _norm_range({**a, "zoom": "suave"})
    assert RF.count('item["zoom"] = _z') == 2, "os DOIS leitores de EDL"


def test_o_clipe_guardado_ve_a_troca():
    """A chave do clipe no caminho J-cut já chama `zoom_for_index`, então
    trocar o zoom do take troca a chave — e o corte não volta do cache com
    o movimento antigo."""
    render = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
    i = render.index("vkey = _seg_key(")
    assert "_zoom_key_fn(edl, i)" in render[i:i + 1500]
    assert "from app.ffmpeg_zoom import zoom_enabled, zoom_for_index" in render


def test_o_editor_manda_e_compara():
    assert "const ZOOMS_DO_TAKE" in PJS
    for v in ("nenhum", "suave", "forte"):
        assert f"['{v}'," in PJS, v
    assert "if (r.zoom) out.zoom = String(r.zoom);" in PJS
    assert "(r.zoom || '') !== (r.orig.zoom || '')" in PJS, "senão o Aplicar não acende"
    assert "'reframe', 'flip', 'zoom'" in PJS, "o `Aplicar a todos` leva o zoom junto"


def test_os_rotulos_da_tela_cobrem_o_catalogo():
    for chave in ZOOMS_DO_TAKE:
        assert f"['{chave}'," in PJS, f"`{chave}` sem botão na tela"
