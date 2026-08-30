# -*- coding: utf-8 -*-
"""Efeito que já vem distorcido não entra no vídeo.

A 4.10 abriu 100 dos 234 efeitos do usuário para o vídeo. Medindo o que
isso significa no som:

    do app   whoosh.mp3        pico -2,3 dBFS
    dele     swoosh--001.mp3   pico -1,2
    dele     swoosh--002.mp3   pico **0,0**   (+4,9 de pico real)
    dele     swoosh--003.mp3   pico -1,8

**40 dos 233 efeitos dele (17%) já chegam no teto.** A troca pegava o mais
recente da categoria — se calhasse de ser um desses, a distorção entrava
em todo vídeo, por cima da voz. E ela já vem dentro do arquivo: abaixar o
volume não a tira.

Normalizar o nível foi tentado e descartado: a ida e volta por MP3 não
deixa cravar o pico do resultado, e prometer um ajuste que não dá para
verificar é pior que escolher melhor.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

BL = (REPO / "app" / "broll_library.py").read_text(encoding="utf-8")


def test_a_troca_pula_o_que_estoura():
    i = BL.index("def aplicar_sfx_do_usuario(")
    corpo = BL[i:i + 2200]
    assert "not _ja_estoura(f)" in corpo
    assert "escolhido is None" in corpo


def test_sem_candidato_limpo_fica_o_som_do_app():
    i = BL.index("def aplicar_sfx_do_usuario(")
    corpo = BL[i:i + 2200]
    j = corpo.index("escolhido is None")
    assert "fica o som do app" in corpo[j:j + 400]
    assert "continue" in corpo[j:j + 400]


def test_nao_acusa_quando_nao_conseguiu_medir():
    """Recusar por falta de medida seria pior que o som."""
    i = BL.index("def _ja_estoura(")
    corpo = BL[i:BL.index("\ndef ", i + 10)]
    assert "pico is not None" in corpo


def test_o_limiar_e_o_teto():
    i = BL.index("def _ja_estoura(")
    corpo = BL[i:BL.index("\ndef ", i + 10)]
    assert "-0.1" in corpo


def test_medir_o_pico_nunca_levanta(tmp_path):
    from app.broll_library import _pico_dbfs

    assert _pico_dbfs(tmp_path / "nao-existe.mp3") is None
    ruim = tmp_path / "ruim.mp3"
    ruim.write_bytes(b"isto nao e audio")
    assert _pico_dbfs(ruim) is None
