# -*- coding: utf-8 -*-
"""A barra do "Aplicar alterações" anda no caminho que é usado.

O redesenho é **80,7% da espera** de quem corrige uma legenda (mediana
52,4s, medido em 57 aplicações). O app conta o progresso pelo QUADRO que
está desenhando — prever quanto falta já foi tentado e reprovado (a faixa
acertava 21 de 45, cara ou coroa).

O fio de progresso estava ligado só no caminho de DUAS ETAPAS, e o
caminho usado é o de UMA PASSADA (`render_final_uma_passada`, ligado por
padrão). Na prática a barra ficava parada em quase todo apply: o único
caminho instrumentado é o que quase nunca roda.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
OP = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")
AE = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")


def test_a_passada_unica_aceita_progresso():
    i = RP.index("def render_final_uma_passada(")
    assinatura = RP[i:RP.index(")", RP.index("progresso=None", i))]
    assert "progresso=None" in assinatura


def test_a_passada_unica_conta_o_quadro():
    i = RP.index("def render_final_uma_passada(")
    corpo = RP[i:i + 9000]
    j = corpo.index("for f in range(frames):")
    assert "progresso(f, frames)" in corpo[j:j + 700]


def test_avisar_nunca_custa_o_render():
    i = RP.index("def render_final_uma_passada(")
    corpo = RP[i:i + 9000]
    j = corpo.index("progresso(f, frames)")
    assert "progresso = None" in corpo[j:j + 260], "erro no aviso derruba o render"


def test_o_overlay_path_passa_o_fio():
    i = OP.index("mix = render_final_uma_passada(")
    assert "progresso=progresso" in OP[i:i + 420]


def test_os_dois_caminhos_do_motor_informam():
    """Duas etapas já informava; a passada única é o padrão."""
    assert OP.count("progresso=progresso") >= 2


def test_o_apply_liga_o_fio_na_porcentagem():
    assert "progresso=lambda f, n: _avisar_redesenho(edit, f, n)" in AE


def test_o_comentario_nao_diz_mais_que_falta():
    """Ele descrevia como trabalho pendente algo já entregue — e é por
    esses comentários que se decide o que fazer em seguida."""
    assert "O que falta para uma barra HONESTA" not in AE
    assert "O caminho honesto ja esta ligado" in AE
