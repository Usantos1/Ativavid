# -*- coding: utf-8 -*-
"""O corte pergunta ao perfil de hardware qual encoder ABRE nesta máquina.

`pick_video_encoder` consulta `app.render_engine` — que guarda o resultado
de um teste real por encoder. Nesta máquina:

    validated: {h264_nvenc: True, h264_qsv: True, h264_amf: False, libx264: True}

Sem esse import ele cai numa sondagem própria, feita com clipe sintético —
e o `h264_amf` **passa na sondagem e falha no arquivo de verdade**
(`Task finished with error code: -22`). Era a lição já registrada nesta
base: fixture sintética passa por padrão.

O import só funcionava porque quem chama exporta `PYTHONPATH`. Rodado à
mão — como a própria documentação do arquivo mostra — o corte saía por um
encoder quebrado, tentando e caindo em cada peça.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")


def test_o_repo_entra_no_path_antes_de_qualquer_uso():
    i = RENDER.index("sys.path.insert(0, str(_REPO_RENDER))")
    j = RENDER.index("def pick_video_encoder(")
    assert i < j, "o path é ajustado depois de quem precisa dele"


def test_o_encoder_sai_do_perfil_de_hardware():
    i = RENDER.index("def pick_video_encoder(")
    corpo = RENDER[i:i + 700]
    assert "from app.render_engine import encoder_args" in corpo


def test_a_sondagem_propria_continua_como_ultimo_recurso():
    """Máquina sem perfil ainda precisa escolher alguma coisa."""
    i = RENDER.index("def pick_video_encoder(")
    corpo = RENDER[i:i + 2500]
    assert "_encoder_works(" in corpo and "libx264" in corpo


def test_o_arquivo_carrega_sozinho_e_escolhe_o_encoder_certo():
    """O teste que teria pego o defeito: importar sem PYTHONPATH."""
    limpo = [p for p in sys.path if "helpers" not in p.lower()]
    guardado, sys.path = sys.path, [*limpo, str(REPO / "helpers")]
    try:
        spec = importlib.util.spec_from_file_location(
            "_render_teste", REPO / "helpers" / "render.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        from app.render_engine import encoder_args

        assert m.pick_video_encoder()[0] == encoder_args()[0]
    finally:
        sys.path = guardado
