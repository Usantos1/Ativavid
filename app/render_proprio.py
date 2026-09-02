# -*- coding: utf-8 -*-
"""Renderizador próprio de overlay — desenha as legendas sem navegador.

O Remotion renderiza o overlay abrindo um Chrome headless: 107 s para um vídeo
de 28 s nesta máquina, com a CPU acima de 90%. Este módulo desenha os MESMOS
gráficos direto (Pillow para os glifos, numpy para a composição) e entrega um
`overlay.mov` com alpha e SFX idêntico em contrato ao do Remotion — validação,
compose, cache e canary continuam funcionando sem saber quem desenhou.

Fidelidade medida no estudo (tools/render_benchmark/results/
RENDERIZADOR_PROPRIO.md): tinta mediana nosso/Remotion = 1,003 na tela inteira,
851 quadros, todos os elementos. Os 74 projetos reais do usuário usam
exatamente o conjunto coberto (legenda `stacked`, headline `realce`).

Todo elemento do template está portado — legendas (8 estilos), headline
(11), cartão final com logo, contador de lista, flashes, emoji, fonte de
marca e b-roll. O gate `motivo_nao_suportado` não barra mais nenhum
RECURSO: só o que é desconhecido (um estilo/preset/transição que o template
ganhou e este módulo ainda não conhece), o que não abre (cue ou fonte
ilegível), resolução fora de 1080x1920, e o emoji num Windows sem a Segoe
UI Emoji. Nesses casos o job cai para o Remotion, que continua no repo.

Kill switch: ATIVAVID_RENDER_PROPRIO=0.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
FONTES = REPO / "assets" / "fonts-render"
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

# ---- constantes do template (StackedCaptions/Main/PencilOutline) ------------
LETTER_SPACING = -1.5
LINE_HEIGHT = 1.12
MARGIN_TOP_EM = -0.34
WORD_PAD_EM = 0.06
# O CSS especifica sigma = raio/2, mas o que o Chrome desenha bate com
# sigma = raio (varrido de 0,5 a 2,5 no estudo; pico em 1,05).
BLUR_K = 1.05

# InsertCard.tsx: cartao fixo, 780x500 a 90px do topo, canto 28, sombra
# 0 18px 50px rgba(0,0,0,.45).
INSERT_W, INSERT_H, INSERT_TOP, INSERT_RAIO = 780, 500, 90, 28
# O cartao de sempre, em fracao do quadro 1080x1920: e o padrao de quem nao
# escolheu nada, para projeto antigo nao mudar de aparencia.
INSERT_X_PAD = 0.5
INSERT_Y_PAD = (INSERT_TOP + INSERT_H / 2) / 1920
INSERT_SIZE_PAD = INSERT_W / 1080


def _foco_do_insert(it: dict, chave: str) -> float:
    """Enquadramento 0..1 (0,5 = centro). `or 0.5` seria armadilha: fx=0.0
    (borda esquerda) e falsy e viraria centro — por isso o teste de None."""
    v = it.get(chave)
    if v is None:
        return 0.5
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


# Padrao do PISCAR (estroboscopio): opacidade por QUADRO nos 6 primeiros
# (entrada) / ultimos (saida). Espelho do PISCA do template.
_PISCA = (0.15, 1.0, 0.15, 1.0, 0.3, 1.0)


def _quique(p: float) -> float:
    """easeOutBounce clássico — a MESMA função do template (mudar lá e cá)."""
    n1, d1 = 7.5625, 2.75
    if p < 1 / d1:
        return n1 * p * p
    if p < 2 / d1:
        p -= 1.5 / d1
        return n1 * p * p + 0.75
    if p < 2.5 / d1:
        p -= 2.25 / d1
        return n1 * p * p + 0.9375
    p -= 2.625 / d1
    return n1 * p * p + 0.984375


def _elastico(p: float) -> float:
    """easeOutElastic clássico — espelho do template."""
    import math
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return (2 ** (-10 * p)) * math.sin((p * 10 - 0.75) * (2 * math.pi / 3)) + 1


def _zoom_do_insert(it: dict) -> float:
    """Zoom do conteudo (>=1): amplia ALEM do cover, ancorado em fx/fy —
    e o que torna o corte de UM lado verdadeiro no editor."""
    try:
        return min(4.0, max(1.0, float(it.get("zoom") or 1.0)))
    except (TypeError, ValueError):
        return 1.0


def geometria_do_insert(it: dict, larg: int, alt: int) -> tuple[int, int, float, float]:
    """(largura, altura, centro x, centro y) em pixels do cartao.

    `size` e a largura em fracao da LARGURA do quadro; a altura segue a
    proporcao do cartao (500/780) para ele nunca deformar.
    """
    def _f(chave, padrao):
        try:
            return float(it.get(chave, padrao))
        except (TypeError, ValueError):
            return padrao

    # Largura e ALTURA soltas: com a proporcao travada a imagem nunca cobria
    # a tela (o cartao e 780x500 e o quadro e 9:16). Pedido de 30/08: "se
    # quiser cobrir toda a tela deve permitir".
    fw = min(1.0, max(0.08, _f("w", _f("size", INSERT_SIZE_PAD))))
    cw = max(16, int(round(fw * larg)))
    padrao_h = (cw * INSERT_H / INSERT_W) / max(1, alt)
    fh = min(1.0, max(0.05, _f("h", padrao_h)))
    ch = max(16, int(round(fh * alt)))
    cx = min(1.0, max(0.0, _f("x", INSERT_X_PAD))) * larg
    cy = min(1.0, max(0.0, _f("y", INSERT_Y_PAD))) * alt
    return cw, ch, cx, cy

# Emoji: o Chrome no Windows desenha com a Segoe UI Emoji do SISTEMA. Lendo o
# MESMO arquivo, o glifo sai identico ao das versoes anteriores — e nada e
# redistribuido junto com o app. Se ela nao existir, o gate manda o caso para
# o Remotion (que tambem cairia na fonte do sistema).
EMOJI_FONT = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "seguiemj.ttf"
EMOJI_FAIXAS = ((0x231A, 0x23FF), (0x2600, 0x27BF), (0x2B00, 0x2BFF),
                (0x1F000, 0x1FAFF))
# FE0F (apresentacao emoji), ZWJ, keycap e tons de pele continuam a MESMA
# sequencia — separa-los desenharia dois glifos onde o Chrome desenha um.
EMOJI_CONT = {0xFE0F, 0x200D, 0x20E3} | set(range(0x1F3FB, 0x1F400))


def tem_emoji(texto: str) -> bool:
    return any(_eh_emoji(c) for c in texto or "")


def _eh_emoji(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in EMOJI_FAIXAS)


def fatiar_emoji(texto: str):
    """[(trecho, eh_emoji)] — trechos de emoji separados do texto comum."""
    partes, buf, modo = [], "", None
    for ch in texto:
        e = _eh_emoji(ch)
        if not e and ord(ch) in EMOJI_CONT and modo is True:
            buf += ch                    # continuacao da sequencia anterior
            continue
        if modo is None or e == modo:
            buf += ch
            modo = e
        else:
            partes.append((buf, modo))
            buf, modo = ch, e
    if buf:
        partes.append((buf, modo))
    return partes

SHADOW = [(0, 5, 9, 0.5)]
SHADOW_STRONG = [(0, 5, 10, 0.55), (0, 2, 3, 0.55)]

FONT_FILE = {
    0: ("Poppins-BlackItalic.ttf", None),
    1: ("Poppins-Regular.ttf", None),
    2: ("PlayfairDisplay-Italic[wght].ttf", "#ff5200"),
    3: ("Poppins-ExtraBold.ttf", None),
    4: ("Poppins-Black.ttf", None),
    5: ("Lora[wght].ttf", None),           # scatter: serifada
    6: ("Lora-Italic[wght].ttf", None),
    # 600. O cartao final usa 900 na primeira linha e 600 nas demais
    # (`fontWeight: i === 0 ? 900 : 600` no EndCardInner); sem este indice a
    # segunda linha caia no 3 (ExtraBold, 800).
    7: ("Poppins-SemiBold.ttf", None),
}
FONT_WGHT = {2: 900}

# Catalogo de fontes da marca (fonts.ts): id -> (arquivo, teto de peso).
# O teto existe porque uma fonte de peso unico (Anton/Bebas/Archivo) nao tem
# negrito — pedir 900 nela daria negrito FALSO. O template clampa igual.
MARCA_FONTES = {
    "poppins":    ("Poppins-Black.ttf", None),
    "inter":      ("Inter[opsz,wght].ttf", None),
    "montserrat": ("Montserrat[wght].ttf", None),
    "playfair":   ("PlayfairDisplay-Italic[wght].ttf", None),
    "lora":       ("Lora[wght].ttf", 700),
    "anton":      ("Anton-Regular.ttf", 400),
    "bebas":      ("BebasNeue-Regular.ttf", 400),
    "archivo":    ("ArchivoBlack-Regular.ttf", 400),
}

# PencilOutline.tsx — o caminho do traço, já parseado (viewBox 312x150)
TRACO_INICIO = (30.0, 78.0)
TRACO_CURVAS = [
    ((26, 40), (120, 20), (190, 24)),
    ((262, 28), (300, 52), (288, 82)),
    ((276, 114), (150, 132), (78, 122)),
    ((28, 114), (8, 92), (34, 66)),
    ((50, 50), (96, 40), (150, 42)),
]
TRACO_VB = (312.0, 150.0)
TRACO_PX = 9
# O `ImageDraw.line` do PIL NAO suaviza: a borda sai em degraus, e num traco
# quase horizontal (o circulo de enfase e uma elipse deitada) o serrilhado
# aparece na tela. Medido em 29/08 contra o Remotion no MESMO quadro: o
# navegador tinha 649 pixels de meio-tom na borda e o motor proprio ZERO.
# Desenhar 3x maior e reduzir por media de area da a suavizacao que falta.
# 6x (nao 3x): medido na DIAGONAL do laco, que e onde o degrau aparece —
# com 3x a borda tinha 0,225 de meio-tom por nucleo contra 0,241 do
# navegador; com 6x, 0,239. Custa 0,07s por video na montagem das camadas
# e nada no desenho dos quadros.
TRACO_SS = 6


def _mascara_linha(pontos, lt: int, at: int, tx0: float, ty0: float,
                   largura: float, raio_x: float | None = None):
    """Mascara "L" do traco, com borda suave (supersampling).

    `raio_x` e o raio HORIZONTAL da ponta arredondada, quando ele nao e
    igual ao vertical. O marca-texto precisa disso: o SVG dele e esticado
    com `preserveAspectRatio="none"` e SEM `vectorEffect`, entao o
    navegador estica a ponta redonda junto — ela vira uma elipse, mais
    larga que alta. Desenhando ponta redonda a faixa saia 130px mais
    estreita que a do preview (65 de cada lado, medido). O circulo NAO
    passa por isso: la o SVG usa `vectorEffect="non-scaling-stroke"`, que
    segura a espessura em pixels de tela, e a ponta e redonda mesmo.
    """
    lt, at = max(1, int(lt)), max(1, int(at))
    grande = Image.new("L", (lt * TRACO_SS, at * TRACO_SS), 0)
    if len(pontos) >= 2:
        dr = ImageDraw.Draw(grande)
        desl = [((x - tx0) * TRACO_SS, (y - ty0) * TRACO_SS)
                for x, y in pontos]
        dr.line(desl, fill=255,
                width=max(1, int(round(largura * TRACO_SS))), joint="curve")
        ry = largura * TRACO_SS / 2
        rx = ry if raio_x is None else raio_x * TRACO_SS
        for x, y in (desl[0], desl[-1]):
            dr.ellipse([x - rx, y - ry, x + rx, y + ry], fill=255)
    return grande.resize((lt, at), Image.BOX)
TRACO_COR = "#39E508"
# Marca-texto (MarkerHighlight.tsx): banda unica com leve inclinacao, no
# MESMO viewBox 312x150 do traco — geometria compartilhada entre motores.
MARCADOR_COR = "#FFE94A"
MARCADOR_PONTOS = ((8.0, 84.0), (90.0, 82.0), (210.0, 80.0), (304.0, 76.0))
MARCADOR_LARG_VB = 92.0     # strokeWidth em unidades do viewBox (escala junto)
MARCADOR_ALPHA = 0.85
MARCADOR_CAIXA = (-0.07, -0.16, 1.14, 1.38)  # left/top/width/height do svg
TRACO_SOMBRA = (0, 3, 8, 0.45)
TRACO_CAIXA = (-0.10, -0.22, 1.20, 1.50)   # esq, topo, larg, alt (fração)
# A caixa do traco e "120% x 150% da palavra", com a palavra medida pela
# ENTRELINHA (tam * 1.12) — igual ao navegador. Isto foi conferido em 29/08
# pelas PONTAS do laco, que o texto nao esconde: esquerda 1281 e direita
# 1258 no motor proprio contra 1281 e 1256 no Remotion. Medir pela BASE do
# laco engana: no navegador o arco de baixo passa atras das letras e some,
# e a base visivel fica ~36px mais alta do que a geometria real.

HL_MIN = 40

# CutFlashes (CustomGraphics.tsx)
VIDEO_LAG = 1
FLASH_LEAD, FLASH_LEN = 2, 7

# SFX (StackedCaptions/Main)
CLICK_VOL = 0.55
STACK_CLICK_VOL = min(0.28, CLICK_VOL * 0.5)
SCRATCH_VOL = 0.28
WHOOSH_VOL = 0.1
# O whoosh da manchete NAO e o mesmo em todo estilo. Lido um por um no
# `Main.tsx`: quase todos tem `volume={0.1}`, o `carimbo` tem `{0.12}` e a
# `pilula` NAO TEM `<Sfx>` NENHUM. O motor proprio tocava 0,1 em todos —
# ou seja, um som a mais na pilula e um som fraco demais no carimbo.
WHOOSH_HL = {"carimbo": 0.12, "pilula": None}


def _pos(d: dict, chave: str, padrao: float) -> float:
    """`??` do template, nao `or`.

    Toda ancora de posicao tem 0 como valor LEGITIMO: manchete colada no topo
    (paddingTop=0), legenda colada na base (paddingBottom=0), bloco no alto da
    tela (offsetY=0). Com `or` o motor proprio trocava esse 0 pelo padrao do
    estilo — arrastar ate a borda devolvia a manchete 299px mais para baixo,
    calado (medido). O template usa `??` justamente por isso.
    """
    v = d.get(chave)
    # `""` conta como ausente: com o `or` antigo uma string vazia caia no
    # padrao, e aqui viraria `float("")` — troca de defeito calado por
    # excecao no meio do render.
    if v is None or v == "":
        return float(padrao)
    try:
        return float(v)
    except (TypeError, ValueError):
        print(f"  [warn] {chave}={v!r} nao e numero — usando {padrao}", flush=True)
        return float(padrao)


# ---------------------------------------------------------------- suporte ----
# Como cada estilo de legenda guarda a altura. `base` diz o que o numero
# significa; `chave` e o campo em edit-data["captions"]. Os dois motores leem
# exatamente estes campos (render_proprio e StackedCaptions/ScatterCaptions/
# ImpactCaptions no template).
LEGENDA_ANCORAS = {
    "stacked": {"chave": "stackedOffsetY", "base": "centro_meio", "padrao": 0.156},
    "scatter": {"chave": "scatterOffsetY", "base": "centro_frac", "padrao": 0.72},
    "impacto": {"chave": "paddingBottom", "base": "bottom_px", "padrao": 430.0},
}


def ancoras_de_legenda() -> dict[str, dict[str, object]]:
    """{estilo: {chave, base, padrao}} — so os estilos com botao LIVRE.

    A familia `simples` fica de fora de proposito: ela posiciona por
    `position` discreto, entao arrastar nao teria onde gravar.
    """
    return {k: dict(v) for k, v in LEGENDA_ANCORAS.items()}


def legenda_y_para_valor(estilo: str, y_px: float, altura: int = 1920):
    """Converte a altura na TELA para o botao do estilo. None se nao suporta.

    `y_px` e o ponto que a ancora do estilo descreve: o CENTRO do bloco para
    stacked/scatter, a BASE dele para o impacto.
    """
    a = LEGENDA_ANCORAS.get(str(estilo or "stacked"))
    if not a or altura <= 0:
        return None
    base = a["base"]
    if base == "centro_meio":          # centro = h/2 + h*off
        return a["chave"], round((y_px - altura / 2) / altura, 4)
    if base == "centro_frac":          # centro = h*off
        return a["chave"], round(y_px / altura, 4)
    return a["chave"], round(altura - y_px)      # bottom_px


def legenda_valor_para_y(estilo: str, valor, altura: int = 1920):
    """Inversa de `legenda_y_para_valor` — usada pelo editor e pelo teste."""
    a = LEGENDA_ANCORAS.get(str(estilo or "stacked"))
    if not a:
        return None
    v = float(a["padrao"] if valor is None else valor)
    base = a["base"]
    if base == "centro_meio":
        return altura / 2 + altura * v
    if base == "centro_frac":
        return altura * v
    return altura - v


def ancoras_de_headline() -> dict[str, dict[str, object]]:
    """{estilo: altura padrao + tipografia} — tudo que o editor precisa.

    O editor desenha a headline arrastavel a partir daqui, entao ele mostra
    exatamente onde o motor vai desenhar. Sem isto, a tabela teria uma
    terceira copia no JavaScript e as tres sairiam de sincronia.

    Vai junto a TIPOGRAFIA do estilo (caixa alta, pesos, teto de fonte,
    largura util, entrelinha) porque a caixa da headline muda de altura com
    ela: tres estilos sobem tudo para maiuscula e cada um tem seu teto de
    tamanho. Sem esses campos o editor mostrava sempre a mesma fonte de 36px
    em caixa baixa, e a manchete — que se ancora pela BASE — aparecia numa
    altura que o render nao usava.
    """
    out: dict[str, dict[str, object]] = {}
    for nome, spec in Renderizador.HL_STYLES.items():
        pesos, cap, safe_w, lh, top = spec
        base = ({"base": "bottom", "px": 140} if nome == "manchete"
                # a manchete se ancora pela BASE (paddingBottom, padrao 140)
                else {"base": "top", "px": int(top)})
        out[nome] = {
            **base,
            "maiuscula": nome in Renderizador.HL_MAIUSCULA,
            "pesos": list(pesos),
            "cap": int(cap),
            "safeWidth": float(safe_w),
            "lineHeight": float(lh),
            "minimo": HL_MIN,
        }
    return out


# O karaoke no motor rapido. Aprovado pelo usuario em 22/08/2026, depois da
# comparacao quadro a quadro (deslocamento 0-1px, tinta 1,000, sombra
# equivalente, entrada dentro de 0,2 quadro) e de um end-to-end de producao.
#
# `ATIVAVID_KARAOKE_PROPRIO=0` DESLIGA -- e o interruptor de emergencia, no
# mesmo estilo de `ATIVAVID_RENDER_PROPRIO=0` e `ATIVAVID_PREP_SOURCE=0`. Com
# ele desligado o karaoke volta pelo Remotion e o motivo fica gravado em
# `overlayEngineSkip`, como qualquer outra recusa. O Remotion nao sai: ele
# continua sendo a queda das janelas de posicao e de tudo que o gate recusar.
# MEDIDO DE NOVO em 30/08: 2,557 de tinta contra o template — o karaoke
# saia com a legenda `stacked` desenhada POR CIMA dele, porque o
# despachante nao zerava `self.cues` neste ramo (o unico dos cinco sem a
# linha). Consertado no mesmo dia: 2,557 -> 1,010, de volta a faixa dos
# outros catorze estilos. Ver `test_karaoke_sozinho.py`.
def karaoke_aprovado() -> bool:
    return (os.environ.get("ATIVAVID_KARAOKE_PROPRIO", "").strip()
            not in ("0", "false", "no", "off"))


def motivo_nao_suportado(edit_data: dict[str, Any], public: Path) -> str | None:
    """None = o renderizador próprio cobre este projeto; senão o motivo."""
    if (os.environ.get("ATIVAVID_RENDER_PROPRIO") or "").strip() == "0":
        return "desligado por ATIVAVID_RENDER_PROPRIO=0"
    # Import LOCAL, como o de `video_layouts` neste mesmo arquivo: quem so
    # olha o portao nao precisa carregar o resto.
    from app import caption_styles as CAPTION_STYLES
    caps = edit_data.get("captions") or {}
    # Os 4 estilos do catalogo, todos validados quadro a quadro contra o
    # Remotion (tinta mediana; 140 quadros de fala continua cada):
    #   serifada 1,009 · recorte 1,014 · scatter 1,024 · bloco 1,033
    #   classica 1,036 · simples 1,059 · impacto 1,094
    estilo = caps.get("style") or "stacked"
    # A lista vive em `app/caption_styles.py`: ela era repetida aqui, no
    # run_fast e no catalogo da tela — e a IA nao tinha lista nenhuma. Um
    # estilo novo que esquecesse uma das copias nao dava erro, so nao
    # acontecia.
    permitidos = CAPTION_STYLES.TODOS
    # Tudo daqui para baixo so importa se a legenda VAI ser desenhada. Com ela
    # desligada o pipeline grava `style="karaoke"` fixo (run_fast: `captions if
    # cap_enabled else "karaoke"`), e sem esta guarda o job perderia o motor
    # rapido por causa de uma legenda que nao aparece no video.
    #
    # `enabled` AUSENTE conta como ligada, de proposito: dizer "suportado" por
    # engano faz o motor desenhar um estilo que ele nao sabe e o video sai
    # errado; dizer "nao suportado" por engano so custa tempo.
    if caps.get("enabled", True):
        if estilo in ("karaoke", "bolha"):
            if estilo == "karaoke" and not karaoke_aprovado():
                return "karaoke desligado por ATIVAVID_KARAOKE_PROPRIO=0"
            if caps.get("windows") or []:
                # As janelas movem a legenda NO MEIO da linha e o template
                # resolve isso POR QUADRO (`CaptionShell` procura a janela em
                # `fromFrame + local`). Aqui cada palavra tem posicao fixa,
                # entao uma linha que atravessasse a borda de uma janela
                # ficaria parada onde o template a moveria.
                return "karaoke com janelas de posicao"
        if estilo not in permitidos:
            return f"estilo de legenda '{caps.get('style')}'"
    hook = edit_data.get("hook") or {}
    if hook.get("enabled"):
        if (hook.get("style") or "outline") not in Renderizador.HL_STYLES:
            return f"estilo de headline '{hook.get('style')}'"
    els = edit_data.get("elements") or {}
    if els.get("emojiCaptions") and not EMOJI_FONT.exists():
        return "emoji nas legendas (Segoe UI Emoji ausente)"
    if int(edit_data.get("width") or 1080) != 1080 or int(edit_data.get("height") or 1920) != 1920:
        return f"resolucao {edit_data.get('width')}x{edit_data.get('height')}"
    for tr in edit_data.get("transitions") or []:
        if tr.get("type") != "flash":
            return f"transicao '{tr.get('type')}'"
    cues_p = public / "caption-cues.json"
    if cues_p.exists():
        try:
            c = json.loads(cues_p.read_text(encoding="utf-8-sig"))
            c = c if isinstance(c, list) else (c.get("cues") or [])
            for x in c:
                if (x.get("preset") or "STACK_MIXED") not in (
                        "STACK_MIXED", "SOLO_BIG", "SOLO_OUTLINE"):
                    return f"preset de cue '{x.get('preset')}'"
        except (OSError, json.JSONDecodeError):
            return "caption-cues ilegivel"
    for nome in FONT_FILE.values():
        if not (FONTES / nome[0]).exists():
            return f"fonte ausente: {nome[0]}"
    return None


def _tem_transparencia(im) -> bool:
    """A imagem usa MESMO o canal alpha, ou so o carrega?

    Um JPEG convertido para RGBA tem alpha 255 em tudo — tratar isso como
    arte tiraria o cartao de fotos comuns. O teste e pelo minimo.
    """
    try:
        faixa = im.getchannel("A").getextrema()
    except (ValueError, KeyError):
        return False
    return bool(faixa and faixa[0] < 250)


def _cor_hex(h: str) -> np.ndarray:
    """#rrggbb -> array 0..1. Usado fora da classe (camada do layout)."""
    t = str(h or "#ffffff").lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    try:
        return np.array([int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4)],
                        dtype=np.float32)
    except ValueError:
        return np.ones(3, dtype=np.float32)


# ---------------------------------------------------------------- modelo ----
@dataclass
class Palavra:
    x0: int
    y0: int
    rgb: np.ndarray
    alpha: np.ndarray
    sombra: np.ndarray
    inicio_f: float
    enter: int
    janela: tuple[float, float] | None = None
    sobe: float = 46.0
    # Opacidade do estagio, quando ele e um quadro de uma animacao de
    # TAMANHO. Animar tamanho aqui e rasterizar em estagios e dar a cada um
    # a sua `janela`; sem este campo a janela forcaria opacidade 1,0 e a
    # palavra apareceria de uma vez, sem o fade.
    opac: float = 1.0
    # Deslocamento HORIZONTAL da entrada (px), aplicado como o `sobe`:
    # anda com (1-opacidade). E o `deslizar` da headline (vem de -56px).
    desliza: float = 0.0
    # Curva de entrada. So o `StackedCaptions.tsx` usa a bezier
    # (`Easing.bezier(0.16, 1, 0.3, 1)`, linha 77); a headline, o cartao
    # final, o scatter e o impacto usam `Easing.out(Easing.cubic)`, que e o
    # padrao aqui. Trocar isso no motor INTEIRO deixava a headline — que fica
    # na tela nos primeiros 4s de todo video — com a curva errada.
    ease: str = "cubic"


@dataclass
class Camada:
    inicio_f: int
    fim_f: int
    palavras: list[Palavra] = field(default_factory=list)
    saida_f: float = 1e9
    dur_f: float = 0.0
    exit_abrupto: bool = False
    exit_fade: bool = False
    dim: float = 0.0
    dim_fade: int = 10
    caixa: tuple[int, int, int, int] | None = None
    insert: tuple | None = None      # (imagem do cartao, quadros) — Ken-Burns
    # take de VIDEO: (pasta dos quadros ja no tamanho do cartao, mascara)
    insert_quadros: tuple | None = None
    # (largura, altura, centro x, centro y) do cartao — o usuario pode mover
    # e redimensionar a imagem que ele mesmo pos
    insert_caixa: tuple | None = None
    # animacao de entrada do cartao: padrao | pop | deslizar | fade | zoom
    insert_entrada: str = "padrao"
    # animacao de saida: suave | encolher | deslizar | corte
    insert_saida: str = "suave"
    cache_chave: tuple | None = None
    cache_tela: np.ndarray | None = None
    cache_pronto: np.ndarray | None = None

    def saida(self, fl: float) -> tuple[float, float, float]:
        if self.exit_abrupto:
            return (0.0 if fl >= self.dur_f - 2 else 1.0), 0.0, 0.0
        if fl <= self.saida_f:
            return 1.0, 0.0, 0.0
        p = min(1.0, (fl - self.saida_f) / max(1e-6, self.dur_f - self.saida_f))
        if self.exit_fade:
            return 1.0 - p, 0.0, 0.0
        return 1.0 - p, -55.0 * p, 14.0 * p


def _tabela_ease_out(n: int = 512) -> list[float]:
    """`Easing.bezier(0.16, 1, 0.3, 1)` do template, amostrada.

    O motor usava `1-(1-t)^3` (que e `Easing.out(Easing.cubic)`), uma curva
    PARECIDA mas nao a mesma: a diferenca de opacidade chega a **0,264** no
    primeiro terco da entrada — em t=0,2 o template ja esta em 0,75 e a
    cubica em 0,49. Como a subida de 46px sai da mesma opacidade, a palavra
    tambem deslizava mais devagar.

    Isso valia para TODA palavra de TODA legenda, e a validacao por razao de
    tinta que aprovou o motor nao pegaria: ela mede AREA sobre a cue inteira,
    e a entrada e uma fracao dela.

    A curva e parametrica (dado x, achar s com Bx(s)=x e devolver By(s));
    resolver isso por chamada seria caro num laco por palavra por quadro,
    entao vira tabela uma vez.
    """
    x1, y1, x2, y2 = 0.16, 1.0, 0.3, 1.0
    amostras = []
    passos = n * 8
    for k in range(passos + 1):
        sv = k / passos
        u = 1.0 - sv
        bx = 3 * u * u * sv * x1 + 3 * u * sv * sv * x2 + sv ** 3
        by = 3 * u * u * sv * y1 + 3 * u * sv * sv * y2 + sv ** 3
        amostras.append((bx, by))
    tab, j = [], 0
    for i in range(n + 1):
        x = i / n
        while j + 1 < len(amostras) and amostras[j + 1][0] < x:
            j += 1
        x0, v0 = amostras[j]
        x2_, v2_ = amostras[min(j + 1, len(amostras) - 1)]
        f = 0.0 if x2_ <= x0 else (x - x0) / (x2_ - x0)
        tab.append(min(1.0, max(0.0, v0 + (v2_ - v0) * f)))
    tab[0], tab[-1] = 0.0, 1.0
    return tab


_EASE_OUT = _tabela_ease_out()


