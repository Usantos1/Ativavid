# -*- coding: utf-8 -*-
"""5.0.68: parar de transcrever o corte só porque o vídeo acaba em silêncio.

O pipeline monta as legendas remapeando o transcript da fonte pelo EDL —
de graça, sem rede. Se a cobertura parecesse fraca, ele transcrevia o corte
inteiro. A regra de "fraca" era: a última legenda tem de terminar a menos
de 0,45 s do fim do vídeo.

Só que um vídeo que acaba num cartão de CTA, num b-roll ou numa pausa
termina em silêncio DE PROPÓSITO. Medido nos jobs reais:

    29 de 133 jobs desde 01/09 (22%) caíram nesse fallback
    em TODOS os 29 a transcrição devolveu as MESMAS palavras do remap
      (razão mediana 1,00, faixa 0,91–1,09; fim a −0,02 s de diferença)
    custo: CAPTIONS 27,8 s contra 0,4 s
    job inteiro: 170,4 s contra 83,4 s — o dobro, para não mudar nada

Em 332 projetos do disco só DOIS tiveram remap de fato incompleto (47% e
67% das palavras). Nos dois a cauda sem legenda foi 10,41 s (26,7%) e
9,92 s (30,3%). Nos 29 falsos alarmes ela nunca passou de 8,05 s.

Daí a regra dupla — cauda maior que 6 s **e** que 15% do vídeo. Pega os
dois remaps ruins e deixa passar 28 dos 29 falsos alarmes. Os limiares são
os mais baixos que ainda pegam os dois: errar para o lado de transcrever
custa 28 s, errar para o outro entrega vídeo com legenda faltando no fim.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from captions_for_remotion import (  # noqa: E402
    CAUDA_SEM_LEGENDA_FRACAO, CAUDA_SEM_LEGENDA_S, captions_coverage_ok,
    cauda_sem_legenda,
)

RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def caps(fim_ms: int) -> list[dict]:
    return [{"startMs": 0, "endMs": fim_ms, "text": "palavra"}]


def test_a_cauda_e_medida_nos_dois_sentidos():
    assert cauda_sem_legenda(caps(18_500), 20.0) == (1.5, 0.075)
    assert cauda_sem_legenda([], 20.0) == (0.0, 0.0)
    assert cauda_sem_legenda(caps(1000), 0) == (0.0, 0.0)
    # legenda que passa do fim do video nao vira cauda negativa
    assert cauda_sem_legenda(caps(21_000), 20.0) == (0.0, 0.0)


def test_o_silencio_normal_do_fim_nao_manda_transcrever():
    """Os 29 casos reais: cauda mediana de 1,47 s, maxima de 8,05 s."""
    assert captions_coverage_ok(caps(18_500), 20.0), "1,5 s de sobra e normal"
    assert captions_coverage_ok(caps(52_000), 60.0), "8 s em 60 s ainda e 13%"
    assert captions_coverage_ok(caps(14_000), 15.5), "vídeo curto que acaba no ar"


def test_os_DOIS_remaps_ruins_de_verdade_continuam_pegos():
    """Os únicos dois em 332 projetos: 10,41 s de 39,0 s e 9,92 s de 32,7 s."""
    assert not captions_coverage_ok(caps(28_590), 39.0)
    assert not captions_coverage_ok(caps(22_780), 32.7)


def test_precisa_dos_dois_criterios():
    """Um só não separa: entre os falsos alarmes há cauda de 8 s e há cauda
    de 33% — o que não há é as duas coisas juntas."""
    # grande em segundos, pequena em fracao (video longo)
    assert captions_coverage_ok(caps(113_000), 120.0), "7 s em 120 s"
    # grande em fracao, pequena em segundos (video curto)
    assert captions_coverage_ok(caps(4_000), 6.0), "2 s em 6 s"
    assert CAUDA_SEM_LEGENDA_S == 6.0 and CAUDA_SEM_LEGENDA_FRACAO == 0.15


def test_sem_legenda_nenhuma_continua_reprovando():
    assert not captions_coverage_ok([], 20.0)
    assert not captions_coverage_ok(caps(0), 0)


def test_a_regra_antiga_continua_disponivel():
    """Quem quiser a conta de antes pede por `slack_end` — o parametro nao
    sumiu, so deixou de ser o padrao."""
    assert not captions_coverage_ok(caps(18_500), 20.0, slack_end=0.45)
    assert captions_coverage_ok(caps(19_700), 20.0, slack_end=0.45)


def test_a_decisao_fica_no_log():
    """Transcrever o corte e a decisao mais cara desta fase: o numero que a
    motivou precisa estar no log do job, nao so na cabeca de quem leu."""
    assert "cauda sem legenda {sobra:.2f}s ({fracao:.0%})" in RF
    assert "from captions_for_remotion import (  # type: ignore" in RF
    assert "cauda_sem_legenda," in RF
