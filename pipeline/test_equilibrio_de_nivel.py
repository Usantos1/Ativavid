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


def _ranges(*ganhos, fonte="A"):
    return [{"start": float(i), "end": i + 0.9, "beat": f"B{i}",
             "source": fonte, "gain_db": float(g)}
            for i, g in enumerate(ganhos)]


def _vozes(**por_fonte):
    """{"A": _voz(...)} — o formato que o pipeline passa desde a 3.24."""
    return dict(por_fonte)


def test_quem_ficou_para_tras_recebe_complemento():
    # tres trechos em -27 com +7 de reforco (viram -20) e um em -28 sem
    # nada: ele fica 8 dB atras SEM ter sido considerado baixo na fonte.
    voz = _voz(-27, -27, -27, -28)
    rs = _ranges(7, 7, 7, 0)
    assert rf._equilibrar_ganhos(rs, {"A": voz}) == 1
    # sobe ate a mediana (-20) menos a folga de 1,5 -> +6,5 dB
    assert rs[3]["gain_db"] == 6.5, rs[3]["gain_db"]
    assert [r["gain_db"] for r in rs[:3]] == [7.0, 7.0, 7.0], "mexeu em quem estava bem"


def test_quem_ja_esta_no_nivel_nao_e_tocado():
    voz = _voz(-20, -20, -20, -20)
    rs = _ranges(0, 0, 0, 0)
    assert rf._equilibrar_ganhos(rs, {"A": voz}) == 0
    assert all(r["gain_db"] == 0 for r in rs)


def test_diferenca_pequena_nao_mexe():
    """3 dB e variacao normal de frase para frase — mexer ali seria achatar
    a interpretacao do locutor."""
    voz = _voz(-20, -20, -20, -23)   # 3 dB abaixo: dentro do normal
    rs = _ranges(0, 0, 0, 0)
    assert rf._equilibrar_ganhos(rs, {"A": voz}) == 0


def test_nunca_passa_do_teto_de_12db():
    """Acima de +12 dB sobe o ruido da sala junto com a voz — teto que o
    proprio voice_levels ja respeita."""
    voz = _voz(-20, -20, -20, -45)
    rs = _ranges(0, 0, 0, 0)
    rf._equilibrar_ganhos(rs, {"A": voz})
    assert rs[3]["gain_db"] == 12.0


def test_nao_abaixa_ninguem():
    """So SOBE: abaixar mexeria no som que o usuario ja aprovou de ouvido."""
    voz = _voz(-20, -20, -20, -5)
    rs = _ranges(0, 0, 0, 0)
    rf._equilibrar_ganhos(rs, {"A": voz})
    assert rs[3]["gain_db"] == 0


def test_sem_analise_de_voz_nao_faz_nada():
    rs = _ranges(0, 0, 0, 0)
    assert rf._equilibrar_ganhos(rs, {"A": {}}) == 0
    assert rf._equilibrar_ganhos(rs, {"A": {"phrases": []}}) == 0


def test_corte_curto_demais_nao_tem_mediana_confiavel():
    voz = _voz(-20, -30)
    rs = _ranges(0, 0)
    assert rf._equilibrar_ganhos(rs, {"A": voz}) == 0


def test_o_pipeline_equilibra_depois_de_decidir_os_trechos():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("_equilibrar_ganhos(ranges, vozes_por_fonte)")
    assert i > 0, "o passo nao esta no fluxo"
    assert s[:i].rfind("ranges = all_ranges") > 0
    assert 'intent_mode not in ("intact",)' in s[i - 500:i], (
        "em Sem cortes nao ha trechos para equilibrar")


def test_o_nivelamento_nao_engole_o_bloco_de_varias_fontes():
    """A 3.18 inseriu o `if` do nivelamento logo apos `ranges = all_ranges`
    e, por indentacao, ABSORVEU o bloco do multi-take: todo render de fonte
    unica passou a sobrescrever llm_meta com "multi_take_concat" — dai o
    guard_ranges voltava a mexer no corte que o usuario salvou no preview e
    a headline era repedida a cada render. E estrutura, nao estilo."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.index('llm_meta = {"ok": True, "backend": "multi_take_concat"')
    linha = s[s.rindex(chr(10), 0, i) + 1:i]
    assert len(linha) - len(linha.lstrip()) == 8, (
        "o bloco do multi-take saiu de dentro do else das "
        "varias fontes")
    j = s.index("_equilibrar_ganhos(ranges, vozes_por_fonte)")
    assert j > i, "o nivelamento tem de vir depois, fora do else"
    bloco = s[s.rindex("if ranges and intent_mode", 0, j):j + 200]
    assert "multi_take_concat" not in bloco and "headline_apenas" not in bloco


def test_cada_take_e_medido_contra_a_propria_voz():
    """Com varios takes os tempos de cada um comecam do zero. Medir o take 2
    contra as frases do take 1 comparava gravacoes diferentes que so por
    acaso caem no mesmo minuto — e o ganho ia para o trecho errado."""
    vozes = {"A": _voz(-20, -20, -20, -20), "B": _voz(-30, -30, -30, -30)}
    rs = _ranges(0, 0, 0, 0, fonte="A") + _ranges(0, 0, 0, 0, fonte="B")
    assert rf._equilibrar_ganhos(rs, vozes) == 0, (
        "take inteiro mais baixo e escolha de gravacao, "
        "nao desnivel interno")
    assert all(r["gain_db"] == 0 for r in rs)


def test_desnivel_dentro_do_take_2_e_corrigido_no_take_2():
    vozes = {"A": _voz(-20, -20, -20, -20), "B": _voz(-30, -30, -30, -38)}
    rs = _ranges(0, 0, 0, 0, fonte="A") + _ranges(0, 0, 0, 0, fonte="B")
    assert rf._equilibrar_ganhos(rs, vozes) == 1
    assert [r["gain_db"] for r in rs[:4]] == [0, 0, 0, 0], "mexeu no take errado"
    assert rs[7]["gain_db"] > 0