def _ease_out(t: float) -> float:
    """A curva do template, por tabela + interpolacao linear."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    x = t * (len(_EASE_OUT) - 1)
    i = int(x)
    f = x - i
    return _EASE_OUT[i] + (_EASE_OUT[i + 1] - _EASE_OUT[i]) * f


def _opacidade(p: Palavra, fl: float) -> float:
    if p.janela is not None:
        ini, fim = p.janela
        return p.opac if ini <= fl < fim else 0.0
    # `enter <= 0` = SEM entrada: a palavra ja esta pronta no primeiro quadro
    # dela. Sem isto o proprio `fl <= inicio_f` abaixo devolveria 0 no quadro 0
    # e nao existiria jeito de desenhar algo ja presente na abertura. Nenhuma
    # outra chamada do arquivo usa enter <= 0 (o minimo em uso e 1), entao isto
    # so muda quem pedir explicitamente.
    if p.enter <= 0:
        return 0.0 if fl < p.inicio_f else 1.0
    if fl <= p.inicio_f:
        return 0.0
    t = min(1.0, (fl - p.inicio_f) / max(1, p.enter))
    return _ease_out(t) if p.ease == "bezier" else 1 - (1 - t) ** 3


class Renderizador:
    """Um por overlay. Guarda config, fontes e as camadas montadas."""

    def __init__(self, public: Path, edit_data: dict[str, Any], *,
                 frames: int, fps: float, width: int = 1080, height: int = 1920):
        self.public = public
        self.ed = edit_data
        self.frames = int(frames)
        self.fps = float(fps)
        self.w, self.h = int(width), int(height)
        caps = edit_data.get("captions") or {}
        self.scale = (self.w / 1080) * float(caps.get("fontScale") or 1.0)
        self.avail = self.w - 180
        self.base_y = round(self.h * _pos(caps, "stackedOffsetY", 0.156))
        accent = caps.get("emphasisAccent") or "#ff5200"
        self.font_file = dict(FONT_FILE)
        self.font_file[2] = (FONT_FILE[2][0], accent)
        self.cor_traco = caps.get("circleAccent") or TRACO_COR
        # "marca-texto": pinta o fundo da enfase em vez de circular (opt-in,
        # pedido do usuario 26/08). Mesmas cues SOLO_OUTLINE, mesmo tempo,
        # mesmo scratch; so o desenho muda — espelho do MarkerHighlight.tsx.
        self.enfase_marcador = str(caps.get("emphasisStyle") or "") == "marker"
        self.cor_marcador = caps.get("circleAccent") or MARCADOR_COR
        sfx = caps.get("sfx") or {}
        self.sfx_on = sfx.get("enabled") is not False
        # `_pos`, nao `or`: volume 0 e "silencia SO este som", um valor de
        # fato — com `or` ele virava o padrao. Nada no app escreve estes
        # knobs hoje (sao de edit-data na mao), mas o template le com `??`.
        self.click_vol = _pos(sfx, "clickVolume", CLICK_VOL)
        self.scratch_vol = _pos(sfx, "scratchVolume", SCRATCH_VOL)
        self.stack_vol = _pos(sfx, "stackClickVolume",
                              min(0.28, self.click_vol * 0.5))
        # O som da legenda EMPILHADA e um tique de digitar (30ms), nao o
        # clique cheio de 0,406s: num video de 33s sao ~42 legendas, uma a
        # cada 0,8s. "cliques de digitando leves nao tantos whosh"
        # (30/08). Mesmo nome de knob do template.
        self.stack_click = str(sfx.get("stackClickFile") or "click.mp3")
        self._fontes: dict = {}
        self._glifos_faltando: dict = {}
        self.marca_cap = self._resolver_marca(
            caps.get("fontFamily"), edit_data.get("brandFontFile"))
        self.marca_hook = self._resolver_marca(
            (edit_data.get("hook") or {}).get("fontFamily"),
            edit_data.get("brandFontFile"))
        d = json.loads((public / "caption-cues.json").read_text(encoding="utf-8-sig")) \
            if (public / "caption-cues.json").exists() else []
        self.cues = d if isinstance(d, list) else (d.get("cues") or [])
        self.camadas: list[Camada] = []
        self.eventos_sfx: list[tuple[str, float, float]] = []   # (arquivo, seg, volume)
        # Efeitos postos na mao pelo usuario. Entram junto dos automaticos:
        # o mixer nao distingue quem pediu o som, so quando ele toca.
        for ev in (edit_data.get("sfxManual") or []):
            try:
                nome = str((ev or {}).get("src") or "").strip()
                em = float((ev or {}).get("atSec"))
            except (TypeError, ValueError):
                continue
            if not nome or em < 0:
                continue
            vol = (ev or {}).get("volume")
            try:
                vol = float(vol) if vol is not None else 0.5
            except (TypeError, ValueError):
                vol = 0.5
            self.eventos_sfx.append((nome, em, max(0.0, min(1.5, vol))))
        # Tinta do layout (degrade/vinheta/cinema/borda): estatica, entao ela
        # e o FUNDO do buffer — ver `_gravar_video`.
        self.fundo = camada_do_layout(
            edit_data.get("videoLayout"), self.w, self.h,
            (edit_data.get("hook") or {}).get("accent") or "#ff5200")
        self._montar_tudo()

    # ------------------------------------------------------------ fontes ----
    def _resolver_marca(self, ident: str, arquivo_marca: str | None):
        """(arquivo, teto de peso) da fonte de marca, ou None.

        `arquivo` (id "arquivo") e a fonte PROPRIA do usuario, que o pipeline
        copia para public/fonts — nunca redistribuida pelo app.
        """
        ident = (ident or "").strip().lower()
        if not ident:
            return None
        # `arquivo` ou `arquivo:<nome>` — o pipeline ja resolveu QUAL e
        # copiou para public/fonts; aqui so importa que e a do usuario.
        if ident.startswith("arquivo"):
            if not arquivo_marca:
                return None
            cam = self.public / str(arquivo_marca)
            if not cam.exists():
                return None
            try:
                ImageFont.truetype(str(cam), 40)
            except OSError:
                print(f"  [warn] fonte da marca ilegivel: {cam.name}", flush=True)
                return None
            return (str(cam), None)
        item = MARCA_FONTES.get(ident)
        if not item:
            return None
        cam = FONTES / item[0]
        return (str(cam), item[1]) if cam.exists() else None


    def fonte(self, idx: int, tam: int, peso: int | None = None,
              marca: str | None = "cap") -> ImageFont.FreeTypeFont:
        """`marca`: "cap", "hook" ou None (tipografia assinada do template).

        Nem todo desenho aceita a fonte da marca. O template diz quem aceita
        pelo import: SimpleCaptions/Scatter/Impact usam `capFamily`,
        ListCounter usa `hookFamily`, e StackedCaptions nao importa nenhum
        dos dois — o stacked e o end card mantem a tipografia do template de
        proposito, porque a familia deles E o estilo (Poppins italico 900 +
        Playfair laranja). O editor ja segue essa regra
        (`style !== 'stacked' && FONT_CSS[captionFont]`); so o motor proprio
        vestia a marca em tudo.
        """
        arq, teto = str(FONTES / self.font_file[idx][0]), None
        escolhida = self.marca_hook if marca == "hook" else (
            self.marca_cap if marca == "cap" else None)
        if escolhida:
            arq, teto = escolhida
        chave = (arq, tam, peso, teto)
        if chave not in self._fontes:
            f = ImageFont.truetype(arq, tam)
            eixo = peso if peso is not None else FONT_WGHT.get(idx)
            if eixo and teto is not None:
                eixo = min(eixo, teto)      # sem negrito falso
            if eixo:
                try:
                    f.set_variation_by_axes([eixo])
                except (OSError, AttributeError):
                    pass
            self._fontes[chave] = f
        return self._fontes[chave]

    def fit_font(self, texto: str, base: int = 86, avail: float | None = None,
                 fator: float = 0.58) -> int:
        avail = self.avail / self.scale if avail is None else avail
        n = max(1, len(texto.strip()))
        return int(avail // (n * fator)) if n * base * fator > avail else base

    def _glifo_falta(self, f: ImageFont.FreeTypeFont, ch: str) -> bool:
        """True quando a fonte nao tem o glifo (desenharia .notdef/DEMO).

        Sem fontTools no venv, compara a mascara do char com a de um code
        point garantidamente sem glifo — igual = faltando. Cacheado por
        (arquivo, char): a pergunta se repete a cada palavra.
        """
        chave = (getattr(f, "path", id(f)), ch)
        if chave not in self._glifos_faltando:
            probe = ImageFont.truetype(f.path, 48) if hasattr(f, "path") else f
            def _tinta(c: str) -> np.ndarray:
                img = Image.new("L", (64, 64), 0)
                ImageDraw.Draw(img).text((4, 4), c, font=probe, fill=255)
                return np.asarray(img)

            notdef = _tinta("\N{TAG LATIN SMALL LETTER A}")
            self._glifos_faltando[chave] = bool(
                np.array_equal(_tinta(ch), notdef))
        return self._glifos_faltando[chave]

    def _so_caixa_alta(self, f: ImageFont.FreeTypeFont) -> bool:
        """True para fonte SO-MAIUSCULAS (o glifo de 'a' E o de 'A').

        A Integral do usuario e assim: tudo que ela desenha e capital. O
        glifo que falta nela nao pode descer para a reserva em minuscula —
        sairia um ç pequeno no meio de capitais ("PROMOçãO"), letras de
        tamanhos diferentes na mesma palavra (reclamacao dele, 01/09).
        """
        chave = (getattr(f, "path", id(f)), "__caixa_alta__")
        if chave not in self._glifos_faltando:
            probe = ImageFont.truetype(f.path, 48) if hasattr(f, "path") else f

            def _tinta(c):
                img = Image.new("L", (64, 64), 0)
                ImageDraw.Draw(img).text((4, 4), c, font=probe, fill=255)
                return np.asarray(img)

            self._glifos_faltando[chave] = bool(
                np.array_equal(_tinta("a"), _tinta("A"))
                and np.array_equal(_tinta("g"), _tinta("G")))
        return self._glifos_faltando[chave]

    def _char_para_reserva(self, f: ImageFont.FreeTypeFont, ch: str) -> str:
        """O char como a RESERVA deve desenha-lo: fonte so-caixa-alta sobe
        a minuscula (ç -> Ç), para toda letra sair do mesmo tamanho."""
        return ch.upper() if ch.islower() and self._so_caixa_alta(f) else ch

    def _fonte_reserva(self, tam: int, peso: int | None) -> ImageFont.FreeTypeFont:
        """A fonte que cobre glifo faltando — Poppins, no peso mais proximo.

        E o que o Chrome faz: a pilha de familias do template termina em
        Poppins, e um "ção" numa fonte DEMO sem acento sai na fonte
        vizinha, nao como carimbo. O motor desenhava o carimbo (a Integral
        DEMO do usuario nao tem NENHUM acento nem ç — medido em 01/09).
        """
        peso = peso or 700
        idx = 4 if peso >= 800 else (3 if peso >= 700 else (7 if peso >= 500 else 1))
        arq = str(FONTES / FONT_FILE[idx][0])
        chave = ("__reserva__", arq, tam)
        if chave not in self._fontes:
            self._fontes[chave] = ImageFont.truetype(arq, tam)
        return self._fontes[chave]

    def _mascara(self, f: ImageFont.FreeTypeFont, texto: str,
                 ls: float = LETTER_SPACING) -> np.ndarray:
        asc, desc = f.getmetrics()
        # Glifo que falta na fonte da marca sai na reserva (como o Chrome);
        # o avanco passa a ser acumulado por char, com a fonte que DESENHA.
        tem_falta = any(self._glifo_falta(f, c) for c in set(texto)
                        if not c.isspace())
        if not tem_falta:
            larg = int(f.getlength(texto) + ls * len(texto)) + 8
            img = Image.new("L", (max(1, larg), asc + desc + 8), 0)
            d = ImageDraw.Draw(img)
            x = 0.0
            for i, ch in enumerate(texto):
                d.text((x, 0), ch, font=f, fill=255)
                x = f.getlength(texto[: i + 1]) + ls * (i + 1)
            return np.asarray(img, dtype=np.float32) / 255.0
        fr = self._fonte_reserva(int(round(f.size)), None)
        asc_r, _ = fr.getmetrics()
        partes = [(ch, self._glifo_falta(f, ch) and not ch.isspace())
                  for ch in texto]
        larg = sum(
            fr.getlength(self._char_para_reserva(f, ch)) if falta
            else f.getlength(ch) for ch, falta in partes)
        larg = int(larg + ls * len(texto)) + 8
        img = Image.new("L", (max(1, larg), asc + desc + 8), 0)
        d = ImageDraw.Draw(img)
        x = 0.0
        for ch, falta in partes:
            if falta:
                cr = self._char_para_reserva(f, ch)
                d.text((x, asc - asc_r), cr, font=fr, fill=255)
                x += fr.getlength(cr) + ls
            else:
                d.text((x, 0), ch, font=f, fill=255)
                x += f.getlength(ch) + ls
        return np.asarray(img, dtype=np.float32) / 255.0

    def _fonte_emoji(self, tam: int):
        """None se a Segoe UI Emoji nao estiver instalada. O gate ja barra o
        caso do emojiCaptions, mas a fala transcrita pode trazer um emoji
        digitado — ai desenha-se o texto sem ele em vez de estourar."""
        chave = ("__emoji__", tam)
        if chave not in self._fontes:
            try:
                self._fontes[chave] = ImageFont.truetype(str(EMOJI_FONT), tam)
            except OSError:
                self._fontes[chave] = None
        return self._fontes[chave]

    def _mascara_cor(self, f: ImageFont.FreeTypeFont, texto: str,
                     ls: float = LETTER_SPACING):
        """(mascara, cor) — `cor` e a camada RGBA dos emojis, ou None.

        A mascara leva o emoji na silhueta dele, entao sombra e contorno o
        acompanham (e o que o Chrome faz com text-shadow sobre emoji). A cor
        volta separada porque o emoji nao aceita a tinta do texto.
        """
        if not tem_emoji(texto):
            return self._mascara(f, texto, ls), None
        partes = fatiar_emoji(texto)
        asc, desc = f.getmetrics()
        tam_e = max(8, int(round(f.size)))   # o CSS desenha emoji no font-size
        fe = self._fonte_emoji(tam_e)
        if fe is None:
            limpo = "".join(c for c in texto
                            if not _eh_emoji(c) and ord(c) not in EMOJI_CONT)
            return self._mascara(f, limpo.strip() or texto, ls), None
        asc_e, _ = fe.getmetrics()

        def _av(trecho: str, eh: bool) -> float:
            """Avanco do trecho. Numa sequencia de emoji so o glifo BASE
            avanca — FE0F/ZWJ/tom de pele nao ocupam largura. Sem Raqm o
            getlength mede code point a code point e dobrava o avanco."""
            if not eh:
                return f.getlength(trecho) + ls * len(trecho)
            base = "".join(c for c in trecho if ord(c) not in EMOJI_CONT)
            return fe.getlength(base or trecho) + ls

        larg = 0.0
        for trecho, eh in partes:
            larg += _av(trecho, eh)
        img = Image.new("L", (max(1, int(larg) + 8), asc + desc + 8), 0)
        cor = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d, dc = ImageDraw.Draw(img), ImageDraw.Draw(cor)
        x = 0.0
        for trecho, eh in partes:
            if eh:
                dc.text((x, asc - asc_e), trecho, font=fe, embedded_color=True)
                d.text((x, asc - asc_e), trecho, font=fe, fill=255)
                x += _av(trecho, True)
                continue
            for i, ch in enumerate(trecho):
                px = x + f.getlength(trecho[:i]) + ls * i
                if not ch.isspace() and self._glifo_falta(f, ch):
                    # glifo que a fonte da marca nao tem sai na reserva,
                    # como no _mascara (e como o Chrome com a pilha CSS)
                    fr = self._fonte_reserva(int(round(f.size)), None)
                    d.text((px, asc - fr.getmetrics()[0]),
                           self._char_para_reserva(f, ch), font=fr,
                           fill=255)
                else:
                    d.text((px, 0), ch, font=f, fill=255)
            x += _av(trecho, False)
        m = np.asarray(img, dtype=np.float32) / 255.0
        c = np.asarray(cor, dtype=np.float32)
        # o alpha do emoji manda na mascara (o fill=255 chapado exagerava
        # a borda: o glifo colorido tem antialias proprio)
        vis = c[..., 3] / 255.0
        m = np.where(vis > 0, vis, m)
        return m, c

    @staticmethod
    def _pintar_emoji(rgb: np.ndarray, cor, dx: int, dy: int = None) -> None:
        """Cola os pixels coloridos do emoji por cima da tinta do texto."""
        if cor is None:
            return
        dy = dx if dy is None else dy
        h = min(cor.shape[0], rgb.shape[0] - dy)
        w = min(cor.shape[1], rgb.shape[1] - dx)
        if h <= 0 or w <= 0:
            return
        c = cor[:h, :w]
        a = c[..., 3:4] / 255.0
        reg = rgb[dy:dy + h, dx:dx + w]
        reg[:] = reg * (1.0 - a) + c[..., :3] * a

    @staticmethod
    def _gradiente(altura: int) -> np.ndarray:
        """linear-gradient(180deg,#fff 0%,#fff 46%,#cfcfcf 100%)."""
        t = np.linspace(0.0, 1.0, max(1, altura), dtype=np.float32)
        return np.where(t <= 0.46, 255.0,
                        255.0 - (t - 0.46) / 0.54 * (255 - 0xCF)).astype(np.float32)

    @staticmethod
    def _cor(hexa: str) -> np.ndarray:
        h = hexa.lstrip("#")
        return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)

    @staticmethod
    def _uma_caixa(a: np.ndarray, larg: int, desl: int, eixo: int) -> np.ndarray:
        """Media movel de `larg` amostras, com o zero de fora contando.

        `desl` diz quantas amostras da janela ficam ANTES do pixel. Com janela
        par nao existe centro, e e por isso que o Skia alterna o lado entre as
        passadas -- somadas, as tres ficam centradas.
        """
        if larg <= 1:
            return a
        n = a.shape[eixo]
        pad = [(0, 0), (0, 0)]
        pad[eixo] = (larg, larg)
        b = np.pad(a, pad, mode="constant")
        cum = np.cumsum(b, axis=eixo)
        zero = [(0, 0), (0, 0)]
        zero[eixo] = (1, 0)
        cum = np.pad(cum, zero, mode="constant")
        lo = np.arange(n) + larg - desl
        hi = lo + larg
        if eixo == 0:
            return (cum[hi, :] - cum[lo, :]) / larg
        return (cum[:, hi] - cum[:, lo]) / larg

    @classmethod
    def _borrao_caixa(cls, m: np.ndarray, sigma: float) -> np.ndarray:
        """Tres passadas de caixa -- o borrao que o Chrome usa de verdade.

        O Skia nao aplica uma Gaussiana em text-shadow: aplica tres box blurs,
        que somados APROXIMAM uma Gaussiana mas tem suporte FINITO. A diferenca
        esta na cauda, e ela e mensuravel: comparando o karaoke deste motor com
        o do Remotion, o alcance da sombra deu 16px la e 18px aqui, com a faixa
        de 10 a 20px pesando 12% a 23% a mais.

        Janela como no Skia (`SkBlurMask::BoxBlur`):
            d = floor(sigma * 3 * sqrt(2*pi) / 4 + 0.5)
        Com `d` impar as tres passadas usam `d` centrado; com `d` par elas usam
        d (encostada a esquerda), d (a direita) e d+1 (centrada).
        """
        d = int(np.floor(sigma * 3.0 * np.sqrt(2.0 * np.pi) / 4.0 + 0.5))
        if d < 1:
            return m.astype(np.float32).copy()
        if d % 2 == 1:
            passos = [(d, d // 2), (d, d // 2), (d, d // 2)]
        else:
            passos = [(d, d // 2), (d, d // 2 - 1), (d + 1, d // 2)]
        out = m.astype(np.float32)
        for larg, desl in passos:
            for eixo in (0, 1):
                out = cls._uma_caixa(out, larg, desl, eixo)
        return out

    def _sombra_de(self, mask: np.ndarray, especs, k: float = BLUR_K,
                   caixa: bool = False) -> np.ndarray:
        """`k` e o fator sigma/raio. O padrao 1,05 vale para drop-shadow (o
        que o Chrome desenha, medido). Para text-shadow e box-shadow o sigma
        e raio/2 — passe k=0,5, senao o halo sai ~80% maior (medido no
        estilo `simples`: 44.930 contra 25.057 pixels de halo)."""
        out = np.zeros_like(mask)
        for dx, dy, blur, sa in especs:
            if caixa:
                b = self._borrao_caixa(mask, blur * k)
            else:
                b = np.asarray(Image.fromarray((mask * 255).astype(np.uint8))
                               .filter(ImageFilter.GaussianBlur(blur * k)),
                               dtype=np.float32) / 255.0
            desl = np.zeros_like(b)
            desl[max(0, dy):, max(0, dx):] = b[:b.shape[0] - max(0, dy),
                                               :b.shape[1] - max(0, dx)]
            out = np.maximum(out, desl * sa)
        return out

    # ----------------------------------------------------------- montagem ----
    def _montar_emojis(self) -> None:
        """Emoji solto no quadro, posto na mao pelo usuario.

        Gemeo do `EmojisManuais` do Main.tsx. Sem a Segoe UI Emoji o item e
        pulado com aviso — desenhar um retangulo vazio seria pior.
        """
        itens = self.ed.get("emojis") or []
        if not itens:
            return
        for it in itens:
            if not isinstance(it, dict):
                continue
            ch = str(it.get("char") or "").strip()
            if not ch:
                continue
            try:
                em = max(0.0, float(it.get("atSec") or 0))
                dur = float(it.get("durSec") or 1.6)
                x = float(it.get("x", 0.5))
                y = float(it.get("y", 0.34))
                tam_frac = float(it.get("size", 0.22))
            except (TypeError, ValueError):
                continue
            tam = max(24, int(round(tam_frac * self.w)))
            fe = self._fonte_emoji(tam)
            if fe is None:
                print("[emoji] Segoe UI Emoji ausente — item pulado", flush=True)
                continue
            cx = fe.getbbox(ch)
            larg = max(1, cx[2] - cx[0])
            alt = max(1, cx[3] - cx[1])
            img = Image.new("RGBA", (larg + 8, alt + 8), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((-cx[0] + 4, -cx[1] + 4), ch, font=fe,
                                     embedded_color=True)
            arr = np.asarray(img, dtype=np.float32) / 255.0
            alpha = arr[..., 3].copy()
            rgb = arr[..., :3] * 255.0
            x0 = int(round(x * self.w - img.width / 2))
            y0 = int(round(y * self.h - img.height / 2))
            ini = int(round(em * self.fps))
            fim = ini + max(1, int(round(max(0.2, dur) * self.fps)))
            cam = Camada(inicio_f=ini, fim_f=fim, dur_f=float(fim - ini))
            cam.palavras.append(Palavra(
                x0, y0, rgb, alpha,
                self._sombra_de(alpha, [(0, 8, 22, 0.45)], k=BLUR_K),
                # enter=0: no template o emoji manual aparece INSTANTANEO
                inicio_f=0, enter=0, sobe=0.0))
            self.camadas.append(cam)

    def _montar_tudo(self) -> None:
        hook = self.ed.get("hook") or {}
        self._montar_emojis()
        if hook.get("enabled"):
            self.camadas.append(self._montar_headline(hook))
            if self.sfx_on:
                vol_hl = WHOOSH_HL.get(hook.get("style") or "outline",
                                       WHOOSH_VOL)
                if vol_hl is not None:
                    self.eventos_sfx.append(("whoosh.mp3", 0.0, vol_hl))
        caps_cfg = self.ed.get("captions") or {}
        # LEGENDA DESLIGADA nao desenha — o template tem
        # `{D.captions.enabled ? ... : null}` e aqui nao havia guarda nenhuma.
        # A manchete (`hook.enabled`) e o card final (`ec.enabled`) sempre
        # tiveram a delas; a legenda passou batido.
        #
        # Provado ponta a ponta: com o estilo "Nenhuma" o pipeline grava
        # `enabled: false` e `style: "karaoke"`, o portao manda para o motor
        # rapido, e ele montava 6 camadas de legenda num video em que o
        # usuario tinha pedido NENHUMA.
        #
        # `is not False` e nao `if enabled`: edit-data de projeto antigo pode
        # nao ter o campo, e ali o certo e continuar desenhando.
        #
        # NAO e um `return`: depois daqui o montador ainda faz o contador de
        # lista, os inserts, o card final e o som dos cortes. A primeira
        # versao desta guarda (3.87) saia da funcao e levava tudo isso junto
        # — um projeto com legenda "Nenhuma" perdia o b-roll. Achado na
        # medicao do contador, que veio com ZERO camadas.
        if caps_cfg.get("enabled") is False:
            self.cues = []
        estilo = caps_cfg.get("style") or "stacked"
        legenda_ligada = caps_cfg.get("enabled") is not False
        if not legenda_ligada:
            estilo = None
        if estilo == "impacto":
            self.camadas.extend(self._montar_impacto())
            self.cues = []
        elif estilo == "scatter":
            self.camadas.extend(self._montar_scatter())
            self.cues = []
        elif estilo == "karaoke":
            self.camadas.extend(self._montar_karaoke())
            # ZERA as cues, como TODO estilo irmao. Sem esta linha o laco
            # abaixo desenhava o `stacked` POR CIMA do karaoke: no template
            # o `<Karaoke/>` e o `else` do despachante e nada mais desenha
            # legenda. Aparecia quando o `caption-cues.json` tinha conteudo —
            # o que acontece num projeto que ja foi renderizado em `stacked`
            # e depois trocou de estilo (o pipeline so criava o arquivo vazio
            # se ele NAO existisse; nao limpava o antigo).
            #
            # Medido: tinta 2,557 contra o template, com as duas legendas
            # na tela ao mesmo tempo. Os outros 14 estilos ficam entre 0,93
            # e 1,04.
            self.cues = []
        elif estilo == "bolha":
            self.camadas.extend(self._montar_bolha())
            self.cues = []
        elif estilo in self.SIMPLE_VARIANTES or estilo == "recorte":
            self.camadas.extend(self._montar_simple(
                "recorte_simple" if estilo == "recorte" else estilo))
            self.cues = []
        for cue in self.cues:
            # Cue sem NENHUMA palavra nao desenha nada e derruba o montador:
            # `_tempos_cue` faz `max()` sobre uma sequencia vazia e os presets
            # SOLO indexam `lines[0][0]` direto. Quem escreve o arquivo ja tira
            # a cue vazia (`_drop_cues_vazias`), mas um caption-cues.json de
            # outra versao ou editado a mao nao pode derrubar o render inteiro
            # — e o preco de pular e zero, porque nao havia o que desenhar.
            if not any(ln for ln in (cue.get("lines") or [])):
                continue
            preset = cue.get("preset") or "STACK_MIXED"
            if preset == "SOLO_OUTLINE":
                leg = self._montar_recorte(cue)
            elif preset == "SOLO_BIG":
                leg = self._montar_solo_big(cue)
            else:
                leg = self._montar_stacked(cue)
            self.camadas.append(leg)
            if self.sfx_on:
                t0 = cue["startMs"] / 1000.0
                solo = preset in ("SOLO_BIG", "SOLO_OUTLINE")
                self.eventos_sfx.append((
                    "caption-click.mp3" if solo else self.stack_click, t0,
                    self.click_vol if solo else self.stack_vol))
                if preset == "SOLO_OUTLINE":
                    self.eventos_sfx.append((
                        "caption-scratch.mp3", t0 + 2 / self.fps, self.scratch_vol))
        self.camadas.sort(key=lambda l: l.inicio_f)
        # Sem gate, como o ListCounter.tsx: ele so olha `listMarkers`. O gate
        # que estava aqui lia `edit_data["elements"]["listCounter"]`, e
        # edit-data NAO tem a chave `elements` — conferido nos 114 projetos do
        # usuario, zero tem. Ela mora no PRESET, e o run_fast usa o preset para
        # decidir se GRAVA `listMarkers`. Ou seja: o selo nunca desenhava neste
        # motor, e desenhava no Remotion. `_montar_contador` ja devolve [] sem
        # marcadores.
        self.camadas.extend(self._montar_contador())
        self.camadas.extend(self._montar_inserts())
        ec = self.ed.get("endCard") or {}
        if ec.get("enabled"):
            self.camadas.append(self._montar_endcard(ec, hook.get("accent")))
        trs = [t for t in (self.ed.get("transitions") or [])
               if t.get("type") == "flash"]
        self.flashes = [float(t["at"]) for t in trs]
        # O flash TEM som no template (`<Sfx src={active.sfx ?? 'cut-click.mp3'}
        # volume={active.volume ?? 0.9}>` dentro de um Sequence que comeca no
        # quadro do corte). O motor proprio desenhava o clarao e o feixe e nao
        # tocava nada — o corte marcado ficava mudo em todo projeto.
        #
        # Fica atras de `sfx_on` como todos os outros deste motor: o template
        # nao gera esse gate aqui, mas "desligar efeitos sonoros" ja desliga o
        # whoosh da headline e os cliques da legenda, e um clique sobrando
        # depois disso seria surpresa.
        if self.sfx_on:
            for t in trs:
                c = round(float(t["at"]) * self.fps) + VIDEO_LAG
                self.eventos_sfx.append((
                    str(t.get("sfx") or "cut-click.mp3"),
                    c / self.fps,
                    float(t["volume"]) if t.get("volume") is not None else 0.9))

    @staticmethod
    def _arredonda_js(x: float) -> int:
        """`Math.round` do JavaScript, nao o `round` do Python.

        O `round` do Python e bancario: `round(0.5)` da 0 e `round(1.5)` da 2.
        O do JavaScript sempre sobe no meio. Numa contagem de quadros isso e a
        diferenca entre casar com o template e ficar um quadro fora.
        """
        return math.floor(float(x) + 0.5)

    def _tempos_cue(self, cue: dict) -> tuple[int, int, float, int, float]:
        """Relogio da cue, igual ao `StackedCaptions.tsx`.

        Ele monta cada cue assim (linhas 280-282):

            from = Math.round(startMs / 1000 * fps)
            end  = Math.round(endMs   / 1000 * fps)
            dur  = Math.max(2, Math.min(end, durationInFrames) - from)

        e passa esse `dur` INTEIRO como `cueDurationFrames`, que e quem manda
        no ENTER, no EXIT e no corte do `exit: abrupt`.

        Aqui era `int()` (que TRUNCA) e uma duracao em float. Medido num
        projeto real: **57 das 112 cues (51%)** caiam num quadro diferente do
        template — a legenda aparecia um quadro antes e todo o relogio interno
        dela (entrada, saida) ia junto.
        """
        ini_f = self._arredonda_js(cue["startMs"] / 1000 * self.fps)
        fim_f = self._arredonda_js(cue["endMs"] / 1000 * self.fps)
        dur = float(max(2, min(fim_f, self.frames) - ini_f))
        enter = max(3, min(8, math.floor(dur * 0.45)))
        exit_ = max(2, min(7, math.floor(dur * 0.35)))
        # `default=0.0`: cue sem palavra nenhuma levantava aqui
        # (`max() iterable argument is empty`) e derrubava o render inteiro.
        # Quem produz o arquivo ja evita isso, mas um cues.json vindo de fora
        # nao deve conseguir quebrar o motor.
        ultima = max((w["fromMs"] - cue["startMs"]) / 1000 * self.fps
                     for ln in cue["lines"] for w in ln) if any(cue.get("lines") or []) else 0.0
        saida_f = max(dur - exit_, min(ultima + enter, dur - 2))
        return ini_f, fim_f, dur, enter, saida_f

    def _nova_camada(self, cue: dict) -> tuple[Camada, int, float]:
        ini_f, fim_f, dur, enter, saida_f = self._tempos_cue(cue)
        leg = Camada(ini_f, fim_f)
        leg.dur_f = dur
        leg.exit_abrupto = cue.get("exit") == "abrupt"
        leg.saida_f = saida_f
        return leg, enter, dur

    @staticmethod
    def _enter_da_palavra(enter: int, saida_f: float, local: float) -> int:
        """Encurta a entrada de quem comeca perto da SAIDA da cue.

        `wordAnim` em StackedCaptions.tsx faz
        `max(2, min(ENTER, floor(exitStart - localStart - 1)))`: a palavra que
        entra tarde tem menos quadros para aparecer, senao ela e cortada no
        meio do fade.

        O motor passava o `enter` da CUE para toda palavra. A que entrava
        tarde ficava com uma janela longa demais e a cue acabava antes de ela
        assentar: mais clara e ainda deslocada para baixo (a subida de 46px
        anda junto com a opacidade). Com `exit: abrupt` — que e o caso da
        maioria — ela pisca e some sem nunca chegar ao lugar.

        Medido nos 114 projetos do usuario: 6.292 de 23.166 palavras (27%)
        deviam ter a entrada encurtada; em 5.580 delas a diferenca de
        opacidade no ultimo quadro visivel passa de 0,15, chegando a 0,67.
        """
        return max(2, min(int(enter), math.floor(saida_f - local - 1)))

    def _palavra_texto(self, leg: Camada, f, texto: str, ls: float, x0: int,
                       topo_caixa: float, alt_caixa: float, y_base: int,
                       cor_fixa: str | None, inicio_f: float, enter: int,
                       especs=SHADOW, ease: str = "cubic",
                       k_sombra: float = BLUR_K) -> None:
        m, cor_e = self._mascara_cor(f, texto, ls)
        h_m, w_m = m.shape
        folga = 24
        pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga), dtype=np.float32)
        pad_m[folga:folga + h_m, folga:folga + w_m] = m
        # `k_sombra` e o fator sigma/raio. O padrao (drop-shadow) vale para
        # os estilos que nasceram com ele; quem vem de um `text-shadow` do
        # CSS precisa de 0,5, senao o halo sai ~80% maior.
        sombra = self._sombra_de(pad_m, especs, k=k_sombra)
        if cor_fixa:
            rgb = np.broadcast_to(self._cor(cor_fixa), (*pad_m.shape, 3)).copy()
        else:
            col = self._gradiente(int(round(alt_caixa)))
            off = int(round(y_base - folga - topo_caixa))
            idxs = np.clip(np.arange(pad_m.shape[0]) + off, 0, len(col) - 1)
            rgb = np.repeat(col[idxs][:, None, None], 3, axis=2) * np.ones(
                (1, pad_m.shape[1], 1), dtype=np.float32)
        self._pintar_emoji(rgb, cor_e, folga)
        leg.palavras.append(Palavra(x0 - folga, y_base - folga, rgb, pad_m,
                                    sombra, inicio_f=inicio_f, enter=enter,
                                    ease=ease))

    def _montar_stacked(self, cue: dict) -> Camada:
        leg, enter, dur = self._nova_camada(cue)
        linhas = []
        for li, line in enumerate(cue["lines"]):
            idx = (cue.get("lineStyles") or [None] * 9)[li]
            if idx is None:
                idx = (li + cue.get("styleOffset", 0)) % 4
            txt = " ".join(w["text"] for w in line)
            sz = self.fit_font(txt)
            if idx == 1:
                sz = round(sz * 0.72)
            if idx == 2:
                sz = round(sz * 0.95)
            if (cue.get("lineEmph") or [False] * 9)[li]:
                sz = round(sz * 1.12)
            if (cue.get("lineBoost") or [False] * 9)[li]:
                sz = round(sz * 1.35)
            linhas.append({"idx": idx, "size": sz, "words": line})
        alturas = [ln["size"] * LINE_HEIGHT for ln in linhas]
        total = alturas[0] if alturas else 0
        for i in range(1, len(alturas)):
            total += alturas[i] + MARGIN_TOP_EM * linhas[i]["size"]
        y = (self.h / 2 + self.base_y) - total / 2
        for li, ln in enumerate(linhas):
            if li > 0:
                y += MARGIN_TOP_EM * ln["size"]
            f = self.fonte(ln["idx"], ln["size"], marca=None)
            pad = WORD_PAD_EM * ln["size"]
            gap = f.getlength(" ")
            largs = [f.getlength(w["text"]) + LETTER_SPACING * len(w["text"]) + 2 * pad
                     for w in ln["words"]]
            largs = [wl + (gap if i < len(largs) - 1 else 0)
                     for i, wl in enumerate(largs)]
            x = (self.w - sum(largs)) / 2
            asc, desc = f.getmetrics()
            base = y + (alturas[li] - (asc + desc)) / 2
            especs = SHADOW_STRONG if ln["idx"] == 1 else SHADOW
            for w, wl in zip(ln["words"], largs):
                local_w = (w["fromMs"] - cue["startMs"]) / 1000 * self.fps
                self._palavra_texto(
                    leg, f, w["text"], LETTER_SPACING, int(round(x + pad)),
                    y, alturas[li], int(round(base)),
                    self.font_file[ln["idx"]][1],
                    local_w,
                    self._enter_da_palavra(enter, leg.saida_f, local_w), especs,
                    ease="bezier")
                x += wl
            y += alturas[li]
        return leg

    def _montar_solo_big(self, cue: dict) -> Camada:
        """A palavra cresce de 88% a 100% enquanto aparece.

        `StackedCaptions.tsx` (preset SOLO_BIG) faz
        `scale: interpolate(a.opacity, [0, 1], [0.88, 1])` — a escala anda
        junto com a OPACIDADE, nao com o tempo. Aqui a palavra era
        rasterizada uma vez, em tamanho final, e so a opacidade animava: ela
        aparecia sem o "pop". Sao 3% das legendas do usuario (245 de 7256
        cues), mas o motor proprio existe para desenhar o mesmo.

        Animar tamanho neste motor e rasterizar em estagios e dar a cada um a
        sua janela de quadros — o mesmo que `_montar_contador` e o POP do
        `_montar_impacto` ja fazem. A diferenca e que aqui a opacidade tambem
        anda, entao cada estagio carrega a sua (`Palavra.opac`).

        O `scale` do CSS cresce a partir do CENTRO da caixa, entao o centro
        fica fixo e cada estagio se posiciona por ele.
        """
        leg, enter, dur = self._nova_camada(cue)
        w = cue["lines"][0][0]
        tam = self.fit_font(w["text"], 150, self.avail / self.scale, 0.6)
        cx, cy = self.w / 2.0, (self.h / 2 + self.base_y)
        ini_f = (w["fromMs"] - cue["startMs"]) / 1000 * self.fps
        # Um estagio por quadro da ENTRADA, nao um numero fixo: a escala anda
        # junto com a opacidade, e `enter` (3 a 8 quadros, pela duracao da
        # cue) e quem manda na opacidade. Com passo fixo, cue curta chegava ao
        # tamanho cheio depois de a palavra ja estar opaca.
        n = max(1, int(enter))

        for est in range(n + 1):
            t = min(1.0, est / n)
            op = _ease_out(t)                # bezier, como o StackedCaptions
            esc = 0.88 + 0.12 * op
            tam_e = max(8, int(round(tam * esc)))
            f = self.fonte(0, tam_e, marca=None)
            ls = -3.0 * esc
            pad = 0.14 * tam_e
            larg = f.getlength(w["text"]) + ls * len(w["text"]) + 2 * pad
            alt = tam_e * LINE_HEIGHT
            x_c, y_c = cx - larg / 2, cy - alt / 2
            asc, desc = f.getmetrics()
            antes = len(leg.palavras)
            self._palavra_texto(
                leg, f, w["text"], ls, int(round(x_c + pad)), y_c, alt,
                int(round(y_c + (alt - (asc + desc)) / 2)), None, ini_f,
                self._enter_da_palavra(enter, leg.saida_f, ini_f),
                ease="bezier")
            for pal in leg.palavras[antes:]:
                # um quadro por estagio durante a entrada; o ultimo fica
                pal.janela = ((ini_f + est, ini_f + est + 1) if est < n
                              else (ini_f + n, 1e9))
                pal.opac = op
        return leg

    # ----- Recorte (SOLO_OUTLINE): traço que se desenha por comprimento -----
    @staticmethod
    def _pontos_traco() -> list[tuple[float, float]]:
        pts = [TRACO_INICIO]
        atual = TRACO_INICIO
        for c1, c2, fim in TRACO_CURVAS:
            for i in range(1, 25):
                t = i / 24
                u = 1 - t
                pts.append((
                    u ** 3 * atual[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * fim[0],
                    u ** 3 * atual[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * fim[1]))
            atual = fim
        return pts

    def _montar_recorte(self, cue: dict) -> Camada:
        leg, enter, dur = self._nova_camada(cue)
        w = cue["lines"][0][0]
        tam = self.fit_font(w["text"], 118, (self.avail - 80) / self.scale, 0.6)
        f = self.fonte(4, tam, marca=None)
        ls = -2.0
        pad = 0.1 * tam
        larg_c = f.getlength(w["text"]) + ls * len(w["text"]) + 2 * pad
        alt_c = tam * LINE_HEIGHT
        x_c = (self.w - larg_c) / 2
        y_c = (self.h / 2 + self.base_y) - alt_c / 2
        asc, desc = f.getmetrics()
        local = (w["fromMs"] - cue["startMs"]) / 1000 * self.fps
        self._palavra_texto(
            leg, f, w["text"], ls, int(round(x_c + pad)), y_c, alt_c,
            int(round(y_c + (alt_c - (asc + desc)) / 2)), None, local,
            self._enter_da_palavra(enter, leg.saida_f, local),
            ease="bezier")

        if self.enfase_marcador:
            esq, topo, larg_f, alt_f = MARCADOR_CAIXA
            bx, by = x_c + esq * larg_c, y_c + topo * alt_c
            bw, bh = larg_f * larg_c, alt_f * alt_c
            pts = [(bx + x / TRACO_VB[0] * bw, by + y / TRACO_VB[1] * bh)
                   for x, y in MARCADOR_PONTOS]
            o_ini = local + 2
            o_fim = max(min(o_ini + 10, leg.saida_f - 1, dur - 2), o_ini + 3)
            larg_px = max(6, int(round(MARCADOR_LARG_VB / TRACO_VB[1] * bh)))
            # a ponta e esticada na horizontal junto com o SVG (ver
            # `_mascara_linha`): ela mede meia espessura na ESCALA X
            raio_x = MARCADOR_LARG_VB / 2 / TRACO_VB[0] * bw
            marg_x = int(raio_x) + 8
            marg_y = larg_px + 8
            tx0 = int(min(x for x, _ in pts) - marg_x)
            ty0 = int(min(y for _, y in pts) - marg_y)
            lt = int(max(x for x, _ in pts) + marg_x) - tx0
            at = int(max(y for _, y in pts) + marg_y) - ty0
            cor = self._cor(self.cor_marcador)
            acum = [0.0]
            for i in range(1, len(pts)):
                acum.append(acum[-1] + math.hypot(
                    pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))

            def _faixa(frac: float, janela: tuple[float, float]) -> None:
                total = acum[-1]
                if frac >= 1:
                    sub = list(pts)
                elif frac <= 0:
                    sub = []
                else:
                    alvo = total * frac
                    sub = [pts[0]]
                    for i in range(1, len(pts)):
                        if acum[i] < alvo:
                            sub.append(pts[i])
                            continue
                        seg = acum[i] - acum[i - 1]
                        t = (alvo - acum[i - 1]) / seg if seg > 1e-9 else 0.0
                        sub.append((
                            pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
                            pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t))
                        break
                img = _mascara_linha(sub, lt, at, tx0, ty0,
                                    larg_px, raio_x)
                alpha = (np.asarray(img, dtype=np.float32) / 255.0
                         * MARCADOR_ALPHA)
                sem_sombra = np.zeros_like(alpha)
                rgb = np.broadcast_to(cor, (at, lt, 3)).copy()
                leg.palavras.insert(0, Palavra(
                    tx0, ty0, rgb, alpha, sem_sombra,
                    inicio_f=0, enter=1, janela=janela))

            q = int(math.floor(o_ini))
            while q < o_fim:
                _faixa(min(1.0, max(0.0, (q - o_ini)
                                    / max(1e-6, o_fim - o_ini))),
                       (q, q + 1))
                q += 1
            # A faixa TEM de ficar ate o fim da legenda. Sem esta etapa ela
            # era pintada durante a entrada (uma peca por quadro) e sumia no
            # quadro seguinte — o traco do circulo sempre teve a etapa final,
            # o marca-texto nasceu sem (2.7x) e ninguem viu porque o estilo
            # padrao e o circulo.
            _faixa(1.0, (o_fim, float(leg.fim_f - leg.inicio_f + 10)))
            return leg

        esq, topo, larg_f, alt_f = TRACO_CAIXA
        bx, by = x_c + esq * larg_c, y_c + topo * alt_c
        bw, bh = larg_f * larg_c, alt_f * alt_c
        pts = [(bx + x / TRACO_VB[0] * bw, by + y / TRACO_VB[1] * bh)
               for x, y in self._pontos_traco()]
        acum = [0.0]
        for i in range(1, len(pts)):
            acum.append(acum[-1] + math.hypot(pts[i][0] - pts[i - 1][0],
                                              pts[i][1] - pts[i - 1][1]))
        o_ini = local + 2
        o_fim = max(min(o_ini + 10, leg.saida_f - 1, dur - 2), o_ini + 3)
        marg = TRACO_PX + 20
        tx0 = int(min(x for x, _ in pts) - marg)
        ty0 = int(min(y for _, y in pts) - marg)
        lt = int(max(x for x, _ in pts) + marg) - tx0
        at = int(max(y for _, y in pts) + marg) - ty0
        cor = self._cor(self.cor_traco)

        def _estagio(frac: float, janela: tuple[float, float]) -> None:
            total = acum[-1]
            if frac >= 1:
                sub = list(pts)
            elif frac <= 0:
                sub = []
            else:
                alvo = total * frac
                sub = [pts[0]]
                for i in range(1, len(pts)):
                    if acum[i] < alvo:
                        sub.append(pts[i])
                        continue
                    seg = acum[i] - acum[i - 1]
                    t = (alvo - acum[i - 1]) / seg if seg > 1e-9 else 0.0
                    sub.append((pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
                                pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t))
                    break
            img = _mascara_linha(sub, lt, at, tx0, ty0, TRACO_PX)
            alpha = np.asarray(img, dtype=np.float32) / 255.0
            sombra = self._sombra_de(alpha, [TRACO_SOMBRA])
            rgb = np.broadcast_to(cor, (at, lt, 3)).copy()
            leg.palavras.insert(0, Palavra(tx0, ty0, rgb, alpha, sombra,
                                           inicio_f=0, enter=1, janela=janela))

        q = int(math.floor(o_ini))
        while q < o_fim:
            _estagio(min(1.0, max(0.0, (q - o_ini) / max(1e-6, o_fim - o_ini))),
                     (q, q + 1))
            q += 1
        _estagio(1.0, (o_fim, float(leg.fim_f - leg.inicio_f + 10)))
        return leg

    # HL_STYLES do template (Main.tsx): pesos, teto, largura segura, entrelinha
    # e distancia do topo. `manchete` ancora embaixo (top ignorado).
    HL_STYLES = {
        "outline":    ((800, 800), 92, 900, 1.02, 330),
        "card":       ((900, 900), 82, 820, 1.06, 120),
        "realce":     ((900, 900), 86, 830, 1.04, 300),
        "misto":      ((400, 900), 98, 900, 0.98, 300),
        "sombra":     ((900, 900), 92, 860, 1.02, 310),
        "sublinhado": ((900, 900), 84, 850, 1.00, 305),
        "pilula":     ((700, 700), 44, 780, 1.10, 130),
        "manchete":   ((800, 800), 54, 780, 1.14, 0),
        "carimbo":    ((900, 900), 80, 720, 1.05, 300),
        "pergunta":   ((800, 900), 84, 840, 1.05, 300),
        "faixa":       ((900, 900), 78, 900, 1.06, 300),
        "fita":        ((900, 900), 84, 800, 1.05, 300),
        "neon":        ((900, 900), 92, 880, 1.02, 310),
        "vazado":      ((900, 900), 86, 820, 1.04, 300),
        "gradiente":   ((900, 900), 96, 900, 1.00, 305),
    }
    HL_MAIUSCULA = ("card", "manchete", "carimbo", "faixa", "vazado")
    # peso -> arquivo Poppins
    # O Main.tsx so carrega Poppins 400/600/900. MEDIDO na varredura de
    # 31/08 (tinta contra o Remotion, projeto real): com 800->Black(900) os
    # estilos de 800 ficam em 0,997-1,03 — o mapa antigo (ExtraBold) saia
    # mais magro que o Chrome. Ja o 700 da pilula mediu MELHOR no SemiBold
    # (1,065) que no Black (1,103): o Chrome nao esta dando 900 ao 700
    # aqui, apesar da regra de casamento do CSS. Pixels > teoria.
    HL_FONTE = {400: 1, 500: 1, 600: 7, 700: 7, 800: 4, 900: 4}

    def _hl_fonte(self, peso: int, tam: int) -> ImageFont.FreeTypeFont:
        if self.marca_hook:
            arq, teto = self.marca_hook
            eixo = min(peso, teto) if teto is not None else peso
            return self._fonte_arquivo(arq, tam, eixo)
        # `marca=None`: sem fonte de HEADLINE escolhida, a headline volta
        # para a do template — nunca para a das LEGENDAS. O template faz
        # `hookFamily(fontFamily)`, que cai no padrao, nao em CAP_FF.
        return self.fonte(self.HL_FONTE.get(peso, 4), tam, marca=None)

    def _larg_hl(self, texto: str, tam: int, peso: int = 900) -> float:
        f = self._hl_fonte(peso, tam)
        if tem_emoji(texto):
            # A fonte de marca nao tem o glifo: getlength mediria a caixa de
            # .notdef por code point (FE0F e ZWJ inclusive) e a moldura sairia
            # larga demais. Mede cada trecho na fonte que vai desenha-lo.
            fe = self._fonte_emoji(max(8, int(round(f.size))))
            larg = 0.0
            for trecho, eh in fatiar_emoji(texto):
                if eh and fe is not None:
                    base = "".join(c for c in trecho if ord(c) not in EMOJI_CONT)
                    larg += fe.getlength(base or trecho)
                elif eh:
                    continue   # sem Segoe: o desenho tambem descarta o emoji
                else:
                    larg += f.getlength(trecho)
            return larg
        if any(self._glifo_falta(f, c) for c in set(texto) if not c.isspace()):
            # Mesmo principio do emoji: o glifo que falta sera desenhado
            # pela RESERVA — medir o avanco dele na fonte da marca (caixa
            # de .notdef) descasaria a moldura da tinta.
            fr = self._fonte_reserva(int(round(f.size)), None)
            larg = sum(
                fr.getlength(self._char_para_reserva(f, c))
                if (not c.isspace() and self._glifo_falta(f, c))
                else f.getlength(c) for c in texto)
            return larg - 1.0 * max(0, len(texto) - 1)
        return f.getlength(texto) - 1.0 * max(0, len(texto) - 1)

    def _hl_linhas(self, texto: str, pesos, cap: int, safe_w: float):
        """Duas linhas balanceadas por LARGURA MEDIDA + tamanho ajustado."""
        palavras = texto.split()
        if len(palavras) < 2:
            linhas = [texto] if texto else []
        else:
            melhor, dif = (palavras[0], " ".join(palavras[1:])), float("inf")
            for i in range(1, len(palavras)):
                a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
                d = abs(self._larg_hl(a, 100, pesos[0])
                        - self._larg_hl(b, 100, pesos[1]))
                if d < dif:
                    melhor, dif = (a, b), d
            linhas = [l for l in melhor if l]

        def mais_larga(t):
            return max([self._larg_hl(l, t, pesos[min(i, 1)])
                        for i, l in enumerate(linhas)] + [1.0])

        tam = int(safe_w / mais_larga(100) * 100)
        tam = max(HL_MIN, min(cap, int(safe_w / mais_larga(tam) * tam)))
        # Altura normalizada tambem na HEADLINE: titulo curto bate no teto
        # (cap) e o teto em px rende alturas diferentes por fonte — Anton
        # 21% mais alta. Mesmo fator da legenda, espelhado no fitHeadline
        # do template (fonts.ts hookSizeFactor).
        # getattr: o harness de paridade do preview monta o Renderizador nu
        # (__new__), sem edit-data — ai o fator fica em 1,0, que e o certo.
        ed = getattr(self, "ed", None) or {}
        fam = str((ed.get("hook") or {}).get("fontFamily") or "").lower()
        fator = {"anton": 0.83}.get(fam, 1.0)
        if fator != 1.0:
            tam = max(HL_MIN, round(tam * fator))
        return linhas, tam

    def _hl_bloco_texto(self, leg, texto, tam, peso, x0, y_topo, alt_cx,
                        cor, especs, k_sombra=0.5, contorno=None,
                        fundo=None, raio=0, pad_xy=(0, 0, 0), enter=8,
                        sobe=24.0, rot=0.0, borda=None, vazar=False):
        """Uma linha de headline: fundo opcional, contorno opcional, texto.

        Concentra o que os 9 estilos tem em comum — o que muda entre eles e
        so QUAL dessas pinturas entra."""
        f = self._hl_fonte(peso, tam)
        asc, desc = f.getmetrics()
        # `_mascara_cor` para o emoji sair COLORIDO, como nas legendas — a
        # headline "Foi Traído 2 Vezes" dele saiu com duas caixas (31/08).
        m, cor_e = self._mascara_cor(f, texto, -1.0)
        h_m, w_m = m.shape
        pad_x, pad_t, pad_b = pad_xy
        folga = 56
        # A caixa segue o AVANCO do texto, nao a largura da mascara: o
        # `_mascara` acrescenta 8px de folga a direita para o antialias nao
        # ser cortado, e usar isso como largura punha esses 8px dentro do
        # fundo — assimetrico, tudo de um lado. As outras caixas do arquivo
        # (manchete, carimbo, pilula) ja derivam de `_larg_hl`.
        larg_txt = self._larg_hl(texto, tam, peso)
        larg_b = int(round(larg_txt + 2 * pad_x))
        alt_b = int(alt_cx + pad_t + pad_b)
        L = larg_b + 2 * folga
        A = alt_b + 2 * folga

        alpha = np.zeros((A, L), dtype=np.float32)
        rgb = np.zeros((A, L, 3), dtype=np.float32)
        base_sombra = None

        if fundo is not None:
            img = Image.new("L", (L, A), 0)
            ImageDraw.Draw(img).rounded_rectangle(
                [folga, folga, folga + larg_b, folga + alt_b],
                radius=raio, fill=255)
            a_f = np.asarray(img, dtype=np.float32) / 255.0
            if isinstance(fundo, tuple):          # (cor, opacidade)
                cor_f, op_f = fundo
                a_f = a_f * op_f
            else:
                cor_f = fundo
            alpha = a_f
            rgb[:] = self._cor(cor_f)
            base_sombra = np.asarray(img, dtype=np.float32) / 255.0

        if borda is not None:
            cor_bd, esp = borda
            img = Image.new("L", (L, A), 0)
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([folga, folga, folga + larg_b, folga + alt_b],
                                radius=raio, outline=255, width=esp)
            a_bd = np.asarray(img, dtype=np.float32) / 255.0
            rgb = rgb * (1 - a_bd[..., None]) + self._cor(cor_bd) * a_bd[..., None]
            alpha = np.maximum(alpha, a_bd)
            if base_sombra is None:
                base_sombra = a_bd

        t_a = np.zeros((A, L), dtype=np.float32)
        tx = folga + int(pad_x)
        ty = folga + int(pad_t + (alt_cx - (asc + desc)) / 2)
        hh, ww = min(h_m, A - ty), min(w_m, L - tx)
        t_a[ty:ty + hh, tx:tx + ww] = m[:hh, :ww]

        if contorno is not None:
            cor_ct, esp = contorno
            ct = np.zeros_like(t_a)
            passos = [(esp, 0), (-esp, 0), (0, esp), (0, -esp)]
            d = int(round(0.7071 * esp))
            passos += [(d, d), (-d, d), (d, -d), (-d, -d)]
            for dx, dy in passos:
                desl = np.zeros_like(t_a)
                ys = slice(max(0, dy), A + min(0, dy))
                xs = slice(max(0, dx), L + min(0, dx))
                ys2 = slice(max(0, -dy), A + min(0, -dy))
                xs2 = slice(max(0, -dx), L + min(0, -dx))
                desl[ys, xs] = t_a[ys2, xs2]
                ct = np.maximum(ct, desl)
            rgb = rgb * (1 - ct[..., None]) + self._cor(cor_ct) * ct[..., None]
            alpha = np.maximum(alpha, ct)
            if base_sombra is None:
                base_sombra = ct

        # `fundo`: sem caixa nao ha o que furar, e tirar a letra de um alpha
        # vazio apagaria a headline inteira. Vazar so faz sentido com caixa.
        if vazar and fundo is not None:
            # A letra nao e pintada: ela e TIRADA da caixa, e por esse buraco
            # aparece o video. A sombra sai da peca JA FURADA — com ela vindo
            # da caixa cheia, o borrao escuro ficava dentro do buraco e as
            # letras saiam sujas (visto no par contra o Remotion, 29/08).
            alpha = np.clip(alpha - t_a, 0.0, 1.0)
            base_sombra = alpha
        else:
            rgb = rgb * (1 - t_a[..., None]) + self._cor(cor) * t_a[..., None]
            alpha = np.maximum(alpha, t_a)
            # O emoji nao aceita a tinta do texto: os pixels coloridos entram
            # por cima, na mesma posicao da mascara. No `vazar` ele fica so
            # silhueta furada — igual ao knockout do Chrome.
            self._pintar_emoji(rgb, cor_e, tx, ty)
        if base_sombra is None:
            base_sombra = t_a
        sombra = self._sombra_de(base_sombra, especs, k=k_sombra) if especs \
            else np.zeros_like(alpha)

        if rot:
            # CSS e Pillow giram para lados OPOSTOS: `rotate(-6deg)` do
            # template inclina num sentido e `Image.rotate(-6)` no outro.
            # Passando o valor direto, o carimbo saia espelhado — a razao
            # de tinta nao via (1,057, area igual) e a diferenca de alfa
            # gritava (107 de 255, a maior do catalogo).
            _giro = -float(rot)

            def _gira(a, modo="L"):
                im = Image.fromarray((a * 255).astype(np.uint8), modo)
                return np.asarray(im.rotate(_giro, expand=False,
                                            resample=Image.BICUBIC),
                                  dtype=np.float32) / 255.0
            alpha = _gira(alpha)
            sombra = _gira(sombra)
            rgb = np.asarray(
                Image.fromarray(rgb.astype(np.uint8), "RGB")
                .rotate(_giro, expand=False, resample=Image.BICUBIC),
                dtype=np.float32)

        leg.palavras.append(Palavra(
            int(x0) - folga, int(y_topo) - folga, rgb, alpha, sombra,
            inicio_f=0, enter=enter, sobe=sobe))
        return alt_b

    def _hl_bloco_multi(self, leg, linhas, tam, peso, alt_cx, x0, y_topo,
                        cor, especs, raio=0, pad_xy=(0, 0, 0), borda=None,
                        rot=0.0, sobe=24.0, fundo=None, enter=8,
                        pad_esq=None):
        """Bloco de VARIAS linhas numa peca so — para molduras/fundos que
        envolvem o conjunto (carimbo), nao cada linha.

        `pad_esq` alinha o texto a ESQUERDA com essa margem, em vez de
        centra-lo: e o que a manchete precisa, porque la a barra de
        acento ocupa o comeco da lapide. Sem o parametro nada muda —
        mexer neste ajudante compartilhado ja custou duas regressoes.
        """
        f = self._hl_fonte(peso, tam)
        asc, desc = f.getmetrics()
        # (mascara, camada de cor do emoji) por linha — ver _hl_bloco_texto
        pares = [self._mascara_cor(f, l, -1.0) for l in linhas]
        mascaras = [m for m, _ in pares]
        pad_x, pad_t, pad_b = pad_xy
        larg_txt = max((m.shape[1] for m in mascaras), default=1)
        larg_b = int(larg_txt + (pad_x if pad_esq is None else pad_esq) + pad_x)
        alt_b = int(alt_cx * len(mascaras) + pad_t + pad_b)
        folga = 56
        L, A = larg_b + 2 * folga, alt_b + 2 * folga

        alpha = np.zeros((A, L), dtype=np.float32)
        rgb = np.zeros((A, L, 3), dtype=np.float32)
        base = None
        if fundo is not None:
            img = Image.new("L", (L, A), 0)
            ImageDraw.Draw(img).rounded_rectangle(
                [folga, folga, folga + larg_b, folga + alt_b], radius=raio,
                fill=255)
            a_f = np.asarray(img, dtype=np.float32) / 255.0
            base = a_f.copy()
            if isinstance(fundo, tuple):        # (cor, opacidade)
                cor_f, op_f = fundo
                a_f = a_f * op_f
            else:
                cor_f = fundo
            alpha = a_f
            rgb[:] = self._cor(cor_f)
        if borda is not None:
            cor_bd, esp = borda
            img = Image.new("L", (L, A), 0)
            ImageDraw.Draw(img).rounded_rectangle(
                [folga, folga, folga + larg_b, folga + alt_b], radius=raio,
                outline=255, width=esp)
            a_bd = np.asarray(img, dtype=np.float32) / 255.0
            rgb = rgb * (1 - a_bd[..., None]) + self._cor(cor_bd) * a_bd[..., None]
            alpha = np.maximum(alpha, a_bd)
            base = a_bd if base is None else np.maximum(base, a_bd)

        t_a = np.zeros((A, L), dtype=np.float32)
        y = folga + pad_t
        posicoes = []
        for m, _ in pares:
            h_m, w_m = m.shape
            tx = (folga + pad_esq if pad_esq is not None
                  else folga + pad_x + int((larg_txt - w_m) / 2))
            ty = int(y + (alt_cx - (asc + desc)) / 2)
            hh, ww = min(h_m, A - ty), min(w_m, L - tx)
            t_a[ty:ty + hh, tx:tx + ww] = np.maximum(
                t_a[ty:ty + hh, tx:tx + ww], m[:hh, :ww])
            posicoes.append((tx, ty))
            y += alt_cx
        rgb = rgb * (1 - t_a[..., None]) + self._cor(cor) * t_a[..., None]
        alpha = np.maximum(alpha, t_a)
        for (tx, ty), (_, cor_e) in zip(posicoes, pares):
            self._pintar_emoji(rgb, cor_e, tx, ty)
        base = t_a if base is None else np.maximum(base, t_a)
        sombra = (self._sombra_de(base, especs, k=0.5) if especs
                  else np.zeros_like(alpha))

        if rot:
            # Mesma troca de convencao do bloco de uma linha: CSS gira para
            # um lado, Pillow para o outro. E a `fita` (-2,4 e 1,8 graus)
            # passa por aqui.
            _giro = -float(rot)

            def _g(a):
                im = Image.fromarray((a * 255).astype(np.uint8), "L")
                return np.asarray(im.rotate(_giro, expand=False,
                                            resample=Image.BICUBIC),
                                  dtype=np.float32) / 255.0
            alpha, sombra = _g(alpha), _g(sombra)
            rgb = np.asarray(Image.fromarray(rgb.astype(np.uint8), "RGB")
                             .rotate(_giro, expand=False,
                                     resample=Image.BICUBIC),
                             dtype=np.float32)
        leg.palavras.append(Palavra(
            int(x0) - folga, int(y_topo) - folga, rgb, alpha, sombra,
            inicio_f=0, enter=enter, sobe=sobe))

    def _montar_headline(self, hook: dict) -> Camada:
        """Desenha a headline e aplica a ENTRADA escolhida no preset.

        `pop` e `deslizar` existiam so no Remotion: pelo caminho rapido a
        escolha do usuario virava um fade parado, sem recusa e sem aviso.
        carimbo e pergunta tem entradas proprias e ignoram (como no Main).
        """
        leg = self._montar_headline_bruta(hook)
        anim = str(hook.get("animation") or "padrao")
        estilo = str(hook.get("style") or "outline")
        if estilo not in ("carimbo", "pergunta"):
            if anim == "deslizar":
                # vem da esquerda (-56px), sem subir — Main.tsx `slideX`
                for pal in leg.palavras:
                    pal.desliza, pal.sobe = -56.0, 0.0
            elif anim == "pop":
                self._pop_na_camada(leg)
        return leg

    def _pop_na_camada(self, leg: Camada) -> None:
        """Escala 0.68→1 com overshoot (Easing.back(2)) — Main.tsx popScale."""
        def _curva(t: float) -> tuple[float, float]:
            u = t - 1.0
            esc = 0.68 + 0.32 * (1.0 + 3.0 * u ** 3 + 2.0 * u ** 2)
            op = 1.0 - (1.0 - min(1.0, t * 9 / 8.0)) ** 3
            return esc, op

        self._entrada_em_escala(leg, 9, _curva)

    def _slam_na_camada(self, leg: Camada) -> None:
        """`carimbo`: bate de 1,9x para 1x em 7 quadros (out-cubic), com a
        opacidade na mesma curva — Main.tsx `1.9 - 0.9 * slam`."""
        def _curva(t: float) -> tuple[float, float]:
            e = 1.0 - (1.0 - t) ** 3
            return 1.9 - 0.9 * e, e

        self._entrada_em_escala(leg, 7, _curva)

    def _entrada_em_escala(self, leg: Camada, n: int, curva) -> None:
        """Reamostra a camada pronta por estagio, como o Chrome faz com
        `transform: scale` (ele tambem nao redesenha o texto). Um estagio
        por quadro; o ultimo fica ate o fim. `curva(t) -> (escala, opac)`."""
        def _redim_l(arr, nw, nh):
            im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "L")
            return np.asarray(im.resize((nw, nh), Image.BILINEAR),
                              dtype=np.float32) / 255.0

        originais = list(leg.palavras)
        leg.palavras = []
        for pal in originais:
            h, w = pal.alpha.shape
            cx, cy = pal.x0 + w / 2.0, pal.y0 + h / 2.0
            for est in range(n + 1):
                # t = est/n, comecando em ZERO: no template o quadro 0 da
                # entrada e invisivel (interpolate parte de 0). Comecar em
                # 1/n punha o carimbo 40% opaco em 1,5x ja no quadro 0.
                t = min(1.0, est / n)
                esc, op = curva(t)
                nw = max(1, int(round(w * esc)))
                nh = max(1, int(round(h * esc)))
                rgb = np.asarray(
                    Image.fromarray(np.clip(pal.rgb, 0, 255).astype(np.uint8),
                                    "RGB").resize((nw, nh), Image.BILINEAR),
                    dtype=np.float32)
                leg.palavras.append(Palavra(
                    int(round(cx - nw / 2)), int(round(cy - nh / 2)), rgb,
                    _redim_l(pal.alpha, nw, nh), _redim_l(pal.sombra, nw, nh),
                    inicio_f=pal.inicio_f, enter=pal.enter,
                    janela=((float(est), float(est + 1)) if est < n
                            else (float(n), 1e9)),
                    opac=op, sobe=0.0))

    def _montar_headline_bruta(self, hook: dict) -> Camada:
        """Os 9 estilos de headline. O layout (duas linhas, ajuste de tamanho,
        entrada e saida) e comum; cada estilo escolhe a PINTURA."""
        estilo = hook.get("style") or "outline"
        pesos, cap0, safe_w0, lh, top0 = self.HL_STYLES.get(
            estilo, self.HL_STYLES["outline"])
        fim = int(float(hook.get("endSec") or 4.0) * self.fps)
        accent = hook.get("accent") or "#ff5200"
        texto = (hook.get("text") or " ".join(hook.get("lines") or [])).strip()
        if estilo in self.HL_MAIUSCULA:
            texto = texto.upper()
        cap = int(hook.get("fontSizePx") or hook.get("maxFontPx") or cap0)
        safe_w = float(hook.get("safeWidth") or safe_w0)
        linhas, tam = self._hl_linhas(texto, pesos, cap, safe_w)
        lh = float(hook.get("lineHeight") or lh)
        top = _pos(hook, "paddingTop", top0)
        # CENTRO da tela: a abertura em que a manchete e a unica coisa no
        # quadro. O calculo mora aqui (e no template) porque so agora se sabe
        # quantas linhas ela tem e com que tamanho de fonte — um paddingTop
        # decidido no pipeline erraria em toda manchete de duas linhas.
        if hook.get("centro"):
            top = max(0.0, (self.h - len(linhas) * lh * tam) / 2.0)

        leg = Camada(0, fim)
        leg.dur_f = fim
        leg.saida_f = fim - 9
        leg.exit_fade = True
        alt_cx = lh * tam

        # entrada: `padrao` NAO tem entrada — a headline existe desde o quadro
        # 0 (Main.tsx, HookInner: `enter = anim === 'padrao' ? 1 : ...`). Ela e
        # a primeira coisa que o espectador le e nascia invisivel. `pop` e
        # `deslizar` sao entradas escolhidas e continuam entrando do zero.
        anim = str(hook.get("animation") or "padrao")
        enter_hl = 0 if anim == "padrao" else 8
        sobe = 0.0

        if estilo == "pergunta":
            # Duas fases na MESMA headline: a pergunta abre em branco (como o
            # `outline`, sem contorno) e some em 6 quadros; no answerAtSec a
            # resposta entra numa pilula do accent com pop (Easing.back 1.8),
            # e fica ate o fim. Cada fase e um conjunto de Palavras com
            # janela — o mesmo mecanismo do traco do Recorte.
            at = max(1, int(round(float(hook.get("answerAtSec") or 2.5) * self.fps)))
            resposta = " ".join(hook.get("answerLines") or []).strip() or texto
            a_linhas, a_tam = self._hl_linhas(resposta, (900, 900), cap, safe_w)
            a_alt_cx = lh * a_tam

            # fase 1: a pergunta, ate `at` (com 6 quadros de fade)
            y = top
            for l in linhas:
                larg = self._larg_hl(l, tam, 800)
                for q in range(6):
                    op = 1.0 - (q + 1) / 6
                    self._hl_bloco_texto(
                        leg, l, tam, 800, (self.w - larg) / 2, y, alt_cx,
                        "#ffffff", [(0, 6, 18, 0.55)], sobe=0.0)
                    p = leg.palavras[-1]
                    p.alpha[:] *= op
                    p.sombra[:] *= op
                    p.janela = (at - 6 + q, at - 6 + q + 1)
                # o corpo estavel da pergunta: do inicio ate o comeco do fade
                self._hl_bloco_texto(
                    leg, l, tam, 800, (self.w - larg) / 2, y, alt_cx,
                    "#ffffff", [(0, 6, 18, 0.55)], sobe=sobe, enter=enter_hl)
                leg.palavras[-1].janela = (0, at - 6)
                y += alt_cx

            # fase 2: a resposta em pilula, com pop
            y2 = top
            for l in a_linhas:
                pad = (0.3 * a_tam, 0.08 * a_tam, 0.16 * a_tam)
                larg_b = self._larg_hl(l, a_tam, 900) + 2 * pad[0]
                for q in range(8):
                    t = min(1.0, q / 7)
                    esc = 0.8 + 0.2 * self._ease_back(t, 1.8)
                    tam_e = max(8, int(a_tam * esc))
                    pad_e = (pad[0] * esc, pad[1] * esc, pad[2] * esc)
                    larg_e = self._larg_hl(l, tam_e, 900) + 2 * pad_e[0]
                    self._hl_bloco_texto(
                        leg, l, tam_e, 900, (self.w - larg_e) / 2,
                        y2 + (a_alt_cx - lh * tam_e) / 2, lh * tam_e,
                        "#ffffff", [(0, 10, 28, 0.45)], fundo=accent,
                        raio=max(2, int(12 * esc)), pad_xy=pad_e, sobe=0.0)
                    leg.palavras[-1].janela = (at + q, at + q + 1) if q < 7 \
                        else (at + 7, 1e9)
                y2 += a_alt_cx + 10
            return leg

        if estilo == "faixa":
            # de ponta a ponta: o respiro lateral e o que sobra da largura
            y = top
            for l in linhas:
                larg = self._larg_hl(l, tam, 900)
                pad_x = max(24.0, (self.w - larg) / 2)
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, (self.w - (larg + 2 * pad_x)) / 2, y,
                    alt_cx, "#ffffff", [(0, 10, 28, 0.45)], fundo=accent,
                    raio=0, pad_xy=(pad_x, 0.08 * tam, 0.16 * tam),
                    sobe=sobe, enter=enter_hl)
                y += alt + 8
            return leg

        if estilo == "fita":
            # as caixas do realce, tortas em sentidos opostos
            y = top
            for i, l in enumerate(linhas):
                pad = (0.34 * tam, 0.08 * tam, 0.16 * tam)
                larg_b = self._larg_hl(l, tam, 900) + 2 * pad[0]
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, (self.w - larg_b) / 2, y, alt_cx,
                    "#ffffff", [(0, 12, 30, 0.5)], fundo=accent, raio=6,
                    pad_xy=pad, sobe=sobe, enter=enter_hl,
                    rot=(-2.4 if i == 0 else 1.8))
                y += alt + 12
            return leg

        if estilo == "neon":
            # duas passadas na MESMA geometria: a de baixo vira brilho, a de
            # cima e a letra branca. Chamar o mesmo ajudante garante que as
            # duas caem no mesmo pixel — calcular a posicao do brilho na mao
            # erraria por causa do `folga` e do centro da caixa.
            y = top
            for l in linhas:
                larg = self._larg_hl(l, tam, 900)
                x = (self.w - larg) / 2
                self._hl_bloco_texto(
                    leg, l, tam, 900, x, y, alt_cx, accent, [],
                    sobe=sobe, enter=enter_hl)
                brilho = leg.palavras[-1]
                # text-shadow 0 0 12/28/52px (sigma = raio/2 no Chrome). As
                # tres sombras sao EMPILHADAS uma sobre a outra, nao a maior
                # das tres: medido contra o Remotion, pegar a maior dava 0,35
                # da tinta dele — um brilho fraco e curto demais.
                base_br = brilho.alpha.copy()
                acc = np.zeros_like(base_br)
                for raio in (12, 28, 52):
                    b_r = self._sombra_de(base_br, [(0, 0, raio, 1.0)], k=0.5)
                    acc = acc + b_r - acc * b_r
                brilho.alpha[:] = np.clip(acc, 0.0, 1.0)
                # a cor tem de cobrir TUDO que o borrao alcancou: ela so
                # existia dentro da letra, e o brilho espalhado saia preto
                # (o par contra o Remotion mostrou halo preto onde devia ser
                # vermelho — a razao de tinta dizia 1,003 e nao viu nada).
                brilho.rgb[:] = self._cor(accent)
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, x, y, alt_cx, "#ffffff",
                    [(0, 6, 16, 0.45)], sobe=sobe, enter=enter_hl)
                y += alt
            return leg

        if estilo == "vazado":
            y = top
            for l in linhas:
                pad = (0.3 * tam, 0.08 * tam, 0.16 * tam)
                larg_b = self._larg_hl(l, tam, 900) + 2 * pad[0]
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, (self.w - larg_b) / 2, y, alt_cx,
                    # `filter: drop-shadow` no <svg> do template: sigma e o
                    # RAIO INTEIRO (BLUR_K). Com o padrao 0,5 o halo saia em
                    # 0,72 do template e a tinta do estilo em 0,856.
                    "#ffffff", [(0, 12, 30, 0.45)], k_sombra=BLUR_K,
                    fundo=accent, raio=10,
                    pad_xy=pad, sobe=sobe, enter=enter_hl, vazar=True)
                y += alt + 10
            return leg

        if estilo == "gradiente":
            y = top
            for l in linhas:
                larg = self._larg_hl(l, tam, 900)
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, (self.w - larg) / 2, y, alt_cx,
                    # `filter: drop-shadow`, nao `text-shadow`: o sigma e o
                    # RAIO INTEIRO (BLUR_K), nao a metade. O padrao 0,5 do
                    # ajudante deixava o halo em 0,71 do template — e a tinta
                    # do estilo em 0,815, o pior das 15 headlines.
                    "#ffffff", [(0, 8, 22, 0.5)], k_sombra=BLUR_K,
                    sobe=sobe, enter=enter_hl)
                pal = leg.palavras[-1]
                # o degrade corre pela LETRA, nao pela imagem inteira: a peca
                # tem 56px de folga em volta, e usar a altura toda achataria
                # a faixa de cor no meio dos glifos.
                ys = np.nonzero(pal.alpha.max(axis=1) > 0.02)[0]
                if len(ys):
                    y0, y1 = int(ys[0]), int(ys[-1])
                    t = np.zeros(pal.alpha.shape[0], dtype=np.float32)
                    if y1 > y0:
                        t[y0:y1 + 1] = np.linspace(0.0, 1.0, y1 - y0 + 1,
                                                   dtype=np.float32)
                    t[y1 + 1:] = 1.0
                    tt = t[:, None, None]
                    pal.rgb[:] = (pal.rgb * (1 - tt)
                                  + self._cor(accent)[None, None, :] * tt)
                y += alt
            return leg

        if estilo == "realce":
            y = top
            for l in linhas:
                pad = (0.3 * tam, 0.08 * tam, 0.16 * tam)
                larg_b = self._larg_hl(l, tam, pesos[0]) + 2 * pad[0]
                alt = self._hl_bloco_texto(
                    leg, l, tam, pesos[0], (self.w - larg_b) / 2, y, alt_cx,
                    "#ffffff", [(0, 10, 28, 0.45)], fundo=accent, raio=12,
                    pad_xy=pad, sobe=sobe, enter=enter_hl)
                y += alt + 10
            return leg

        if estilo == "card":
            # linha opcional de logo + assinatura acima do bloco (gap 28),
            # como o container em coluna do template. O logo tem canto
            # arredondado e box-shadow (sigma raio/2); a assinatura tem
            # drop-shadow (sigma ~= raio).
            y = top
            imgs = []
            lg = self._abrir_imagem(hook.get("logo"), 300, raio=18)
            if lg:
                imgs.append((lg, [(0, 12, 34, 0.4)], 0.5))
            sg = self._abrir_imagem(hook.get("sign"), 128)
            if sg:
                imgs.append((sg, [(0, 8, 20, 0.45)], BLUR_K))
            if imgs:
                gap_i = 34
                larg_l = sum(i[0][1].shape[1] for i in imgs) + gap_i * (len(imgs) - 1)
                alt_l = max(i[0][1].shape[0] for i in imgs)
                x = (self.w - larg_l) / 2
                for img, esp, k in imgs:          # centralizados na linha
                    h_i, w_i = img[1].shape
                    self._palavra_imagem(leg, img, x, y + (alt_l - h_i) / 2,
                                         esp, k, enter_hl, sobe)
                    x += w_i + gap_i
                y += alt_l + 28
            # a caixa escura envolve o BLOCO. Aplicada por linha, a segunda
            # (mais curta) ganhava uma caixa mais estreita e a borda direita
            # saia em degrau — o mesmo defeito que a manchete tinha.
            larg_max = max((self._larg_hl(l, tam, 900) for l in linhas),
                           default=0)
            self._hl_bloco_multi(
                leg, linhas, tam, 900, alt_cx,
                (self.w - (larg_max + 92)) / 2, y, "#ffffff",
                [(0, 18, 50, 0.45)], raio=24, pad_xy=(46, 28, 28),
                fundo="#232326", sobe=sobe, enter=enter_hl)
            return leg

        if estilo == "misto":
            y = top
            for i, l in enumerate(linhas):
                peso = pesos[min(i, 1)]
                cor = "#ffffff" if i == 0 else accent
                larg = self._larg_hl(l, tam, peso)
                alt = self._hl_bloco_texto(
                    leg, l, tam, peso, (self.w - larg) / 2, y, alt_cx, cor,
                    [(0, 6, 16, 0.55)], k_sombra=BLUR_K, sobe=sobe, enter=enter_hl)
                y += alt
            return leg

        if estilo == "sombra":
            off = max(4, round(tam * 0.07))   # `off = max(4, size*0.07)` do template
            y = top
            for l in linhas:
                larg = self._larg_hl(l, tam, 900)
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, (self.w - larg) / 2, y, alt_cx, "#ffffff",
                    [(off, off, 0, 1.0), (0, 6, 18, 0.5)], sobe=sobe, enter=enter_hl)
                # textShadow `off off 0 accent`: copia DURA do glifo por
                # baixo, deslocada — so aparece onde o texto nao cobre.
                p = leg.palavras[-1]
                dura = np.zeros_like(p.alpha)
                dura[off:, off:] = p.alpha[:-off, :-off]
                fica = np.clip(dura - p.alpha, 0.0, 1.0)
                p.rgb[:] = p.rgb * (1 - fica[..., None])                     + self._cor(accent) * fica[..., None]
                p.alpha[:] = np.maximum(p.alpha, dura)
                y += alt
            return leg

        if estilo == "sublinhado":
            # 0,19 e nao 0,14: o template subiu a barra de 0,13 para 0,19 de
            # proposito ("0.13 rendered as a hairline rule that competed with
            # busy footage instead of anchoring the text") e o motor proprio
            # ficou no numero antigo.
            barra_h = max(8, round(tam * 0.19))
            sobra = round(tam * 0.06)        # `left/right: -0.06em`
            y = top
            for l in linhas:
                larg = self._larg_hl(l, tam, 900)
                # A BARRA VEM PRIMEIRO: no template ela e o irmao de baixo do
                # texto dentro do wrapper `position: relative`, entao o texto
                # passa POR CIMA dela. Aqui a ordem em `palavras` e a ordem de
                # pintura — a barra era a ultima, cobria os descendentes, e a
                # linha lia como uma regua solta em vez de um marca-texto.
                larg_b = int(larg) + 2 * sobra
                img = Image.new("L", (larg_b, barra_h), 0)
                ImageDraw.Draw(img).rounded_rectangle(
                    [0, 0, larg_b - 1, barra_h - 1], radius=barra_h // 2,
                    fill=255)
                a_b = np.asarray(img, dtype=np.float32) / 255.0
                # base da barra a `0.06em` do fim da caixa de linha
                y_barra = int(y + alt_cx - round(tam * 0.06) - barra_h)
                leg.palavras.append(Palavra(
                    int((self.w - larg) / 2) - sobra, y_barra,
                    np.broadcast_to(self._cor(accent), (*a_b.shape, 3)).copy(),
                    a_b, np.zeros_like(a_b), inicio_f=0, enter=enter_hl,
                    sobe=sobe))
                alt = self._hl_bloco_texto(
                    leg, l, tam, 900, (self.w - larg) / 2, y, alt_cx, "#ffffff",
                    # `0 4px 16px rgba(0,0,0,0.55)` do template. Estava
                    # `(0, 6, 18, 0.5)` — deslocamento e borrao maiores, o que
                    # deixava o halo 43% acima do dele.
                    [(0, 4, 16, 0.55)], sobe=sobe, enter=enter_hl)
                y += alt + round(tam * 0.16)
            return leg

        if estilo == "pilula":
            uma = " ".join(linhas)
            larg = self._larg_hl(uma, tam, 700)
            # [bolinha 0.3, vao 0.35, texto] dentro da capsula — Main.tsx
            # 998-1006. A pilula fica na tela o video INTEIRO; sem a bolinha
            # era a divergencia mais visivel em tempo de tela do catalogo.
            bola = round(tam * 0.3)
            vao = round(tam * 0.35)
            pad_lado = round(tam * 0.6)
            pad = (pad_lado, round(tam * 0.3), round(tam * 0.3))
            pad_esq = pad_lado + bola + vao
            larg_b = larg + pad_esq + pad_lado
            x0 = (self.w - larg_b) / 2
            self._hl_bloco_multi(
                leg, [uma], tam, 700, alt_cx, x0, top, "#ffffff",
                [(0, 10, 30, 0.35)], fundo=("#111214", 0.78), raio=999,
                pad_xy=pad, sobe=sobe, enter=enter_hl, pad_esq=pad_esq)
            img = Image.new("L", (bola, bola), 0)
            ImageDraw.Draw(img).ellipse([0, 0, bola - 1, bola - 1], fill=255)
            a_bola = np.asarray(img, dtype=np.float32) / 255.0
            alt_b = alt_cx + pad[1] + pad[2]
            leg.palavras.append(Palavra(
                int(x0 + pad_lado), int(top + (alt_b - bola) / 2),
                np.broadcast_to(self._cor(hook.get("accent") or "#ff5200"),
                                (*a_bola.shape, 3)).copy(),
                a_bola, np.zeros_like(a_bola), inicio_f=0, enter=enter_hl,
                sobe=sobe))
            return leg

        if estilo == "manchete":
            # a faixa escura envolve as DUAS linhas (uma peca so), com a
            # barra de acento colada a esquerda dela. Aplicar o fundo por
            # linha deixava a faixa 20% mais baixa que a do Remotion
            # (182px contra 230px, medido).
            bottom = _pos(hook, "paddingBottom", 140)
            # `padding: 26px 44px` e `gap: 26` do template, com os filhos
            # [barra de 12px, texto]: a barra fica DENTRO da lapide, a 44px
            # da borda, e o texto comeca a 44+12+26 = 82px, alinhado a
            # ESQUERDA. Antes a barra era desenhada 30px a esquerda da
            # lapide (do lado de fora) e o texto ia centrado.
            pad_lado, barra, vao = 44, 12, 26
            pad = (pad_lado, 26, 26)
            pad_esq = pad_lado + barra + vao
            larg_max = max((self._larg_hl(l, tam, 800) for l in linhas),
                           default=0)
            larg_b = larg_max + pad_esq + pad_lado
            alt_b = alt_cx * len(linhas) + pad[1] + pad[2]
            x_faixa = (self.w - larg_b) / 2
            y0 = self.h - bottom - alt_b
            img = Image.new("L", (barra, int(alt_b)), 0)
            ImageDraw.Draw(img).rounded_rectangle(
                [0, 0, barra - 1, int(alt_b) - 1], radius=6, fill=255)
            a_b = np.asarray(img, dtype=np.float32) / 255.0
            self._hl_bloco_multi(
                leg, linhas, tam, 800, alt_cx, x_faixa, y0, "#ffffff",
                # `0 14px 40px rgba(0,0,0,0.45)` do template. Estava
                # `(0, 10, 26, 0.4)` — deslocamento, borrao e opacidade os
                # tres menores, o que deixava o halo em 0,622.
                [(0, 14, 40, 0.45)], raio=18, pad_xy=pad,
                fundo=("#0c0d0f", 0.86), sobe=sobe, enter=enter_hl,
                pad_esq=pad_esq)
            # A barra vem DEPOIS da lapide: a ordem em `palavras` e a ordem de
            # pintura, e a lapide (86% opaca) cobria a barra quando ela era
            # desenhada antes. Fora da lapide isso nao aparecia — o defeito
            # nasceu junto com a barra entrando para dentro.
            leg.palavras.append(Palavra(
                int(x_faixa + pad_lado), int(y0),
                np.broadcast_to(self._cor(accent), (*a_b.shape, 3)).copy(),
                a_b, np.zeros_like(a_b), inicio_f=0, enter=enter_hl, sobe=sobe))
            return leg

        if estilo == "carimbo":
            # a moldura envolve o BLOCO INTEIRO (as duas linhas): o carimbo e
            # uma peca so, girada -6 graus de uma vez.
            bw = max(6, round(tam * 0.09))
            # padding 0.18em/0.4em, fundo rgba(10,10,12,0.25) e text-shadow
            # `0 4px 14px .45` do template — os quatro estavam divergentes.
            pad = (round(tam * 0.4), round(tam * 0.18), round(tam * 0.18))
            larg_max = max((self._larg_hl(l, tam, 900) for l in linhas),
                           default=0)
            self._hl_bloco_multi(
                leg, linhas, tam, 900, alt_cx,
                (self.w - (larg_max + 2 * pad[0])) / 2, top,
                accent, [(0, 4, 14, 0.45)], raio=18, pad_xy=pad,
                fundo=("#0a0a0c", 0.25),
                borda=(accent, bw), rot=-6.0, sobe=0.0)
            # o slam e a entrada PROPRIA do carimbo (por isso ele ignora
            # pop/deslizar no wrapper): 1,9x -> 1x em 7 quadros.
            self._slam_na_camada(leg)
            return leg

        # outline (padrao): branco com contorno preto grosso.
        # `-webkit-text-stroke` do template e CENTRADO — metade do traco cai
        # dentro do glifo e o `paint-order: stroke fill` cobre essa metade com
        # o branco. So a metade de FORA aparece. Medido no proprio Chrome
        # (traco 40): o glifo branco fica igual, 44px, e o preto sai 20px para
        # fora. Dilatar `strokePx` inteiro pintava o contorno em DOBRO.
        # `is None`, nao `or`: strokePx=0 e "sem contorno", um valor de fato.
        _st = hook.get("strokePx")
        stroke = max(0, round((12.0 if _st is None else float(_st)) / 2.0))
        y = top
        for l in linhas:
            larg = self._larg_hl(l, tam, 800)
            alt = self._hl_bloco_texto(
                leg, l, tam, 800, (self.w - larg) / 2, y, alt_cx, "#ffffff",
                [(0, 6, 14, 0.45)], k_sombra=BLUR_K,
                contorno=(("#000000", stroke) if stroke > 0 else None),
                sobe=sobe, enter=enter_hl)
            y += alt
        return leg

    # ----- cartão final ------------------------------------------------------
    def _montar_endcard(self, ec: dict, hook_accent: str | None) -> Camada:
        dur = int(round(float(ec.get("lastSec") or 2.5) * self.fps))
        ini = self.frames - dur
        accent = ec.get("accent") or hook_accent or "#ff5200"
        # TODAS as linhas, como o EndCardInner — o [:2] comia a 3a calado.
        linhas = [l for l in (ec.get("lines") or []) if l]
        fade = min(round(0.35 * self.fps), max(1, dur // 2))
        leg = Camada(ini, self.frames + 10)
        leg.dur_f = dur + 20
        leg.saida_f = 1e9
        leg.dim = float(ec.get("dim") if ec.get("dim") is not None else 0.82)
        leg.dim_fade = fade
        # logo do cartao final: imagem 44% da largura, acima das linhas
        logo_rel = ec.get("logo")
        logo_arr = None
        if logo_rel:
            cam = self.public / str(logo_rel)
            if cam.exists():
                try:
                    im = Image.open(cam).convert("RGBA")
                    larg = int(self.w * 0.44)
                    alt = max(1, int(im.height * larg / max(1, im.width)))
                    im = im.resize((larg, alt), Image.LANCZOS)
                    logo_arr = np.asarray(im, dtype=np.float32)
                except OSError:
                    logo_arr = None

        base = round(self.w * 0.058)
        safe_w = self.w * 0.70
        # `scaleOf = i === 0 ? 1 : 0.62` (EndCardInner) — vale para TODAS as
        # linhas; a lista fixa de 2 estourava com a terceira.
        def escala(i: int) -> float:
            return 1.0 if i == 0 else 0.62

        ajuste = 1.0
        for i, t in enumerate(linhas):
            f = self.fonte(4 if i == 0 else 7, int(base * escala(i)), marca=None)
            wl = f.getlength(t) - 1.0 * max(0, len(t) - 1)
            if wl > safe_w:
                ajuste = min(ajuste, safe_w / wl)
        tam = max(28, round(base * ajuste))
        mascaras = []
        for i, t in enumerate(linhas):
            # 900 na primeira, 600 nas demais — `EndCardInner` em Main.tsx
            f = self.fonte(4 if i == 0 else 7, int(tam * escala(i)), marca=None)
            m, cor_e = self._mascara_cor(f, t, -1.0)
            mascaras.append((m, i, cor_e))
        gap = round(tam * 0.34)
        total = sum(m.shape[0] for m, _, _ in mascaras) + gap * max(0, len(mascaras) - 1)
        if logo_arr is not None:
            total += logo_arr.shape[0] + gap
        y = (self.h - total) / 2.0
        if logo_arr is not None:
            a_l = logo_arr[..., 3] / 255.0
            leg.palavras.append(Palavra(
                int((self.w - logo_arr.shape[1]) / 2), int(y),
                logo_arr[..., :3].copy(), a_l, np.zeros_like(a_l),
                inicio_f=0, enter=fade, sobe=26.0))
            y += logo_arr.shape[0] + gap
        for m, i, cor_e in mascaras:
            h_m, w_m = m.shape
            folga = 32
            pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga), dtype=np.float32)
            pad_m[folga:folga + h_m, folga:folga + w_m] = m
            b = np.asarray(Image.fromarray((pad_m * 255).astype(np.uint8))
                           .filter(ImageFilter.GaussianBlur(24 * 0.5)),
                           dtype=np.float32) / 255.0
            sombra = np.zeros_like(b)
            sombra[4:, :] = b[:-4, :] * 0.6
            cor = self._cor(accent) if i == 0 else np.array([255.0] * 3, dtype=np.float32)
            rgb = np.broadcast_to(cor, (*pad_m.shape, 3)).copy()
            self._pintar_emoji(rgb, cor_e, folga)
            leg.palavras.append(Palavra(
                int((self.w - w_m) / 2) - folga, int(y) - folga, rgb, pad_m,
                sombra, inicio_f=0, enter=fade, sobe=26.0))
            y += h_m + gap
        return leg

    # ----- legendas `impacto` ------------------------------------------------
    @staticmethod
    def _agrupar_impacto(words, larg_de, max_w: float = 820.0,
                         max_words: int = 3):
        """O agrupamento do ImpactCaptions: largura medida > contagem >
        respiro (pontuacao ou pausa >450 ms). O contrato de quebra e o mesmo
        dos estilos estaticos — trocar de estilo nao reagrupa a fala."""
        import re

        cues, cur = [], []
        for i, w in enumerate(words):
            trial = cur + [w]
            if cur and (len(trial) > max_words or larg_de(trial) > max_w):
                cues.append(cur)
                cur = [w]
            else:
                cur = trial
            nxt = words[i + 1] if i + 1 < len(words) else None
            gap = (nxt["startMs"] - w["endMs"]) if nxt else 0
            if cur and (re.search(r"[.,!?\u2026]$", w["text"]) or gap > 450):
                cues.append(cur)
                cur = []
        if cur:
            cues.append(cur)
        return cues

    @staticmethod
    def _ease_back(t: float, b: float = 2.2) -> float:
        """Easing.out(Easing.back(2.2)) do Remotion: overshoot que assenta."""
        t -= 1.0
        return 1.0 + (b + 1.0) * t ** 3 + b * t * t

    @staticmethod
    def _tinta_na_caixa(bg: str) -> str:
        n = int(bg.lstrip("#"), 16)
        r, g, b = ((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255
        return "#111214" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6 else "#ffffff"

    def _montar_impacto(self):
        """Uma Camada por PERIODO de palavra quente: quando a caixa muda de
        palavra, a linha inteira se reposiciona (a caixa tem padding proprio),
        entao cada periodo e um layout completo."""
        import re

        caps_cfg = self.ed.get("captions") or {}
        tam = round(72 * float(caps_cfg.get("sizeScale") or 1.0))
        bottom = _pos(caps_cfg, "paddingBottom", 430)
        cor_caixa = caps_cfg.get("emphasisAccent") or "#ffd400"
        cor_tinta = self._tinta_na_caixa(cor_caixa)
        f = self.fonte(4, tam, 900)   # capWeight(900) — marca variavel inclusa

        raw = json.loads((self.public / "captions.json")
                         .read_text(encoding="utf-8-sig"))
        words = raw if isinstance(raw, list) else (raw.get("words") or [])

        def limpar(t):
            return re.sub(r"[.,!?\u2026]+$", "", t).upper()

        larg_pal = lambda w: f.getlength(limpar(w["text"]))
        larg_grupo = lambda ws: f.getlength(" ".join(limpar(w["text"]) for w in ws))
        cues = self._agrupar_impacto(words, larg_grupo)

        POP = 5
        pad = round(tam * 0.18)
        gap = round(tam * 0.22)
        raio = round(tam * 0.18)
        camadas = []

        for ci, cue in enumerate(cues):
            ini_f = int(round(cue[0]["startMs"] / 1000 * self.fps))
            nxt = cues[ci + 1] if ci + 1 < len(cues) else None
            fim_f = (int(round(nxt[0]["startMs"] / 1000 * self.fps)) - 1 if nxt
                     else min(self.frames,
                              int(round(cue[-1]["endMs"] / 1000 * self.fps))
                              + int(self.fps)))
            for hi, hot_w in enumerate(cue):
                h_ini = max(ini_f, int(round(hot_w["startMs"] / 1000 * self.fps)))
                h_fim = (int(round(cue[hi + 1]["startMs"] / 1000 * self.fps)) - 1
                         if hi + 1 < len(cue) else fim_f)
                if h_fim < h_ini:
                    continue
                leg = Camada(h_ini, h_fim)
                leg.dur_f = h_fim - h_ini + 1
                leg.saida_f = 1e9

                largs = []
                for i, w in enumerate(cue):
                    lw = larg_pal(w)
                    if i == hi:
                        lw += 2 * pad
                    largs.append(lw)
                total = sum(largs) + gap * (len(cue) - 1)
                x = (self.w - total) / 2
                asc, desc = f.getmetrics()
                alt_linha = tam * 1.08
                y_base = self.h - bottom - alt_linha
                y_texto = int(round(y_base + (alt_linha - (asc + desc)) / 2))

                for i, w in enumerate(cue):
                    texto = limpar(w["text"])
                    if i != hi:
                        # `textShadow: 0 4px 18px` (ImpactCaptions.tsx:142) —
                        # text-shadow pede sigma = raio/2. Com o padrao de
                        # drop-shadow o halo de CADA palavra branca saia
                        # maior, e como o numero de palavras muda de video
                        # para video, a divergencia do `impacto` mudava
                        # junto: 1,032 num projeto e 1,174 noutro.
                        self._palavra_texto(
                            leg, f, texto, 0.0, int(round(x)), y_base,
                            alt_linha, y_texto, "#ffffff", -1, 1,
                            especs=[(0, 4, 18, 0.6)], k_sombra=0.5)
                        leg.palavras[-1].sobe = 0.0
                    else:
                        lw = larg_pal(w)
                        cw = int(lw + 2 * pad)
                        # caixa CSS = line-height (1.08em) + paddings, NAO
                        # ascent+descent (medido: 113px contra 92px do
                        # Remotion). Mesmo erro que a headline teve.
                        ch = int(tam * 1.08 + pad * 0.35 + pad * 0.5)
                        for est in range(POP + 1):
                            t = min(1.0, est / POP)
                            esc = 0.7 + 0.3 * self._ease_back(t)
                            ew, eh = max(2, int(cw * esc)), max(2, int(ch * esc))
                            img = Image.new("L", (ew + 64, eh + 64), 0)
                            ImageDraw.Draw(img).rounded_rectangle(
                                [32, 32, 32 + ew, 32 + eh],
                                radius=max(2, int(raio * esc)), fill=255)
                            a_caixa = np.asarray(img, dtype=np.float32) / 255.0
                            fe = self.fonte(4, max(8, int(tam * esc)), 900)  # capWeight(900)
                            m, cor_emj = self._mascara_cor(fe, texto, 0.0)
                            t_a = np.zeros_like(a_caixa)
                            tx = 32 + int(pad * esc)
                            # texto centrado na caixa de linha (meia-entrelinha)
                            ty = 32 + int((pad * 0.35
                                           + (tam * 1.08 - (asc + desc)) / 2) * esc)
                            hm = min(m.shape[0], t_a.shape[0] - ty)
                            wm = min(m.shape[1], t_a.shape[1] - tx)
                            t_a[ty:ty + hm, tx:tx + wm] = m[:hm, :wm]
                            cor_c = self._cor(cor_caixa)
                            cor_t = self._cor(cor_tinta)
                            rgb = np.broadcast_to(cor_c, (*a_caixa.shape, 3)).copy()
                            rgb = rgb * (1 - t_a[..., None]) + cor_t * t_a[..., None]
                            self._pintar_emoji(rgb, cor_emj, tx, ty)
                            alpha = np.maximum(a_caixa, t_a)
                            # boxShadow 0 10px 26px rgba(0,0,0,.45): para
                            # box-shadow o sigma e raio/2 (ao contrario do
                            # drop-shadow, onde o Chrome usa ~raio). Medido:
                            # com sigma=raio o halo saia 49% maior que o do
                            # Remotion.
                            #
                            #
                            # E ESTE COMENTARIO desmentia a propria linha:
                            # o codigo usava `26 * 0.25`, que e raio/4.
                            #
                            # SAO DUAS SOMBRAS, e as duas pedem raio/2: esta,
                            # da caixa da palavra quente (`box-shadow`), e a
                            # do TEXTO das palavras brancas (`text-shadow 0
                            # 4px 18px`, la em cima). So a primeira tinha sido
                            # olhada, e por isso a divergencia mudava de
                            # projeto para projeto — o halo a mais das
                            # palavras brancas cresce com o NUMERO delas:
                            #
                            #     so a caixa em raio/4:  0,846 e 1,062
                            #     so a caixa em raio/2:  1,032 e 1,174
                            #     as duas  em raio/2:    1,020 e 1,020
                            #
                            # Dois projetos, o mesmo numero. Foi o que fechou
                            # o caso.
                            b = np.asarray(
                                Image.fromarray((a_caixa * 255).astype(np.uint8))
                                .filter(ImageFilter.GaussianBlur(26 * 0.5)),
                                dtype=np.float32) / 255.0
                            sombra = np.zeros_like(b)
                            sombra[10:, :] = b[:-10, :] * 0.45
                            cx = x + (cw - ew) / 2
                            cy = y_base + (alt_linha - ch) / 2 + (ch - eh) / 2
                            jan = ((h_ini - leg.inicio_f + est,
                                    h_ini - leg.inicio_f + est + 1)
                                   if est < POP else
                                   (h_ini - leg.inicio_f + POP, 1e9))
                            leg.palavras.append(Palavra(
                                int(cx) - 32, int(cy) - 32, rgb, alpha, sombra,
                                inicio_f=0, enter=1, janela=jan, sobe=0.0))
                    x += largs[i] + gap
                camadas.append(leg)
        return camadas

    # ----- legendas `scatter` (disperso) ------------------------------------
    @staticmethod
    def _hash_det(n: float) -> float:
        """O hash deterministico do template: mesmo layout em todo quadro."""
        x = math.sin(n * 127.1 + 311.7) * 43758.5453
        return x - math.floor(x)

    def _montar_scatter(self):
        """Serifada, minusculas, uma palavra por vez em linhas irregulares.
        O deslocamento parece aleatorio mas e HASH do indice — igual ao
        template, que nunca usa Math.random (cada quadro renderiza sozinho).

        Palavra comum: so fade (7 quadros). Destaque (a mais longa >6 letras):
        resolve de um desfoque pesado a 1,62x do tamanho, e volta ao desfoque
        na saida — estagios por quadro, como o traco do Recorte."""
        import re

        caps_cfg = self.ed.get("captions") or {}
        SAFE_W = float(caps_cfg.get("scatterSafeWidth") or 820)
        BASE = int(caps_cfg.get("scatterFontSize") or 72)
        OFFSET_Y = _pos(caps_cfg, "scatterOffsetY", 0.72)
        HI_COLOR = caps_cfg.get("emphasisAccent")
        HI_SCALE, SPREAD, GAP = 1.62, 0.45, 12
        ENTER, HI_ENTER, EXIT = 7, 10, 8

        raw = json.loads((self.public / "captions.json")
                         .read_text(encoding="utf-8-sig"))
        words = raw if isinstance(raw, list) else (raw.get("words") or [])

        def limpar(t):
            return re.sub(r"[.,!?\u2026]+$", "", t).lower()

        # agrupar: pontuacao, 6 palavras ou pausa >400ms
        grupos, cur = [], []
        for i, w in enumerate(words):
            cur.append(w)
            nxt = words[i + 1] if i + 1 < len(words) else None
            gap = (nxt["startMs"] - w["endMs"]) if nxt else 1e9
            if len(cur) >= 6 or re.search(r"[.,!?\u2026]$", w["text"]) or gap > 400:
                grupos.append(cur)
                cur = []
        if cur:
            grupos.append(cur)

        camadas = []
        gradiente_scatter = ("#f8f5ef", "#f4f1e9", "#d5cec1")

        def cor_grad(alt):
            t = np.linspace(0.0, 1.0, max(1, alt), dtype=np.float32)
            c0 = self._cor(gradiente_scatter[0])
            c1 = self._cor(gradiente_scatter[1])
            c2 = self._cor(gradiente_scatter[2])
            saida = np.empty((len(t), 3), dtype=np.float32)
            for k in range(len(t)):
                if t[k] <= 0.54:
                    a = t[k] / 0.54
                    saida[k] = c0 * (1 - a) + c1 * a
                else:
                    a = (t[k] - 0.54) / 0.46
                    saida[k] = c1 * (1 - a) + c2 * a
            return saida

        for gi, g in enumerate(grupos):
            ini_f = int(round(g[0]["startMs"] / 1000 * self.fps))
            nxt = grupos[gi + 1] if gi + 1 < len(grupos) else None
            end_f = (int(round(nxt[0]["startMs"] / 1000 * self.fps)) if nxt
                     else min(self.frames,
                              int(round(g[-1]["endMs"] / 1000 * self.fps))
                              + int(self.fps)))
            if end_f <= ini_f:
                continue
            dur = end_f - ini_f

            hi_idx, hi_len = -1, 6
            for i, w in enumerate(g):
                if len(limpar(w["text"])) > hi_len:
                    hi_len, hi_idx = len(limpar(w["text"])), i

            # linhas de 3-4 palavras; destaque em linha propria
            linhas, linha = [], []
            for i, w in enumerate(g):
                if i == hi_idx:
                    if linha:
                        linhas.append(linha)
                    linhas.append([i])
                    linha = []
                    continue
                linha.append(i)
                want = 4 if self._hash_det(gi * 31 + i) > 0.5 else 3
                if len(linha) >= want:
                    linhas.append(linha)
                    linha = []
            if linha:
                linhas.append(linha)

            leg = Camada(ini_f, end_f - 1)
            leg.dur_f = dur
            leg.saida_f = dur - EXIT
            leg.exit_fade = True

            drop = (self._hash_det(gi * 53 + 11) * 2 - 1) * 40
            alt_total = 0.0
            alturas = []
            for idxs in linhas:
                t_max = round(BASE * HI_SCALE) if hi_idx in idxs else BASE
                alturas.append(t_max * 1.03)
                alt_total += t_max * 1.03
            y = self.h * OFFSET_Y - alt_total / 2 + drop

            for li, idxs in enumerate(linhas):
                # largura da linha (peso 400, tamanho de cada palavra)
                largs = []
                for i in idxs:
                    tam_i = round(BASE * HI_SCALE) if i == hi_idx else BASE
                    fw = self.fonte(5, tam_i, 400)
                    largs.append(fw.getlength(limpar(g[i]["text"])))
                larg_linha = sum(largs) + GAP * (len(idxs) - 1)
                room = max(0.0, (SAFE_W - larg_linha) / 2) * SPREAD
                shift = (self._hash_det(gi * 17 + li * 5 + 3) * 2 - 1) * room
                x = (self.w - larg_linha) / 2 + shift

                for k, i in enumerate(idxs):
                    w = g[i]
                    eh_hi = i == hi_idx
                    tam_i = round(BASE * HI_SCALE) if eh_hi else BASE
                    peso = 600 if eh_hi else 400
                    # `hash(li*7 + wi)` no template usa o indice NA LINHA
                    # (`k`), nao no grupo — com o indice do grupo, a palavra
                    # que sai italica era OUTRA em cada motor.
                    italico = eh_hi and self._hash_det(li * 7 + k) > 0.65
                    f = self.fonte(6 if italico else 5, tam_i, peso)
                    m, cor_e = self._mascara_cor(f, limpar(w["text"]), 0.0)
                    h_m, w_m = m.shape
                    folga = 40
                    pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga),
                                     dtype=np.float32)
                    pad_m[folga:folga + h_m, folga:folga + w_m] = m
                    sombra = self._sombra_de(pad_m, [(0, 4, 14, 0.5)])
                    if eh_hi and HI_COLOR:
                        rgb = np.broadcast_to(self._cor(HI_COLOR),
                                              (*pad_m.shape, 3)).copy()
                    else:
                        col = cor_grad(h_m)
                        idx_l = np.clip(np.arange(pad_m.shape[0]) - folga,
                                        0, h_m - 1)
                        rgb = np.repeat(col[idx_l][:, None, :],
                                        pad_m.shape[1], axis=1)
                    self._pintar_emoji(rgb, cor_e, folga)
                    asc, desc = f.getmetrics()
                    x0 = int(round(x)) - folga
                    y0 = int(round(y + (alturas[li] - (asc + desc)) / 2)) - folga
                    local = w["startMs"] / 1000 * self.fps - ini_f

                    if not eh_hi:
                        leg.palavras.append(Palavra(
                            x0, y0, rgb, pad_m, sombra,
                            inicio_f=local, enter=ENTER, sobe=0.0))
                    else:
                        # destaque: estagios com desfoque na ENTRADA e na SAIDA
                        def estagio(blur_px, opac, jan):
                            if blur_px > 0.4:
                                a2 = np.asarray(
                                    Image.fromarray((pad_m * 255).astype(np.uint8))
                                    .filter(ImageFilter.GaussianBlur(blur_px / 2)),
                                    dtype=np.float32) / 255.0
                            else:
                                a2 = pad_m
                            leg.palavras.append(Palavra(
                                x0, y0, rgb, a2 * opac,
                                sombra * opac, inicio_f=0, enter=1,
                                janela=jan, sobe=0.0))
                        for q in range(HI_ENTER):
                            t = 1 - (1 - min(1.0, q / HI_ENTER)) ** 3
                            estagio((1 - t) * 26, t,
                                    (local + q, local + q + 1))
                        estagio(0.0, 1.0, (local + HI_ENTER, leg.saida_f))
                        for q in range(EXIT):
                            out = (q + 1) / EXIT
                            estagio(out * 30, 1.0,
                                    (leg.saida_f + q, leg.saida_f + q + 1))
                    x += largs[k] + GAP
                y += alturas[li]
            camadas.append(leg)
        return camadas

    # ----- legendas `simple` (5 variantes estaticas) ------------------------
    SIMPLE_VARIANTES = {
        #        fonte        peso  tam  maxP lin  sqX   sqY   track bottom maxW  modo
        "simples":  ("Poppins-SemiBold.ttf", None, 82, 3, 1, 0.9, 0.9, -3, 430, 860, ""),
        "serifada": ("LibreBaskerville[wght].ttf", 700, 84, 3, 1, 1.0, 1.0, -1, 430, 860, ""),
        "classica": ("Inter[opsz,wght].ttf", "Medium", 52, 14, 2, 1.0, 1.0, 0, 430, 840, ""),
        "bloco":    ("Poppins-ExtraBold.ttf", None, 76, 3, 1, 1.0, 1.0, -2, 430, 760, "bloco"),
        "recorte_simple": ("Poppins-ExtraBold.ttf", None, 78, 3, 1, 1.0, 1.0, -1, 430, 800, "sticker"),
        # --- os cinco de 30/08 -------------------------------------------
        "metal":    ("Poppins-ExtraBold.ttf", None, 76, 3, 1, 1.0, 1.0, -1, 430, 800, "metal"),
        "vidro":    ("Poppins-SemiBold.ttf", None, 72, 3, 1, 1.0, 1.0, -1, 430, 840, "vidro"),
        "traco":    ("Poppins-ExtraBold.ttf", None, 74, 3, 1, 1.0, 1.0, -1, 430, 820, "traco"),
        "moldura":  ("Inter[opsz,wght].ttf", "SemiBold", 44, 6, 1, 1.0, 1.0, 6, 430, 700, "moldura"),
        "eco":      ("Poppins-ExtraBold.ttf", None, 78, 3, 1, 1.0, 1.0, -2, 430, 800, "eco"),
    }
    # Modos que desenham em CAIXA ALTA. Isso muda a MEDIDA das linhas, entao
    # os tres motores tem de concordar sobre quem esta nesta lista.
    SIMPLE_MAIUSCULA = ("sticker", "metal", "moldura", "eco")
    # Modos com um painel em volta do cue INTEIRO (e nao por linha, como o
    # bloco): a caixa e uma so para as duas linhas. O `vidro` saiu daqui —
    # ele virou uma LETRA de vidro, nao uma caixa atras da letra.
    SIMPLE_PAINEL = ("moldura",)
    # Peso que cada variante estatica tem no template (`capWeight(base.weight)`
    # em SimpleCaptions.tsx:218). Aqui ele fica implicito no ARQUIVO —
    # `Poppins-SemiBold.ttf` E o 600 — entao, quando a fonte da marca
    # substitui o arquivo, o peso se perdia junto. Escrito, ele sobrevive.
    SIMPLE_PESO = {"simples": 600, "serifada": 700, "classica": 500,
                   "bloco": 800, "recorte_simple": 800,
                   "metal": 800, "vidro": 600, "traco": 800,
                   "moldura": 600, "eco": 800}

    # Opacidades do Vidro e do Metalico. Ficam aqui, com nome, porque os
    # tres motores tem de usar o MESMO numero — um 0,32 que vira 0,30 no
    # template sai como outra legenda e ninguem percebe.
    VIDRO_OPACO = 0.32     # o preenchimento da letra
    VIDRO_FIO = 0.92       # o fio de luz da borda
    METAL_OPACO = 0.88     # a prata deixa o take pulsar por baixo

    _ORFAO = ("o", "a", "os", "as", "e", "\u00e9", "de", "do", "da", "em", "no",
              "na", "um", "uma", "que", "se", "ao", "\u00e0", "por", "com")

    def _fonte_estilo(self, nome: str, tam: int, eixo,
                      peso: int | None = None) -> ImageFont.FreeTypeFont:
        """Fonte de um estilo que ACEITA a marca (`capFamily` no template).

        `eixo` e como a fonte DO ESTILO pede o peso (um numero, ou o nome de
        uma instancia como "Medium", ou None quando o arquivo ja e o peso).
        Nada disso vale na fonte da marca — nela o que se pede e `peso`, o
        numero que o template usa, clampado no teto da familia. E exatamente
        o que `capWeight(base.weight)` faz: clampar em vez de pedir um
        negrito que a fonte nao tem.
        """
        if not self.marca_cap:
            return self._fonte_arquivo(nome, tam, eixo)
        arq, teto = self.marca_cap
        alvo = peso if peso is not None else (eixo if isinstance(eixo, int) else None)
        if alvo is not None and teto is not None:
            alvo = min(alvo, teto)
        return self._fonte_arquivo(arq, tam, alvo if alvo is not None else teto)

    def _fonte_arquivo(self, nome: str, tam: int, eixo) -> ImageFont.FreeTypeFont:
        chave = (nome, tam, str(eixo))
        if chave not in self._fontes:
            cam = nome if "\\" in nome or "/" in nome else str(FONTES / nome)
            f = ImageFont.truetype(cam, tam)
            if isinstance(eixo, int):
                try:
                    f.set_variation_by_axes([eixo])
                except (OSError, AttributeError):
                    pass
            elif isinstance(eixo, str):
                try:
                    f.set_variation_by_name(eixo)
                except (OSError, AttributeError):
                    pass
            self._fontes[chave] = f
        return self._fontes[chave]

    # ------------------------------------------------------------ karaoke --
    #
    # Portado de `Main.tsx` (Karaoke 382-427, Word 335-360, CaptionShell
    # 362-380, buildLines 319-333). NAO existe "palavra acesa": a linha
    # inteira tem uma cor so, e o que anima e a ENTRADA de cada palavra --
    # opacidade 0->1 e subida de 34px, em 7 quadros, com Easing.out(cubic).
    KAR_ENTER = 7           # Word: interpolate(frame, [start, start+7], [0,1])
    KAR_SOBE = 34.0         # Word: translate 34px -> 0
    KAR_MARGIN = 18.0       # Word: marginRight
    KAR_LS = -1.0           # div: letterSpacing -1
    KAR_SOMBRA = [(0, 4, 20, 0.55)]   # div: textShadow 0 4px 20px rgba(0,0,0,.55)

    # Espelho do BubbleCaptions (Main.tsx): agrupamento por CONTAGEM
    # (12 palavras / pontuacao final / respiro >450ms) — mesmo spec, sem
    # medir largura, para os dois motores quebrarem as bolhas IGUAL.
    BOLHA_MAX_PALAVRAS = 12
    BOLHA_RESPIRO_MS = 450
    BOLHA_BG = "#005C4B"
    BOLHA_CHECK = "#53BDEB"

    def _montar_bolha(self):
        """Uma Camada por bolha; a bolha inteira e UMA Palavra (sobe+fade)."""
        import re

        C = self.ed.get("captions") or {}
        tam = max(8, int(round(int(C.get("fontSize") or 76) * 0.62)))
        safe_w = float(C.get("safeWidth") or 720)
        pad_b = float(C.get("paddingBottom") or 420)
        # Poppins REGULAR, nao Black. O indice 4 e o `Poppins-Black.ttf`, um
        # arquivo de peso unico: pedir 500 nele nao muda nada, entao a bolha
        # saia em 900. O template pede `fontWeight: 500` numa familia com
        # 400/600/900 carregados, e a regra de casamento do CSS para 500
        # escolhe o MENOR peso <= 500 — ou seja, 400. Medido: a bolha do
        # motor proprio tinha 0,744 da tinta da do template; todos os outros
        # estilos ficam entre 0,93 e 1,09.
        f = self.fonte(1, tam, 400, marca="cap")
        f_meta = self.fonte(1, max(8, int(round(tam * 0.52))), 400, marca="cap")
        asc, desc = f.getmetrics()
        alt_linha = int(round(tam * 1.3))

        def quebra(t):
            return bool(re.search(r"[.,!?\u2026]$", str(t or "")))

        raw = json.loads((self.public / "captions.json")
                         .read_text(encoding="utf-8-sig"))
        words = raw if isinstance(raw, list) else (raw.get("words") or [])

        bolhas, cur = [], []
        for i, w in enumerate(words):
            cur.append(w)
            prox = words[i + 1] if i + 1 < len(words) else None
            respiro = (float(prox.get("startMs") or 0)
                       - float(w.get("endMs") or 0)) if prox else 0.0
            if (len(cur) >= self.BOLHA_MAX_PALAVRAS or quebra(w.get("text"))
                    or respiro > self.BOLHA_RESPIRO_MS):
                bolhas.append(cur)
                cur = []
        if cur:
            bolhas.append(cur)

        pad_x = int(round(tam * 0.55))
        pad_top = int(round(tam * 0.42))
        pad_bot = int(round(tam * 0.3))
        cor_bg = self._cor(self.BOLHA_BG)
        cor_chk = self._cor(self.BOLHA_CHECK)
        saida = []
        for bi, grupo in enumerate(bolhas):
            ini_ms = float(grupo[0].get("startMs") or 0)
            fim_ms = (float(bolhas[bi + 1][0].get("startMs") or 0)
                      if bi + 1 < len(bolhas)
                      else self.frames / self.fps * 1000.0)
            ini_f = round(ini_ms / 1000 * self.fps)
            fim_f = max(ini_f + 1, round(fim_ms / 1000 * self.fps))

            texto = " ".join(str(w.get("text") or "") for w in grupo)
            # quebra visual gulosa. `maxWidth: safeWidth` no template e
            # CONTENT-box (o padding fica por fora): o texto quebra em
            # safe_w cheio, e a bolha total sai safe_w + 2*pad. Descontar o
            # padding aqui deixava as bolhas ~1,1 fonte mais estreitas e as
            # quebras cairiam em palavras diferentes das do Remotion.
            linhas, atual = [], ""
            interno = safe_w
            for palavra in texto.split():
                tent = (atual + " " + palavra).strip()
                if atual and f.getlength(tent) > interno:
                    linhas.append(atual)
                    atual = palavra
                else:
                    atual = tent
            if atual:
                linhas.append(atual)

            secs = int(ini_ms // 1000)
            hora = f"{secs // 60:02d}:{secs % 60:02d}"
            meta = hora + "  "
            larg_meta = f_meta.getlength(meta) + tam * 0.9  # + checks
            larg_txt = max((f.getlength(ln) for ln in linhas), default=0)
            larg = int(min(safe_w, max(larg_txt + larg_meta * 0.0,
                                       larg_txt) + 2 * pad_x))
            # a meta divide a ultima linha; se nao couber, ganha linha propria
            ultima_com_meta = (f.getlength(linhas[-1]) + tam * 0.4
                               + larg_meta <= larg - 2 * pad_x) if linhas else False
            alt = (pad_top + len(linhas) * alt_linha
                   + (0 if ultima_com_meta else int(alt_linha * 0.72))
                   + pad_bot)

            img = Image.new("L", (larg, alt), 0)
            dr = ImageDraw.Draw(img)
            dr.rounded_rectangle([0, 0, larg - 1, alt - 1], radius=20,
                                 fill=255,
                                 corners=(True, True, False, True))
            dr.rounded_rectangle([larg - 13, alt - 13, larg - 1, alt - 1],
                                 radius=6, fill=255)
            base_a = np.asarray(img, dtype=np.float32) / 255.0

            cam_img = Image.new("L", (larg, alt), 0)
            cor_img = np.broadcast_to(cor_bg, (alt, larg, 3)).copy()
            dtx = ImageDraw.Draw(cam_img)
            y = pad_top
            for ln in linhas:
                dtx.text((pad_x, y), ln, font=f, fill=255)
                y += alt_linha
            # hora + checks (vetoriais — o glifo U+2713 nem sempre existe)
            my = alt - pad_bot - int(alt_linha * 0.55)
            mx = larg - pad_x - int(larg_meta)
            dtx.text((mx, my), hora, font=f_meta, fill=180)
            cx = mx + f_meta.getlength(hora) + tam * 0.18
            r = tam * 0.16
            for desloc in (0.0, r * 1.1):
                dtx.line([(cx + desloc, my + r * 1.1),
                          (cx + desloc + r * 0.55, my + r * 1.7),
                          (cx + desloc + r * 1.5, my + r * 0.4)],
                         fill=255, width=max(2, int(tam * 0.05)))
            texto_a = np.asarray(cam_img, dtype=np.float32) / 255.0

            # composicao: fundo verde + texto branco/azul POR CIMA, tudo numa
            # unica Palavra (rgb blend do texto sobre o fundo)
            rgb = cor_img.astype(np.float32)
            branco = np.array([255.0, 255.0, 255.0])
            t3 = texto_a[..., None]
            rgb = rgb * (1 - t3) + branco * t3
            # tinge os checks de azul: mascara na regiao dos checks
            chk_x0 = int(cx - 2)
            rgb[my - 2:, chk_x0:, :] = (
                rgb[my - 2:, chk_x0:, :] * (1 - t3[my - 2:, chk_x0:, :])
                + np.array(cor_chk, dtype=np.float32)
                * t3[my - 2:, chk_x0:, :]
                + rgb[my - 2:, chk_x0:, :] * 0)
            alpha = np.maximum(base_a, texto_a)

            # FOLGA em volta, antes da sombra. Sem ela o borrao era calculado
            # num quadro do tamanho exato do balao e ficava preso DENTRO dele,
            # onde o proprio balao o cobre: media 126 pixels de halo contra
            # 23.279 do template — ou seja, a bolha saia sem sombra nenhuma.
            # Todos os outros estilos ja faziam isto; este era o unico sem.
            #
            # `box-shadow` tambem pede sigma = raio/2 (k=0,5), nao o raio
            # inteiro do drop-shadow. E ele parte do BALAO, nao do balao mais
            # o texto: a sombra segue a caixa, e o texto esta dentro dela.
            folga_b = 70
            def _com_folga(a2d):
                out = np.zeros((alt + 2 * folga_b, larg + 2 * folga_b),
                               dtype=np.float32)
                out[folga_b:folga_b + alt, folga_b:folga_b + larg] = a2d
                return out

            base_pad = _com_folga(base_a)
            alpha = _com_folga(alpha)
            rgb_pad = np.zeros((*alpha.shape, 3), dtype=np.float32)
            rgb_pad[folga_b:folga_b + alt, folga_b:folga_b + larg] = rgb
            rgb = rgb_pad
            sombra = self._sombra_de(base_pad, [(0, 8, 26, 0.45)], k=0.5)

            x0 = int(round((self.w - larg) / 2)) - folga_b
            y0 = int(round(self.h - pad_b - alt)) - folga_b
            leg = Camada(inicio_f=ini_f, fim_f=fim_f, saida_f=fim_f - ini_f,
                         palavras=[])
            leg.palavras.append(Palavra(
                x0, y0, rgb, alpha, sombra,
                inicio_f=0, enter=7, sobe=24.0, ease="cubic"))
            saida.append(leg)
            if self.sfx_on:
                self.eventos_sfx.append(("pop.mp3", ini_ms / 1000.0, 0.12))
        return saida

    def _montar_karaoke(self):
        """Uma Camada por LINHA, uma Palavra por palavra."""
        import re

        C = self.ed.get("captions") or {}
        tam = int(C.get("fontSize") or 76)
        max_p = max(1, int(C.get("maxWords") or 3))
        safe_w = float(C.get("safeWidth") or 720)
        pad_b = float(C.get("paddingBottom") or 420)
        cor = C.get("accent") or "#ffffff"          # `C.accent ?? 'white'`
        ls = self.KAR_LS

        # `capWeight(900)` sobre `capFamily(Poppins)`: Poppins-Black e o 900
        # upright do catalogo. A fonte da marca entra por `marca="cap"`, com o
        # teto de peso que o proprio resolvedor aplica (sem negrito falso).
        f = self.fonte(4, tam, 900, marca="cap")
        asc, desc = f.getmetrics()

        def limpar(t):                                   # cleanW
            return re.sub(r"[.,!?\u2026]+$", "", str(t or ""))

        def quebra(t):                                   # isBreak
            return bool(re.search(r"[.,!?\u2026]$", str(t or "")))

        raw = json.loads((self.public / "captions.json")
                         .read_text(encoding="utf-8-sig"))
        words = raw if isinstance(raw, list) else (raw.get("words") or [])

        # buildLines: fecha em maxWords OU em pontuacao final
        linhas, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= max_p or quebra(w.get("text")):
                linhas.append(cur)
                cur = []
        if cur:
            linhas.append(cur)

        def larg(t):
            """Avanco + espacamento por letra, como o motor mede em todo lugar.

            O `letter-spacing` do CSS soma DEPOIS de cada caractere, inclusive
            o ultimo -- por isso `len(t)`, nao `len(t) - 1`.
            """
            return f.getlength(t) + ls * len(t)

        camadas = []
        for i, linha in enumerate(linhas):
            ini_f = self._arredonda_js(linha[0]["startMs"] / 1000 * self.fps)
            prox = (self._arredonda_js(linhas[i + 1][0]["startMs"] / 1000 * self.fps)
                    if i + 1 < len(linhas) else self.frames)
            dur = max(1, prox - ini_f)
            fim_f = ini_f + dur - 1
            if fim_f < 0 or ini_f >= self.frames:
                continue

            pares = [(w, limpar(w.get("text"))) for w in linha]
            pares = [(w, t) for w, t in pares if t]
            if not pares:
                continue
            textos = [t for _w, t in pares]

            # DUAS larguras diferentes, de proposito:
            #   fit    mede o texto juntado com ESPACO (`measureText` recebe
            #          `line.map(cleanW).join(' ')`)
            #   layout usa `marginRight: 18` e nenhum espaco
            # Trocar uma pela outra desloca a linha inteira.
            fit = min(1.0, safe_w / max(1e-6, larg(" ".join(textos))))
            largs = [larg(t) for t in textos]
            # A margem sobra na ULTIMA palavra e entra na largura da caixa --
            # e por isso a linha centralizada fica meia margem a esquerda do
            # centro real. Reproduzido, nao corrigido.
            total = sum(largs) + self.KAR_MARGIN * len(largs)

            leg = Camada(max(0, ini_f), min(self.frames - 1, fim_f))
            leg.dur_f = leg.fim_f - leg.inicio_f + 1
            leg.saida_f = 1e9        # some de uma vez quando a proxima entra

            # `scale` do CSS reduz em torno do CENTRO da caixa.
            cx, cy = self.w / 2.0, self.h - pad_b - tam / 2.0
            # lineHeight 1 => a caixa tem `tam` de altura e `flex-end` poe a
            # base dela em H - paddingBottom. Dentro dela, o Chrome centra
            # ascendente+descendente (meia-entrelinha), e a mascara do motor
            # comeca justamente na linha do ascendente.
            y_asc = (self.h - pad_b - tam) + (tam - (asc + desc)) / 2.0
            topo = cy + (y_asc - cy) * fit
            esq = cx - total * fit / 2.0

            self._karaoke_linha(leg, f, pares, largs, ls, cor,
                                esq=esq, topo=topo, fit=fit, ini_f=ini_f)
            if leg.palavras:
                camadas.append(leg)
        return camadas

    # A sombra e da LINHA, nao de cada palavra.
    #
    # Desenhando uma sombra por palavra, onde as sombras de duas palavras
    # vizinhas se cruzam o alfa ACUMULA: 0,55 + 0,55*(1-0,55) = 0,80. O Chrome
    # pinta as palavras ja entradas na MESMA camada, entao a sombra da linha e
    # uma so, com teto de 0,55. Medido contra o Remotion: a sombra por palavra
    # saia com 12% de massa a mais, concentrada justamente nos vaos.
    #
    # Aqui a linha inteira e desenhada num canvas, borrada UMA vez, e cada
    # palavra leva a fatia da sombra que cai na sua faixa -- as faixas se
    # dividem no meio dos vaos, entao a soma delas reconstroi a sombra da linha
    # sem contar nada duas vezes.
    def _karaoke_linha(self, leg, f, pares, largs, ls, cor, *,
                       esq, topo, fit, ini_f) -> None:
        folga = 40
        larg_total = int(round(sum(largs) + self.KAR_MARGIN * (len(largs) - 1)))
        mascaras, cor_emojis, cursores = [], [], []
        cur = 0.0
        for (_w, t), wl in zip(pares, largs):
            m, ce = self._mascara_cor(f, t, ls)
            mascaras.append(m)
            cor_emojis.append(ce)
            cursores.append(cur)
            cur += wl + self.KAR_MARGIN
        alt = max(m.shape[0] for m in mascaras)
        canvas = np.zeros((alt + 2 * folga, larg_total + 2 * folga),
                          dtype=np.float32)
        for m, c in zip(mascaras, cursores):
            x0 = folga + int(round(c))
            h_m, w_m = m.shape
            fim_x = min(canvas.shape[1], x0 + w_m)
            if fim_x > x0:
                np.maximum(canvas[folga:folga + h_m, x0:fim_x],
                           m[:, :fim_x - x0],
                           out=canvas[folga:folga + h_m, x0:fim_x])
        # `caixa=True`: o Chrome borra text-shadow com tres passadas de caixa,
        # nao com Gaussiana. So o karaoke pede isso; os outros estilos deste
        # motor ja foram validados com a Gaussiana e nao se mexe neles.
        sombra_linha = self._sombra_de(canvas, self.KAR_SOMBRA, k=0.5, caixa=True)

        # as faixas se dividem no MEIO de cada vao
        bordas = [0]
        for k in range(len(pares) - 1):
            dir_k = cursores[k] + largs[k]
            bordas.append(int(round(folga + dir_k + self.KAR_MARGIN / 2.0)))
        bordas.append(canvas.shape[1])
        bordas[0] = 0

        for k, ((w, _t), m) in enumerate(zip(pares, mascaras)):
            bx0, bx1 = bordas[k], bordas[k + 1]
            if bx1 <= bx0:
                continue
            alpha = np.zeros((canvas.shape[0], bx1 - bx0), dtype=np.float32)
            x0 = folga + int(round(cursores[k]))
            h_m, w_m = m.shape
            a0, a1 = max(bx0, x0), min(bx1, x0 + w_m)
            if a1 > a0:
                alpha[folga:folga + h_m, a0 - bx0:a1 - bx0] = m[:, a0 - x0:a1 - x0]
            sombra = sombra_linha[:, bx0:bx1].copy()
            rgb = np.broadcast_to(self._cor(cor), (*alpha.shape, 3)).copy()
            # a mascara desta palavra comeca em `x0 - bx0` dentro da fatia,
            # nao na folga -- o emoji tem de seguir a mesma origem
            self._pintar_emoji(rgb, cor_emojis[k], x0 - bx0, folga)

            if fit < 0.999:
                novo = (max(1, int(round(alpha.shape[1] * fit))),
                        max(1, int(round(alpha.shape[0] * fit))))

                def _red(a):
                    return np.asarray(
                        Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
                        .resize(novo, Image.LANCZOS), dtype=np.float32) / 255.0

                alpha, sombra = _red(alpha), _red(sombra)
                rgb = np.asarray(Image.fromarray(rgb.astype(np.uint8))
                                 .resize(novo, Image.LANCZOS), dtype=np.float32)

            leg.palavras.append(Palavra(
                int(round(esq + (bx0 - folga) * fit)),
                int(round(topo - folga * fit)),
                rgb, alpha, sombra,
                # `startLocal` do template, SEM arredondar: a interpolacao do
                # Remotion aceita limite fracionario.
                inicio_f=(w["startMs"] / 1000 * self.fps) - ini_f,
                enter=self.KAR_ENTER, sobe=self.KAR_SOBE * fit, ease="cubic"))

    def _montar_simple(self, variante: str):
        """Cinco variantes ESTATICAS: o texto do cue aparece pronto e some no
        cue seguinte — sem animacao por palavra. Agrupamento por largura
        medida > contagem > respiro, e a quebra em 2 linhas evita terminar
        linha em palavra funcional (penalidade de ~200px, como o template)."""
        import re

        (arq, eixo, tam0, max_p, n_lin, sq_x, sq_y,
         track, bottom0, max_w, modo) = self.SIMPLE_VARIANTES[variante]
        caps_cfg = self.ed.get("captions") or {}
        tam = round(tam0 * float(caps_cfg.get("sizeScale") or 1.0))
        pos = {"centro": 900, "alto": 1330}.get(caps_cfg.get("position") or "")
        bottom = pos if pos else bottom0
        accent = caps_cfg.get("accent")
        f = self._fonte_estilo(arq, tam, eixo, self.SIMPLE_PESO.get(variante))

        def limpar(t):
            t = re.sub(r"[.,!?\u2026]+$", "", t)
            return t.upper() if modo in self.SIMPLE_MAIUSCULA else t

        def largura(ws):
            txt = " ".join(limpar(w["text"]) for w in ws)
            return (f.getlength(txt) + track * max(0, len(txt) - 1)) * sq_x

        raw = json.loads((self.public / "captions.json")
                         .read_text(encoding="utf-8-sig"))
        words = raw if isinstance(raw, list) else (raw.get("words") or [])

        cues, cur = [], []
        orc = max_w * n_lin
        for i, w in enumerate(words):
            trial = cur + [w]
            if cur and (len(trial) > max_p or largura(trial) > orc):
                cues.append(cur)
                cur = [w]
            else:
                cur = trial
            nxt = words[i + 1] if i + 1 < len(words) else None
            gap = (nxt["startMs"] - w["endMs"]) if nxt else 0
            if cur and (re.search(r"[.,!?\u2026]$", w["text"]) or gap > 450):
                cues.append(cur)
                cur = []
        if cur:
            cues.append(cur)

        def duas(ws):
            if n_lin == 1 or len(ws) < 2:
                return [ws]
            melhor, m_score = 0, float("inf")
            for i in range(1, len(ws)):
                dif = abs(largura(ws[:i]) - largura(ws[i:]))
                cauda = limpar(ws[i - 1]["text"]).lower()
                score = dif + (200 if cauda in self._ORFAO else 0)
                if score < m_score:
                    m_score, melhor = score, i
            return [ws[:melhor], ws[melhor:]]

        camadas = []
        lh = {"bloco": 1.06, "sticker": 1.16, "metal": 1.10, "vidro": 1.16,
              "traco": 1.16, "moldura": 1.20, "eco": 1.14}.get(modo, 1.18)
        for ci, cue in enumerate(cues):
            ini_f = int(round(cue[0]["startMs"] / 1000 * self.fps))
            nxt = cues[ci + 1] if ci + 1 < len(cues) else None
            fim_f = (int(round(nxt[0]["startMs"] / 1000 * self.fps)) - 1 if nxt
                     else min(self.frames,
                              int(round(cue[-1]["endMs"] / 1000 * self.fps))
                              + int(self.fps)))
            if fim_f < ini_f:
                continue
            leg = Camada(ini_f, fim_f)
            leg.dur_f = fim_f - ini_f + 1
            leg.saida_f = 1e9
            linhas = duas(cue)
            asc, desc = f.getmetrics()
            alt_l = tam * lh
            if modo in self.SIMPLE_PAINEL:
                leg.palavras.append(
                    self._painel_legenda(modo, linhas, f, track, tam, alt_l,
                                         bottom, accent, limpar))
                camadas.append(leg)
                continue
            gap_l = round(tam * 0.14) if modo == "bloco" else 0
            alt_total = alt_l * len(linhas) * sq_y + gap_l * (len(linhas) - 1)
            y = self.h - bottom - alt_total

            for ln in linhas:
                texto = " ".join(limpar(w["text"]) for w in ln)
                if sq_x != 1.0 or sq_y != 1.0:
                    # scale(0.9, 0.9) do CSS espreme a CAIXA e, com ela, a
                    # espessura do traco. Rasterizar no tamanho final e
                    # so redimensionar deixava o texto 44% mais gordo que o
                    # do Remotion (medido). Rasteriza-se maior e reduz.
                    f_big = self._fonte_estilo(arq, max(8, int(tam / sq_y)), eixo,
                                            self.SIMPLE_PESO.get(variante))
                    m, cor_emj = self._mascara_cor(f_big, texto,
                                                   float(track) / sq_x)
                    novo_t = (max(1, int(m.shape[1] * sq_x * sq_y)),
                              max(1, int(m.shape[0] * sq_y * sq_y)))
                    m = np.asarray(
                        Image.fromarray((m * 255).astype(np.uint8))
                        .resize(novo_t, Image.LANCZOS),
                        dtype=np.float32) / 255.0
                    if cor_emj is not None:    # o emoji aperta junto
                        cor_emj = np.asarray(
                            Image.fromarray(cor_emj.astype(np.uint8), "RGBA")
                            .resize(novo_t, Image.LANCZOS), dtype=np.float32)
                else:
                    m, cor_emj = self._mascara_cor(f, texto, float(track))
                h_m, w_m = m.shape
                folga = 48
                x0 = int((self.w - w_m) / 2)

                if modo == "bloco":
                    pad = round(tam * 0.16)
                    slab = accent or "#111214"
                    tinta = self._tinta_na_caixa(slab)
                    cw = w_m + 2 * pad
                    ch = int(alt_l + pad * 0.55 + pad * 0.75)
                    L, A = cw + 2 * folga, ch + 2 * folga
                    img = Image.new("L", (L, A), 0)
                    ImageDraw.Draw(img).rounded_rectangle(
                        [folga, folga, folga + cw, folga + ch],
                        radius=round(tam * 0.16), fill=255)
                    a_c = np.asarray(img, dtype=np.float32) / 255.0
                    t_a = np.zeros_like(a_c)
                    tx = folga + pad
                    ty = folga + int(pad * 0.55 + (alt_l - (asc + desc)) / 2)
                    hh = min(h_m, A - ty)
                    ww = min(w_m, L - tx)
                    t_a[ty:ty + hh, tx:tx + ww] = m[:hh, :ww]
                    rgb = np.broadcast_to(self._cor(slab), (*a_c.shape, 3)).copy()
                    rgb = rgb * (1 - t_a[..., None]) \
                        + self._cor(tinta) * t_a[..., None]
                    self._pintar_emoji(rgb, cor_emj, tx, ty)
                    alpha = np.maximum(a_c, t_a)
                    b = np.asarray(Image.fromarray((a_c * 255).astype(np.uint8))
                                   .filter(ImageFilter.GaussianBlur(30 * 0.5)),
                                   dtype=np.float32) / 255.0
                    sombra = np.zeros_like(b)
                    sombra[12:, :] = b[:-12, :] * 0.45
                    leg.palavras.append(Palavra(
                        int((self.w - cw) / 2) - folga, int(y) - folga,
                        rgb, alpha, sombra, inicio_f=-1, enter=1, sobe=0.0))
                    y += ch + gap_l
                    continue

                pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga),
                                 dtype=np.float32)
                pad_m[folga:folga + h_m, folga:folga + w_m] = m
                if modo in ("metal", "traco", "eco", "vidro"):
                    rgb, alpha, sombra = self._tinta_dos_novos(
                        modo, pad_m, folga, h_m, tam, accent, cor_emj)
                    leg.palavras.append(Palavra(
                        x0 - folga,
                        int(y + (alt_l - (asc + desc)) / 2) - folga,
                        rgb, alpha, sombra, inicio_f=-1, enter=1, sobe=0.0))
                    y += alt_l * sq_y + gap_l
                    continue
                if modo == "sticker":
                    R = max(5, round(tam * 0.09))
                    D = int(round(0.7071 * R))
                    contorno = np.zeros_like(pad_m)
                    for dx, dy in ((R, 0), (-R, 0), (0, R), (0, -R),
                                   (D, D), (-D, D), (D, -D), (-D, -D)):
                        desl = np.zeros_like(pad_m)
                        ys = slice(max(0, dy), pad_m.shape[0] + min(0, dy))
                        xs = slice(max(0, dx), pad_m.shape[1] + min(0, dx))
                        ys2 = slice(max(0, -dy), pad_m.shape[0] + min(0, -dy))
                        xs2 = slice(max(0, -dx), pad_m.shape[1] + min(0, -dx))
                        desl[ys, xs] = pad_m[ys2, xs2]
                        contorno = np.maximum(contorno, desl)
                    cor_t = self._cor(accent or "#ffffff")
                    cor_e = self._cor("#141518")
                    alpha = np.maximum(contorno, pad_m)
                    rgb = np.broadcast_to(cor_e, (*pad_m.shape, 3)).copy()
                    rgb = rgb * (1 - pad_m[..., None]) + cor_t * pad_m[..., None]
                    self._pintar_emoji(rgb, cor_emj, folga)
                    # A sombra do CSS parte do GLIFO, nao do contorno: usar
                    # `alpha` (glifo+contorno, ~25% maior) inflava o halo em
                    # 60% (medido: 35.816 contra 22.335 pixels).
                    sombra = self._sombra_de(pad_m, [(0, 14, 30, 0.5)], k=0.5)
                    leg.palavras.append(Palavra(
                        x0 - folga,
                        int(y + (alt_l - (asc + desc)) / 2) - folga,
                        rgb, alpha, sombra, inicio_f=-1, enter=1, sobe=0.0))
                else:
                    sombra = self._sombra_de(pad_m, [(0, 4, 18, 0.55)], k=0.5)
                    cor = self._cor(accent or "#f4f1e9")
                    rgb = np.broadcast_to(cor, (*pad_m.shape, 3)).copy()
                    self._pintar_emoji(rgb, cor_emj, folga)
                    leg.palavras.append(Palavra(
                        x0 - folga,
                        int(y + (alt_l * sq_y - (asc + desc) * sq_y) / 2) - folga,
                        rgb, pad_m, sombra, inicio_f=-1, enter=1, sobe=0.0))
                y += alt_l * sq_y + gap_l
            camadas.append(leg)
        return camadas

    # ---- os cinco estilos de 30/08 ---------------------------------------
    @staticmethod
    def _contorno(mask, r: int):
        """Uniao da mascara deslocada em 8 direcoes — o mesmo contorno que o
        CSS faz com `text-shadow` repetido (nao com `-webkit-text-stroke`,
        que come metade da espessura para dentro do glifo)."""
        import numpy as np
        d = int(round(0.7071 * r))
        out = np.zeros_like(mask)
        for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r),
                       (d, d), (-d, d), (d, -d), (-d, -d)):
            desl = np.zeros_like(mask)
            ys = slice(max(0, dy), mask.shape[0] + min(0, dy))
            xs = slice(max(0, dx), mask.shape[1] + min(0, dx))
            ys2 = slice(max(0, -dy), mask.shape[0] + min(0, -dy))
            xs2 = slice(max(0, -dx), mask.shape[1] + min(0, -dx))
            desl[ys, xs] = mask[ys2, xs2]
            out = np.maximum(out, desl)
        return out

    @staticmethod
    def _degrade_metal(cor, n: int):
        """As cinco paradas do cromado, tiradas DA COR escolhida.

        `f > 1` clareia em direcao ao branco, `f < 1` escurece. A parada
        escura em 0,50 com o estalo em 0,56 e o que o olho le como metal: um
        degrade suave de claro para escuro parece papel, nao cromo.
        """
        import numpy as np
        # PRATA LISO. A versao anterior tinha uma parada escura no meio com
        # um estalo de luz abaixo — o cromado de catalogo. O usuario leu
        # aquilo como um risco atravessando a letra, e ele tem razao: numa
        # legenda de 3 palavras a faixa escura corta o glifo no meio.
        paradas = ((0.00, 1.38), (0.42, 1.06), (1.00, 0.74))
        t = np.linspace(0.0, 1.0, max(1, n), dtype=np.float32)
        fs = np.interp(t, [q for q, _ in paradas], [v for _, v in paradas])
        fs = fs.astype(np.float32)[:, None]
        c = np.asarray(cor, dtype=np.float32)[None, :]
        claro = c + (255.0 - c) * np.clip(fs - 1.0, 0.0, 1.0)
        escuro = c * np.clip(fs, 0.0, 1.0)
        return np.where(fs > 1.0, claro, escuro).astype(np.float32)

    def _tinta_dos_novos(self, modo, pad_m, folga, h_m, tam, accent, cor_emj):
        """(rgb, alpha, sombra) de metal / traco / eco — os tres que pintam
        a LINHA, sem painel em volta."""
        import numpy as np

        if modo == "metal":
            base = self._cor(accent or "#e8edf3")
            faixa = self._degrade_metal(base, h_m)          # (h_m, 3)
            rgb = np.zeros((*pad_m.shape, 3), dtype=np.float32)
            rgb[folga:folga + h_m, :, :] = faixa[:, None, :]
            rgb[:folga] = faixa[0]
            rgb[folga + h_m:] = faixa[-1]
            r = max(2, round(tam * 0.035))
            borda = self._contorno(pad_m, r)
            cor_b = self._cor("#0e1013")
            # 88% na letra: a prata deixa o take pulsar por baixo, que e a
            # "certa transparencia" pedida. A BORDA fica opaca — e ela que
            # segura a leitura sobre imagem clara.
            alpha = np.maximum(borda, pad_m * self.METAL_OPACO)
            rgb = rgb * pad_m[..., None] + cor_b * (1.0 - pad_m[..., None])
            self._pintar_emoji(rgb, cor_emj, folga)
            return rgb, alpha, self._sombra_de(pad_m, [(0, 10, 24, 0.5)], k=0.5)

        if modo == "vidro":
            # A LETRA e de vidro: 32% de branco, entao o take aparece
            # ATRAVES dela. O fio de luz de 2px e o que garante a leitura
            # sobre qualquer imagem — sem ele isto vira texto apagado.
            #
            # O fio e CENTRADO (metade para dentro, metade para fora), que e
            # como o `-webkit-text-stroke` desenha: por isso dilata E corroe.
            r = max(1, round(tam * 0.028))
            fora = self._contorno(pad_m, r)
            dentro = 1.0 - self._contorno(1.0 - pad_m, r)
            fio = np.clip(fora - dentro, 0.0, 1.0)
            cor_t = self._cor(accent or "#ffffff")
            alpha = np.maximum(pad_m * self.VIDRO_OPACO, fio * self.VIDRO_FIO)
            rgb = np.broadcast_to(cor_t, (*pad_m.shape, 3)).copy()
            self._pintar_emoji(rgb, cor_emj, folga)
            # O `drop-shadow` do CSS parte do elemento JA com a opacidade
            # dele: a sombra de uma letra a 32% e 32% mais fraca. Lancar do
            # glifo cheio deixava a legenda 28% mais "tinta" que a do
            # template (medido: 1,280 contra 1,007 dos outros estilos).
            # `filter: drop-shadow` — sigma e o RAIO INTEIRO (BLUR_K), nao a
            # metade. Mesmo tropeco que deixou `vazado` e `gradiente` com
            # metade do borrao; aqui era eu repetindo o padrao do ajudante.
            return rgb, alpha, self._sombra_de(
                pad_m, [(0, 8, 22, 0.55 * self.VIDRO_OPACO)], k=BLUR_K)

        if modo == "traco":
            # o Recorte com contorno FINO: 3px em vez dos 7px dele
            r = max(2, round(tam * 0.035))
            borda = self._contorno(pad_m, r)
            cor_t = self._cor(accent or "#ffffff")
            cor_b = self._cor("#101215")
            alpha = np.maximum(borda, pad_m)
            rgb = np.broadcast_to(cor_b, (*pad_m.shape, 3)).copy()
            rgb = rgb * (1 - pad_m[..., None]) + cor_t * pad_m[..., None]
            self._pintar_emoji(rgb, cor_emj, folga)
            return rgb, alpha, self._sombra_de(pad_m, [(0, 8, 20, 0.4)], k=0.5)

        # eco: ciano atras, magenta na frente, e o texto por cima das duas
        d = max(3, round(tam * 0.085))
        rgb = np.zeros((*pad_m.shape, 3), dtype=np.float32)
        alpha = np.zeros_like(pad_m)
        # magenta primeiro, ciano depois: no CSS a PRIMEIRA sombra da lista
        # e a que fica por cima, e aqui quem pinta depois e que fica.
        for desloc, cor_hex in (((d, d), "#ff2e88"), ((-d, -d), "#28e0d8")):
            dx, dy = desloc
            copia = np.zeros_like(pad_m)
            ys = slice(max(0, dy), pad_m.shape[0] + min(0, dy))
            xs = slice(max(0, dx), pad_m.shape[1] + min(0, dx))
            ys2 = slice(max(0, -dy), pad_m.shape[0] + min(0, -dy))
            xs2 = slice(max(0, -dx), pad_m.shape[1] + min(0, -dx))
            copia[ys, xs] = pad_m[ys2, xs2]
            cor = self._cor(cor_hex)
            inv = 1.0 - copia
            rgb = rgb * inv[..., None] + cor * copia[..., None]
            alpha = alpha * inv + copia
        cor_t = self._cor(accent or "#ffffff")
        inv = 1.0 - pad_m
        rgb = rgb * inv[..., None] + cor_t * pad_m[..., None]
        alpha = alpha * inv + pad_m
        self._pintar_emoji(rgb, cor_emj, folga)
        return rgb, alpha, self._sombra_de(pad_m, [(0, 10, 26, 0.45)], k=0.5)

    def _painel_legenda(self, modo, linhas, f, track, tam, alt_l, bottom,
                        accent, limpar):
        """Vidro e Moldura: UM painel em volta do cue inteiro.

        Diferente do `bloco`, que da uma lapide para cada linha — aqui a
        caixa e uma so, com as duas linhas dentro, que e o que faz o vidro
        parecer uma placa e nao duas etiquetas.
        """
        import numpy as np

        folga = 60
        gap = round(tam * 0.16)
        masks = []
        for ln in linhas:
            texto = " ".join(limpar(w["text"]) for w in ln)
            masks.append(self._mascara_cor(f, texto, float(track)))
        w_txt = max(m.shape[1] for m, _ in masks)
        h_txt = alt_l * len(masks) + gap * (len(masks) - 1)
        pad_x = round(tam * (0.62 if modo == "vidro" else 0.72))
        pad_y = round(tam * (0.44 if modo == "vidro" else 0.40))
        cw = int(w_txt + 2 * pad_x)
        ch = int(h_txt + 2 * pad_y)
        raio = round(tam * 0.60) if modo == "vidro" else 4
        L, A = cw + 2 * folga, ch + 2 * folga

        cheio = Image.new("L", (L, A), 0)
        ImageDraw.Draw(cheio).rounded_rectangle(
            [folga, folga, folga + cw, folga + ch], radius=raio, fill=255)
        a_cheio = np.asarray(cheio, dtype=np.float32) / 255.0
        largura_b = 2
        dentro = Image.new("L", (L, A), 0)
        ImageDraw.Draw(dentro).rounded_rectangle(
            [folga + largura_b, folga + largura_b,
             folga + cw - largura_b, folga + ch - largura_b],
            radius=max(0, raio - largura_b), fill=255)
        a_dentro = np.asarray(dentro, dtype=np.float32) / 255.0
        a_borda = np.clip(a_cheio - a_dentro, 0.0, 1.0)

        if modo == "vidro":
            # Vidro FUMADO. O motor rapido desenha um overlay, sem o take
            # embaixo — entao um desfoque de verdade nao cabe aqui. O que
            # cabe, e o que faz a letra descolar, e escurecer: 46% de tinta
            # escura, com o brilho de luz caindo de cima.
            escuro = self._cor("#0d0f14")
            branco = self._cor("#ffffff")
            g = np.linspace(0.16, 0.02, A, dtype=np.float32)[:, None]
            a_pan = (1.0 - (1.0 - 0.46) * (1.0 - g)) * a_cheio
            num = branco * g + escuro * 0.46 * (1.0 - g)
            rgb_pan = num / np.maximum(1.0 - (1.0 - 0.46) * (1.0 - g), 1e-6)
            rgb_pan = np.broadcast_to(rgb_pan[:, None, :], (A, L, 3)).copy()
            cor_b = branco
            a_b = a_borda * 0.34
            cor_txt = self._cor(accent or "#f7f9fc")
        else:
            escuro = self._cor("#0b0d10")
            a_pan = a_cheio * 0.30
            rgb_pan = np.broadcast_to(escuro, (A, L, 3)).copy()
            cor_b = self._cor(accent or "#ffffff")
            a_b = a_borda * 0.85
            cor_txt = self._cor(accent or "#ffffff")

        # borda POR CIMA do fundo (o `border` do CSS cobre o background)
        alpha = a_b + a_pan * (1.0 - a_b)
        rgb = (cor_b * a_b[..., None]
               + rgb_pan * (a_pan * (1.0 - a_b))[..., None]) \
            / np.maximum(alpha[..., None], 1e-6)

        asc, desc = f.getmetrics()
        ty = folga + pad_y
        for m, cor_emj in masks:
            h_m, w_m = m.shape
            tx = folga + int((cw - w_m) / 2)
            # `alt_l` e float (tam * lh): sem o int aqui o recorte da fatia
            # recebe um float e o numpy recusa
            oy = int(ty + (alt_l - (asc + desc)) / 2)
            hh = min(h_m, A - oy)
            ww = min(w_m, L - tx)
            if hh > 0 and ww > 0:
                sub = np.zeros_like(alpha)
                sub[oy:oy + hh, tx:tx + ww] = m[:hh, :ww]
                inv = 1.0 - sub
                rgb = rgb * inv[..., None] + cor_txt * sub[..., None]
                alpha = alpha * inv + sub
                self._pintar_emoji(rgb, cor_emj, tx, oy)
            ty += alt_l + gap

        sombra = self._sombra_de(a_cheio, [(0, 18, 40, 0.45)], k=0.5)
        return Palavra(int((self.w - cw) / 2) - folga,
                       int(self.h - bottom - ch) - folga,
                       rgb, alpha, sombra, inicio_f=-1, enter=1, sobe=0.0)

    @staticmethod
    def _ordinal(f, n: int) -> str:
        """`1º` como no template — mas so se a fonte tiver o glifo.

        As oito fontes do catalogo tem U+00BA; a fonte PROPRIA do usuario
        (fontFamily "arquivo") pode nao ter, e ai o PIL desenha o .notdef —
        um quadradinho no video entregue. Nesse caso vale mais o numero seco.
        """
        import numpy as np

        try:
            m = np.asarray(f.getmask("\u00ba", mode="L"))
            falta = np.asarray(f.getmask("\uffff", mode="L"))
            ok = bool(m.size and m.any()) and not (
                m.shape == falta.shape and bool((m == falta).all()))
        except Exception:  # noqa: BLE001
            ok = False
        return f"{n}\u00ba" if ok else str(n)

    # ----- contador de lista (ListCounter.tsx) ------------------------------
    def _montar_contador(self):
        """Selo com o numero, canto superior direito, girado 4 graus, com pop.
        Cada marcador vale ate o proximo (o ultimo vai ate o fim)."""
        marcadores = self.ed.get("listMarkers") or []
        if not marcadores:
            return []
        accent = (self.ed.get("hook") or {}).get("accent") or "#ff5200"
        tinta = self._tinta_na_caixa(accent)
        tam = 64
        f = self.fonte(4, tam, 900, marca="hook")   # hookWeight(900)
        camadas = []
        for i, mk in enumerate(marcadores):
            ini = int(round(float(mk["atSec"]) * self.fps))
            fim = (int(round(float(marcadores[i + 1]["atSec"]) * self.fps)) - 1
                   if i + 1 < len(marcadores) else self.frames)
            if fim < ini:
                continue
            leg = Camada(ini, fim)
            leg.dur_f = fim - ini + 1
            leg.saida_f = 1e9
            texto = self._ordinal(f, int(mk["n"]))
            asc, desc = f.getmetrics()
            for est in range(9):
                t = min(1.0, est / 8)
                esc = 0.6 + 0.4 * self._ease_back(t)
                m = self._mascara(
                    self.fonte(4, max(8, int(tam * esc)), 900, marca="hook"),
                    texto, 0.0)   # hookWeight(900) — marca variavel inclusa
                h_m, w_m = m.shape
                pad_x, pad_t, pad_b = (int(26 * esc), int(18 * esc), int(22 * esc))
                cw, ch = w_m + 2 * pad_x, int(tam * esc) + pad_t + pad_b
                folga = 40
                L, A = cw + 2 * folga, ch + 2 * folga
                img = Image.new("L", (L, A), 0)
                ImageDraw.Draw(img).rounded_rectangle(
                    [folga, folga, folga + cw, folga + ch],
                    radius=max(2, int(20 * esc)), fill=255)
                a_c = np.asarray(img, dtype=np.float32) / 255.0
                t_a = np.zeros_like(a_c)
                tx, ty = folga + pad_x, folga + pad_t
                hh, ww = min(h_m, A - ty), min(w_m, L - tx)
                t_a[ty:ty + hh, tx:tx + ww] = m[:hh, :ww]
                rgb = np.broadcast_to(self._cor(accent), (*a_c.shape, 3)).copy()
                rgb = rgb * (1 - t_a[..., None]) + self._cor(tinta) * t_a[..., None]
                alpha = np.maximum(a_c, t_a)
                sombra = self._sombra_de(a_c, [(0, 12, 32, 0.4)], k=0.5)

                def _g(arr, modo="L"):
                    im = Image.fromarray(
                        (arr * 255).astype(np.uint8) if modo == "L"
                        else arr.astype(np.uint8), modo)
                    out = im.rotate(-4.0, expand=False, resample=Image.BICUBIC)
                    return (np.asarray(out, dtype=np.float32) / 255.0
                            if modo == "L" else
                            np.asarray(out, dtype=np.float32))
                alpha, sombra = _g(alpha), _g(sombra)
                rgb = _g(rgb, "RGB")
                # canto superior direito: paddingTop 150, paddingRight 54
                x0 = self.w - 54 - cw - folga
                y0 = 150 - folga
                jan = (est, est + 1) if est < 8 else (8, 1e9)
                leg.palavras.append(Palavra(
                    x0, y0, rgb, alpha, sombra, inicio_f=0, enter=1,
                    janela=jan, sobe=0.0,
                    # `opacity: min(1, pop*1.4)` do ListCounter — sem isto o
                    # selo nascia 100% opaco ainda em escala 0.6
                    opac=min(1.0, t * 1.4)))
            camadas.append(leg)
        return camadas

    def _abrir_imagem(self, rel, larg: int, raio: int = 0):
        """(rgb, alpha) de uma imagem de public/, redimensionada para `larg`.

        `raio` arredonda os cantos como o borderRadius do template. Devolve
        None se o arquivo sumiu ou nao abre — imagem faltando nao pode
        derrubar o render inteiro.
        """
        if not rel:
            return None
        cam = self.public / str(rel)
        if not cam.exists():
            return None
        try:
            im = Image.open(cam).convert("RGBA")
        except OSError:
            print(f"  [warn] imagem ilegivel: {cam.name}", flush=True)
            return None
        alt = max(1, int(round(im.height * larg / max(1, im.width))))
        im = im.resize((larg, alt), Image.LANCZOS)
        arr = np.asarray(im, dtype=np.float32)
        a = arr[..., 3] / 255.0
        if raio > 0:
            m = Image.new("L", (larg, alt), 0)
            ImageDraw.Draw(m).rounded_rectangle(
                [0, 0, larg - 1, alt - 1], radius=raio, fill=255)
            a = a * (np.asarray(m, dtype=np.float32) / 255.0)
        return arr[..., :3].copy(), a

    def _palavra_imagem(self, leg, img, x: int, y: int, especs,
                        k: float, enter: int, sobe: float):
        """Empilha uma imagem como Palavra, com folga para a sombra caber."""
        rgb, a = img
        h, w = a.shape
        folga = 60
        A = np.zeros((h + 2 * folga, w + 2 * folga), dtype=np.float32)
        A[folga:folga + h, folga:folga + w] = a
        R = np.zeros((*A.shape, 3), dtype=np.float32)
        R[folga:folga + h, folga:folga + w] = rgb
        leg.palavras.append(Palavra(
            int(x) - folga, int(y) - folga, R, A,
            self._sombra_de(A, especs, k=k),
            inicio_f=0, enter=enter, sobe=sobe))

    # ----- b-roll / inserts (InsertCard.tsx) --------------------------------
    def _quadros_do_take(self, cam: Path, total: int,
                         fx: float = 0.5, fy: float = 0.5,
                         zoom: float = 1.0) -> Path | None:
        """Extrai o take ja no tamanho do cartao, uma vez, para o disco.

        Guardar os quadros em memoria custaria 1,5 MB cada (780x500 RGBA):
        um take de 2,5s levaria ~117 MB. Em JPEG no disco sao ~60 KB por
        quadro, e so os quadros da janela do insert sao lidos.

        `fx`/`fy` = enquadramento (object-position): o crop do `cover` sai
        do centro para a parte escolhida. Entram na CHAVE do cache — mudar o
        enquadramento re-extrai.
        """
        marca_foco = ("" if abs(fx - 0.5) < 1e-3 and abs(fy - 0.5) < 1e-3
                      and abs(zoom - 1.0) < 1e-3
                      else f"-{fx:.2f}x{fy:.2f}z{zoom:.2f}")
        destino = cam.parent / f".f-{cam.stem[:24]}{marca_foco}"
        pronto = destino / "ok.txt"
        if pronto.is_file():
            return destino
        import shutil

        shutil.rmtree(destino, ignore_errors=True)
        destino.mkdir(parents=True, exist_ok=True)
        # `fps` alinha o take ao relogio do video; scale+crop e o `cover`
        # (o zoom amplia a base do scale e o crop volta ao tamanho do cartao)
        zw = max(1, int(round(INSERT_W * zoom)))
        zh = max(1, int(round(INSERT_H * zoom)))
        vf = (f"fps={self.fps:.6f},scale={zw}:{zh}:"
              f"force_original_aspect_ratio=increase,"
              f"crop={INSERT_W}:{INSERT_H}:(iw-ow)*{fx:.4f}:(ih-oh)*{fy:.4f}")
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-i", str(cam), "-an",
                 "-vf", vf, "-frames:v", str(max(1, total)), "-q:v", "3",
                 str(destino / "%04d.jpg")],
                capture_output=True, text=True, timeout=180, **NOWIN)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"  [warn] take nao extraido ({str(e)[:60]})", flush=True)
            return None
        quadros = sorted(destino.glob("*.jpg"))
        if r.returncode != 0 or not quadros:
            print(f"  [warn] take sem quadros: {cam.name}", flush=True)
            return None
        pronto.write_text(str(len(quadros)), encoding="utf-8")
        return destino

    def _montar_inserts(self):
        """Uma camada por insert. A imagem entra em `cover` no cartao e o
        arredondamento ja vem no alpha; o resto (escala, opacidade, subida)
        e por quadro, em `_desenhar_insert`."""
        camadas = []
        # Ordem de PINTURA = ordem de INICIO na timeline: quem entra depois
        # desenha por cima (padrao de editor). Sem isto a ordem era a de
        # criacao, e o cartao girando passava POR TRAS de outra imagem
        # (relato de 02/09). Espelho do sort no Inserts do template.
        fila = sorted((self.ed.get("inserts") or []),
                      key=lambda x: float((x or {}).get("start") or 0.0)
                      if isinstance(x, dict) else 0.0)
        for it in fila:
            src = it.get("src")
            if not src:
                continue
            cam = self.public / str(src)
            if not cam.exists():
                print(f"  [warn] insert ausente: {src}", flush=True)
                continue
            ini = int(round(float(it.get("start") or 0.0) * self.fps))
            fim = int(round(float(it.get("end") or 0.0) * self.fps))
            total = fim - ini
            if total <= 0:
                continue
            # Take de VIDEO (Biblioteca): o cartao toca o take, nao uma foto
            video = cam.suffix.lower() in (".mp4", ".mov", ".webm")
            foco_x = _foco_do_insert(it, "fx")
            foco_y = _foco_do_insert(it, "fy")
            pasta = (self._quadros_do_take(cam, total, fx=foco_x, fy=foco_y,
                                           zoom=_zoom_do_insert(it))
                     if video else None)
            if video and pasta is None:
                continue
            try:
                im = (Image.open(sorted(pasta.glob("*.jpg"))[0]).convert("RGBA")
                      if video else Image.open(cam).convert("RGBA"))
            except (OSError, IndexError):
                print(f"  [warn] insert ilegivel: {src}", flush=True)
                continue
            cw, ch, ccx, ccy = geometria_do_insert(it, self.w, self.h)
            raio = max(4, int(round(INSERT_RAIO * cw / INSERT_W)))
            # ARTE com transparencia (uma logo em PNG) nao e uma foto: ela
            # nao quer cartao, nao quer ser recortada e a sombra dela sai da
            # PROPRIA forma. Foto continua entrando em `cover`, no cartao.
            arte = (not video) and cam.suffix.lower() in (".png", ".webp") \
                and _tem_transparencia(im)
            if arte:
                esc = min(cw / im.width, ch / im.height)     # objectFit: contain
                nw = max(1, round(im.width * esc))
                nh = max(1, round(im.height * esc))
                menor = im.resize((nw, nh), Image.LANCZOS)
                im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                im.paste(menor, ((cw - nw) // 2, (ch - nh) // 2))
                masc = im.getchannel("A")
            else:
                # objectFit: cover — recorta o excedente, nao deforma.
                # fx/fy = ENQUADRAMENTO (object-position do template): que
                # parte do excedente fica visivel; 0,5 = centro, o padrao.
                # `zoom` amplia alem do cover (corte de um lado no editor).
                fx, fy = foco_x, foco_y
                esc = max(cw / im.width, ch / im.height) * _zoom_do_insert(it)
                nw = max(1, round(im.width * esc))
                nh = max(1, round(im.height * esc))
                x0 = int(round((nw - cw) * fx))
                y0 = int(round((nh - ch) * fy))
                im = im.resize((nw, nh), Image.LANCZOS).crop(
                    (x0, y0, x0 + cw, y0 + ch))
                masc = Image.new("L", (cw, ch), 0)
                ImageDraw.Draw(masc).rounded_rectangle(
                    [0, 0, cw - 1, ch - 1], radius=raio, fill=255)
                # MULTIPLICAR, nao substituir: o `putalpha(masc)` que estava
                # aqui jogava fora o alpha da imagem, e todo PNG chegava ao
                # video com o fundo preto dentro do cartao (print de 30/08).
                im.putalpha(ImageChops.multiply(im.getchannel("A"), masc))
            folga = 70
            base = np.zeros((ch + 2 * folga, cw + 2 * folga), dtype=np.float32)
            base[folga:folga + ch, folga:folga + cw] = \
                np.asarray(masc, dtype=np.float32) / 255.0
            # drop-shadow(0 14px 34px .45) do template: e filter, sigma =
            # raio INTEIRO (k=BLUR_K), nao a metade do box-shadow do cartao.
            sombra = self._sombra_de(base, [(0, 14, 34, 0.45)], k=BLUR_K)
            leg = Camada(ini, min(self.frames, fim) - 1)
            leg.dur_f = total
            leg.saida_f = 1e9
            s_rgba = np.zeros((*sombra.shape, 4), dtype=np.uint8)
            s_rgba[..., 3] = (sombra * 255).astype(np.uint8)   # preta
            leg.insert = (im, total, Image.fromarray(s_rgba, "RGBA"))
            leg.insert_quadros = (pasta, masc) if video else None
            # onde e de que tamanho: sem isto o desenho voltaria ao cartao fixo
            leg.insert_caixa = (cw, ch, ccx, ccy)
            # animacoes escolhidas pelo usuario no preview — espelho do
            # InsertCard do template (mesmas formulas)
            leg.insert_entrada = str(it.get("entrada") or "padrao")
            leg.insert_saida = str(it.get("saida") or "suave")
            camadas.append(leg)
            self.eventos_sfx.append(("whoosh.mp3", ini / self.fps, 0.09))
        return camadas

    def _desenhar_insert(self, leg, fl: float, buf, sujo, mesclar) -> None:
        im, total, sombra_im = leg.insert
        f = max(0.0, fl)
        # Take de video: o quadro do cartao muda a cada quadro do video.
        # Take mais curto que a janela congela no ultimo (e o que o
        # OffthreadVideo do template faz quando o video acaba).
        quadros = getattr(leg, "insert_quadros", None)
        if quadros:
            pasta, masc = quadros
            lista = getattr(leg, "_take_lista", None)
            if lista is None:
                lista = sorted(pasta.glob("*.jpg"))
                leg._take_lista = lista
            if lista:
                idx = min(len(lista) - 1, max(0, int(f)))
                if getattr(leg, "_take_idx", None) != idx:
                    try:
                        q = Image.open(lista[idx]).convert("RGBA")
                        q.putalpha(masc)
                        im = q
                        leg._take_idx = idx
                        leg._take_im = q
                    except OSError:
                        im = getattr(leg, "_take_im", None) or im
                else:
                    im = getattr(leg, "_take_im", None) or im
        # entra em 9 quadros (Easing.out cubic), sai nos ultimos 7
        t = min(1.0, f / 9.0)
        ent = 1.0 - (1.0 - t) ** 3
        s_lin = 0.0 if f <= total - 7 else min(1.0, (f - (total - 7)) / 7.0)
        entrada = getattr(leg, "insert_entrada", "padrao")
        saida = getattr(leg, "insert_saida", "suave")
        # OPACIDADE por efeito (espelho do InsertCard):
        #   nenhum aparece inteiro do quadro 0 · carimbo sobe rapido
        #   piscar estroboscopio nos 6 primeiros/ultimos quadros
        #   corte/nenhum na saida seguram cheio ate o fim
        if entrada == "nenhum":
            op_ent = 1.0
        elif entrada == "carimbo":
            op_ent = min(1.0, t * 2.5)
        elif entrada == "piscar":
            op_ent = _PISCA[int(f)] if 0 <= int(f) < 6 else 1.0
        else:
            op_ent = ent
        if saida in ("corte", "nenhum"):
            op_sai = 1.0
        elif saida == "piscar":
            idx = int(round(total - 1 - f))
            op_sai = _PISCA[idx] if 0 <= idx < 6 else 1.0
        else:
            op_sai = 1.0 - s_lin
        op = min(op_ent, op_sai)
        if op <= 0.004:
            return
        cw, ch, ccx, ccy = getattr(
            leg, "insert_caixa",
            (INSERT_W, INSERT_H, self.w / 2.0,
             INSERT_TOP + INSERT_H / 2.0))
        # Ken-Burns: a imagem cresce 8% enquanto esta na tela
        cresce = 1.0 + 0.08 * min(1.0, f / max(1.0, total))
        # Entrada escolhida pelo usuario — MESMAS formulas do InsertCard:
        #   padrao   sobe 26px, escala 0,92 -> 1
        #   pop      escala 0,5 -> 1 com overshoot (back.out)
        #   deslizar/direita/baixo/cima  vem daquele lado
        #   fade so opacidade · zoom 1,25 -> 1 · girar -12 graus -> 0
        dx = 0.0
        ang = 0.0
        sx = 1.0          # escala so na LARGURA (efeito Virar)
        sy = 1.0          # escala so na ALTURA (efeito Esticar)
        desfoque = 0.0    # raio do blur em px de 1080 (efeito Borrao)
        if entrada == "pop":
            b = 1.0 + 2.70158 * (t - 1.0) ** 3 + 1.70158 * (t - 1.0) ** 2
            escala = (0.5 + 0.5 * b) * cresce
            dy = 0.0
        elif entrada == "deslizar":
            escala = cresce
            dy = 0.0
            dx = -0.35 * cw * (1.0 - ent)
        elif entrada == "direita":
            escala = cresce
            dy = 0.0
            dx = 0.35 * cw * (1.0 - ent)
        elif entrada == "baixo":
            escala = cresce
            dy = 0.45 * ch * (1.0 - ent)
        elif entrada == "cima":
            escala = cresce
            dy = -0.45 * ch * (1.0 - ent)
        elif entrada == "fade":
            escala = cresce
            dy = 0.0
        elif entrada == "zoom":
            escala = (1.25 - 0.25 * ent) * cresce
            dy = 0.0
        elif entrada == "girar":
            escala = (0.85 + 0.15 * ent) * cresce
            dy = 0.0
            ang = -12.0 * (1.0 - ent)
        elif entrada == "quicar":
            escala = cresce
            dy = -0.45 * ch * (1.0 - _quique(t))
        elif entrada == "elastico":
            escala = max(0.2, _elastico(t)) * cresce
            dy = 0.0
        elif entrada == "balancar":
            import math
            escala = cresce
            dy = 0.0
            ang = 18.0 * math.exp(-3.0 * t) * math.cos(7.0 * t)
        elif entrada == "borrao":
            escala = cresce
            dy = 0.0
            desfoque = 14.0 * (1.0 - ent)
        elif entrada == "virar":
            escala = cresce
            dy = 0.0
            sx = max(0.02, ent)
        elif entrada == "nenhum" or entrada == "piscar":
            escala = cresce
            dy = 0.0
        elif entrada == "carimbo":
            # bate grande e assenta em 7 quadros, como o carimbo da headline
            t7 = min(1.0, f / 7.0)
            e7 = 1.0 - (1.0 - t7) ** 3
            escala = (1.9 - 0.9 * e7) * cresce
            dy = 0.0
        elif entrada == "esticar":
            escala = cresce
            dy = 0.0
            sy = max(0.03, ent)
        else:
            escala = (0.92 + 0.08 * ent) * cresce
            dy = 26.0 * (1.0 - ent)
        # Saida escolhida — espelho do template:
        #   suave (fade) · encolher 1 -> 0,6 · deslizar p/ DIREITA ·
        #   esquerda · baixo · zoom 1 -> 1,3 · girar +12 graus ·
        #   corte seco (sem fade)
        if saida == "encolher":
            escala *= 1.0 - 0.4 * s_lin
        elif saida == "deslizar":
            dx += 0.35 * cw * s_lin
        elif saida == "esquerda":
            dx -= 0.35 * cw * s_lin
        elif saida == "baixo":
            dy += 0.45 * ch * s_lin
        elif saida == "zoom":
            escala *= 1.0 + 0.3 * s_lin
        elif saida == "girar":
            escala *= 1.0 - 0.15 * s_lin
            ang += 12.0 * s_lin
        elif saida == "cima":
            dy -= 0.45 * ch * s_lin
        elif saida == "borrao":
            desfoque = max(desfoque, 14.0 * s_lin)
        elif saida == "virar":
            sx *= max(0.02, 1.0 - s_lin)
        elif saida == "esticar":
            sy *= max(0.03, 1.0 - s_lin)
        lw = max(1, int(round(cw * escala * sx)))
        lh = max(1, int(round(ch * escala * sy)))
        # `scale` do CSS cresce a partir do CENTRO da caixa
        cx = ccx + dx
        cy = ccy + dy
        folga = 70
        L, A = lw + 2 * folga, lh + 2 * folga
        tela_im = sombra_im.resize((L, A), Image.BILINEAR)
        tela_im.alpha_composite(im.resize((lw, lh), Image.BILINEAR),
                                (folga, folga))
        if abs(ang) > 0.05:
            # `rotate` do CSS gira em graus HORARIOS sobre o centro; o do
            # Pillow e anti-horario — por isso o sinal trocado. `expand`
            # cresce a tela e o centro continua sendo o centro.
            tela_im = tela_im.rotate(-ang, resample=Image.BILINEAR,
                                     expand=True)
            L, A = tela_im.size
        if desfoque > 0.3:
            # blur(R) do CSS ~ Gaussiana de sigma R/2; o raio e em px da
            # composicao (1080), entao escala com a largura real
            sigma = (desfoque / 2.0) * (self.w / 1080.0)
            tela_im = tela_im.filter(ImageFilter.GaussianBlur(sigma))
        comp = np.asarray(tela_im, dtype=np.uint8)
        if op < 0.996:
            comp = comp.copy()
            comp[..., 3] = (comp[..., 3] * op).astype(np.uint8)
        # recorta no que cabe no quadro (posicao pelo CENTRO — com rotacao a
        # tela expandida continua centrada no mesmo ponto)
        fx, fy = int(round(cx - L / 2)), int(round(cy - A / 2))
        cx0, cy0 = max(0, fx), max(0, fy)
        cx1 = min(buf.shape[1], fx + L)
        cy1 = min(buf.shape[0], fy + A)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        comp = comp[cy0 - fy:cy1 - fy, cx0 - fx:cx1 - fx]
        self._blit(comp, leg, buf, sujo, cx0, cy0, cx1, cy1, 0, mesclar)

    # ------------------------------------------------------------ desenho ----
    def _caixa_leg(self, leg: Camada) -> tuple[int, int, int, int]:
        if leg.caixa is None:
            x0 = max(0, min(p.x0 for p in leg.palavras))
            y0 = max(0, min(p.y0 for p in leg.palavras))
            x1 = min(self.w, max(p.x0 + p.alpha.shape[1] for p in leg.palavras))
            y1 = min(self.h, max(p.y0 + p.alpha.shape[0] for p in leg.palavras))
            leg.caixa = (x0, y0, max(x0 + 1, x1), max(y0 + 1, y1))
        return leg.caixa

    @staticmethod
    def _blend(tela: np.ndarray, p: Palavra, op: float, x0: int, y0: int) -> None:
        h, w = p.alpha.shape
        # Sem o `if p.janela is None` que estava aqui: a subida sai da
        # OPACIDADE, e quem usa janela com opacidade 1,0 (traco do Recorte,
        # estagios do contador, do impacto e da pergunta) ja da `sobe*(1-1)`
        # = 0 sozinho. A condicao so servia enquanto nenhum estagio tinha
        # opacidade propria — e passou a apagar a subida de 46px do SOLO_BIG
        # quando ele ganhou estagios de escala.
        desloc = int(round(p.sobe * (1.0 - op)))
        py = p.y0 - y0 + desloc
        px = p.x0 - x0 + int(round(p.desliza * (1.0 - op)))
        ys0, xs0 = max(0, py), max(0, px)
        ys1 = min(tela.shape[0], py + h)
        xs1 = min(tela.shape[1], px + w)
        if ys1 <= ys0 or xs1 <= xs0:
            return
        sy, sx = ys0 - py, xs0 - px
        alt, larg = ys1 - ys0, xs1 - xs0
        sub = tela[ys0:ys1, xs0:xs1]
        a_s = p.sombra[sy:sy + alt, sx:sx + larg] * op
        a_t = p.alpha[sy:sy + alt, sx:sx + larg] * op
        rgb = p.rgb[sy:sy + alt, sx:sx + larg]
        inv = 1.0 - a_s
        sub[..., :3] *= inv[..., None]
        sub[..., 3] = sub[..., 3] * inv + a_s
        inv = 1.0 - a_t
        sub[..., :3] = sub[..., :3] * inv[..., None] + rgb * a_t[..., None]
        sub[..., 3] = sub[..., 3] * inv + a_t

    @staticmethod
    def _converter(tela: np.ndarray) -> np.ndarray:
        a = np.clip(tela[..., 3:4], 0.0, 1.0)
        rgb = np.clip(tela[..., :3] / np.maximum(a, 1e-6), 0.0, 255.0)
        out = np.empty(tela.shape, dtype=np.float32)
        out[..., :3] = rgb
        out[..., 3] = a[..., 0] * 255.0
        return out.astype(np.uint8)

    def _blit(self, pronto8, leg, buf, sujo, bx0, by0, bx1, by1, dy, mesclar):
        dy0, dy1 = by0 + dy, by1 + dy
        corte0 = max(0, -dy0)
        dy0, dy1 = max(0, dy0), min(buf.shape[0], dy1)
        if dy1 <= dy0:
            return
        pedaco = pronto8[corte0:corte0 + (dy1 - dy0)]
        if mesclar:
            fundo = buf[dy0:dy1, bx0:bx1].astype(np.float32)
            pf = pedaco.astype(np.float32)
            a_f = pf[..., 3:4] / 255.0
            a_b = fundo[..., 3:4] / 255.0
            a_o = a_f + a_b * (1.0 - a_f)
            rgb = (pf[..., :3] * a_f + fundo[..., :3] * a_b * (1.0 - a_f)) \
                / np.maximum(a_o, 1e-6)
            buf[dy0:dy1, bx0:bx1] = np.clip(
                np.concatenate([rgb, a_o * 255.0], axis=2), 0, 255).astype(np.uint8)
        else:
            buf[dy0:dy1, bx0:bx1] = pedaco
        sujo[0] = min(sujo[0], bx0) if sujo[2] > sujo[0] else bx0
        sujo[1] = min(sujo[1], dy0) if sujo[3] > sujo[1] else dy0
        sujo[2] = max(sujo[2], bx1)
        sujo[3] = max(sujo[3], dy1)

    def desenhar(self, leg: Camada, fl: float, buf: np.ndarray,
                 sujo: list[int], mesclar: bool) -> None:
        if leg.insert is not None:
            self._desenhar_insert(leg, fl, buf, sujo, mesclar)
            return
        op_cue, dy_cue, blur_cue = leg.saida(fl)
        if op_cue <= 0.004:
            return
        assentadas, animando = [], []
        for p in leg.palavras:
            op = _opacidade(p, fl)
            if op <= 0.004:
                continue
            (assentadas if op >= 0.996 else animando).append(
                p if op >= 0.996 else (p, op))
        if not assentadas and not animando:
            return
        x0, y0, x1, y1 = self._caixa_leg(leg)
        bx0, by0 = max(0, x0), max(0, y0)
        bx1, by1 = min(buf.shape[1], x1), min(buf.shape[0], y1)
        if bx1 <= bx0 or by1 <= by0:
            return
        chave = tuple(id(p) for p in assentadas)
        if chave != leg.cache_chave:
            base = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.float32)
            for p in assentadas:
                self._blend(base, p, 1.0, x0, y0)
            leg.cache_chave, leg.cache_tela = chave, base
            leg.cache_pronto = self._converter(base)
        tela = leg.cache_tela
        rapido = op_cue >= 0.996 and blur_cue <= 0.25 and abs(dy_cue) < 0.5
        if not animando and rapido:
            self._blit(leg.cache_pronto, leg, buf, sujo, bx0, by0, bx1, by1, 0, mesclar)
            return
        if animando and rapido:
            pronto8 = leg.cache_pronto.copy()
            ax0 = min(max(0, p.x0 - x0 - abs(int(p.desliza))) for p, _ in animando)
            ay0 = min(max(0, p.y0 - y0 - int(p.sobe)) for p, _ in animando)
            ax1 = max(min(x1 - x0, p.x0 - x0 + p.alpha.shape[1] + abs(int(p.desliza)) + 1)
                      for p, _ in animando)
            ay1 = max(min(y1 - y0, p.y0 - y0 + p.alpha.shape[0] + int(p.sobe) + 1)
                      for p, _ in animando)
            if ax1 > ax0 and ay1 > ay0:
                sub = tela[ay0:ay1, ax0:ax1].copy()
                for p, op in animando:
                    self._blend_em(sub, p, op, x0 + ax0, y0 + ay0)
                pronto8[ay0:ay1, ax0:ax1] = self._converter(sub)
            self._blit(pronto8, leg, buf, sujo, bx0, by0, bx1, by1, 0, mesclar)
            return
        tela = tela.copy()
        for p, op in animando:
            self._blend(tela, p, op, x0, y0)
        if blur_cue > 0.25:
            tela = np.asarray(
                Image.fromarray(np.clip(tela * [1, 1, 1, 255], 0, 255).astype(np.uint8),
                                mode="RGBA").filter(ImageFilter.GaussianBlur(blur_cue / 2)),
                dtype=np.float32)
            tela[..., 3] /= 255.0
        pronto = self._converter(tela).astype(np.float32)
        pronto[..., 3] *= op_cue
        self._blit(pronto.astype(np.uint8), leg, buf, sujo, bx0, by0, bx1, by1,
                   int(round(dy_cue)), mesclar)

    def _blend_em(self, sub, p, op, abs_x0, abs_y0):
        h, w = p.alpha.shape
        # Sem o `if p.janela is None` que estava aqui: a subida sai da
        # OPACIDADE, e quem usa janela com opacidade 1,0 (traco do Recorte,
        # estagios do contador, do impacto e da pergunta) ja da `sobe*(1-1)`
        # = 0 sozinho. A condicao so servia enquanto nenhum estagio tinha
        # opacidade propria — e passou a apagar a subida de 46px do SOLO_BIG
        # quando ele ganhou estagios de escala.
        desloc = int(round(p.sobe * (1.0 - op)))
        py = p.y0 - abs_y0 + desloc
        px = p.x0 - abs_x0 + int(round(p.desliza * (1.0 - op)))
        ys0, xs0 = max(0, py), max(0, px)
        ys1, xs1 = min(sub.shape[0], py + h), min(sub.shape[1], px + w)
        if ys1 <= ys0 or xs1 <= xs0:
            return
        sy, sx = ys0 - py, xs0 - px
        alt, larg = ys1 - ys0, xs1 - xs0
        dst = sub[ys0:ys1, xs0:xs1]
        a_s = p.sombra[sy:sy + alt, sx:sx + larg] * op
        a_t = p.alpha[sy:sy + alt, sx:sx + larg] * op
        rgb = p.rgb[sy:sy + alt, sx:sx + larg]
        inv = 1.0 - a_s
        dst[..., :3] *= inv[..., None]
        dst[..., 3] = dst[..., 3] * inv + a_s
        inv = 1.0 - a_t
        dst[..., :3] = dst[..., :3] * inv[..., None] + rgb * a_t[..., None]
        dst[..., 3] = dst[..., 3] * inv + a_t

    # ------------------------------------------------------------ efeitos ----
    def _tabelas_dim(self, a: float):
        """(rgb, alpha) de 256 entradas para escurecer com fator `a`.

        Montadas com as MESMAS contas da versao que operava no quadro
        inteiro — inclusive o truncamento do astype e o float32 do alpha —
        para o resultado sair identico bit a bit.
        """
        cache = getattr(self, "_dim_luts", None)
        if cache is None:
            cache = self._dim_luts = {}
        chave = round(a, 6)
        if chave not in cache:
            v = np.arange(256, dtype=np.uint8)
            t_rgb = (v * (1.0 - a)).astype(np.uint8)
            alpha = v.astype(np.float32) / 255.0
            t_a = ((alpha + a * (1.0 - alpha)) * 255.0).astype(np.uint8)
            cache[chave] = (t_rgb, t_a)
        return cache[chave]

    def _aplicar_dim(self, buf, sujo, dim, fl, fade):
        t = min(1.0, max(0.0, fl / max(1, fade)))
        # Aqui a cubica esta CERTA: o end card do template usa
        # `Easing.out(Easing.cubic)` (Main.tsx:506), nao o bezier da entrada
        # de palavra. Conferido antes de trocar.
        a = dim * (1 - (1 - t) ** 3)
        if a <= 0.004:
            return
        # Tabela em vez de conta no quadro inteiro: `buf * (1.0 - a)` promovia
        # 6 milhoes de uint8 a float64 (48 MB por quadro) so para voltar a
        # uint8 logo depois. Medido: 244 ms por quadro, 44% do desenho.
        t_rgb, t_a = self._tabelas_dim(a)
        buf[..., :3] = t_rgb[buf[..., :3]]
        buf[..., 3] = t_a[buf[..., 3]]
        sujo[:] = [0, 0, buf.shape[1], buf.shape[0]]

    _flash_cache: dict[int, np.ndarray]

    # O FEIXE ESTAVA FORA DE LUGAR (varredura `transicoes`, 30/08). O
    # flash aparece em quase todo video do usuario — mediana de 8 por
    # video — e nunca tinha sido comparado com o template: os outros
    # grupos da varredura zeram `transitions` para isolar o desenho.
    #
    # Comparado, deu 0,629 de tinta. A causa: `expand=True` devolve uma
    # imagem MAIOR que o retangulo, e ela era colada em `(x, -0.3h)` como
    # se o canto dela fosse o canto do retangulo — o feixe inteiro andava
    # meia expansao para a direita (+462px num quadro de 1080). Medido
    # contra a posicao do CSS (`x + 0,23w`): est=1 dava CSS -724 e nosso
    # +120. Colando pelo CENTRO: **0,629 -> 0,892**.
    #
    # SOBRA 4% e nao se sabe de onde. Duas hipoteses ja foram medidas e
    # descartadas: inverter o giro do feixe (0,629 -> 0,630, com o feixe
    # ainda fora de lugar) e somar o `blur(16px)` do template (0,892 ->
    # 0,895 — nao paga o custo). E vale a ressalva: a varredura desenha o
    # overlay SEM o video por baixo, e o flash e a unica peca que compoe
    # contra o quadro existente.
    def _flash_quadro(self, at_s: float, f: int) -> np.ndarray | None:
        c = round(at_s * self.fps) + VIDEO_LAG
        if not (c - FLASH_LEAD <= f < c - FLASH_LEAD + FLASH_LEN):
            return None
        est = f - (c - FLASH_LEAD)
        bloom = float(np.interp(f, [c - 1, c, c + 2], [0, 0.5, 0]))
        cache = getattr(self, "_flash_masks", None)
        if cache is None:
            cache = self._flash_masks = {}
        if est not in cache:
            p = est / (FLASH_LEN - 1)
            x = (-1.35 + 2.7 * p) * self.w
            beam = float(np.interp(p, [0, 0.35, 1], [0, 1, 0]))
            img = Image.new("L", (self.w, self.h), 0)
            grad = np.abs(np.linspace(-1, 1, int(self.w * 0.46)))
            linha = ((1 - grad) * 0.95 * 255).astype(np.uint8)
            barra_np = np.repeat(linha[None, :], int(self.h * 1.6), axis=0)
            barra = Image.fromarray(barra_np, mode="L").rotate(
                -18, expand=True, resample=Image.BILINEAR)
            # A colagem parte do CENTRO. `expand=True` devolve uma imagem
            # maior que o retangulo, e colar essa imagem em `(x, -0.3h)`
            # tratava o canto dela como o canto do retangulo — o feixe
            # inteiro andava meia expansao para a direita (+462px num
            # quadro de 1080, medido). O CSS gira em torno do proprio
            # centro (`transform-origin` padrao), entao e o centro que tem
            # de cair no mesmo lugar nos dois motores.
            cx = x + 0.46 * self.w / 2.0
            cy = -0.3 * self.h + 1.6 * self.h / 2.0
            img.paste(barra,
                      (int(round(cx - barra.width / 2.0)),
                       int(round(cy - barra.height / 2.0))), barra)
            cache[est] = np.clip(
                np.asarray(img, dtype=np.float32) / 255.0 * beam, 0.0, 1.0)
        return np.maximum(cache[est], np.float32(bloom))

    def _aplicar_flash(self, buf, sujo, a):
        a_b = buf[..., 3].astype(np.float32) / 255.0
        a_o = a + a_b * (1.0 - a)
        peso = (a_b * (1.0 - a))[..., None]
        rgb = (255.0 * a[..., None] + buf[..., :3].astype(np.float32) * peso) \
            / np.maximum(a_o[..., None], 1e-6)
        buf[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        buf[..., 3] = (np.clip(a_o, 0, 1) * 255.0).astype(np.uint8)
        sujo[:] = [0, 0, buf.shape[1], buf.shape[0]]

    # ------------------------------------------------------------- saída ----
    def _assinatura(self, f: int):
        chave = []
        for leg in self.camadas:
            if not (leg.inicio_f <= f <= leg.fim_f):
                continue
            fl = f - leg.inicio_f
            if leg.insert is not None:
                chave.append((id(leg), f))    # zoom continuo: sempre muda
                continue
            op_cue, dy_cue, blur_cue = leg.saida(fl)
            if op_cue <= 0.004:
                continue
            estados = []
            for pal in leg.palavras:
                if pal.janela is not None:
                    ini, fim = pal.janela
                    estados.append(int(ini <= fl < fim) and (round(ini), round(fim)))
                elif fl <= pal.inicio_f:
                    estados.append(0)
                elif fl >= pal.inicio_f + pal.enter:
                    estados.append(1)
                else:
                    estados.append(round(fl * 2) / 2)
            chave.append((id(leg), round(op_cue, 3), round(dy_cue),
                          round(blur_cue, 1), round(leg.dim * min(
                              1.0, fl / max(1, leg.dim_fade)), 3) if leg.dim else 0,
                          tuple(estados)))
        for at in self.flashes:
            c = round(at * self.fps) + VIDEO_LAG
            if c - FLASH_LEAD <= f < c - FLASH_LEAD + FLASH_LEN:
                chave.append(("flash", f))
        return tuple(chave)

    def _gravar_video(self, alvo: Path, *, progresso=None) -> None:
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgba",
             "-s", f"{self.w}x{self.h}", "-r", f"{self.fps:g}", "-i", "-",
             # qtrle: RGBA com RLE — para overlay esparso e ~3x mais rapido
             # de encodar que ProRes 4444 e o compose decodifica nativo.
             *(["-c:v", "prores_ks", "-profile:v", "4444",
                "-pix_fmt", "yuva444p10le"]
               if os.environ.get("ATIVAVID_PROPRIO_PRORES") == "1" else
               ["-c:v", "qtrle"]),
             str(alvo)],
            stdin=subprocess.PIPE, **NOWIN)
        buf = (self.fundo.copy() if self.fundo is not None
               else np.zeros((self.h, self.w, 4), dtype=np.uint8))
        sujo = [0, 0, 0, 0]
        ass_ant, bytes_ant = None, None
        try:
            for f in range(self.frames):
                # O aviso vem NO LACO, nao na escrita: quadro identico ao
                # anterior e reaproveitado com um `continue`, e contar so os
                # escritos fazia a barra travar em video parado.
                # De 30 em 30 (1s de video): contar de mais custa mais que
                # informar.
                if progresso is not None and f % 30 == 0:
                    try:
                        progresso(f + 1, self.frames)
                    except Exception:  # noqa: BLE001
                        progresso = None   # quem escuta quebrou; o render
                        # NAO para por causa disso
                ass = self._assinatura(f)
                if ass == ass_ant and bytes_ant is not None:
                    ff.stdin.write(bytes_ant)
                    continue
                ass_ant = ass
                if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
                    # limpar = voltar para a tinta do layout, nao para zero
                    buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = (
                        0 if self.fundo is None
                        else self.fundo[sujo[1]:sujo[3], sujo[0]:sujo[2]])
                sujo[:] = [0, 0, 0, 0]
                # `primeira` copia por cima em vez de mesclar — de graca
                # quando o buffer esta zerado, mas com camada de layout isso
                # APAGARIA a tinta dela onde a legenda passa (a vinheta saiu
                # com um retangulo claro em volta da headline, 29/08).
                primeira = self.fundo is None
                for leg in self.camadas:
                    if leg.inicio_f <= f <= leg.fim_f:
                        if leg.dim:
                            self._aplicar_dim(buf, sujo, leg.dim,
                                              f - leg.inicio_f, leg.dim_fade)
                            primeira = False
                        self.desenhar(leg, f - leg.inicio_f, buf, sujo,
                                      mesclar=not primeira)
                        primeira = False
                for at in self.flashes:
                    a = self._flash_quadro(at, f)
                    if a is not None:
                        self._aplicar_flash(buf, sujo, a)
                bytes_ant = buf.tobytes()
                ff.stdin.write(bytes_ant)
        finally:
            ff.stdin.close()
            ff.wait()
        if ff.returncode != 0:
            raise RuntimeError("RENDER_PROPRIO_FFMPEG_VIDEO")

    def _gravar_sfx(self, alvo: Path) -> bool:
        """Mixa os eventos de SFX num wav. False se não houver eventos."""
        eventos = [(self.public / "sfx" / nome, t, vol)
                   for nome, t, vol in self.eventos_sfx
                   if (self.public / "sfx" / nome).exists()]
        if not eventos:
            return False
        dur = self.frames / self.fps
        argv = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        partes = []
        for i, (arq, t, vol) in enumerate(eventos):
            argv += ["-i", str(arq)]
            ms = int(round(t * 1000))
            partes.append(
                f"[{i}:a]volume={vol:.4f},adelay={ms}|{ms},"
                f"apad,atrim=end={dur:.6f}[a{i}]")
        soma = "".join(f"[a{i}]" for i in range(len(eventos)))
        partes.append(
            f"{soma}amix=inputs={len(eventos)}:normalize=0,"
            f"atrim=end={dur:.6f},asetpts=N/SR/TB[out]")
        argv += ["-filter_complex", ";".join(partes), "-map", "[out]",
                 "-c:a", "pcm_s16le", "-ar", "48000", str(alvo)]
        r = subprocess.run(argv, capture_output=True, text=True, **NOWIN)
        if r.returncode != 0 or not alvo.exists():
            raise RuntimeError(f"RENDER_PROPRIO_SFX {(r.stderr or '')[-300:]}")
        return True

    def render(self, out: Path, *, progresso=None) -> Path:
        """Escreve o overlay.mov (vídeo com alpha + SFX).

        `progresso(feitos, total)` e chamado a cada ~30 quadros. Ele
        existe porque o redesenho e 80% da espera de quem corrige uma
        legenda, e uma frase parada nao diz se aquilo anda.
        """
        out.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        so_video = out.with_name(out.stem + "._video.mov")
        self._gravar_video(so_video, progresso=progresso)
        sfx = out.with_name(out.stem + "._sfx.wav")
        tem_sfx = self._gravar_sfx(sfx)
        if tem_sfx:
            r = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-i", str(so_video), "-i", str(sfx),
                 "-map", "0:v", "-map", "1:a", "-c", "copy", str(out)],
                capture_output=True, text=True, **NOWIN)
            if r.returncode != 0 or not out.exists():
                raise RuntimeError(f"RENDER_PROPRIO_MUX {(r.stderr or '')[-300:]}")
            so_video.unlink(missing_ok=True)
            sfx.unlink(missing_ok=True)
        else:
            so_video.replace(out)
        print(f"RENDER_PROPRIO ok {self.frames}f em {time.perf_counter() - t0:.1f}s",
              flush=True)
        return out


