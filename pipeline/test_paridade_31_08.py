# -*- coding: utf-8 -*-
"""Paridade entre os dois motores — consertos da auditoria de 31/08.

A auditoria varreu os 15 .tsx do template contra o render_proprio, feature
por feature, e achou divergências de contrato: o mesmo vídeo saía DIFERENTE
conforme o motor que o desenhasse. Este arquivo trava cada alinhamento.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
MAIN = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
OVERLAY = (REPO / "assets" / "overlay-proto" / "Overlay.tsx").read_text(encoding="utf-8")
OP = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")


def _ed(hook=None, caps=None, extra=None):
    d = {"width": 1080, "height": 1920, "fps": 30, "durationSec": 4,
         "hook": hook or {"enabled": False},
         "captions": caps or {"enabled": False},
         "endCard": {"enabled": False}, "soundtrack": {"enabled": False},
         "transitions": [], "inserts": [], "behind": [],
         "camera": {"enabled": False, "zooms": [1]}}
    d.update(extra or {})
    return d


def _render(tmp_path, **kw):
    from app.render_proprio import Renderizador

    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True, exist_ok=True)
    return Renderizador(public, _ed(**kw), frames=120, fps=30)


# ---- E1: a rede de seguranca nao pode perder camadas ----------------------

def test_overlay_fallback_monta_emoji_e_sfx_manuais():
    """Main monta EmojisManuais e SfxManual; o Overlay (fallback) nao
    montava NENHUM — emoji e som postos a mao sumiam do video, calado,
    sempre que a rede de seguranca entrava. Mesma familia do bug historico
    da bolha-que-virava-karaoke (dispatcher proprio divergindo)."""
    assert "<SfxManual />" in OVERLAY and "<EmojisManuais />" in OVERLAY
    assert "SfxManual" in OVERLAY.split("from './Main'")[0]
    # e a injecao de export cobre projeto scaffoldado antes da 4.50
    i = OP.index('"BubbleCaptions"')
    assert "SfxManual" in OP[i:i + 120] and "EmojisManuais" in OP[i:i + 120]
    assert "export const SfxManual" in MAIN
    assert "export const EmojisManuais" in MAIN


# ---- E2: a entrada escolhida acontece nos dois motores --------------------

def test_pop_e_deslizar_existem_no_motor(tmp_path):
    r = _render(tmp_path, hook={"enabled": True, "endSec": 3,
                                "style": "blocos", "animation": "pop",
                                "lines": ["Primeira", "Linha"]})
    pops = [p for p in r.camadas[0].palavras if p.janela is not None]
    assert len(pops) >= 10, "pop sem estagios de escala"
    tams = {p.alpha.shape for p in pops}
    assert len(tams) > 3, "estagios todos do mesmo tamanho = nao ha escala"

    r2 = _render(tmp_path, hook={"enabled": True, "endSec": 3,
                                 "style": "blocos", "animation": "deslizar",
                                 "lines": ["Primeira", "Linha"]})
    assert all(p.desliza == -56.0 for p in r2.camadas[0].palavras)

    r3 = _render(tmp_path, hook={"enabled": True, "endSec": 3,
                                 "style": "blocos", "lines": ["A", "B"]})
    assert all(p.desliza == 0.0 and p.janela is None
               for p in r3.camadas[0].palavras), "padrao nao anima"


# ---- E3/E4: pilula e carimbo ---------------------------------------------

def test_pilula_tem_a_bolinha_do_accent(tmp_path):
    r = _render(tmp_path, hook={"enabled": True, "endSec": 3,
                                "style": "pilula", "accent": "#ff5200",
                                "lines": ["Oferta do dia"]})
    pals = r.camadas[0].palavras
    assert len(pals) >= 2, "capsula + bolinha"
    bola = min(pals, key=lambda p: p.alpha.shape[0] * p.alpha.shape[1])
    h, w = bola.alpha.shape
    assert abs(h - w) <= 2, "a bolinha e redonda"
    # cor do accent, nao a tinta do texto
    vis = bola.alpha > 0.5
    assert vis.any() and bola.rgb[vis][:, 0].mean() > 200


def test_carimbo_bate_com_o_template():
    i = RP.index('if estilo == "carimbo"')
    bloco = RP[i:i + 1400]
    assert 'fundo=("#0a0a0c", 0.25)' in bloco, "rgba(10,10,12,.25) do template"
    assert "[(0, 4, 14, 0.45)]" in bloco, "text-shadow 0 4px 14px .45"
    assert "round(tam * 0.4), round(tam * 0.18)" in bloco, "padding .18/.4em"
    assert "_slam_na_camada" in bloco, "a entrada de 1,9x -> 1x"
    j = RP.index("def _slam_na_camada")
    assert "1.9 - 0.9" in RP[j:j + 500]


# ---- E5/E6: pesos que o Chrome resolve ------------------------------------

def test_pesos_da_headline_seguem_a_medicao():
    """Main.tsx carrega Poppins 400/600/900. MEDIDO na varredura (tinta
    contra o Remotion): 800 -> Black 900 (0,997-1,03 na faixa); o 700 da
    pilula mediu melhor no SemiBold (1,065) que no Black (1,103) — pixels
    valem mais que a regra de casamento do CSS na teoria."""
    i = RP.index("HL_FONTE = ")
    linha = RP[i:i + 80]
    assert "800: 4, 900: 4" in linha, "800 tem de ser Black, como o Chrome"
    assert "600: 7, 700: 7" in linha, "600/700 medidos no SemiBold"


def test_fonte_de_marca_nao_perde_o_900():
    """`fonte(4, tam)` sem peso deixa fonte VARIAVEL (Inter/Montserrat) no
    peso default ~400; o Poppins estatico escondia o furo. Todos os pontos
    de impacto e contador passam 900 explicito."""
    sem_peso = [ln.strip() for ln in RP.splitlines()
                if "self.fonte(4," in ln
                and "900" not in ln and "marca=None" not in ln]
    assert not sem_peso, sem_peso


# ---- E7/E8: bolha e scatter ----------------------------------------------

def test_bolha_recusa_janelas_como_o_karaoke():
    from app.render_proprio import motivo_nao_suportado

    ed = _ed(caps={"enabled": True, "style": "bolha",
                   "windows": [{"fromMs": 0, "toMs": 1000}]})
    assert motivo_nao_suportado(ed, Path(".")) is not None


def test_bolha_quebra_na_largura_do_template():
    i = RP.index("interno = safe_w")
    assert "interno = safe_w\n" in RP[i:i + 40], \
        "maxWidth do template e content-box: quebra em safe_w CHEIO"


def test_scatter_italico_usa_o_indice_da_linha():
    i = RP.index("italico = eh_hi and self._hash_det(li * 7 + k)")
    assert i > 0, "com o indice do grupo, a palavra italica era outra"


# ---- E9/E10: cartao final e miudezas -------------------------------------

def test_endcard_desenha_todas_as_linhas(tmp_path):
    from app.render_proprio import Renderizador

    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True)
    ed = _ed(extra={"endCard": {
        "enabled": True, "lastSec": 2.0,
        "lines": ["SIGA @lojaprimecamp", "link na bio", "terceira linha"]}})
    r = Renderizador(public, ed, frames=120, fps=30)
    textos = [c for c in r.camadas if c.palavras]
    assert textos, "endcard nao montou"
    # 3 linhas de texto (o logo pode ou nao existir)
    assert len(textos[-1].palavras) >= 3, "a 3a linha sumia com o [:2]"


def test_miudezas_alinhadas_ao_template():
    assert "off = max(4, round(tam * 0.07))" in RP          # estilo sombra
    assert RP.count("[(0, 6, 18, 0.55)]") >= 2               # pergunta
    assert "[(0, 14, 34, 0.45)], k=BLUR_K" in RP             # ARTE drop-shadow
    assert "opac=min(1.0, t * 1.4)" in RP                    # contador
    i = RP.index("# enter=0: no template o emoji manual aparece INSTANTANEO")
    assert "enter=0" in RP[i:i + 120]
    assert "(self.w - larg_b) / 2 + 15" not in RP             # manchete centrada
