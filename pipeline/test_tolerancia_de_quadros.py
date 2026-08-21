# -*- coding: utf-8 -*-
"""A guarda de quadros do quick apply recusava 64% dos projetos legítimos.

O mapa soma `duração × fps` por range; o corte é o que o ffmpeg entrega. Os
dois nunca bateram: cada segmento sai 2 a 7 quadros mais curto que a duração
pedida (medido também num projeto de 15/08, muito antes de qualquer mudança
recente — não é regressão, é como o `extract_segment` sempre funcionou), e a
emenda com J-cut compensa parte disso.

O que sobra é uma deriva que ACOMPANHA o número de emendas. Medido nos 39
projetos do usuário em 21/08/2026:

| ranges | deriva observada |
|---|---|
| 3 a 5 | 0 a 3 quadros |
| 10 a 15 | 2 a 8 |
| 38 | 21 |

Nunca acima de **0,75 quadro por emenda**. Com a tolerância de 1 quadro que
estava no código, **25 dos 39 projetos (64%)** eram recusados: o usuário
corrigia uma legenda e o apply respondia `OLD map Nf vs cut.mp4 Mf` sem
aplicar nada. Foram 9 das 10 falhas de apply no histórico dele.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import tolerancia_de_quadros  # noqa: E402

# (ranges, deriva) — os casos reais medidos na máquina do usuário
MEDIDOS = [
    (3, 0), (4, 0), (5, 0), (5, 3), (5, 1), (6, 0), (7, 0), (7, 1),
    (8, 2), (8, 3), (10, 2), (10, 5), (11, 3), (11, 5), (12, 2), (12, 3),
    (12, 5), (12, 5), (13, 4), (13, 7), (14, 5), (15, 5), (15, 8), (15, 9),
    (20, 9), (38, 21),
]


def test_todos_os_casos_reais_passam():
    """Nenhum projeto legítimo do usuário pode ser recusado."""
    recusados = [(n, d) for n, d in MEDIDOS if d > tolerancia_de_quadros(n)]
    assert not recusados, recusados


def test_a_folga_nao_e_generosa_demais():
    """A guarda existe para pegar um mapa de OUTRO corte, que difere pelo
    tamanho de um range inteiro. A folga tem de ficar bem abaixo disso."""
    for n, _ in MEDIDOS:
        folga = tolerancia_de_quadros(n)
        # margem confortável sobre a deriva máxima observada (0,75/emenda)
        assert folga >= 0.75 * n, (n, folga)
        # mas nunca mais que ~1,2 quadro por emenda + a almofada
        assert folga <= 1.2 * n + 3, (n, folga)


def test_projeto_de_um_range_ainda_tem_folga_minima():
    assert tolerancia_de_quadros(0) >= 2
    assert tolerancia_de_quadros(1) >= 2


def test_a_folga_cresce_com_as_emendas():
    """O ponto todo: a deriva é por emenda, então a folga também tem de ser."""
    valores = [tolerancia_de_quadros(n) for n in (1, 5, 15, 38)]
    assert valores == sorted(valores)
    assert valores[-1] > valores[0] * 4


def test_as_duas_guardas_usam_a_mesma_conta():
    """Havia duas cópias do `> 1` — a do mapa antigo e a do cut temporário."""
    s = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")
    assert s.count("tolerancia_de_quadros(") == 3, "definição + os dois usos"
    assert "abs(predicted - cut_frames) > 1" not in s
    assert "abs(int(actual) - predicted) > 1" not in s
