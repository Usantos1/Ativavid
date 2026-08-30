# -*- coding: utf-8 -*-
"""A varredura acusa defeito de FORMA, não só de área.

A razão de tinta é cega para forma: o `carimbo` saiu **espelhado** — girado
ao contrário do template — com a tinta em 1,057, dentro da faixa saudável.
Quem denunciou foi a diferença média de alfa: **107 de 255**, e só porque
alguém olhou o número na mão.

Distribuição medida no catálogo inteiro (30/08), já com o carimbo
corrigido:

    camadas de layout   0,0 – 0,6
    manchetes           1,8 – 59,8
    legendas           16,9 – 73,0

O maior saudável é 73. O teto de 80 deixa folga e não perde o próximo
espelhamento.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

VD = (REPO / "tools" / "varrer_desenho.py").read_text(encoding="utf-8")


def test_o_teto_existe_e_e_folgado():
    m = re.search(r"TETO_ALFA = (\d+(?:\.\d+)?)", VD)
    assert m, "sem teto de forma"
    teto = float(m.group(1))
    assert 73 < teto <= 100, teto


def test_o_veredito_olha_os_dois_numeros():
    i = VD.index("ok = ")
    linha = VD[i:VD.index("\n", i)]
    assert "FAIXA[0]" in linha and "TETO_ALFA" in linha


def test_a_saida_diz_qual_dos_dois_falhou():
    """"FORA" por área e "FORA (forma)" pedem investigações diferentes."""
    assert '"   <- FORA (forma)"' in VD


def test_o_numero_que_pegou_o_carimbo_esta_documentado():
    assert "107" in VD and "1,057" in VD
