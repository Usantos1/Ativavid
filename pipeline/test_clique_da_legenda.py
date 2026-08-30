# -*- coding: utf-8 -*-
""""poderia ser cliques de digitando leves nao tantos whosh" (30/08).

O video das 19:12 tem 42 legendas em 33 segundos — uma a cada 0,8s. Cada
uma tocava o arquivo mais longo E mais alto da pasta:

    caption-click.mp3   0,406 s   pico -0,8 dBFS
    click.mp3           0,030 s   pico -4,9 dBFS

Quase meio segundo, quase no teto, 42 vezes. A legenda empilhada passa a
tocar o tique de 30ms; a palavra unica (SOLO) continua no som cheio,
porque e rara e e o ponto.

Os dois motores tem de concordar — o proprio renderiza 5x mais rapido e
e o que sai na maioria dos videos, mas o Remotion e a referencia.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
TSX = (REPO / "assets" / "shortform" / "src" / "StackedCaptions.tsx").read_text(
    encoding="utf-8")
SFX = REPO / "assets" / "shortform" / "public" / "sfx"


def test_o_tique_existe_na_pasta_do_template():
    """Sem o arquivo, a legenda ficaria muda nos dois motores."""
    assert (SFX / "click.mp3").is_file()


def test_o_tique_e_MESMO_mais_curto_e_mais_baixo():
    """O numero e o argumento inteiro — se um dia trocarem o arquivo por
    outro tao longo quanto, a queixa volta e o teste nao veria."""
    sys.path.insert(0, str(REPO))
    from app.broll_library import _dur_seg, _pico_dbfs

    curto = _dur_seg(SFX / "click.mp3")
    cheio = _dur_seg(SFX / "caption-click.mp3")
    assert curto is not None and cheio is not None
    assert curto < 0.10, curto
    assert cheio / curto > 5, (cheio, curto)
    pc, pf = _pico_dbfs(SFX / "click.mp3"), _pico_dbfs(SFX / "caption-click.mp3")
    if pc is not None and pf is not None:
        assert pc < pf, (pc, pf)


def test_o_motor_proprio_toca_o_tique_no_empilhado():
    i = RP.index('"caption-click.mp3" if solo else self.stack_click')
    assert i > 0
    j = RP.index("self.stack_click = ")
    assert 'or "click.mp3"' in RP[j:j + 120]


def test_o_template_toca_o_mesmo():
    assert "const STACK_CLICK_FILE = SFX.stackClickFile ?? 'click.mp3';" in TSX
    assert "staticFile(`sfx/${STACK_CLICK_FILE}`)" in TSX


def test_a_palavra_unica_continua_no_som_cheio():
    """SOLO_BIG/SOLO_OUTLINE sao o acento raro — no video da queixa foram
    0 de 42. Trocar o som deles seria mexer no que ninguem reclamou."""
    i = RP.index('"caption-click.mp3" if solo else')
    assert "self.click_vol if solo else self.stack_vol" in RP[i:i + 200]
    assert "<Audio src={staticFile('sfx/caption-click.mp3')} volume={CLICK_VOL} />" in TSX


def test_o_knob_tem_o_mesmo_nome_nos_dois():
    assert "SFX.stackClickFile" in TSX
    assert '"stackClickFile"' in RP
