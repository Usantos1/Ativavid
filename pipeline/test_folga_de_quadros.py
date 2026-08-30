# -*- coding: utf-8 -*-
"""Um quadro de diferença não pode custar um render inteiro.

TODAS as 15 quedas do motor rápido registradas nos projetos do usuário são
da mesma forma — `FRAMES N!=M` com 1 a 3 quadros de diferença:

    2362!=2364 · 860!=861 · 645!=646 · 1619!=1620
    1852!=1853 · 2548!=2550 · 3223!=3226 · 2320!=2322

E cada queda refaz o vídeo no Chrome, 3,3x mais lento (143 ms/quadro
contra 35,5). Nenhuma consertou nada: o vídeo já estava certo.

A incoerência estava dentro da própria função: a checagem de DURAÇÃO logo
abaixo aceitava 0,08s — que a 30 quadros são 2,4 quadros — enquanto a de
QUADROS exigia igualdade exata. Duas guardas sobre a mesma grandeza,
discordando.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FONTE = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")

# as diferenças reais, tiradas dos `canary.json` dos projetos
QUEDAS = ((2362, 2364), (860, 861), (645, 646), (1619, 1620),
          (1852, 1853), (2548, 2550), (3223, 3226), (2320, 2322))


def _folga(fps: float) -> int:
    return max(1, int(0.08 * fps))


def test_a_folga_sai_da_duracao_e_nao_de_um_numero_magico():
    i = FONTE.index('got = int(count_frames(final) or 0)')
    bloco = FONTE[i:i + 1600]
    assert "folga_f = max(1, int(0.08 * fps_tl))" in bloco
    assert "if abs(got - expected) > folga_f:" in bloco
    # a mesma constante 0,08 governa as duas checagens
    assert "abs(got_sec - exp_sec) > 0.08" in bloco
    # e a igualdade exata não pode voltar
    assert "if got != expected:" not in FONTE


def test_a_folga_salva_as_quedas_de_um_e_dois_quadros():
    folga = _folga(30.0)
    assert folga == 2
    salvas = [q for q in QUEDAS if abs(q[0] - q[1]) <= folga]
    assert len(salvas) == 7, [abs(a - b) for a, b in QUEDAS]


def test_o_que_a_guarda_existe_para_pegar_continua_pego():
    """Overlay truncado ou de outro corte difere por SEGUNDOS."""
    folga = _folga(30.0)
    for perdidos in (30, 90, 300):        # 1s, 3s, 10s
        assert perdidos > folga


def test_a_folga_acompanha_o_fps():
    """A 60 quadros por segundo, 0,08s são o dobro de quadros."""
    assert _folga(60.0) == 4
    assert _folga(24.0) == 1
    # e nunca some: um fps baixo não pode zerar a folga
    assert _folga(1.0) == 1