def render_overlay_proprio(public: Path, edit_data: dict[str, Any], *,
                           frames: int, fps: float, width: int, height: int,
                           out: Path, progresso=None) -> Path:
    """Entrada única: monta e renderiza. Levanta em qualquer problema —
    o caller decide o fallback."""
    r = Renderizador(public, edit_data, frames=frames, fps=fps,
                     width=width, height=height)
    return r.render(out, progresso=progresso)


# ------------------------------------------------------ camada do layout ----
def camada_do_layout(layout: str, w: int, h: int,
                     accent: str = "#ff5200") -> np.ndarray | None:
    """RGBA (h,w,4) da tinta que o layout poe POR CIMA do quadro cheio.

    Espelho do `LayoutScrim` do Main.tsx — os numeros aqui e la sao os
    mesmos de proposito; mudou um, muda o outro. `None` = nada a desenhar
    (quadro limpo, ou um layout que TRANSFORMA o video e por isso vai pelo
    Remotion).
    """
    from app.video_layouts import normalizar

    nome = normalizar(layout)
    buf = np.zeros((h, w, 4), dtype=np.float32)

    if nome == "degrade":
        # linear-gradient(180deg, transparent 52%, rgba(0,0,0,.74) 100%)
        y = np.arange(h, dtype=np.float32) / max(1, h - 1)
        t = np.clip((y - 0.52) / 0.48, 0.0, 1.0)
        buf[..., 3] = (t * 0.74)[:, None]
        return (buf * 255.0 + 0.5).astype(np.uint8)

    if nome == "vinheta":
        # radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,.62))
        # O raio da elipse padrao do CSS vai ate o CANTO mais distante, por
        # isso a distancia normalizada divide por raiz de 2.
        yy = (np.arange(h, dtype=np.float32) - (h - 1) / 2) / ((h - 1) / 2)
        xx = (np.arange(w, dtype=np.float32) - (w - 1) / 2) / ((w - 1) / 2)
        d = np.sqrt(yy[:, None] ** 2 + xx[None, :] ** 2) / np.float32(2 ** 0.5)
        buf[..., 3] = np.clip((d - 0.45) / 0.55, 0.0, 1.0) * 0.62
        return (buf * 255.0 + 0.5).astype(np.uint8)

    if nome == "cinema":
        # duas tarjas pretas de 10% — o corte 2.39:1 dentro do 9:16
        faixa = int(round(h * 0.10))
        buf[:faixa, :, 3] = 1.0
        buf[h - faixa:, :, 3] = 1.0
        return (buf * 255.0 + 0.5).astype(np.uint8)

    if nome == "borda":
        # moldura fina na cor da marca, 26px para dentro, 6px de traco
        from PIL import Image as _I, ImageDraw as _D

        m = _I.new("L", (w, h), 0)
        _D.Draw(m).rounded_rectangle(
            [26, 26, w - 27, h - 27], radius=28, outline=255, width=6)
        cor = _cor_hex(accent)
        buf[..., :3] = cor
        buf[..., 3] = np.asarray(m, dtype=np.float32) / 255.0
        return (buf * 255.0 + 0.5).astype(np.uint8)

    return None


