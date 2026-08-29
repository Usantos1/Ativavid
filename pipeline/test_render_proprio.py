# -*- coding: utf-8 -*-
"""Renderizador próprio (app/render_proprio): gate, contrato e motores."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from app.render_proprio import (  # noqa: E402
    EMOJI_FONT,
    Renderizador,
    motivo_nao_suportado,
    render_overlay_proprio,
)

_EMOJI_OK = EMOJI_FONT.exists()

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def _ed(**mud) -> dict:
    base = {"width": 1080, "height": 1920, "fps": 30,
            "captions": {"style": "stacked"},
            "hook": {"enabled": True, "style": "realce", "lines": ["a", "b"],
                     "endSec": 2.0, "accent": "#e30004"},
            "endCard": {"enabled": True, "lines": ["Segue @x", "direct"],
                        "lastSec": 1.0, "dim": 0.82}}
    base.update(mud)
    return base


def _public(tmp_path: Path, cues=None) -> Path:
    pub = tmp_path / "public"
    pub.mkdir(parents=True, exist_ok=True)
    if cues is None:
        cues = [{"i": 0, "preset": "STACK_MIXED", "exit": "blur_up",
                 "startMs": 0, "endMs": 900, "styleOffset": 0,
                 "lines": [[{"text": "Olá", "fromMs": 0, "toMs": 400}]]}]
    (pub / "caption-cues.json").write_text(json.dumps(cues), encoding="utf-8")
    return pub


# ------------------------------------------------------------------- gate ----
def test_projeto_padrao_e_suportado(tmp_path):
    assert motivo_nao_suportado(_ed(), _public(tmp_path)) is None


def test_gate_derruba_o_que_nao_desenha(tmp_path):
    pub = _public(tmp_path)
    casos = [
        (_ed(captions={"style": "estilo_do_futuro"}), "estilo de legenda"),
        (_ed(hook={"enabled": True, "style": "estilo_novo", "lines": ["a"]}), "headline"),
        (_ed(width=720), "resolucao"),
    ]
    for ed, trecho in casos:
        motivo = motivo_nao_suportado(ed, pub)
        assert motivo and trecho in motivo, (trecho, motivo)


def test_preset_desconhecido_derruba(tmp_path):
    pub = _public(tmp_path, cues=[{"i": 0, "preset": "NOVO_ESTILO",
                                   "startMs": 0, "endMs": 500,
                                   "lines": [[{"text": "x", "fromMs": 0}]]}])
    assert "preset" in (motivo_nao_suportado(_ed(), pub) or "")


def test_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("ATIVAVID_RENDER_PROPRIO", "0")
    assert "desligado" in motivo_nao_suportado(_ed(), _public(tmp_path))


# ---------------------------------------------------------------- contrato ----
def test_render_produz_overlay_com_os_quadros_pedidos(tmp_path):
    """Smoke real: 20 quadros, 1 legenda + headline + cartão."""
    pub = _public(tmp_path)
    out = tmp_path / "overlay.mov"
    render_overlay_proprio(pub, _ed(), frames=20, fps=30.0,
                           width=1080, height=1920, out=out)
    assert out.exists() and out.stat().st_size > 1000
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, **NOWIN)
    # first_record: a saída pode vir repetida (stream group)
    primeiro = next(l for l in r.stdout.splitlines() if l.strip())
    assert int(primeiro.strip().rstrip(",")) == 20


def test_overlay_tem_alpha_e_tinta_onde_deve(tmp_path):
    pub = _public(tmp_path)
    out = tmp_path / "overlay.mov"
    render_overlay_proprio(pub, _ed(hook={"enabled": False},
                                    endCard={"enabled": False}),
                           frames=12, fps=30.0, width=1080, height=1920, out=out)
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-vf", "select=eq(n\\,8)",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True, **NOWIN)
    import numpy as np
    q = np.frombuffer(r.stdout, dtype=np.uint8).reshape(1920, 1080, 4)
    assert (q[..., 3] > 8).sum() > 500, "a legenda 'Olá' tem de aparecer"
    assert (q[:900, :, 3] > 8).sum() == 0, "acima da faixa deve ser transparente"


def test_fps_diferente_muda_o_relogio(tmp_path):
    """Projetos de câmera são 24 fps — o tempo em quadros muda junto."""
    pub = _public(tmp_path)
    r30 = Renderizador(pub, _ed(hook={"enabled": False}, endCard={"enabled": False}),
                       frames=30, fps=30.0)
    r24 = Renderizador(pub, _ed(hook={"enabled": False}, endCard={"enabled": False}),
                       frames=24, fps=24.0)
    # a mesma cue de 900 ms termina em quadros diferentes.
    # `Math.round` como o template (`StackedCaptions.tsx:281`), não `int()`:
    # este teste fixava a truncagem, que era justamente o defeito — 0,9*24 dá
    # 21,6, que o template arredonda para 22.
    import math

    arredonda = lambda x: math.floor(x + 0.5)   # noqa: E731
    assert r30.camadas[0].fim_f == arredonda(0.9 * 30)
    assert r24.camadas[0].fim_f == arredonda(0.9 * 24)
    assert r24.camadas[0].fim_f == 22


def test_sfx_eventos_seguem_o_template(tmp_path):
    cues = [
        {"i": 0, "preset": "SOLO_OUTLINE", "startMs": 0, "endMs": 500,
         "lines": [[{"text": "Não", "fromMs": 0}]]},
        {"i": 1, "preset": "STACK_MIXED", "startMs": 600, "endMs": 1200,
         "lines": [[{"text": "oi", "fromMs": 600}]]},
    ]
    r = Renderizador(_public(tmp_path, cues), _ed(endCard={"enabled": False}),
                     frames=40, fps=30.0)
    nomes = [e[0] for e in r.eventos_sfx]
    assert nomes.count("whoosh.mp3") == 1          # headline
    assert nomes.count("caption-click.mp3") == 2   # uma por cue
    assert nomes.count("caption-scratch.mp3") == 1  # so no Recorte
    vols = {e[0]: e[2] for e in r.eventos_sfx if e[0] == "caption-click.mp3"}


# ------------------------------------------------------------------ motores ----
def test_motores_diferentes_nunca_se_emendam():
    from app.overlay_path import _incremental_ranges

    velho = {"_template": "t", "_engine": "remotion",
             "edit-data.json": {}, "captions.json": [], "caption-cues.json": []}
    novo = dict(velho, _engine="proprio")
    assert _incremental_ranges(velho, novo, 30.0, 100) is None


# --------------------------------------------------------- passada única ----
def test_grafo_audio_espelha_o_compose():
    """Mesmas cadeias do overlay_compose._mix_audio_graph, com índices móveis."""
    from app.render_proprio import _grafo_audio

    g = _grafo_audio(0, 1, 2, 0.12, 28.4, 26.9)
    assert g[0].startswith("[0:a]aformat=")
    assert g[1].startswith("[1:a]aformat=")
    assert "volume=0.1200" in g[2] and "afade=t=out:st=26.900" in g[2]
    assert g[-1].endswith("dropout_transition=0:normalize=0[pre]")

    so_voz = _grafo_audio(0, None, None, 0.12, 10.0, 8.5)
    assert so_voz[-1] == "[voice]anull[pre]"

    sem_sfx = _grafo_audio(0, None, 1, 0.2, 10.0, 8.5)
    assert "[1:a]volume=0.2000" in sem_sfx[1]
    assert "amix=inputs=2" in sem_sfx[-1]


# ----------------------------------------------------------- estilo impacto ----
def test_impacto_agrupa_como_o_template():
    """Largura medida > contagem > respiro (pontuação/pausa >450 ms)."""
    ws = [
        {"text": "um", "startMs": 0, "endMs": 100},
        {"text": "dois", "startMs": 100, "endMs": 200},
        {"text": "tres.", "startMs": 200, "endMs": 300},     # pontuação quebra
        {"text": "quatro", "startMs": 300, "endMs": 400},
        {"text": "cinco", "startMs": 900, "endMs": 1000},    # pausa 500ms quebra
        {"text": "seis", "startMs": 1000, "endMs": 1100},
        {"text": "sete", "startMs": 1100, "endMs": 1200},
        {"text": "oito", "startMs": 1200, "endMs": 1300},    # 4a palavra quebra
    ]
    cues = Renderizador._agrupar_impacto(ws, lambda g: 100.0 * len(g))
    textos = [[w["text"] for w in c] for c in cues]
    assert textos == [["um", "dois", "tres."], ["quatro"],
                      ["cinco", "seis", "sete"], ["oito"]]


def test_impacto_quebra_por_largura():
    ws = [{"text": "a", "startMs": i * 100, "endMs": i * 100 + 90}
          for i in range(3)]
    cues = Renderizador._agrupar_impacto(ws, lambda g: 500.0 * len(g))
    assert [len(c) for c in cues] == [1, 1, 1], "820px / 500 por palavra"


def test_impacto_tinta_por_luminancia():
    assert Renderizador._tinta_na_caixa("#ffd400") == "#111214"  # amarelo -> preto
    assert Renderizador._tinta_na_caixa("#e30004") == "#ffffff"  # vermelho -> branco


def test_ease_back_assenta_em_1():
    assert abs(Renderizador._ease_back(1.0) - 1.0) < 1e-9
    assert Renderizador._ease_back(0.6) > 1.0, "overshoot no meio"


def test_catalogo_de_legendas_todo_suportado(tmp_path):
    """Os 4 estilos (7 variantes) validados contra o Remotion — tinta mediana
    entre 1,009 e 1,094 em 140 quadros cada."""
    for estilo in ("stacked", "impacto", "scatter", "simples",
                   "serifada", "classica", "bloco", "recorte"):
        assert motivo_nao_suportado(
            _ed(captions={"style": estilo}), _public(tmp_path)) is None, estilo


def test_estilo_desconhecido_ainda_derruba(tmp_path):
    assert "estilo de legenda" in (motivo_nao_suportado(
        _ed(captions={"style": "estilo_do_futuro"}), _public(tmp_path)) or "")

# --------------------------------------------------------- headlines ----
def test_catalogo_de_headlines_todo_suportado(tmp_path):
    """Os 9 estilos validados contra o Remotion — tinta mediana 0,862-1,166."""
    for estilo in ("outline", "card", "realce", "misto", "sombra",
                   "sublinhado", "pilula", "manchete", "carimbo"):
        ed = _ed(hook={"enabled": True, "style": estilo,
                       "text": "Quase perdi essa venda", "endSec": 3.0})
        assert motivo_nao_suportado(ed, _public(tmp_path)) is None, estilo


def test_headline_desconhecida_ainda_derruba(tmp_path):
    ed = _ed(hook={"enabled": True, "style": "estilo_do_futuro", "lines": ["a"]})
    assert "headline" in (motivo_nao_suportado(ed, _public(tmp_path)) or "")


def test_headline_quebra_em_duas_linhas_por_largura(tmp_path):
    """A quebra e por largura MEDIDA, nao por contagem de palavras."""
    r = Renderizador(_public(tmp_path), _ed(hook={"enabled": False},
                                            endCard={"enabled": False}),
                     frames=30, fps=30.0)
    linhas, tam = r._hl_linhas("Quase perdi essa venda", (900, 900), 86, 830)
    assert len(linhas) == 2
    assert 40 <= tam <= 86
    # as duas metades devem ficar proximas em largura
    a = r._larg_hl(linhas[0], tam, 900)
    b = r._larg_hl(linhas[1], tam, 900)
    assert abs(a - b) / max(a, b) < 0.4


def test_headline_maiuscula_bate_com_o_template():
    """Caixa alta e escolha de ESTILO, e tem de ser a mesma nos dois motores:
    o mesmo texto sairia "É assim" num caminho e "É ASSIM" no outro."""
    esperado = {"card", "manchete", "carimbo", "faixa", "vazado"}
    assert set(Renderizador.HL_MAIUSCULA) == esperado
    tsx = (Path(__file__).resolve().parent.parent / "assets" / "shortform"
           / "src" / "Main.tsx").read_text(encoding="utf-8")
    i = tsx.index("const isUpper =")
    linha = tsx[i:tsx.index(";", i)]
    for nome in esperado:
        assert f"'{nome}'" in linha, nome

def test_contador_e_logo_agora_sao_suportados(tmp_path):
    """Portados na v2.26 — deixaram de derrubar para o Remotion."""
    assert motivo_nao_suportado(
        _ed(elements={"listCounter": True},
            listMarkers=[{"n": 1, "atSec": 0.5}]), _public(tmp_path)) is None
    assert motivo_nao_suportado(
        _ed(endCard={"enabled": True, "lines": ["x"], "logo": "logo.png"}),
        _public(tmp_path)) is None


def test_contador_um_selo_por_marcador(tmp_path):
    r = Renderizador(_public(tmp_path),
                     _ed(elements={"listCounter": True},
                         listMarkers=[{"n": 1, "atSec": 0.5},
                                      {"n": 2, "atSec": 2.0}],
                         hook={"enabled": False}, endCard={"enabled": False}),
                     frames=120, fps=30.0)
    selos = [c for c in r.camadas if c.inicio_f in (15, 60)]
    assert len(selos) == 2, "um selo por marcador, cada um ate o proximo"
    assert selos[0].fim_f == 59 and selos[1].fim_f == 120

# ------------------------------------------------- pergunta e fonte de marca ----
def test_pergunta_resposta_suportada(tmp_path):
    ed = _ed(hook={"enabled": True, "style": "pergunta",
                   "text": "Sabe por que?", "answerLines": ["Falta de estoque"],
                   "answerAtSec": 2.0, "endSec": 5.0})
    assert motivo_nao_suportado(ed, _public(tmp_path)) is None


def test_pergunta_tem_as_duas_fases(tmp_path):
    ed = _ed(hook={"enabled": True, "style": "pergunta", "text": "Por que?",
                   "answerLines": ["Estoque"], "answerAtSec": 2.0,
                   "endSec": 5.0}, endCard={"enabled": False})
    r = Renderizador(_public(tmp_path), ed, frames=150, fps=30.0)
    hl = r.camadas[0]
    at = 60
    # antes do answerAt so a pergunta; depois do pop so a resposta
    antes = [p for p in hl.palavras
             if p.janela and p.janela[0] <= 10 < p.janela[1]]
    depois = [p for p in hl.palavras
              if p.janela and p.janela[0] <= at + 20 < p.janela[1]]
    assert antes and depois, "as duas fases tem de existir"
    assert antes != depois


def test_fonte_de_marca_do_catalogo(tmp_path):
    for fam in ("poppins", "inter", "montserrat", "playfair",
                "lora", "anton", "bebas", "archivo"):
        ed = _ed(captions={"style": "stacked", "fontFamily": fam})
        assert motivo_nao_suportado(ed, _public(tmp_path)) is None, fam


def test_fonte_de_peso_unico_nao_ganha_negrito_falso(tmp_path):
    """Anton/Bebas/Archivo tem um peso so: pedir 900 nelas tem de ser
    clampado, como o hookWeight do template faz."""
    r = Renderizador(_public(tmp_path),
                     _ed(hook={"enabled": True, "style": "outline",
                               "text": "oi", "fontFamily": "anton"}),
                     frames=30, fps=30.0)
    assert r.marca_hook is not None
    assert r.marca_hook[1] == 400, "teto de peso da Anton"


def test_fonte_de_marca_inexistente_e_ignorada(tmp_path):
    """Id desconhecido nao pode derrubar o render — cai na fonte padrao."""
    r = Renderizador(_public(tmp_path),
                     _ed(captions={"style": "stacked", "fontFamily": "nao_existe"}),
                     frames=30, fps=30.0)
    assert r.marca_cap is None


def test_fonte_propria_ausente_nao_quebra(tmp_path):
    """id `arquivo` com o .ttf faltando cai na padrao em vez de estourar."""
    r = Renderizador(_public(tmp_path),
                     _ed(captions={"style": "stacked", "fontFamily": "arquivo"},
                         brandFontFile="fonts/sumiu.ttf"),
                     frames=30, fps=30.0)
    assert r.marca_cap is None

# ----------------------------------------------------------------- emoji ----
def test_emoji_passa_quando_a_fonte_do_sistema_existe(tmp_path):
    from app.render_proprio import EMOJI_FONT
    motivo = motivo_nao_suportado(_ed(elements={"emojiCaptions": True}),
                                  _public(tmp_path))
    if EMOJI_FONT.exists():
        assert motivo is None
    else:
        assert motivo and "emoji" in motivo


def test_fatiar_separa_emoji_do_texto():
    from app.render_proprio import fatiar_emoji
    assert fatiar_emoji("gratis \U0001F193") == [("gratis ", False),
                                                 ("\U0001F193", True)]
    assert fatiar_emoji("so texto") == [("so texto", False)]
    assert fatiar_emoji("a\U0001F525b") == [("a", False), ("\U0001F525", True),
                                            ("b", False)]


def test_seletor_de_variacao_fica_no_mesmo_glifo():
    """FE0F nao pode virar um segundo pedaco — o Chrome desenha UM glifo, e
    medi-lo em separado dobrava o avanco (medido: 223px contra 113px)."""
    from app.render_proprio import fatiar_emoji
    assert fatiar_emoji("cuidado \u26A0\uFE0F") == [("cuidado ", False),
                                                    ("\u26A0\uFE0F", True)]


def test_texto_comum_nao_e_confundido_com_emoji():
    from app.render_proprio import tem_emoji
    for t in ("Nao, senhora", "R$ 1.200,00", "voce ja tentou\u2026", "aspas \u201cx\u201d"):
        assert not tem_emoji(t), t


@pytest.mark.skipif(not _EMOJI_OK, reason="Segoe UI Emoji ausente")
def test_emoji_sai_colorido_e_do_tamanho_do_texto(tmp_path):
    """A cor volta separada da mascara (o emoji nao aceita a tinta do texto)
    e o glifo ocupa o font-size, nao a ascendente."""
    r = Renderizador(_public(tmp_path), _ed(), frames=30, fps=30.0)
    f = r.fonte(2, 64)
    m_so, cor_so = r._mascara_cor(f, "grande", 0.0)
    assert cor_so is None
    m, cor = r._mascara_cor(f, "grande \U0001F525", 0.0)
    assert cor is not None and cor.shape[:2] == m.shape
    vis = cor[..., 3] > 128
    assert vis.any(), "o emoji tem de deixar tinta"
    px = cor[vis][:, :3]
    assert (px.max(axis=1) - px.min(axis=1) > 40).sum() > 100, "tem de ser colorido"
    ys = np.nonzero(vis.any(axis=1))[0]
    assert 40 <= ys.max() - ys.min() <= 64, "o glifo cabe no font-size"


@pytest.mark.skipif(not _EMOJI_OK, reason="Segoe UI Emoji ausente")
def test_emoji_nao_dobra_a_largura_da_palavra(tmp_path):
    """Regressao do avanco: `getlength` sem Raqm media FE0F como um segundo
    glifo e a palavra saia com o dobro do espaco depois do emoji."""
    r = Renderizador(_public(tmp_path), _ed(), frames=30, fps=30.0)
    f = r.fonte(2, 64)
    um, _ = r._mascara_cor(f, "x \U0001F525", 0.0)
    vs, _ = r._mascara_cor(f, "x \u26A0\uFE0F", 0.0)
    assert abs(um.shape[1] - vs.shape[1]) <= 12, (um.shape, vs.shape)


def test_sem_a_fonte_de_emoji_o_texto_ainda_sai(tmp_path, monkeypatch):
    """Emoji digitado na fala + Windows sem a fonte: desenha o resto."""
    r = Renderizador(_public(tmp_path), _ed(), frames=30, fps=30.0)
    monkeypatch.setattr(r, "_fonte_emoji", lambda tam: None)
    m, cor = r._mascara_cor(r.fonte(2, 64), "oferta \U0001F525", 0.0)
    assert cor is None and m.shape[1] > 10


# ------------------------------------------------- logo/assinatura da headline ----
def test_headline_com_logo_e_assinatura_suportada(tmp_path):
    pub = _public(tmp_path)
    Image.new("RGBA", (600, 300), (255, 82, 0, 255)).save(pub / "lg.png")
    base = {"enabled": True, "style": "card", "text": "oi", "endSec": 3.0}
    ed = _ed(hook=dict(base, logo="lg.png", sign="lg.png"),
             endCard={"enabled": False})
    assert motivo_nao_suportado(ed, pub) is None
    com = Renderizador(pub, ed, frames=30, fps=30.0).camadas[0]
    sem = Renderizador(pub, _ed(hook=base, endCard={"enabled": False}),
                       frames=30, fps=30.0).camadas[0]
    assert len(com.palavras) == len(sem.palavras) + 2, "logo + assinatura"
    # a linha de imagens empurra o bloco de texto para baixo
    assert max(p.y0 for p in com.palavras) > max(p.y0 for p in sem.palavras)


def test_logo_ausente_nao_derruba_a_headline(tmp_path):
    ed = _ed(hook={"enabled": True, "style": "card", "text": "oi",
                   "logo": "sumiu.png"})
    assert motivo_nao_suportado(ed, _public(tmp_path)) is None
    r = Renderizador(_public(tmp_path), ed, frames=30, fps=30.0)
    assert r.camadas, "a headline continua desenhando sem o logo"


def test_card_desenha_a_caixa_numa_peca_so(tmp_path):
    """Aplicada por linha, a segunda (mais curta) ganhava uma caixa mais
    estreita e a borda direita saia em degrau."""
    ed = _ed(hook={"enabled": True, "style": "card", "endSec": 3.0,
                   "text": "VOCE QUASE PERDEU ESSA VENDA POR UM DETALHE"},
             endCard={"enabled": False})
    r = Renderizador(_public(tmp_path), ed, frames=30, fps=30.0)
    hl = r.camadas[0].palavras
    assert len(hl) == 1, f"a caixa tem de ser uma peca so, veio {len(hl)}"
    alt = hl[0].alpha.shape[0]
    assert alt > 200, f"as duas linhas cabem na mesma caixa ({alt}px)"

# ------------------------------------------------------------ b-roll ----
def _com_insert(pub, **mud):
    Image.new("RGB", (1200, 800), (18, 22, 40)).save(pub / "br.jpg")
    it = dict({"src": "br.jpg", "start": 0.5, "end": 2.5}, **mud)
    return _ed(inserts=[it], hook={"enabled": False},
               endCard={"enabled": False}, captions={"style": "stacked"})


def test_insert_suportado(tmp_path):
    pub = _public(tmp_path)
    assert motivo_nao_suportado(_com_insert(pub), pub) is None


def test_insert_vira_camada_com_a_janela_certa(tmp_path):
    pub = _public(tmp_path)
    r = Renderizador(pub, _com_insert(pub), frames=120, fps=30.0)
    br = [c for c in r.camadas if c.insert is not None]
    assert len(br) == 1
    assert (br[0].inicio_f, br[0].fim_f) == (15, 74)
    assert not br[0].palavras, "o cartao e desenhado na hora, sem Palavras"
    assert ("whoosh.mp3", 0.5, 0.09) in r.eventos_sfx


def test_insert_ausente_nao_derruba_o_render(tmp_path):
    pub = _public(tmp_path)
    ed = _com_insert(pub)
    ed["inserts"][0]["src"] = "sumiu.jpg"
    assert motivo_nao_suportado(ed, pub) is None
    r = Renderizador(pub, ed, frames=120, fps=30.0)
    assert not [c for c in r.camadas if c.insert is not None]


def test_insert_de_duracao_zero_e_ignorado(tmp_path):
    pub = _public(tmp_path)
    r = Renderizador(pub, _com_insert(pub, end=0.5), frames=120, fps=30.0)
    assert not [c for c in r.camadas if c.insert is not None]


def test_ken_burns_muda_a_assinatura_de_cada_quadro(tmp_path):
    """A camada nao tem Palavras: sem tratamento proprio a assinatura sairia
    constante e o motor repetiria o primeiro quadro o filme inteiro."""
    pub = _public(tmp_path)
    r = Renderizador(pub, _com_insert(pub), frames=120, fps=30.0)
    assinaturas = {r._assinatura(f) for f in range(20, 60)}
    assert len(assinaturas) == 40


def test_o_cartao_cresce_e_fica_no_lugar(tmp_path):
    """Ken-Burns (1 -> 1,08) a partir do centro da caixa fixa."""
    pub = _public(tmp_path)
    r = Renderizador(pub, _com_insert(pub), frames=120, fps=30.0)
    leg = [c for c in r.camadas if c.insert is not None][0]
    largs, centros = [], []
    for f in (10, 20, 30, 40):        # 53+ ja e o fade de saida
        buf = np.zeros((1920, 1080, 4), dtype=np.uint8)
        r.desenhar(leg, f, buf, [0, 0, 0, 0], False)
        xs = np.nonzero((buf[..., 3] > 200).any(axis=0))[0]
        largs.append(int(xs.max() - xs.min()))
        centros.append(int((xs.max() + xs.min()) / 2))
    assert largs == sorted(largs) and largs[-1] > largs[0], largs
    assert max(largs) <= round(780 * 1.08) + 4, largs
    assert max(centros) - min(centros) <= 2, centros



def test_dim_por_tabela_e_identico_ao_calculo_antigo():
    """O escurecimento do cartão final custava 44% do desenho (17,1s de
    38,8s em 70 quadros). A causa era `buf[..., :3] * (1.0 - a)`: uint8 vezes
    float do Python promove 6 milhões de valores a float64 — 48 MB por
    quadro — só para voltar a uint8 na linha seguinte.

    Como `a` é escalar, o resultado só assume 256 valores por canal. A tabela
    tem de dar EXATAMENTE o mesmo byte, inclusive o truncamento do astype."""
    import numpy as np

    def antigo(buf, a):
        b = buf.copy()
        alpha = b[..., 3].astype(np.float32) / 255.0
        b[..., :3] = (b[..., :3] * (1.0 - a)).astype(np.uint8)
        b[..., 3] = ((alpha + a * (1.0 - alpha)) * 255.0).astype(np.uint8)
        return b

    r = Renderizador.__new__(Renderizador)      # só as tabelas
    rng = np.random.default_rng(11)
    for a in (0.02, 0.2, 0.5, 0.82, 0.999):
        buf = rng.integers(0, 256, size=(120, 90, 4), dtype=np.uint8)
        novo = buf.copy()
        t_rgb, t_a = r._tabelas_dim(a)
        novo[..., :3] = t_rgb[novo[..., :3]]
        novo[..., 3] = t_a[novo[..., 3]]
        assert np.array_equal(antigo(buf, a), novo), f"divergiu em a={a}"


def test_tabela_do_dim_e_reusada(tmp_path):
    """Mesmo fator não pode remontar a tabela a cada quadro."""
    r = Renderizador.__new__(Renderizador)
    p1 = r._tabelas_dim(0.82)
    p2 = r._tabelas_dim(0.82)
    assert p1[0] is p2[0] and p1[1] is p2[1]


def _hl_extremos(tmp_path, hook: dict):
    ed = _ed(hook=dict({"enabled": True, "lines": ["ola", "mundo"],
                        "endSec": 2.0}, **hook), endCard={"enabled": False})
    r = Renderizador(_public(tmp_path, []), ed, frames=30, fps=30.0)
    c = r._montar_headline(ed["hook"])
    return (min(p.y0 for p in c.palavras),
            max(p.y0 + p.alpha.shape[0] for p in c.palavras))


def test_arrastar_ate_a_borda_nao_volta_para_o_padrao(tmp_path):
    """Zero é posição, não "vazio".

    O template usa `??`; o motor próprio usava `or`, então arrastar a manchete
    até o topo (paddingTop=0, o limite do clamp em quick_corrections) caía no
    padrão do estilo — 299px mais abaixo, calado. O sinal do defeito é a
    descontinuidade: 0 e 1 têm de ficar a 1px um do outro."""
    t0, _ = _hl_extremos(tmp_path, {"style": "realce", "paddingTop": 0})
    t1, _ = _hl_extremos(tmp_path, {"style": "realce", "paddingTop": 1})
    assert abs(t1 - t0) == 1, f"0 -> {t0}, 1 -> {t1}"
    # e ausente continua sendo o padrão do estilo, não zero
    tn, _ = _hl_extremos(tmp_path, {"style": "realce"})
    assert tn - t0 == 300

    # a manchete ancora pela BASE — mesmo teste do outro lado
    _, b0 = _hl_extremos(tmp_path, {"style": "manchete", "paddingBottom": 0})
    _, b1 = _hl_extremos(tmp_path, {"style": "manchete", "paddingBottom": 1})
    assert abs(b0 - b1) == 1, f"0 -> {b0}, 1 -> {b1}"


def test_legenda_no_alto_da_tela_nao_volta_para_o_padrao(tmp_path):
    """Mesma classe do anterior, do lado das legendas: offsetY=0 é o topo."""
    def base_y(caps):
        ed = _ed(captions=caps, hook={"enabled": False}, endCard={"enabled": False})
        return Renderizador(_public(tmp_path, []), ed, frames=30, fps=30.0).base_y

    assert base_y({"style": "stacked", "stackedOffsetY": 0}) == 0
    assert base_y({"style": "stacked"}) == round(1920 * 0.156)


def _contorno_para_fora(tmp_path, stroke) -> tuple[int, int]:
    """Quantos pixels de preto saem para FORA do glifo branco."""
    hook = {"enabled": True, "style": "outline", "lines": ["III"], "endSec": 2.0}
    if stroke is not None:
        hook["strokePx"] = stroke
    ed = _ed(hook=hook, endCard={"enabled": False})
    r = Renderizador(_public(tmp_path, []), ed, frames=30, fps=30.0)
    pl = r._montar_headline(ed["hook"]).palavras[0]
    lin = pl.alpha.shape[0] // 2
    op = pl.alpha[lin] > 0.6
    branco = np.where(op & (pl.rgb[lin, :, 0] > 0.78))[0]
    preto = np.where(op & (pl.rgb[lin, :, 0] < 0.16))[0]
    if not preto.size:
        return 0, 0
    return int(branco.min() - preto.min()), int(preto.max() - branco.max())


def test_contorno_da_headline_sai_metade_para_fora(tmp_path):
    """`-webkit-text-stroke` é CENTRADO: metade do traço cai dentro do glifo e
    o `paint-order: stroke fill` cobre essa metade com o preenchimento — só a
    metade de fora aparece.

    Medido no próprio Chrome (headless, traço 40 em HTML com paint-order): o
    glifo branco fica idêntico, 44px, e o preto sai 20px para fora à esquerda
    e 19 à direita (antialiasing). O motor dilatava `strokePx` inteiro, ou
    seja, pintava o contorno em dobro."""
    esq, dir_ = _contorno_para_fora(tmp_path, 40)
    assert 19 <= esq <= 21 and 18 <= dir_ <= 21, (esq, dir_)
    # o padrão do template é 12 → 6px para fora
    esq12, _ = _contorno_para_fora(tmp_path, None)
    assert 5 <= esq12 <= 7, esq12


def test_contorno_zero_nao_desenha_contorno(tmp_path):
    """strokePx=0 é "sem contorno", um valor de fato — com `or` virava 12."""
    assert _contorno_para_fora(tmp_path, 0) == (0, 0)


def test_flash_tem_som(tmp_path):
    """O corte marcado toca `cut-click.mp3` no template — um `<Sfx>` dentro de
    um Sequence que começa no quadro do corte. O motor próprio desenhava o
    clarão e o feixe e não tocava nada: o flash ficava mudo em todo projeto.

    O instante segue a mesma conta do desenho (`round(at*fps) + VIDEO_LAG`),
    senão o som chegaria antes ou depois do clarão."""
    from app.render_proprio import VIDEO_LAG

    ed = _ed(hook={"enabled": False}, endCard={"enabled": False},
             transitions=[{"type": "flash", "at": 1.0},
                          {"type": "flash", "at": 2.5, "volume": 0.4},
                          {"type": "flash", "at": 3.0, "sfx": "pop.mp3"}])
    r = Renderizador(_public(tmp_path, []), ed, frames=120, fps=30.0)
    ev = [e for e in r.eventos_sfx if e[0] in ("cut-click.mp3", "pop.mp3")]
    assert len(ev) == 3, r.eventos_sfx
    assert ev[0] == ("cut-click.mp3", (round(1.0 * 30) + VIDEO_LAG) / 30.0, 0.9)
    assert ev[1][2] == 0.4, "volume da transição vence o padrão"
    assert ev[2][0] == "pop.mp3", "sfx da transição vence o padrão"


def test_flash_respeita_o_desligar_efeitos(tmp_path):
    ed = _ed(hook={"enabled": False}, endCard={"enabled": False},
             captions={"style": "stacked", "sfx": {"enabled": False}},
             transitions=[{"type": "flash", "at": 1.0}])
    r = Renderizador(_public(tmp_path, []), ed, frames=60, fps=30.0)
    assert not r.eventos_sfx


def test_contador_desenha_sem_gate_de_elements(tmp_path):
    """O `ListCounter.tsx` só olha `listMarkers` — não tem gate nenhum. Aqui
    havia `edit_data["elements"]["listCounter"]`, e edit-data NÃO tem a chave
    `elements`: conferido nos 114 projetos do usuário, zero têm. Ela mora no
    PRESET, que o run_fast usa para decidir se GRAVA `listMarkers`.

    Ou seja: com o contador ligado no estilo, o selo desenhava no Remotion e
    sumia no motor próprio."""
    ed = _ed(hook={"enabled": False}, endCard={"enabled": False},
             listMarkers=[{"n": 1, "atSec": 0.5}, {"n": 2, "atSec": 2.0}])
    assert "elements" not in ed
    r = Renderizador(_public(tmp_path, []), ed, frames=120, fps=30.0)
    selos = [c for c in r.camadas if c.inicio_f in (15, 60)]
    assert len(selos) == 2, "o selo tem de desenhar só com listMarkers"


def test_sem_marcadores_o_contador_nao_desenha_nada(tmp_path):
    ed = _ed(hook={"enabled": False}, endCard={"enabled": False})
    r = Renderizador(_public(tmp_path, []), ed, frames=120, fps=30.0)
    assert r.camadas == [] or all(c.inicio_f != 15 for c in r.camadas)


def test_o_selo_traz_o_indicador_ordinal(tmp_path):
    """O template escreve `{cur.n}º`. O motor escrevia só o número."""
    from PIL import ImageFont

    from app.render_proprio import FONTES

    f = ImageFont.truetype(str(FONTES / "Poppins-Black.ttf"), 64)
    assert Renderizador._ordinal(f, 1) == "1º"
    assert Renderizador._ordinal(f, 12) == "12º"


def test_fonte_sem_o_glifo_cai_para_o_numero_seco(tmp_path):
    """As oito fontes do catálogo têm U+00BA, mas a fonte PRÓPRIA do usuário
    pode não ter — e aí o PIL desenha o .notdef, um quadradinho no vídeo
    entregue."""
    class SemGlifo:
        def getmask(self, ch, mode="L"):
            return np.zeros((4, 4), dtype=np.uint8)

    assert Renderizador._ordinal(SemGlifo(), 3) == "3"


def _solo_big(tmp_path, dur_ms=1200):
    cues = [{"i": 0, "preset": "SOLO_BIG", "startMs": 0, "endMs": dur_ms,
             "lines": [[{"text": "AGORA", "fromMs": 0, "toMs": int(dur_ms * 0.6)}]]}]
    ed = _ed(hook={"enabled": False}, endCard={"enabled": False})
    r = Renderizador(_public(tmp_path, cues), ed, frames=60, fps=30.0)
    return r.camadas[0]


def test_solo_big_cresce_de_88_a_100(tmp_path):
    """`StackedCaptions.tsx` faz `scale: interpolate(a.opacity, [0,1], [0.88,1])`
    no preset SOLO_BIG — a palavra cresce enquanto aparece. O motor
    rasterizava uma vez, em tamanho final, e só a opacidade animava."""
    leg = _solo_big(tmp_path)
    larguras = [p.alpha.shape[1] for p in leg.palavras]
    assert len(larguras) > 1, "precisa de mais de um estágio"
    assert larguras == sorted(larguras), larguras
    razao = larguras[-1] / larguras[0]
    assert 1.10 < razao < 1.16, f"cresceu {razao:.3f}, esperado ~1/0.88"


def test_solo_big_mostra_um_estagio_por_quadro(tmp_path):
    """Os estágios são exclusivos: dois visíveis ao mesmo tempo desenhariam a
    palavra duas vezes, sobrepostas."""
    from app.render_proprio import _opacidade

    leg = _solo_big(tmp_path)
    for f in range(0, 30):
        vis = [p for p in leg.palavras if _opacidade(p, f) > 0]
        assert len(vis) <= 1, f"quadro {f}: {len(vis)} estágios visíveis"


def test_solo_big_ainda_faz_o_fade(tmp_path):
    """A janela do estágio forçava opacidade 1,0 — a palavra apareceria de uma
    vez. Cada estágio carrega a sua opacidade (`Palavra.opac`)."""
    from app.render_proprio import _opacidade

    leg = _solo_big(tmp_path)
    ops = [max((_opacidade(p, f) for p in leg.palavras), default=0.0)
           for f in range(0, 12)]
    assert ops[0] == 0.0
    assert 0.0 < ops[1] < 1.0, ops
    assert ops == sorted(ops), ops
    assert ops[-1] == 1.0


def test_solo_big_acompanha_a_duracao_da_cue(tmp_path):
    """`enter` vai de 3 a 8 quadros conforme a duração. Com passo fixo, cue
    curta chegava ao tamanho cheio depois de a palavra já estar opaca."""
    longa = len(_solo_big(tmp_path, 1200).palavras)
    curta = len(_solo_big(tmp_path, 300).palavras)
    assert curta < longa, (curta, longa)


def test_solo_big_sobe_46px_enquanto_cresce(tmp_path):
    """No template a palavra do SOLO_BIG faz TRÊS coisas ao mesmo tempo:
    opacidade, `translate: 0px {46→0}px` e `scale: 0.88→1`.

    Ao dar estágios de escala à palavra (para o `scale`), ela ganhou `janela`
    — e `_blend` zerava o deslocamento vertical justamente quando havia
    janela. A palavra passou a crescer sem subir. Regressão introduzida no
    mesmo commit que trouxe a escala."""
    from app.render_proprio import _opacidade

    leg = _solo_big(tmp_path)
    vistos = []
    for f in range(0, 12):
        for p in leg.palavras:
            op = _opacidade(p, f)
            if op > 0:
                vistos.append((f, int(round(p.sobe * (1.0 - op)))))
                break
    deslocs = [d for _, d in vistos]
    # O valor do primeiro quadro sai da CURVA, não de um número escolhido a
    # dedo: `translate: interpolate(p, [0,1], [46,0])` com o mesmo ease do
    # template. Calibrar isso na mão amarraria o teste à curva antiga.
    from app.render_proprio import _ease_out

    enter = leg.palavras[0].enter
    esperado_1 = int(round(46 * (1 - _ease_out(1 / max(1, enter)))))
    assert deslocs[0] == esperado_1, (deslocs, esperado_1)
    assert deslocs[0] > 10, f"tem de nascer abaixo: {vistos}"
    assert deslocs == sorted(deslocs, reverse=True), vistos
    assert deslocs[-1] == 0, vistos


def test_quem_usa_janela_com_opacidade_cheia_continua_sem_subir(tmp_path):
    """A condição removida (`if p.janela is None`) não era o que segurava os
    outros: eles têm opacidade 1,0 dentro da janela, então `sobe*(1-1)` já dá
    zero sozinho. Este teste é a prova de que a remoção não os mexeu."""
    from app.render_proprio import _opacidade

    # contador: estágios com sobe=0.0
    ed = _ed(hook={"enabled": False}, endCard={"enabled": False},
             listMarkers=[{"n": 1, "atSec": 0.5}])
    r = Renderizador(_public(tmp_path, []), ed, frames=120, fps=30.0)
    selos = [c for c in r.camadas if c.inicio_f == 15]
    assert selos, "o contador tem de estar desenhando"
    for p in selos[0].palavras:
        for f in range(15, 30):
            op = _opacidade(p, f)
            if op > 0:
                assert int(round(p.sobe * (1.0 - op))) == 0, (p.sobe, op)

    # recorte (SOLO_OUTLINE): o traço usa janela com o `sobe` padrão
    cues = [{"i": 0, "preset": "SOLO_OUTLINE", "startMs": 0, "endMs": 900,
             "lines": [[{"text": "Não", "fromMs": 0, "toMs": 400}]]}]
    r2 = Renderizador(_public(tmp_path, cues),
                      _ed(hook={"enabled": False}, endCard={"enabled": False}),
                      frames=60, fps=30.0)
    com_janela = [p for p in r2.camadas[0].palavras if p.janela is not None]
    assert com_janela, "o traço do Recorte usa janela"
    for p in com_janela:
        for f in range(0, 30):
            op = _opacidade(p, f)
            if op > 0:
                assert int(round(p.sobe * (1.0 - op))) == 0, (p.sobe, op, f)


def test_a_curva_de_entrada_e_a_do_template():
    """`StackedCaptions.tsx:77` usa `Easing.bezier(0.16, 1, 0.3, 1)`. O motor
    usava `1-(1-t)^3` (`Easing.out(Easing.cubic)`) — parecida, mas a diferença
    de opacidade chega a **0,264** no primeiro terço da entrada: em t=0,2 o
    template já está em 0,75 e a cúbica em 0,49.

    Valia para TODA palavra de TODA legenda. A validação por razão de tinta
    que aprovou o motor não pegaria: ela mede ÁREA sobre a cue inteira, e a
    entrada é uma fração dela."""
    from app.render_proprio import _ease_out

    def bezier(x, it=60):
        x1, y1, x2, y2 = 0.16, 1.0, 0.3, 1.0
        lo, hi = 0.0, 1.0
        for _ in range(it):
            t = (lo + hi) / 2
            u = 1 - t
            if 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 < x:
                lo = t
            else:
                hi = t
        t = (lo + hi) / 2
        u = 1 - t
        return 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3

    pior = max(abs(_ease_out(i / 200) - bezier(i / 200)) for i in range(201))
    assert pior < 1e-3, pior
    assert _ease_out(0.0) == 0.0 and _ease_out(1.0) == 1.0
    # e é mesmo diferente da cúbica que estava aí
    assert abs(_ease_out(0.2) - (1 - 0.8 ** 3)) > 0.2


def test_o_escurecimento_do_end_card_continua_cubico():
    """Nem tudo usa a curva da palavra: `Main.tsx:506` usa
    `Easing.out(Easing.cubic)` para o dim do cartão final. Conferido antes de
    trocar, para não sair aplicando a curva nova em tudo."""
    s = (REPO := Path(__file__).resolve().parent.parent)
    src = (s / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = src.index("def _aplicar_dim")
    assert "(1 - (1 - t) ** 3)" in src[i:i + 700]


def test_o_enter_encurta_para_quem_entra_perto_da_saida(tmp_path):
    """`wordAnim` no template: `max(2, min(ENTER, floor(exitStart - localStart
    - 1)))`. O motor passava o `enter` da CUE para toda palavra, então quem
    entrava tarde ficava com uma janela longa demais e a cue acabava antes de
    ela assentar — mais clara e ainda deslocada para baixo. Com `exit:
    abrupt`, que é o caso da maioria, ela pisca e some.

    Medido nos 114 projetos do usuário: 6.292 de 23.166 palavras (27%)
    deviam ter a entrada encurtada."""
    import math

    from app.render_proprio import _opacidade

    cue = {"i": 0, "preset": "STACK_MIXED", "startMs": 0, "endMs": 1000,
           "exit": "abrupt", "lines": [[
               {"text": "voce", "fromMs": 0, "toMs": 300},
               {"text": "vai", "fromMs": 860, "toMs": 960}]]}
    r = Renderizador(_public(tmp_path, [cue]),
                     _ed(hook={"enabled": False}, endCard={"enabled": False}),
                     frames=120, fps=30.0)
    leg = r.camadas[0]
    cedo = min(leg.palavras, key=lambda p: p.inicio_f)
    tarde = max(leg.palavras, key=lambda p: p.inicio_f)
    assert cedo.enter > tarde.enter, (cedo.enter, tarde.enter)
    assert tarde.enter == max(2, min(cedo.enter,
                                     math.floor(leg.saida_f - tarde.inicio_f - 1)))
    # e no último quadro visível ela já está praticamente opaca
    ultimo = int(leg.dur_f) - 3
    assert _opacidade(tarde, ultimo) > 0.85, _opacidade(tarde, ultimo)


def test_cartao_final_usa_600_na_segunda_linha(tmp_path):
    """`EndCardInner` faz `fontWeight: i === 0 ? 900 : 600`. Sem um índice de
    SemiBold na tabela, a segunda linha caía no ExtraBold (800)."""
    ed = _ed(hook={"enabled": False},
             endCard={"enabled": True, "lines": ["Segue @x", "manda um direct"],
                      "lastSec": 1.0, "dim": 0.82})
    r = Renderizador(_public(tmp_path, []), ed, frames=120, fps=30.0)
    nomes = {Path(k[0]).name for k in r._fontes}
    assert "Poppins-SemiBold.ttf" in nomes, nomes
    assert "Poppins-ExtraBold.ttf" not in nomes, nomes


def test_o_fundo_da_headline_segue_o_texto_e_nao_a_mascara(tmp_path):
    """`_mascara` acrescenta 8px de folga à direita para o antialias não ser
    cortado. Usar essa largura como a da CAIXA punha os 8px dentro do fundo —
    assimétrico, tudo de um lado. As outras caixas do arquivo (manchete,
    carimbo, pílula) já derivam de `_larg_hl`."""
    ed = _ed(hook={"enabled": True, "style": "realce", "lines": ["ola", "mundo"],
                   "endSec": 2.0, "accent": "#e30004"},
             endCard={"enabled": False})
    r = Renderizador(_public(tmp_path, []), ed, frames=60, fps=30.0)
    leg = r._montar_headline(ed["hook"])
    for p, texto in zip(leg.palavras, ["ola", "mundo"]):
        # a caixa é o avanço do texto + 2*pad; a folga do rasterizador (56 de
        # cada lado) é o que sobra
        larg_txt = r._larg_hl(texto, 86, 900)
        # sem o `+8` da máscara: a largura da camada não pode passar do
        # avanço + paddings + as duas folgas por uma margem grande
        assert p.alpha.shape[1] < larg_txt + 2 * 40 + 2 * 56 + 4, (
            p.alpha.shape[1], larg_txt)


def test_o_relogio_da_cue_arredonda_como_o_template(tmp_path):
    """`StackedCaptions.tsx:280-282` monta cada cue com

        from = Math.round(startMs / 1000 * fps)
        end  = Math.round(endMs   / 1000 * fps)
        dur  = Math.max(2, Math.min(end, durationInFrames) - from)

    e passa esse `dur` INTEIRO como `cueDurationFrames` — é ele que manda no
    ENTER, no EXIT e no corte do `exit: abrupt`.

    Aqui era `int()`, que TRUNCA. Medido num projeto real: **57 das 112 cues
    (51%)** caíam num quadro diferente do template; a legenda aparecia um
    quadro antes e todo o relógio interno dela ia junto."""
    import math

    # 64757 ms a 30 fps = 1942,71 → trunca em 1942, arredonda em 1943
    cue = {"i": 0, "preset": "STACK_MIXED", "startMs": 64757, "endMs": 65217,
           "exit": "abrupt", "lines": [[{"text": "oi", "fromMs": 64757}]]}
    r = Renderizador(_public(tmp_path, [cue]),
                     _ed(hook={"enabled": False}, endCard={"enabled": False}),
                     frames=2528, fps=30.0)
    leg = r.camadas[0]
    assert leg.inicio_f == 1943, leg.inicio_f
    assert leg.fim_f == 1957, leg.fim_f
    # e a duração é INTEIRA, como o `dur` do template
    assert leg.dur_f == float(1957 - 1943)
    assert leg.dur_f == int(leg.dur_f)


def test_o_arredondamento_e_o_do_javascript():
    """O `round` do Python é bancário: `round(0.5)` dá 0 e `round(2.5)` dá 2.
    O `Math.round` do JavaScript sempre sobe no meio."""
    a = Renderizador._arredonda_js
    assert [a(x) for x in (0.5, 1.5, 2.5, 3.5)] == [1, 2, 3, 4]
    assert [round(x) for x in (0.5, 2.5)] == [0, 2], "o do Python difere mesmo"


def test_a_duracao_da_cue_nao_passa_do_video(tmp_path):
    """`Math.min(end, durationInFrames)` no template: uma cue que termina
    depois do fim da composição é cortada ali."""
    cue = {"i": 0, "preset": "STACK_MIXED", "startMs": 0, "endMs": 100000,
           "lines": [[{"text": "oi", "fromMs": 0}]]}
    r = Renderizador(_public(tmp_path, [cue]),
                     _ed(hook={"enabled": False}, endCard={"enabled": False}),
                     frames=90, fps=30.0)
    assert r.camadas[0].dur_f == 90.0


def test_so_a_legenda_stacked_usa_a_curva_bezier(tmp_path):
    """Só o `StackedCaptions.tsx` usa `Easing.bezier(0.16, 1, 0.3, 1)`
    (linha 77). A headline, o cartão final, o scatter e o impacto usam
    `Easing.out(Easing.cubic)`.

    Trocar a curva no motor INTEIRO deixou a headline errada — e ela fica na
    tela nos primeiros 4 s de todo vídeo. Pego pela varredura contra o
    Remotion: no quadro 2 a razão de tinta era 1,537 e o centro vertical
    ficava 11,8 px fora; com a curva por palavra, 1,177 e 1,4 px."""
    cues = [{"i": 0, "preset": "STACK_MIXED", "startMs": 0, "endMs": 1200,
             "lines": [[{"text": "oi", "fromMs": 0}]]}]
    ed = _ed(hook={"enabled": True, "style": "realce", "lines": ["ola", "mundo"],
                   "endSec": 2.0},
             endCard={"enabled": True, "lines": ["a", "b"], "lastSec": 1.0,
                      "dim": 0.82})
    r = Renderizador(_public(tmp_path, cues), ed, frames=120, fps=30.0)
    por_curva = {}
    for leg in r.camadas:
        for p in leg.palavras:
            por_curva.setdefault(p.ease, 0)
            por_curva[p.ease] += 1
    assert por_curva.get("bezier", 0) >= 1, por_curva
    assert por_curva.get("cubic", 0) >= 1, por_curva


def test_a_headline_nao_usa_a_curva_da_legenda(tmp_path):
    ed = _ed(hook={"enabled": True, "style": "realce", "lines": ["ola", "mundo"],
                   "endSec": 2.0},
             endCard={"enabled": False})
    r = Renderizador(_public(tmp_path, []), ed, frames=120, fps=30.0)
    leg = r._montar_headline(ed["hook"])
    assert leg.palavras, "a headline tem de desenhar"
    assert all(p.ease == "cubic" for p in leg.palavras), \
        [p.ease for p in leg.palavras]


# --- legenda desligada não pode derrubar o motor rápido --------------------
#
# Descoberto rodando um job de verdade: o pipeline grava `style="karaoke"` fixo
# quando a legenda está desligada (`captions if cap_enabled else "karaoke"`), e
# karaoke é o único estilo do template que o motor próprio não desenha. Ou
# seja: desligar a legenda custava 3,3x no render, por causa de uma legenda que
# não aparece no vídeo.


def test_legenda_desligada_nao_derruba_o_motor(tmp_path):
    ed = _ed(captions={"enabled": False, "style": "karaoke"})
    assert motivo_nao_suportado(ed, _public(tmp_path)) is None


def test_legenda_ligada_com_estilo_de_fora_ainda_derruba(tmp_path):
    """A guarda continua valendo para o que VAI ser desenhado.

    O exemplo era `karaoke` ate ele ganhar suporte; agora precisa ser um
    estilo que nao existe mesmo, senao o teste passa a nao testar nada.
    """
    ed = _ed(captions={"enabled": True, "style": "estilo_que_nao_existe"})
    assert "estilo_que_nao_existe" in str(motivo_nao_suportado(ed, _public(tmp_path)))


def test_sem_o_campo_enabled_a_guarda_continua_valendo(tmp_path):
    """Na dúvida, o erro barato: perder o motor rápido custa tempo; desenhar um
    estilo que o motor não sabe custa um vídeo errado."""
    ed = _ed(captions={"style": "estilo_que_nao_existe"})
    assert "estilo_que_nao_existe" in str(motivo_nao_suportado(ed, _public(tmp_path)))


# --- karaoke ---------------------------------------------------------------
#
# O estilo `karaoke` e o unico do template que o motor rapido nao desenhava, e
# tres dos doze modelos da tela usam ele -- quem escolhesse um deles pagava o
# Remotion inteiro, 3,5x mais lento, em silencio.
#
# A implementacao foi portada de `Main.tsx` (Karaoke 382-427, Word 335-360,
# CaptionShell 362-380, buildLines 319-333) e conferida quadro a quadro contra
# o Remotion. Estes testes travam o que a comparacao visual nao alcanca: as
# regras de agrupamento, o tempo, e a porta de recusa.


def _cap_karaoke(**mud):
    base = {"enabled": True, "style": "karaoke", "fontSize": 76,
            "maxWords": 3, "safeWidth": 720, "paddingBottom": 420}
    base.update(mud)
    return base


def _palavras(pub: Path, ws) -> None:
    (pub / "captions.json").write_text(json.dumps(
        [{"text": t, "startMs": a, "endMs": b} for t, a, b in ws]),
        encoding="utf-8")


def test_karaoke_e_o_padrao(tmp_path):
    """Aprovado em 22/08/2026: o motor rapido desenha o karaoke por padrao."""
    ed = _ed(captions=_cap_karaoke())
    assert motivo_nao_suportado(ed, _public(tmp_path)) is None


def test_kill_switch_do_karaoke_devolve_ao_remotion(tmp_path, monkeypatch):
    """O interruptor de emergencia, para o caso visual que os testes nao
    cobrirem. O Remotion continua no lugar."""
    monkeypatch.setenv("ATIVAVID_KARAOKE_PROPRIO", "0")
    ed = _ed(captions=_cap_karaoke())
    motivo = motivo_nao_suportado(ed, _public(tmp_path))
    assert motivo and "ATIVAVID_KARAOKE_PROPRIO" in motivo


def test_karaoke_com_janela_cai_para_o_remotion(tmp_path):
    """As janelas movem a legenda NO MEIO da linha e o template resolve isso
    por quadro; aqui a posicao e fixa por palavra. Recusa explicita, mesmo com
    o karaoke ja sendo o padrao."""
    ed = _ed(captions=_cap_karaoke(
        windows=[{"start": 1.0, "end": 2.0, "paddingBottom": 900}]))
    motivo = motivo_nao_suportado(ed, _public(tmp_path))
    assert motivo and "janela" in motivo


def _montar(tmp_path, ws, **cap):
    from app.render_proprio import Renderizador

    pub = _public(tmp_path)
    _palavras(pub, ws)
    ed = _ed(captions=_cap_karaoke(**cap))
    r = Renderizador(pub, ed, frames=300, fps=30, width=1080, height=1920)
    return r._montar_karaoke()


def test_agrupa_ate_maxwords(tmp_path):
    ws = [(f"p{i}", i * 300, i * 300 + 250) for i in range(6)]
    camadas = _montar(tmp_path, ws, maxWords=3)
    assert len(camadas) == 2, "6 palavras com maxWords=3 sao 2 linhas"
    assert [len(c.palavras) for c in camadas] == [3, 3]


def test_pontuacao_fecha_a_linha_antes_do_limite(tmp_path):
    """`isBreak` do template: a linha fecha na pontuacao mesmo com vaga."""
    ws = [("oi.", 0, 200), ("tudo", 300, 500), ("bem", 600, 800)]
    camadas = _montar(tmp_path, ws, maxWords=3)
    assert len(camadas) == 2
    assert len(camadas[0].palavras) == 1, "'oi.' tinha de fechar sozinha"


def test_a_linha_dura_ate_a_proxima_comecar(tmp_path):
    """No template a linha fica ate a SEGUINTE entrar, nao ate a fala acabar —
    e por isso que ela nao pisca nas pausas."""
    ws = [("um", 0, 100), ("dois", 2000, 2100)]
    camadas = _montar(tmp_path, ws, maxWords=1)
    assert len(camadas) == 2
    # 2000ms a 30fps = quadro 60; a primeira linha vai ate o 59
    assert camadas[0].inicio_f == 0
    assert camadas[0].fim_f == 59


def test_o_tempo_da_palavra_vem_do_timestamp_original(tmp_path):
    """Sem arredondar: o template interpola com limite fracionario."""
    ws = [("um", 0, 100), ("dois", 133, 250), ("tres", 266, 400)]
    camadas = _montar(tmp_path, ws, maxWords=3)
    ini = [p.inicio_f for p in camadas[0].palavras]
    assert ini[0] == 0
    assert abs(ini[1] - 133 / 1000 * 30) < 1e-6, ini
    assert abs(ini[2] - 266 / 1000 * 30) < 1e-6, ini


def test_entrada_de_7_quadros_com_subida_de_34(tmp_path):
    ws = [("um", 0, 100), ("dois", 300, 400)]
    p0 = _montar(tmp_path, ws, maxWords=2)[0].palavras[0]
    assert p0.enter == 7
    assert abs(p0.sobe - 34.0) < 1e-6
    assert p0.ease == "cubic", "o karaoke usa Easing.out(cubic), nao a bezier"


def test_pontuacao_final_nao_e_desenhada(tmp_path):
    """`cleanW` tira `.,!?…` do texto mostrado — mas `isBreak` olha o original."""
    from app.render_proprio import Renderizador

    pub = _public(tmp_path)
    _palavras(pub, [("fim.", 0, 300)])
    ed = _ed(captions=_cap_karaoke())
    r = Renderizador(pub, ed, frames=90, fps=30, width=1080, height=1920)
    largura_com = r.fonte(4, 76, 900).getlength("fim.")
    largura_sem = r.fonte(4, 76, 900).getlength("fim")
    camada = r._montar_karaoke()[0]
    assert len(camada.palavras) == 1
    # a caixa desenhada tem de caber na largura SEM o ponto
    desenhada = camada.palavras[0].alpha.shape[1]
    assert desenhada < largura_com + 90, (desenhada, largura_com)
    assert largura_sem < largura_com


def test_linha_larga_demais_encolhe_e_nao_vaza(tmp_path):
    """`fit = min(1, safeWidth/largura)`: reduz, nunca aumenta."""
    ws = [("palavraenorme", 0, 300), ("outrapalavraenorme", 400, 700),
          ("maisumagigante", 800, 1100)]
    camadas = _montar(tmp_path, ws, maxWords=3, safeWidth=720)
    ps = camadas[0].palavras
    esq = min(p.x0 for p in ps)
    dir_ = max(p.x0 + p.alpha.shape[1] for p in ps)
    assert esq > -60, f"vazou pela esquerda: {esq}"
    assert dir_ < 1080 + 60, f"vazou pela direita: {dir_}"


def test_linha_curta_nao_e_esticada(tmp_path):
    """Com `fit` limitado a 1, uma linha curta sai no tamanho natural."""
    from app.render_proprio import Renderizador

    pub = _public(tmp_path)
    _palavras(pub, [("oi", 0, 300)])
    ed = _ed(captions=_cap_karaoke())
    r = Renderizador(pub, ed, frames=90, fps=30, width=1080, height=1920)
    p0 = r._montar_karaoke()[0].palavras[0]
    natural = r.fonte(4, 76, 900).getlength("oi")
    assert p0.alpha.shape[1] < natural + 200, "a palavra curta foi esticada"


def test_palavra_vazia_nao_derruba(tmp_path):
    """Transcricao real traz token so de pontuacao; ele some no cleanW."""
    ws = [("...", 0, 100), ("ok", 200, 400)]
    camadas = _montar(tmp_path, ws, maxWords=3)
    assert sum(len(c.palavras) for c in camadas) == 1
