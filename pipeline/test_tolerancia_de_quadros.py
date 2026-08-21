# -*- coding: utf-8 -*-
"""A guarda de quadros do quick apply, calibrada contra os projetos de verdade.

O mapa soma `duração × fps` por range; o corte é o que o ffmpeg entrega. Os
dois nunca bateram: cada segmento sai 2 a 7 quadros mais curto que a duração
pedida (medido também num projeto de 15/08, muito antes de qualquer mudança
recente — não é regressão, é como o `extract_segment` sempre funcionou), e a
emenda com J-cut compensa parte disso.

Com a tolerância de 1 quadro que estava no código, **25 dos 39 projetos
medidos na época (64%)** eram recusados: o usuário corrigia uma legenda e o
apply respondia `OLD map Nf vs cut.mp4 Mf` sem aplicar nada. Foram 9 das 10
falhas de apply no histórico dele.

A folga passou então a `2 + 0,8n`, calibrada naqueles 39 projetos, onde a
deriva nunca passava de 0,75 quadro por emenda. **Rodando nos 128 projetos
que existem hoje, essa afirmação é falsa**: um projeto de 5 ranges tem deriva
de 9 quadros — 1,80 por emenda — e era recusado por 3 quadros.

E a deriva não cresce em linha com as emendas, cresce como RAIZ: 9 quadros
com 5 emendas e 21 com 38. Isolando cada ponta, a constante que sai é a mesma
(~3,1), o que confirma o modelo. Um linear generoso o bastante para o projeto
de 5 daria 78 quadros de folga no de 38 — mais que um take inteiro de 2s, e a
guarda deixaria de pegar exatamente o que existe para pegar.

Medido nos 128 projetos, `2 + 5,0·√n` contra o `2 + 0,8n`:

| | 2+0,8n | 2+5,0·√n |
|---|---|---|
| projetos aceitos | 127/128 | **128/128** |
| margem no mais apertado | −3 (recusa) | +4 |
| folga com 38 emendas | 32 | 33 |
| menor take que ainda pega | 1,1s | 1,1s |
| mapa de OUTRO corte que passa | 3/128 | 3/128 |
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.apply_execute import tolerancia_de_quadros  # noqa: E402

# (ranges, deriva) — os 66 pares distintos medidos nos 128 projetos do usuário
# em 21/08/2026. Extraído com `build_timeline_map` contra o `cut.mp4` de cada
# projeto; é o dado real, não um cenário inventado.
MEDIDOS = [
    (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (4, 0), (4, 1), (5, 0), (5, 1),
    (5, 3), (5, 9), (6, 0), (6, 1), (6, 2), (6, 3), (7, 0), (7, 1), (7, 2),
    (7, 6), (8, 0), (8, 1), (8, 2), (8, 3), (9, 1), (9, 3), (9, 4), (9, 5),
    (10, 0), (10, 1), (10, 2), (10, 3), (10, 4), (10, 5), (11, 1), (11, 2),
    (11, 3), (11, 5), (12, 1), (12, 2), (12, 3), (12, 4), (12, 5), (12, 6),
    (13, 3), (13, 4), (13, 5), (13, 7), (14, 0), (14, 5), (14, 7), (15, 0),
    (15, 3), (15, 4), (15, 5), (15, 6), (15, 8), (15, 9), (16, 1), (16, 4),
    (16, 8), (18, 1), (19, 7), (20, 9), (21, 1), (29, 13), (38, 21),
]

# O menor corte que a guarda ainda precisa recusar. Um take removido é um
# range inteiro; os mais curtos nos projetos do usuário passam de 1 segundo.
FPS = 30
TAKE_MAIS_CURTO_F = 33  # ~1,1s


def test_todos_os_casos_reais_passam():
    """Nenhum projeto legítimo do usuário pode ser recusado.

    Este é o teste que o modelo linear reprovava: `(5, 9)` existe no disco e
    `2 + 0,8·5 = 6` o recusava por 3 quadros.
    """
    recusados = [(n, d) for n, d in MEDIDOS if d > tolerancia_de_quadros(n)]
    assert not recusados, recusados


def test_o_caso_que_reprovava_o_modelo_linear():
    """Ancorado no par exato, para que trocar a fórmula por outra linear
    'só um pouco maior' não passe calado."""
    assert tolerancia_de_quadros(5) >= 9


def test_sobra_margem_de_guarda_em_todo_projeto():
    """Uma guarda encostada no pior caso medido não é guarda — o próximo
    projeto com uma emenda a mais volta a ser recusado."""
    apertados = [(n, d, tolerancia_de_quadros(n)) for n, d in MEDIDOS
                 if tolerancia_de_quadros(n) - d < 3]
    assert not apertados, apertados


def test_a_folga_nunca_engole_um_take_inteiro():
    """A guarda existe para pegar o mapa de OUTRO corte, que difere pelo
    tamanho de um range. Se a folga passar do menor take, ela para de pegar.

    É este teste que o `2 + 2,0n` (linear que aceitaria todos os 128)
    reprovava: 78 quadros de folga num projeto de 38 emendas.
    """
    for n, _ in MEDIDOS:
        assert tolerancia_de_quadros(n) < TAKE_MAIS_CURTO_F + 1, (n, tolerancia_de_quadros(n))


def test_projeto_de_um_range_ainda_tem_folga_minima():
    assert tolerancia_de_quadros(0) >= 2
    assert tolerancia_de_quadros(1) >= 2


def test_a_folga_cresce_com_as_emendas_mas_desacelera():
    """A deriva é por emenda, então a folga tem de crescer. Mas cresce como
    raiz: dobrar as emendas não pode dobrar a folga, senão volta o problema
    do linear nos projetos longos."""
    valores = [tolerancia_de_quadros(n) for n in (1, 5, 15, 38)]
    assert valores == sorted(valores), valores
    assert valores[-1] > valores[0], valores
    assert tolerancia_de_quadros(38) < 2 * tolerancia_de_quadros(19), (
        "a folga está crescendo em linha com as emendas de novo"
    )


def test_as_duas_guardas_usam_a_mesma_conta():
    """Havia duas cópias do `> 1` — a do mapa antigo e a do cut temporário."""
    s = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")
    assert s.count("tolerancia_de_quadros(") == 3, "definição + os dois usos"
    assert "abs(predicted - cut_frames) > 1" not in s
    assert "abs(int(actual) - predicted) > 1" not in s
