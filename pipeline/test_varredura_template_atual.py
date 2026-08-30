# -*- coding: utf-8 -*-
"""A varredura mede contra o template DE HOJE, não contra o do projeto.

Cada projeto guarda a cópia do template do dia em que foi renderizado. Em
30/08 rodar a varredura num projeto de 29/08 acusou cinco manchetes fora
da faixa — `faixa` 2,001, `vazado` 1,822, `fita`, `neon`, `gradiente`.
Nenhuma era defeito: aqueles estilos **não existem naquela cópia** (55 KB
contra os 66 KB de hoje) e o Remotion caía no estilo padrão.

Com o template do app como referência, os mesmos cinco medem 0,992 a
1,039 no mesmo projeto.

E isso destravou a ferramenta: só **1 dos 187** projetos tinha o template
atual, então a varredura só rodava nele.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

VD = (REPO / "tools" / "varrer_desenho.py").read_text(encoding="utf-8")


def test_o_src_vem_do_app():
    i = VD.index('src_app = REPO /')
    corpo = VD[i:i + 900]
    assert 'shutil.copytree(src_app, palco / "src")' in corpo


def test_os_dados_continuam_sendo_do_projeto():
    i = VD.index('src_app = REPO /')
    corpo = VD[i:i + 900]
    assert '"public"' in corpo


def test_a_troca_acontece_antes_do_prepare():
    """`prepare_overlay_remotion` injeta a composição `Overlay` no src —
    trocar depois apagava a injeção e o Remotion respondia
    "Could not find composition with ID Overlay"."""
    i = VD.index('shutil.copytree(src_app, palco / "src")')
    j = VD.index("prepare_overlay_remotion(palco, ov)")
    assert i < j


def test_o_palco_e_limpo_no_fim():
    assert '.varredura_fonte' in VD
    i = VD.index('shutil.rmtree(ov, ignore_errors=True)')
    assert ".varredura_fonte" in VD[i:i + 300]


def test_o_episodio_fica_no_cabecalho():
    assert "O SEGUNDO PROJETO PRECISA TER O MESMO TEMPLATE" in VD
    assert "2,001" in VD and "55 KB" in VD
