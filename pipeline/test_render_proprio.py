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
    # a mesma cue de 900 ms termina em quadros diferentes
    assert r30.camadas[0].fim_f == int(0.9 * 30)
    assert r24.camadas[0].fim_f == int(0.9 * 24)


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


def test_headline_maiuscula_so_em_tres_estilos():
    assert set(Renderizador.HL_MAIUSCULA) == {"card", "manchete", "carimbo"}

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
