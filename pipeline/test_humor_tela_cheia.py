# -*- coding: utf-8 -*-
"""Inserção de humor em TELA CHEIA, e no máximo uma a cada 12 segundos.

As duas coisas saíram de um render de verdade (30/08, material do
usuário, ambiente isolado):

    teste 1   2 inserções em 9,6s   cartão 780x500 no alto
    teste 2   2 inserções em 34,5s  tela cheia (w=1 h=1 x=.5 y=.5)

1. "não quero tipo B roll, quero em tela cheia a inserção". A geometria já
   aceitava (`w`/`h` em fração do quadro, nos DOIS motores) — o b-roll
   automático é que nunca pedia. Para humor a reação tem de tomar a tela:
   num cartão de 780x500 ela vira miniatura e a piada não acontece.

2. `_mode_count` conta pelo MODO de b-roll e nunca olhou a duração: 2
   inserções em 9,6s é uma a cada 4,8s. Teto de uma a cada 12s.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")


def test_o_clipe_de_humor_pede_a_tela_inteira():
    i = RUN.index('geo = ({"w": 1.0, "h": 1.0, "x": 0.5, "y": 0.5}')
    bloco = RUN[i:i + 400]
    assert "if humor_com_acervo else {}" in bloco, (
        "tela cheia so no humor: o cartao continua servindo para ilustrar")
    # e a geometria entra no insert
    assert "**geo," in RUN[i:i + 700]


def test_os_dois_motores_leem_a_geometria():
    """Se so um lesse, o video mudaria de aparencia conforme o caminho."""
    i = RP.index("def geometria_do_insert(")
    bloco = RP[i:RP.index("\n# ", i)]
    for chave in ('"w"', '"h"', '"x"', '"y"'):
        assert chave in bloco, chave
    assert "w ?? size ?? CARD_W / 1080" in TSX
    assert "h ?? altPadrao" in TSX


def test_a_conta_de_quantos_olha_a_duracao():
    i = RUN.index("teto_tempo = max(1, int(duration // 12))")
    bloco = RUN[i:i + 400]
    assert "quantos = max(1, min(_mode_count(mode), teto_tempo))" in bloco


def test_a_matematica_do_teto():
    """Os numeros do caso real, presos ao teste."""
    def quantos(duracao, do_modo):
        return max(1, min(do_modo, max(1, int(duracao // 12))))

    assert quantos(9.6, 3) == 1, "o video do teste 1 nao podia levar 2"
    assert quantos(34.5, 3) == 2, "o do teste 2 levou 2, e ficou bem espacado"
    assert quantos(60, 3) == 3, "em video longo o teto nao segura nada"
    assert quantos(5, 3) == 1, "nunca zero: o minimo e uma"


def test_video_longo_nao_perde_insercao():
    """O teto existe para proteger video CURTO. Se ele mordesse os longos,
    seria menos b-roll onde o b-roll cabe."""
    i = RUN.index("teto_tempo = max(1, int(duration // 12))")
    bloco = RUN[i:i + 500]
    assert "min(_mode_count(mode), teto_tempo)" in bloco
    assert "//" in bloco and "12" in bloco
