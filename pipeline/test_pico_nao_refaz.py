# -*- coding: utf-8 -*-
"""Pico 0,1 dB acima do alvo não vale refazer o vídeo inteiro.

Medido nos 174 vídeos do usuário com pico registrado:

    mediana                 -1,40 dBTP   (saudável)
    acima de -1,0            14 vídeos
    entre -0,99 e -0,50      13 desses    → no máximo 0,49 dB de excesso
    acima de -0,50            1 vídeo

Seis dos 14 refizeram o vídeo inteiro no Remotion por causa disso (484s,
533s, 207s… só de render) — e o pico registrado nesses seis é o FINAL:
continuou acima de -1,0 depois do retrabalho. A queda custou caro e não
corrigiu o que a motivou.

O limite de -0,5 sai dessa distribuição: cobre 13 dos 14 casos reais e
deixa de fora o único que estava mesmo alto (-0,30).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def test_o_limite_existe_e_e_o_medido():
    from pipeline.run_fast import TRUE_PEAK_TOLERADO

    assert TRUE_PEAK_TOLERADO == -0.5


def test_excesso_pequeno_entrega_o_video():
    i = RUN.index('tp = au.get("truePeakDb")')
    bloco = RUN[i:i + 900]
    assert "if float(tp) <= TRUE_PEAK_TOLERADO:" in bloco
    assert '_RENDER_META["truePeakAcima"] = float(tp)' in bloco
    # e NAO devolve veredito nesse ramo
    ramo = bloco[bloco.index("if float(tp) <= TRUE_PEAK_TOLERADO:"):]
    ramo = ramo[:ramo.index("else:")]
    assert "return" not in ramo, ramo


def test_excesso_grande_continua_derrubando():
    """-0,30 dBTP (1 dos 174) nao e arredondamento de medicao."""
    i = RUN.index("if float(tp) <= TRUE_PEAK_TOLERADO:")
    bloco = RUN[i:i + 600]
    assert "else:" in bloco
    assert 'return f"TRUE_PEAK {tp}>-1.0"' in bloco


def test_o_conserto_de_audio_continua_vindo_antes():
    """`garantir_true_peak` renormaliza so o audio — barato. A folga e
    para o que SOBRA depois dele, nao no lugar dele."""
    i = RUN.index("au = garantir_true_peak(final)")
    j = RUN.index("if float(tp) <= TRUE_PEAK_TOLERADO:")
    assert i < j


def test_o_excesso_tolerado_fica_registrado():
    """Entregar calado seria esconder; o numero viaja no timing.json."""
    assert 'payload["truePeakAcima"] = _RENDER_META["truePeakAcima"]' in RUN


def test_a_faixa_cobre_os_casos_reais_e_nao_o_alto():
    """Os numeros que motivaram o limite, presos ao teste."""
    from pipeline.run_fast import TRUE_PEAK_TOLERADO

    reais = [-0.70, -0.70, -0.80, -0.80, -0.80, -0.80, -0.80,
             -0.90, -0.90, -0.90, -0.90, -0.90, -0.90]
    assert all(tp <= TRUE_PEAK_TOLERADO for tp in reais)
    assert -0.30 > TRUE_PEAK_TOLERADO, "o caso alto tem de continuar caindo"
