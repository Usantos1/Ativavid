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

O que este módulo NÃO desenha (o gate `motivo_nao_suportado` derruba para o
Remotion): outros estilos de legenda/headline, contador de lista, emoji,
pergunta→resposta, logo no cartão, fonte de marca, b-roll/inserts.

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
}
FONT_WGHT = {2: 900}

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
TRACO_COR = "#39E508"
TRACO_SOMBRA = (0, 3, 8, 0.45)
TRACO_CAIXA = (-0.10, -0.22, 1.20, 1.50)   # esq, topo, larg, alt (fração)

# HL_STYLES.realce (Main.tsx)
REALCE = {"cap": 86, "safe_w": 830, "lh": 1.04, "top": 300}
HL_MIN = 40

# CutFlashes (CustomGraphics.tsx)
VIDEO_LAG = 1
FLASH_LEAD, FLASH_LEN = 2, 7

# SFX (StackedCaptions/Main)
CLICK_VOL = 0.55
STACK_CLICK_VOL = min(0.28, CLICK_VOL * 0.5)
SCRATCH_VOL = 0.28
WHOOSH_VOL = 0.1


# ---------------------------------------------------------------- suporte ----
def motivo_nao_suportado(edit_data: dict[str, Any], public: Path) -> str | None:
    """None = o renderizador próprio cobre este projeto; senão o motivo."""
    if (os.environ.get("ATIVAVID_RENDER_PROPRIO") or "").strip() == "0":
        return "desligado por ATIVAVID_RENDER_PROPRIO=0"
    caps = edit_data.get("captions") or {}
    estilo = caps.get("style") or "stacked"
    permitidos = {"stacked"}
    if os.environ.get("ATIVAVID_PROPRIO_IMPACTO") == "1":
        # portado, aguardando validacao visual — liga por env para testar
        permitidos.add("impacto")
    if os.environ.get("ATIVAVID_PROPRIO_SCATTER") == "1":
        permitidos.add("scatter")
    if estilo not in permitidos:
        return f"estilo de legenda '{caps.get('style')}'"
    if caps.get("fontFamily"):
        return "fonte de marca nas legendas"
    hook = edit_data.get("hook") or {}
    if hook.get("enabled"):
        if (hook.get("style") or "outline") != "realce":
            return f"estilo de headline '{hook.get('style')}'"
        if hook.get("answerLines"):
            return "headline pergunta-resposta"
        if hook.get("fontFamily"):
            return "fonte de marca na headline"
        if hook.get("logo") or hook.get("sign"):
            return "logo/assinatura na headline"
    ec = edit_data.get("endCard") or {}
    if ec.get("enabled") and ec.get("logo"):
        return "logo no cartao final"
    els = edit_data.get("elements") or {}
    if els.get("listCounter"):
        return "contador de lista"
    if els.get("emojiCaptions"):
        return "emoji nas legendas"
    if edit_data.get("inserts"):
        return "inserts/b-roll"
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