# ------------------------------------------------------- passada única ------
def _grafo_audio(idx_voz: int, idx_sfx: int | None, idx_trilha: int | None,
                 trilha_volume: float, duration_sec: float,
                 fade_out_at: float) -> list[str]:
    """O grafo de áudio do compose (overlay_compose._mix_audio_graph), com os
    índices de entrada parametrizados — aqui o vídeo vem por cano e os índices
    dos arquivos de áudio mudam de posição."""
    a_fmt = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
    a_len = f"{a_fmt},atrim=0:{duration_sec:.6f},asetpts=PTS-STARTPTS"
    parts = [f"[{idx_voz}:a]{a_len}[voice]"]
    mix_in = ["[voice]"]
    if idx_sfx is not None:
        parts.append(f"[{idx_sfx}:a]{a_len}[sfx]")
        mix_in.append("[sfx]")
    if idx_trilha is not None:
        parts.append(
            f"[{idx_trilha}:a]volume={trilha_volume:.4f},"
            f"afade=t=in:st=0:d=0.4,afade=t=out:st={fade_out_at:.3f}:d=1.5,"
            f"{a_len}[music]")
        mix_in.append("[music]")
    if len(mix_in) == 1:
        parts.append("[voice]anull[pre]")
    else:
        parts.append(
            f"{''.join(mix_in)}amix=inputs={len(mix_in)}:duration=first:"
            f"dropout_transition=0:normalize=0[pre]")
    return parts


