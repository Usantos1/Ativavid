# -*- coding: utf-8 -*-
"""Acento e ç em QUALQUER fonte, e toda fonte com a mesma altura.

Pedido do usuário (01/09): "testando todas as fontes e legendas pra fazer
letras com acento e ç … todas as fontes deve ter a mesma altura".

Medido no catálogo inteiro (13 fontes, 01/09):
- nenhuma fonte embutida falta acento/ç — mas a fonte DELE (Integral DEMO)
  não tem NENHUM dos 26 (á…Ç): desenhava o carimbo DEMO no vídeo.
- alturas de caixa alta a 100px: 69-73 na maioria, Anton 86 (21% maior) —
  trocar de fonte mudava o tamanho visível da legenda.

Consertos:
- FALLBACK POR GLIFO no motor próprio (o Chrome já fazia pelo lado do
  template): glifo que falta sai na Poppins, alinhado pelo ascent.
- FATOR DE ALTURA no DADO (edit-data): os dois motores e o preview leem o
  mesmo número; a Anton entra com 0,83. Fonte "arquivo" é medida na hora.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "pipeline") not in sys.path:
    sys.path.insert(0, str(REPO / "pipeline"))
if str(REPO / "helpers") not in sys.path:
    sys.path.insert(0, str(REPO / "helpers"))

from app.render_proprio import FONT_FILE, FONTES, MARCA_FONTES, Renderizador  # noqa: E402

ACENTOS_PT = "áéíóúâêôãõàçüÁÉÍÓÚÂÊÔÃÕÀÇÜ"


def _r(tmp_path) -> Renderizador:
    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True, exist_ok=True)
    ed = {"width": 1080, "height": 1920, "fps": 30, "durationSec": 4,
          "hook": {"enabled": False}, "captions": {"enabled": False},
          "endCard": {"enabled": False}, "soundtrack": {"enabled": False},
          "transitions": [], "inserts": [], "behind": [],
          "camera": {"enabled": False, "zooms": [1]}}
    return Renderizador(public, ed, frames=60, fps=30)


def test_todas_as_fontes_embutidas_tem_acento_e_c(tmp_path):
    """Se uma fonte nova entrar no catalogo sem acento, este teste acusa
    ANTES de um cliente ver 'AÇÃO' virar caixinhas."""
    r = _r(tmp_path)
    arquivos = {arq for arq, _ in FONT_FILE.values()}
    arquivos |= {arq for arq, _ in MARCA_FONTES.values()}
    from PIL import ImageFont

    for arq in sorted(arquivos):
        f = ImageFont.truetype(str(FONTES / arq), 60)
        faltam = [ch for ch in ACENTOS_PT if r._glifo_falta(f, ch)]
        assert not faltam, f"{arq} sem {faltam}"


def test_deteccao_de_glifo_faltando(tmp_path):
    r = _r(tmp_path)
    from PIL import ImageFont

    f = ImageFont.truetype(str(FONTES / "Poppins-Black.ttf"), 60)
    assert r._glifo_falta(f, "ç") is False
    assert r._glifo_falta(f, "Ã") is False
    # tailandes nao existe na Poppins — e o "faltando" de verdade
    assert r._glifo_falta(f, "ก") is True


def test_glifo_que_falta_sai_na_reserva(tmp_path, monkeypatch):
    """A Integral DEMO do usuario nao tem NENHUM acento: sem o fallback, o
    video saia com o carimbo DEMO no lugar do Ç. Simula-se a falta na
    propria Poppins para nao depender da fonte licenciada dele."""
    r = _r(tmp_path)
    from PIL import ImageFont

    f = ImageFont.truetype(str(FONTES / "Poppins-Regular.ttf"), 80)
    normal = r._mascara(f, "AÇÃO")
    original = r._glifo_falta

    def _falta(fonte, ch):
        if ch in "ÇÃ" and getattr(fonte, "path", "").endswith("Poppins-Regular.ttf"):
            return True
        return original(fonte, ch)

    monkeypatch.setattr(r, "_glifo_falta", _falta)
    r._fontes.clear()
    com_reserva = r._mascara(f, "AÇÃO")
    assert com_reserva.sum() > 0.5 * normal.sum(), "o fallback nao desenhou nada"
    # a reserva e um arquivo DIFERENTE (peso/desenho distintos): as duas
    # mascaras nao podem ser identicas
    hmin = min(normal.shape[0], com_reserva.shape[0])
    wmin = min(normal.shape[1], com_reserva.shape[1])
    assert not np.array_equal(normal[:hmin, :wmin], com_reserva[:hmin, :wmin])


def test_fator_de_altura_do_catalogo():
    import run_fast as rf

    assert rf._fator_de_altura("anton", None) == 0.83
    assert rf._fator_de_altura("poppins", None) == 1.0
    assert rf._fator_de_altura("", None) == 1.0


def test_alturas_do_catalogo_ficam_na_faixa_com_o_fator():
    """A prova do pedido: com o fator aplicado, o H de TODA fonte do
    catalogo (no peso que o render usa) fica a ate 8% do H da Poppins."""
    from PIL import Image, ImageDraw, ImageFont

    import run_fast as rf

    def altura_H(arq, peso, fator):
        f = ImageFont.truetype(str(FONTES / arq), round(100 * fator))
        if peso:
            try:
                f.set_variation_by_axes([900 if peso is None else peso])
            except (OSError, AttributeError):
                pass
        img = Image.new("L", (160, 220), 0)
        ImageDraw.Draw(img).text((10, 40), "H", font=f, fill=255)
        arr = np.asarray(img)
        linhas = np.where(arr.max(axis=1) > 8)[0]
        return int(linhas[-1] - linhas[0] + 1)

    base = altura_H("Poppins-Black.ttf", None, 1.0)
    for fid, (arq, teto) in MARCA_FONTES.items():
        fator = rf._fator_de_altura(fid, None)
        h = altura_H(arq, teto, fator)
        assert abs(h - base) / base <= 0.08, \
            f"{fid}: H={h} contra {base} da Poppins (fator {fator})"


def test_normalizar_escreve_nos_knobs_certos():
    import run_fast as rf

    ed = {"captions": {"fontFamily": "anton", "fontSize": 90,
                       "fontScale": 1.18, "enabled": True}}
    rf._normalizar_altura_da_fonte(ed, None)
    cap = ed["captions"]
    assert cap["fontSize"] == round(90 * 0.83)
    assert cap["scatterFontSize"] == round(72 * 0.83)
    assert cap["sizeScale"] == round(0.83, 3)
    # stacked mantem a tipografia do template: fontScale NAO muda
    assert cap["fontScale"] == 1.18


def test_preview_do_editor_espelha_o_fator():
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("FONT_ALTURA = { anton: 0.83 }")
    assert "style !== 'stacked'" in js[i:i + 220]


def test_o_aviso_diz_a_verdade_nova():
    """Com o fallback, "a fonte desenha o simbolo dela" virou mentira."""
    jv = (REPO / "app" / "jobs_view.py").read_text(encoding="utf-8")
    assert "essas letras saem na fonte" in jv
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "fallback por glifo" in rf


def test_os_dois_fallbacks_sao_a_mesma_fonte():
    """O template caia na fonte do SISTEMA (BrandLocal sozinho na pilha)
    enquanto o motor cobre com Poppins — o mesmo video sairia com
    fallbacks diferentes conforme o motor. A pilha agora termina em
    Poppins nos tres lugares: fonts.ts, motor (_fonte_reserva) e preview."""
    ts = (REPO / "assets" / "shortform" / "src" / "fonts.ts").read_text(encoding="utf-8")
    i = ts.index("function loadBrandFile")
    bloco = ts[i:i + 1600]
    assert "family}, ${reserva}" in bloco, "pilha do template sem a reserva"
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "arquivo: \"'BrandLocal','Poppins',sans-serif\"" in js
    assert "function garantirFonteDaMarca" in js
    assert "new FontFace('BrandLocal'" in js


def test_larg_hl_mede_com_a_fonte_que_desenha(tmp_path, monkeypatch):
    """Moldura da headline: com glifo faltando, medir o avanco na fonte da
    marca (caixa de .notdef) descasa a moldura da tinta."""
    r = _r(tmp_path)
    from PIL import ImageFont

    f = ImageFont.truetype(str(FONTES / "Poppins-Regular.ttf"), 100)
    monkeypatch.setattr(r, "_hl_fonte", lambda peso, tam: f)
    normal = r._larg_hl("AÇÃO", 100)
    original = r._glifo_falta

    def _falta(fonte, ch):
        return ch in "ÇÃ" or original(fonte, ch)

    monkeypatch.setattr(r, "_glifo_falta", _falta)
    com_reserva = r._larg_hl("AÇÃO", 100)
    # a reserva (Poppins-ExtraBold) e mais larga que a Regular: a conta
    # TEM de mudar quando os glifos passam a sair nela
    assert com_reserva != normal
    assert com_reserva > 0


def test_headline_tambem_normaliza_a_altura(tmp_path):
    """Titulo curto bate no teto de px — e o teto rende alturas diferentes
    por fonte. O fator vale nos DOIS motores (_hl_linhas e fitHeadline)."""
    from app.render_proprio import Renderizador

    def _tam(fam):
        public = tmp_path / f"pub-{fam or 'nada'}"
        (public / "sfx").mkdir(parents=True, exist_ok=True)
        ed = {"width": 1080, "height": 1920, "fps": 30, "durationSec": 4,
              "hook": {"enabled": False, "fontFamily": fam},
              "captions": {"enabled": False}, "endCard": {"enabled": False},
              "soundtrack": {"enabled": False}, "transitions": [],
              "inserts": [], "behind": [],
              "camera": {"enabled": False, "zooms": [1]}}
        r = Renderizador(public, ed, frames=60, fps=30)
        _, tam = r._hl_linhas("Oi", (900, 900), 100, 900.0)
        return tam

    assert _tam("anton") == round(_tam("poppins") * 0.83)

    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    i = tsx.index("function fitHeadline")
    assert "hookSizeFactor()" in tsx[i:i + 700], "o template ficou sem o fator"
    ts = (REPO / "assets" / "shortform" / "src" / "fonts.ts").read_text(encoding="utf-8")
    assert "ALTURA_FATOR: Record<string, number> = {anton: 0.83}" in ts, \
        "as duas tabelas tem de dizer o MESMO numero"


def test_alucinacao_do_whisper_e_filtrada():
    """Caso real C066 (31/08): 132 palavras, 121 duplicatas exatas, "ei,"
    107 vezes — a legenda saia "toda errada e remontada" a cada refazer.
    Duplicata exata cai; a mesma palavra em metralhadora para na 3a."""
    import captions_for_remotion as cfr

    raw = {"words": (
        [{"type": "word", "text": "Oi", "start": 1.0, "end": 1.3}]
        + [{"type": "word", "text": "ei,", "start": 2.0, "end": 2.04}] * 5
        + [{"type": "word", "text": "ei,", "start": round(2.0 + i * 0.05, 2),
            "end": round(2.04 + i * 0.05, 2)} for i in range(1, 30)]
        + [{"type": "word", "text": "tchau", "start": 9.0, "end": 9.4}]
    )}
    ws = cfr._word_items(raw)
    textos = [str(w["text"]).strip(",").strip() for w in ws]
    assert textos[0] == "Oi" and textos[-1] == "tchau"
    assert textos.count("ei") <= 3, textos
    # repeticao LENTA (fala real: "nao, nao, nao" pausado) sobrevive
    raw2 = {"words": [
        {"type": "word", "text": "não,", "start": 1.0 + i * 0.6,
         "end": 1.3 + i * 0.6} for i in range(6)]}
    assert len(cfr._word_items(raw2)) == 6


def test_fonte_so_caixa_alta_sobe_a_reserva(tmp_path, monkeypatch):
    """"PROMOçãO" — ç minusculo da reserva no meio das capitais da
    Integral: letras de tamanhos diferentes na mesma palavra (reclamacao
    dele, 01/09). Fonte so-maiusculas => reserva desenha Ç."""
    r = _r(tmp_path)
    from PIL import ImageFont

    poppins = ImageFont.truetype(str(FONTES / "Poppins-Black.ttf"), 60)
    assert r._so_caixa_alta(poppins) is False
    assert r._char_para_reserva(poppins, "ç") == "ç"
    monkeypatch.setattr(r, "_so_caixa_alta", lambda f: True)
    assert r._char_para_reserva(poppins, "ç") == "Ç"
    assert r._char_para_reserva(poppins, "A") == "A"


def test_caps_only_esta_nos_tres_lugares():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'ed["brandFontCapsOnly"] = True' in rf
    ts = (REPO / "assets" / "shortform" / "src" / "fonts.ts").read_text(encoding="utf-8")
    assert "capTransform" in ts and "hookTransform" in ts
    assert "brandFontCapsOnly" in ts
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "brandFontCapsOnly" in js
    # e os componentes de legenda aplicam o transform
    for comp in ("SimpleCaptions", "ScatterCaptions", "ImpactCaptions", "Main"):
        tsx = (REPO / "assets" / "shortform" / "src" / f"{comp}.tsx").read_text(encoding="utf-8")
        assert "capTransform()" in tsx or "hookTransform()" in tsx, comp