def _opacidade(p: Palavra, fl: float) -> float:
    if p.janela is not None:
        ini, fim = p.janela
        return 1.0 if ini <= fl < fim else 0.0
    if fl <= p.inicio_f:
        return 0.0
    t = min(1.0, (fl - p.inicio_f) / max(1, p.enter))
    return 1 - (1 - t) ** 3


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
        self.base_y = round(self.h * float(caps.get("stackedOffsetY") or 0.156))
        accent = caps.get("emphasisAccent") or "#ff5200"
        self.font_file = dict(FONT_FILE)
        self.font_file[2] = (FONT_FILE[2][0], accent)
        self.cor_traco = caps.get("circleAccent") or TRACO_COR
        sfx = caps.get("sfx") or {}
        self.sfx_on = sfx.get("enabled") is not False
        self.click_vol = float(sfx.get("clickVolume") or CLICK_VOL)
        self.scratch_vol = float(sfx.get("scratchVolume") or SCRATCH_VOL)
        self.stack_vol = float(sfx.get("stackClickVolume")
                               or min(0.28, self.click_vol * 0.5))
        self._fontes: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        d = json.loads((public / "caption-cues.json").read_text(encoding="utf-8-sig")) \
            if (public / "caption-cues.json").exists() else []
        self.cues = d if isinstance(d, list) else (d.get("cues") or [])
        self.camadas: list[Camada] = []
        self.eventos_sfx: list[tuple[str, float, float]] = []   # (arquivo, seg, volume)
        self._montar_tudo()

    # ------------------------------------------------------------ fontes ----
    def fonte(self, idx: int, tam: int,
              peso: int | None = None) -> ImageFont.FreeTypeFont:
        chave = (self.font_file[idx][0], tam, peso)
        if chave not in self._fontes:
            f = ImageFont.truetype(str(FONTES / self.font_file[idx][0]), tam)
            eixo = peso if peso is not None else FONT_WGHT.get(idx)
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

    def _mascara(self, f: ImageFont.FreeTypeFont, texto: str,
                 ls: float = LETTER_SPACING) -> np.ndarray:
        larg = int(f.getlength(texto) + ls * len(texto)) + 8
        asc, desc = f.getmetrics()
        img = Image.new("L", (max(1, larg), asc + desc + 8), 0)
        d = ImageDraw.Draw(img)
        x = 0.0
        for i, ch in enumerate(texto):
            d.text((x, 0), ch, font=f, fill=255)
            x = f.getlength(texto[: i + 1]) + ls * (i + 1)
        return np.asarray(img, dtype=np.float32) / 255.0

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

    def _sombra_de(self, mask: np.ndarray, especs) -> np.ndarray:
        out = np.zeros_like(mask)
        for dx, dy, blur, sa in especs:
            b = np.asarray(Image.fromarray((mask * 255).astype(np.uint8))
                           .filter(ImageFilter.GaussianBlur(blur * BLUR_K)),
                           dtype=np.float32) / 255.0
            desl = np.zeros_like(b)
            desl[max(0, dy):, max(0, dx):] = b[:b.shape[0] - max(0, dy),
                                               :b.shape[1] - max(0, dx)]
            out = np.maximum(out, desl * sa)
        return out

    # ----------------------------------------------------------- montagem ----
    def _montar_tudo(self) -> None:
        hook = self.ed.get("hook") or {}
        if hook.get("enabled"):
            self.camadas.append(self._montar_headline(hook))
            if self.sfx_on:
                self.eventos_sfx.append(("whoosh.mp3", 0.0, WHOOSH_VOL))
        estilo = (self.ed.get("captions") or {}).get("style") or "stacked"
        if estilo == "impacto":
            self.camadas.extend(self._montar_impacto())
            self.cues = []
        elif estilo == "scatter":
            self.camadas.extend(self._montar_scatter())
            self.cues = []
        for cue in self.cues:
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
                    "caption-click.mp3", t0,
                    self.click_vol if solo else self.stack_vol))
                if preset == "SOLO_OUTLINE":
                    self.eventos_sfx.append((
                        "caption-scratch.mp3", t0 + 2 / self.fps, self.scratch_vol))
        self.camadas.sort(key=lambda l: l.inicio_f)
        ec = self.ed.get("endCard") or {}
        if ec.get("enabled"):
            self.camadas.append(self._montar_endcard(ec, hook.get("accent")))
        self.flashes = [float(t["at"]) for t in (self.ed.get("transitions") or [])
                        if t.get("type") == "flash"]

    def _tempos_cue(self, cue: dict) -> tuple[int, int, float, int, float]:
        ini_f = int(cue["startMs"] / 1000 * self.fps)
        fim_f = int(cue["endMs"] / 1000 * self.fps)
        dur = (cue["endMs"] - cue["startMs"]) / 1000 * self.fps
        enter = max(3, min(8, int(dur * 0.45)))
        exit_ = max(2, min(7, int(dur * 0.35)))
        ultima = max((w["fromMs"] - cue["startMs"]) / 1000 * self.fps
                     for ln in cue["lines"] for w in ln)
        saida_f = max(dur - exit_, min(ultima + enter, dur - 2))
        return ini_f, fim_f, dur, enter, saida_f

    def _nova_camada(self, cue: dict) -> tuple[Camada, int, float]:
        ini_f, fim_f, dur, enter, saida_f = self._tempos_cue(cue)
        leg = Camada(ini_f, fim_f)
        leg.dur_f = dur
        leg.exit_abrupto = cue.get("exit") == "abrupt"
        leg.saida_f = saida_f
        return leg, enter, dur

    def _palavra_texto(self, leg: Camada, f, texto: str, ls: float, x0: int,
                       topo_caixa: float, alt_caixa: float, y_base: int,
                       cor_fixa: str | None, inicio_f: float, enter: int,
                       especs=SHADOW) -> None:
        m = self._mascara(f, texto, ls)
        h_m, w_m = m.shape
        folga = 24
        pad_m = np.zeros((h_m + 2 * folga, w_m + 2 * folga), dtype=np.float32)
        pad_m[folga:folga + h_m, folga:folga + w_m] = m
        sombra = self._sombra_de(pad_m, especs)
        if cor_fixa:
            rgb = np.broadcast_to(self._cor(cor_fixa), (*pad_m.shape, 3)).copy()
        else:
            col = self._gradiente(int(round(alt_caixa)))
            off = int(round(y_base - folga - topo_caixa))
            idxs = np.clip(np.arange(pad_m.shape[0]) + off, 0, len(col) - 1)
            rgb = np.repeat(col[idxs][:, None, None], 3, axis=2) * np.ones(
                (1, pad_m.shape[1], 1), dtype=np.float32)
        leg.palavras.append(Palavra(x0 - folga, y_base - folga, rgb, pad_m,
                                    sombra, inicio_f=inicio_f, enter=enter))

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
            f = self.fonte(ln["idx"], ln["size"])
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
                self._palavra_texto(
                    leg, f, w["text"], LETTER_SPACING, int(round(x + pad)),
                    y, alturas[li], int(round(base)),
                    self.font_file[ln["idx"]][1],
                    (w["fromMs"] - cue["startMs"]) / 1000 * self.fps, enter, especs)
                x += wl
            y += alturas[li]
        return leg

    def _montar_solo_big(self, cue: dict) -> Camada:
        leg, enter, dur = self._nova_camada(cue)
        w = cue["lines"][0][0]
        tam = self.fit_font(w["text"], 150, self.avail / self.scale, 0.6)
        f = self.fonte(0, tam)
        ls = -3.0
        pad = 0.14 * tam
        larg = f.getlength(w["text"]) + ls * len(w["text"]) + 2 * pad
        alt = tam * LINE_HEIGHT
        x_c = (self.w - larg) / 2
        y_c = (self.h / 2 + self.base_y) - alt / 2
        asc, desc = f.getmetrics()
        self._palavra_texto(
            leg, f, w["text"], ls, int(round(x_c + pad)), y_c, alt,
            int(round(y_c + (alt - (asc + desc)) / 2)), None,
            (w["fromMs"] - cue["startMs"]) / 1000 * self.fps, enter)
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
        f = self.fonte(4, tam)
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
            int(round(y_c + (alt_c - (asc + desc)) / 2)), None, local, enter)

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
            img = Image.new("L", (lt, at), 0)
            if len(sub) >= 2:
                dr = ImageDraw.Draw(img)
                desl = [(x - tx0, y - ty0) for x, y in sub]
                dr.line(desl, fill=255, width=TRACO_PX, joint="curve")
                r = TRACO_PX / 2
                for x, y in (desl[0], desl[-1]):
                    dr.ellipse([x - r, y - r, x + r, y + r], fill=255)
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

    # ----- headline `realce` -------------------------------------------------
    def _larg_hl(self, texto: str, tam: int) -> float:
        f = self.fonte(4, tam)
        return f.getlength(texto) - 1.0 * max(0, len(texto) - 1)

    def _montar_headline(self, hook: dict) -> Camada:
        fim = int(float(hook.get("endSec") or 4.0) * self.fps)
        accent = hook.get("accent") or "#ff5200"
        texto = (hook.get("text") or " ".join(hook.get("lines") or [])).strip()
        palavras = texto.split()
        if len(palavras) < 2:
            linhas = [texto] if texto else []
        else:
            melhor, dif = (palavras[0], " ".join(palavras[1:])), float("inf")
            for i in range(1, len(palavras)):
                a, b = " ".join(palavras[:i]), " ".join(palavras[i:])
                d = abs(self._larg_hl(a, 100) - self._larg_hl(b, 100))
                if d < dif:
                    melhor, dif = (a, b), d
            linhas = [l for l in melhor if l]
        mais = lambda t: max(*(self._larg_hl(l, t) for l in linhas), 1.0)
        tam = int(REALCE["safe_w"] / mais(100) * 100)
        tam = max(HL_MIN, min(REALCE["cap"], int(REALCE["safe_w"] / mais(tam) * tam)))
        f = self.fonte(4, tam)

        leg = Camada(0, fim)
        leg.dur_f = fim
        leg.saida_f = fim - 9
        leg.exit_fade = True
        cor_b = self._cor(accent)
        y = float(REALCE["top"])
        for texto_l in linhas:
            larg_t = self._larg_hl(texto_l, tam)
            pad_x, pad_t, pad_b = 0.3 * tam, 0.08 * tam, 0.16 * tam
            asc, desc = f.getmetrics()
            larg_b = int(larg_t + 2 * pad_x)
            # caixa CSS = line-height + paddings, NAO ascent+descent (medido:
            # ascent+descent dava bloco 13% mais alto que producao)
            alt_b = int(REALCE["lh"] * tam + pad_t + pad_b)
            folga = 40
            L, A = larg_b + 2 * folga, alt_b + 2 * folga
            bloco = Image.new("L", (L, A), 0)
            ImageDraw.Draw(bloco).rounded_rectangle(
                [folga, folga, folga + larg_b, folga + alt_b], radius=12, fill=255)
            a_bloco = np.asarray(bloco, dtype=np.float32) / 255.0
            m = self._mascara(f, texto_l, -1.0)
            h_m, w_m = m.shape
            tx = folga + int(pad_x)
            ty = folga + int(pad_t + (REALCE["lh"] * tam - (asc + desc)) / 2)
            t_a = np.zeros_like(a_bloco)
            t_a[ty:ty + h_m, tx:tx + w_m] = m[:A - ty, :L - tx]
            rgb = np.broadcast_to(cor_b, (A, L, 3)).copy()
            rgb = rgb * (1 - t_a[..., None]) + 255.0 * t_a[..., None]
            alpha = np.maximum(a_bloco, t_a)
            b = np.asarray(Image.fromarray((a_bloco * 255).astype(np.uint8))
                           .filter(ImageFilter.GaussianBlur(28 * 0.5)),
                           dtype=np.float32) / 255.0
            sombra = np.zeros_like(b)
            sombra[10:, :] = b[:-10, :] * 0.45
            leg.palavras.append(Palavra(
                int((self.w - larg_b) / 2) - folga, int(y) - folga,
                rgb, alpha, sombra, inicio_f=0, enter=8, sobe=24.0))
            y += alt_b + 10
        return leg

    # ----- cartão final ------------------------------------------------------
    def _montar_endcard(self, ec: dict, hook_accent: str | None) -> Camada:
        dur = int(round(float(ec.get("lastSec") or 2.5) * self.fps))
        ini = self.frames - dur
        accent = ec.get("accent") or hook_accent or "#ff5200"
        linhas = [l for l in (ec.get("lines") or []) if l][:2]
        fade = min(round(0.35 * self.fps), max(1, dur // 2))
        leg = Camada(ini, self.frames + 10)
        leg.dur_f = dur + 20
        leg.saida_f = 1e9
        leg.dim = float(ec.get("dim") if ec.get("dim") is not None else 0.82)
        leg.dim_fade = fade
        base = round(self.w * 0.058)
        safe_w = self.w * 0.70
        escala = [1.0, 0.62]
        ajuste = 1.0
        for i, t in enumerate(linhas):
            f = self.fonte(4 if i == 0 else 3, int(base * escala[i]))
            wl = f.getlength(t) - 1.0 * max(0, len(t) - 1)
            if wl > safe_w:
                ajuste = min(ajuste, safe_w / wl)
        tam = max(28, round(base * ajuste))
        mascaras = []
        for i, t in enumerate(linhas):
            f = self.fonte(4 if i == 0 else 3, int(tam * escala[i]))
            mascaras.append((self._mascara(f, t, -1.0), i))
        gap = round(tam * 0.34)
        total = sum(m.shape[0] for m, _ in mascaras) + gap * max(0, len(mascaras) - 1)
        y = (self.h - total) / 2.0
        for m, i in mascaras:
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
        bottom = float(caps_cfg.get("paddingBottom") or 430)
        cor_caixa = caps_cfg.get("emphasisAccent") or "#ffd400"
        cor_tinta = self._tinta_na_caixa(cor_caixa)
        f = self.fonte(4, tam)

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
                        self._palavra_texto(
                            leg, f, texto, 0.0, int(round(x)), y_base,
                            alt_linha, y_texto, "#ffffff", -1, 1,
                            especs=[(0, 4, 18, 0.6)])
                        leg.palavras[-1].sobe = 0.0
                    else:
                        lw = larg_pal(w)
                        cw = int(lw + 2 * pad)
                        ch = int(asc + desc + pad * 0.35 + pad * 0.5)
                        for est in range(POP + 1):
                            t = min(1.0, est / POP)
                            esc = 0.7 + 0.3 * self._ease_back(t)
                            ew, eh = max(2, int(cw * esc)), max(2, int(ch * esc))
                            img = Image.new("L", (ew + 64, eh + 64), 0)
                            ImageDraw.Draw(img).rounded_rectangle(
                                [32, 32, 32 + ew, 32 + eh],
                                radius=max(2, int(raio * esc)), fill=255)
                            a_caixa = np.asarray(img, dtype=np.float32) / 255.0
                            fe = self.fonte(4, max(8, int(tam * esc)))
                            m = self._mascara(fe, texto, 0.0)
                            t_a = np.zeros_like(a_caixa)
                            tx = 32 + int(pad * esc)
                            ty = 32 + int(pad * 0.35 * esc)
                            hm = min(m.shape[0], t_a.shape[0] - ty)
                            wm = min(m.shape[1], t_a.shape[1] - tx)
                            t_a[ty:ty + hm, tx:tx + wm] = m[:hm, :wm]
                            cor_c = self._cor(cor_caixa)
                            cor_t = self._cor(cor_tinta)
                            rgb = np.broadcast_to(cor_c, (*a_caixa.shape, 3)).copy()
                            rgb = rgb * (1 - t_a[..., None]) + cor_t * t_a[..., None]
                            alpha = np.maximum(a_caixa, t_a)
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
        OFFSET_Y = float(caps_cfg.get("scatterOffsetY") or 0.72)
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
                    italico = eh_hi and self._hash_det(li * 7 + i) > 0.65
                    f = self.fonte(6 if italico else 5, tam_i, peso)
                    m = self._mascara(f, limpar(w["text"]), 0.0)
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
        desloc = int(round(p.sobe * (1.0 - op))) if p.janela is None else 0
        py, px = p.y0 - y0 + desloc, p.x0 - x0
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
            ax0 = min(max(0, p.x0 - x0) for p, _ in animando)
            ay0 = min(max(0, p.y0 - y0 - int(p.sobe)) for p, _ in animando)
            ax1 = max(min(x1 - x0, p.x0 - x0 + p.alpha.shape[1]) for p, _ in animando)
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
        desloc = int(round(p.sobe * (1.0 - op))) if p.janela is None else 0
        py, px = p.y0 - abs_y0 + desloc, p.x0 - abs_x0
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
    def _aplicar_dim(self, buf, sujo, dim, fl, fade):
        t = min(1.0, max(0.0, fl / max(1, fade)))
        a = dim * (1 - (1 - t) ** 3)
        if a <= 0.004:
            return
        alpha = buf[..., 3].astype(np.float32) / 255.0
        buf[..., :3] = (buf[..., :3] * (1.0 - a)).astype(np.uint8)
        buf[..., 3] = ((alpha + a * (1.0 - alpha)) * 255.0).astype(np.uint8)
        sujo[:] = [0, 0, buf.shape[1], buf.shape[0]]

    _flash_cache: dict[int, np.ndarray]

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
            img.paste(barra, (int(x), int(-0.3 * self.h)), barra)
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

    def _gravar_video(self, alvo: Path) -> None:
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
        buf = np.zeros((self.h, self.w, 4), dtype=np.uint8)
        sujo = [0, 0, 0, 0]
        ass_ant, bytes_ant = None, None
        try:
            for f in range(self.frames):
                ass = self._assinatura(f)
                if ass == ass_ant and bytes_ant is not None:
                    ff.stdin.write(bytes_ant)
                    continue
                ass_ant = ass
                if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
                    buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
                sujo[:] = [0, 0, 0, 0]
                primeira = True
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

    def render(self, out: Path) -> Path:
        """Escreve o overlay.mov (vídeo com alpha + SFX)."""
        out.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        so_video = out.with_name(out.stem + "._video.mov")
        self._gravar_video(so_video)
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
                           out: Path) -> Path:
    """Entrada única: monta e renderiza. Levanta em qualquer problema —
    o caller decide o fallback."""
    r = Renderizador(public, edit_data, frames=frames, fps=fps,
                     width=width, height=height)
    return r.render(out)


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

    cut_frames = count_frames(cut)
    if cut_frames and cut_frames < frames:
        cut_v = (f"[0:v]tpad=stop_mode=clone:stop={frames - cut_frames},"
                 "setpts=PTS-STARTPTS[cutv]")
    else:
        cut_v = f"[0:v]trim=end_frame={frames},setpts=PTS-STARTPTS[cutv]"

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
        buf = np.zeros((r.h, r.w, 4), dtype=np.uint8)
        sujo = [0, 0, 0, 0]
        ass_ant, bytes_ant = None, None
        try:
            for f in range(frames):
                ass = r._assinatura(f)
                if ass == ass_ant and bytes_ant is not None:
                    ff.stdin.write(bytes_ant)
                    continue
                ass_ant = ass
                if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
                    buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
                sujo[:] = [0, 0, 0, 0]
                primeira = True
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