def render_final_uma_passada(
    public: Path, edit_data: dict[str, Any], *,
    cut: Path, dest: Path, frames: int, fps: float,
    width: int = 1080, height: int = 1920,
    trilha: Path | None = None, trilha_volume: float = 0.12,
    progresso=None,
) -> dict[str, Any]:
    """Desenha, compõe e encoda numa passada — sem overlay.mov intermediário.

    Voz + SFX + trilha e o loudnorm em 2 passadas são os MESMOS do compose
    (funções importadas de overlay_compose); a diferença é que o vídeo do
    overlay chega por cano, quadro a quadro, em vez de virar um arquivo de
    150 MB que seria lido de volta logo em seguida.

    Levanta em qualquer problema; o caller cai no caminho de duas etapas.
    """
    from app.overlay_compose import (
        LOUDNORM_I,
        LOUDNORM_LRA,
        LOUDNORM_TP,
        _loudnorm_filter,
        count_frames,
        measure_loudnorm,
    )
    from app.render_engine import encoder_args

    t0 = time.perf_counter()
    r = Renderizador(public, edit_data, frames=frames, fps=fps,
                     width=width, height=height)
    sfx_wav = dest.with_name(dest.stem + "._sfx.wav")
    tem_sfx = r._gravar_sfx(sfx_wav)
    music = bool(trilha and trilha.exists())
    duration_sec = frames / fps
    fade_out_at = max(0.0, duration_sec - 1.5)

    # UMA receita para os DOIS defeitos de relogio do cut:
    #   - BURACO (quadros a MENOS que as posicoes): 2424 quadros em 2426
    #     posicoes — `fps=` preenche duplicando, `tpad` clona o que faltar
    #     no fim.
    #   - EXCESSO (quadros a MAIS que o relogio): 1655 quadros em 68,83s
    #     (job real de 24/08 22:11) — o ramo antigo fazia `trim` ANTES do
    #     `fps=`, e o `fps=` reamostrava pelo relogio DEPOIS, derrubando 3
    #     quadros: saia 1651!=1654 e o job caia para o Remotion completo
    #     (568s em vez de ~100s).
    # A ordem fps -> tpad -> trim normaliza o relogio primeiro e corta por
    # ultimo, entao a contagem sai EXATA nos dois sentidos — provado no
    # cut real: antigo 1651, novo 1654/1654.
    _sp = f"fps={fps:g},setpts=PTS-STARTPTS"
    cut_v = (f"[0:v]{_sp},tpad=stop_mode=clone:stop={frames},"
             f"trim=end_frame={frames}[cutv]")
    cut_frames = count_frames(cut)  # telemetria: quantos o cut trouxe

    inputs = ["-i", str(cut)]
    idx_sfx = idx_trilha = None
    prox = 1
    if tem_sfx:
        idx_sfx = prox
        inputs += ["-i", str(sfx_wav)]
        prox += 1
    if music:
        idx_trilha = prox
        inputs += ["-i", str(trilha)]
        prox += 1
    idx_pipe = prox
    inputs += ["-f", "rawvideo", "-pix_fmt", "rgba",
               "-s", f"{width}x{height}", "-r", f"{fps:g}", "-i", "-"]

    vid = (
        f"{cut_v};[{idx_pipe}:v]setpts=PTS-STARTPTS[ov];"
        "[cutv][ov]overlay=eof_action=pass:format=auto,"
        "format=yuv420p,"
        "scale=in_range=full:out_range=limited,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vid]"
    )
    fc = vid + ";" + ";".join(_grafo_audio(
        0, idx_sfx, idx_trilha, trilha_volume, duration_sec, fade_out_at))

    prenorm = dest.with_name(dest.stem + "._prenorm.mp4")
    primary, flags = encoder_args()

    def _passada(enc: str, extra: list[str]) -> bool:
        # `nonlocal` porque a linha "progresso = None" la embaixo (quando
        # quem escuta quebra) tornava `progresso` LOCAL desta funcao — e a
        # leitura, no primeiro quadro, batia em UnboundLocalError. Efeito:
        # com barra de progresso ligada a passada unica levantava SEMPRE, e
        # o render caia no caminho de duas etapas, que escreve um
        # overlay.mov de ~150 MB e le de volta. Aconteceu em 3 dos 174
        # projetos (os que passam callback, que sao os de "aplicar
        # alteracoes") e ficava so no timing.json, calado.
        nonlocal progresso
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
             *inputs, "-filter_complex", fc,
             "-map", "[vid]", "-map", "[pre]",
             "-c:v", enc, *extra,
             "-colorspace", "bt709", "-color_primaries", "bt709",
             "-color_trc", "bt709", "-color_range", "tv",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-frames:v", str(frames), "-t", f"{duration_sec:.6f}",
             "-movflags", "+faststart", str(prenorm)],
            stdin=subprocess.PIPE, **NOWIN)
        buf = (r.fundo.copy() if r.fundo is not None
               else np.zeros((r.h, r.w, 4), dtype=np.uint8))
        sujo = [0, 0, 0, 0]
        ass_ant, bytes_ant = None, None
        try:
            for f in range(frames):
                # Quantos quadros JA foram. O redesenho e 80,7% da espera
                # de um apply, e a barra so tinha isto no caminho de duas
                # etapas — que quase nunca roda. Cada 30 quadros: contar em
                # todos custaria uma escrita de arquivo por quadro.
                if progresso is not None and f % 30 == 0:
                    try:
                        progresso(f, frames)
                    except Exception:  # noqa: BLE001
                        progresso = None      # avisar nao pode custar o render
                ass = r._assinatura(f)
                if ass == ass_ant and bytes_ant is not None:
                    ff.stdin.write(bytes_ant)
                    continue
                ass_ant = ass
                if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
                    # limpar = voltar para a tinta do layout, nao para zero
                    buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = (
                        0 if r.fundo is None
                        else r.fundo[sujo[1]:sujo[3], sujo[0]:sujo[2]])
                sujo[:] = [0, 0, 0, 0]
                # `primeira` copia por cima em vez de mesclar — de graca
                # quando o buffer esta zerado, mas com camada de layout isso
                # APAGARIA a tinta dela onde a legenda passa (a vinheta saiu
                # com um retangulo claro em volta da headline, 29/08).
                primeira = r.fundo is None
                for leg in r.camadas:
                    if leg.inicio_f <= f <= leg.fim_f:
                        if leg.dim:
                            r._aplicar_dim(buf, sujo, leg.dim,
                                           f - leg.inicio_f, leg.dim_fade)
                            primeira = False
                        r.desenhar(leg, f - leg.inicio_f, buf, sujo,
                                   mesclar=not primeira)
                        primeira = False
                for at in r.flashes:
                    a = r._flash_quadro(at, f)
                    if a is not None:
                        r._aplicar_flash(buf, sujo, a)
                bytes_ant = buf.tobytes()
                ff.stdin.write(bytes_ant)
        except OSError:
            pass          # cano fechou: o returncode conta o que houve
        finally:
            try:
                ff.stdin.close()
            except OSError:
                pass
            ff.wait()
        return ff.returncode == 0 and prenorm.exists()

    ok = _passada(primary, list(flags))
    if not ok and primary != "libx264":
        print(f"UMA_PASSADA_ENCODER_FALLBACK {primary}->libx264", flush=True)
        ok = _passada("libx264", ["-preset", "veryfast", "-crf", "19"])
    if not ok:
        sfx_wav.unlink(missing_ok=True)
        raise RuntimeError("UMA_PASSADA_PRENORM")
    render_sec = time.perf_counter() - t0

    t1 = time.perf_counter()
    measured = measure_loudnorm(prenorm)
    tp_target = LOUDNORM_TP if measured else -1.5
    if measured:
        print(f"LOUDNORM_PASS1 I={measured['input_i']} TP={measured['input_tp']} "
              f"LRA={measured['input_lra']} offset={measured['target_offset']}",
              flush=True)
    else:
        print("LOUDNORM_PASS1_FAILED fallback=1pass TP=-1.5", flush=True)
    ln = _loudnorm_filter(measured, TP=tp_target)
    print(f"LOUDNORM_PASS2 target I={LOUDNORM_I} TP={tp_target} LRA={LOUDNORM_LRA}",
          flush=True)
    p2 = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-nostats", "-i", str(prenorm),
         "-c:v", "copy", "-af", ln,
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-frames:v", str(frames), "-t", f"{duration_sec:.6f}",
         "-movflags", "+faststart", str(dest)],
        capture_output=True, text=True, **NOWIN)
    prenorm.unlink(missing_ok=True)
    sfx_wav.unlink(missing_ok=True)
    if p2.returncode != 0 or not dest.exists():
        raise RuntimeError(f"UMA_PASSADA_LOUDNORM {(p2.stderr or '')[-300:]}")
    compose_sec = time.perf_counter() - t1
    print(f"UMA_PASSADA ok {frames}f render={render_sec:.1f}s "
          f"norm={compose_sec:.1f}s sfx={tem_sfx} trilha={music}", flush=True)
    return {
        "sfxFromOverlay": tem_sfx,
        "soundtrack": music,
        "out": str(dest),
        "expectedFrames": frames,
        "cutFrames": cut_frames,
        "canonicalSec": duration_sec,
        "renderSec": round(render_sec, 3),
        "normSec": round(compose_sec, 3),
        "loudnorm": {"pass1": measured, "targetI": LOUDNORM_I,
                     "targetTP": tp_target, "targetLRA": LOUDNORM_LRA},
    }
