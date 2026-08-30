# -*- coding: utf-8 -*-
"""A Fila diz em que passo o vídeo está.

As quatro primeiras etapas — olhar o vídeo, ouvir o que foi falado,
escolher os cortes, cortar — mostravam **a mesma frase**, "Preparando
vídeo...". E são elas que levam a primeira metade dos minutos de espera:
medido nos 31 vídeos mais recentes, `ANALYZE` + `PLAN` + `CUT` somam 48%
do tempo total. Quem olhava a Fila não sabia se tinha andado.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.local_server import STAGE_LABELS  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")

PASSOS = ("analyzing", "transcribing", "planning", "cutting")


def test_cada_passo_tem_frase_propria():
    frases = [STAGE_LABELS[p] for p in PASSOS]
    assert len(set(frases)) == len(frases), frases
    assert "Preparando vídeo" not in " ".join(frases)


def test_as_frases_falam_a_lingua_do_usuario():
    """Sem jargão: nada de "transcrever", "EDL", "render"."""
    juntas = " ".join(STAGE_LABELS[p] for p in PASSOS).lower()
    for termo in ("transcri", "edl", "render", "pipeline", "encode"):
        assert termo not in juntas, termo


def test_a_tela_usa_os_mesmos_passos():
    i = JS.index("const PASSO = {")
    bloco = JS[i:JS.index("\n  };", i)]
    for p in PASSOS:
        assert f"{p}:" in bloco, p


def test_o_generico_continua_para_quando_o_passo_nao_chegou():
    """O status pode não ter passo ainda — a frase antiga cobre isso."""
    assert "Preparando vídeo..." in JS


def test_os_passos_existem_no_pipeline():
    """Rótulo de passo que o pipeline nunca emite é enfeite."""
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    for p in PASSOS:
        assert f'"{p}"' in rf, p
