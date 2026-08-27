# -*- coding: utf-8 -*-
"""Trechos que nao receberam reforco nao podem ficar para tras.

O voice_levels reforca so quem esta >= 5 dB abaixo da mediana da FONTE.
Com +7 dB nos vizinhos, um trecho intocado passa a soar 6-8 dB abaixo do
resto — o reforco CRIA o desnivel. Medido em 27/08: 6 de 10 videos tinham
um trecho assim, e no vídeo checado a fundo os marcados eram exatamente os
de ganho 0, com fala cobrindo 90-100% do trecho (nao era artefato de
medida). Render real com o conserto: pior desnivel -6,3 dB -> -2,1 dB e
verify_flags 2 -> 0.
"""
from pathlib import Path

import pipeline.run_fast as rf

RAIZ = Path(__file__).resolve().parent.parent


def _voz(*niveis):
    """Uma frase por segundo, com o nivel pedido."""
    return {"phrases": [{"start": float(i), "end": i + 0.9,
                         "level_db": float(n)}
                        for i, n in enumerate(niveis)]}


def _ranges(*ganhos):
    return [{"start": float(i), "end": i + 0.9, "beat": f"B{i}",
             "gain_db": float(g)} for i, g in enumerate(ganhos)]


def test_quem_ficou_para_tras_recebe_complemento():
    # tres trechos em -27 com +7 de reforco (viram -20) e um em -28 sem
    # nada: ele fica 8 dB atras SEM ter sido considerado baixo na fonte.
    voz = _voz(-27, -27, -27, -28)
    rs = _ranges(7, 7, 7, 0)
    assert rf._equilibrar_ganhos(rs, voz) == 1
    # sobe ate a mediana (-20) menos a folga de 1,5 -> +6,5 dB
    assert rs[3]["gain_db"] == 6.5, rs[3]["gain_db"]
    assert [r["gain_db"] for r in rs[:3]] == [7.0, 7.0, 7.0], "mexeu em quem estava bem"


def test_quem_ja_esta_no_nivel_nao_e_tocado():
    voz = _voz(-20, -20, -20, -20)
    rs = _ranges(0, 0, 0, 0)
    assert rf._equilibrar_ganhos(rs, voz) == 0
    assert all(r["gain_db"] == 0 for r in rs)


def test_diferenca_pequena_nao_mexe():
    """3 dB e variacao normal de frase para frase — mexer ali seria achatar
    a interpretacao do locutor."""
    voz = _voz(-20, -20, -20, -23)   # 3 dB abaixo: dentro do normal
    rs = _ranges(0, 0, 0, 0)
    assert rf._equilibrar_ganhos(rs, voz) == 0


def test_nunca_passa_do_teto_de_12db():
    """Acima de +12 dB sobe o ruido da sala junto com a voz — teto que o
    proprio voice_levels ja respeita."""
    voz = _voz(-20, -20, -20, -45)
    rs = _ranges(0, 0, 0, 0)
    rf._equilibrar_ganhos(rs, voz)
    assert rs[3]["gain_db"] == 12.0


def test_nao_abaixa_ninguem():
    """So SOBE: abaixar mexeria no som que o usuario ja aprovou de ouvido."""
    voz = _voz(-20, -20, -20, -5)
    rs = _ranges(0, 0, 0, 0)
    rf._equilibrar_ganhos(rs, voz)
    assert rs[3]["gain_db"] == 0


def test_sem_analise_de_voz_nao_faz_nada():
    rs = _ranges(0, 0, 0, 0)
    assert rf._equilibrar_ganhos(rs, {}) == 0
    assert rf._equilibrar_ganhos(rs, {"phrases": []}) == 0


def test_corte_curto_demais_nao_tem_mediana_confiavel():
    voz = _voz(-20, -30)
    rs = _ranges(0, 0)
    assert rf._equilibrar_ganhos(rs, voz) == 0


def test_o_pipeline_equilibra_depois_de_decidir_os_trechos():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("_equilibrar_ganhos(ranges, voice)")
    assert i > 0, "o passo nao esta no fluxo"
    antes = s[:i]
    assert antes.rfind("ranges = all_ranges") > 0
    assert 'intent_mode not in ("intact",)' in s[i - 300:i], \
        "em Sem cortes nao ha trechos para equilibrar"
