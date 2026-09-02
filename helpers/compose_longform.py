# -*- coding: utf-8 -*-
"""Caminho RÁPIDO do vídeo longo (YouTube 16:9).

O template longform NÃO queima legenda (ela vai em .srt): o vídeo final é o
`cut.mp4` inteiro + lower thirds + cartões de capítulo + callouts + trilha.
No primeiro vídeo longo real (02/09, 11min35 em 1080p60) o Remotion passou
HORAS re-renderizando 42 mil quadros no Chrome por causa de 9,5 segundos de
arte. Aqui a arte é pintada com Pillow SÓ nos quadros das janelas dos
elementos (espelhando a matemática do template, como o motor próprio faz no
shortform) e UM ffmpeg compõe: decode do cut + overlay das janelas + NVENC
+ mixagem (voz + trilha com o envelope de fade + whoosh/pop dos elementos).

B-roll (cutaway que cobre o quadro inteiro, com Ken-Burns) fica de fora da
primeira versão: com ele o job segue no Remotion, com o motivo gravado.
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
FONTES = REPO / "assets" / "fonts-render"
MARGIN = 96  # o mesmo safe-margin 16:9 do template


# ---------------------------------------------------------------- easing
def _ease_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_out_back(t: float, s: float = 1.6) -> float:
    """Espelho de Easing.out(Easing.back(1.6)) do Remotion."""
    t = min(1.0, max(0.0, t))
    u = 1.0 - t
    return 1.0 - u * u * ((s + 1.0) * u - s)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _cor(hexstr: str) -> tuple[int, int, int]:
    h = (hexstr or "#33e0a3").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore
    except ValueError:
        return (51, 224, 163)


def _fonte(nome: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTES / nome), px)


def _sombra(base: Image.Image, forma: Image.Image, dx: int, dy: int,
            raio_css: float, alfa: float) -> None:
    """box/text-shadow do CSS: o raio é o DOBRO do sigma gaussiano."""
    mascara = forma.split()[3].filter(
        ImageFilter.GaussianBlur(raio_css / 2.0))
    preto = Image.new("RGBA", base.size, (0, 0, 0, 0))
    preto.paste((0, 0, 0, int(alfa * 255)), mask=mascara)
    des = Image.new("RGBA", base.size, (0, 0, 0, 0))
    des.paste(preto, (dx, dy))
    base.alpha_composite(des)


def _com_opacidade(camada: Image.Image, op: float) -> Image.Image:
    if op >= 0.999:
        return camada
    a = camada.split()[3].point(lambda v: int(v * _clamp(op, 0.0, 1.0)))
    camada.putalpha(a)
    return camada


# ------------------------------------------------------------- elementos
def _pintar_lower_third(tela: Image.Image, item: dict, f: int, total: int,
                        accent: tuple[int, int, int]) -> None:
    inn = _ease_out_cubic(f / 12.0)
    out = _clamp((total - f) / 10.0, 0.0, 1.0)
    op = min(inn, out)
    if op <= 0.004:
        return
    x_off = -40.0 * (1.0 - inn)

    nome = str(item.get("name") or "")
    titulo = str(item.get("title") or "")
    f_nome = _fonte("Poppins-Black.ttf", 40)
    f_tit = _fonte("Poppins-SemiBold.ttf", 24)

    med = ImageDraw.Draw(tela)
    w_nome = med.textlength(nome, font=f_nome)
    w_tit = med.textlength(titulo, font=f_tit) if titulo else 0
    box_w = int(math.ceil(max(w_nome, w_tit))) + 44          # padding 22+22
    alt_nome = int(round(40 * 1.05))
    box_h = 28 + alt_nome + ((4 + int(round(24 * 1.2))) if titulo else 0)

    W, H = tela.size
    x0 = int(round(MARGIN + x_off))
    y0 = H - MARGIN - box_h
    camada = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(camada)
    # sombra da caixa (0 12px 34px 0.4)
    forma = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    ImageDraw.Draw(forma).rounded_rectangle(
        [x0 + 24, y0, x0 + 24 + box_w, y0 + box_h], radius=12,
        fill=(0, 0, 0, 255))
    _sombra(camada, forma, 0, 12, 34, 0.4)
    # barra de destaque (8px, stretch) + caixa
    dr.rounded_rectangle([x0, y0, x0 + 8, y0 + box_h], radius=4, fill=accent)
    dr.rounded_rectangle([x0 + 24, y0, x0 + 24 + box_w, y0 + box_h],
                         radius=12, fill=(20, 22, 26, 219))
    tx = x0 + 24 + 22
    dr.text((tx, y0 + 14), nome, font=f_nome, fill=(255, 255, 255, 255))
    if titulo:
        dr.text((tx, y0 + 14 + alt_nome + 4), titulo, font=f_tit,
                fill=accent + (255,))
    tela.alpha_composite(_com_opacidade(camada, op))


def _pintar_capitulo(tela: Image.Image, item: dict, f: int, total: int,
                     accent: tuple[int, int, int]) -> None:
    inn = _ease_out_cubic(f / 14.0)
    out = _clamp((total - f) / 12.0, 0.0, 1.0)
    op = min(inn, out)
    if op <= 0.004:
        return
    y_off = 30.0 * (1.0 - inn)
    largura_linha = 120.0 * inn

    titulo = str(item.get("title") or "")
    f_tit = _fonte("Poppins-Black.ttf", 76)
    W, H = tela.size
    x0 = MARGIN
    base = H - (MARGIN + 40)                 # paddingBottom = MARGIN + 40
    alt = 6 + 16 + 76                        # linha + gap + título (lh 1)
    y0 = int(round(base - alt + y_off))

    camada = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(camada)
    if largura_linha >= 1:
        dr.rounded_rectangle([x0, y0, x0 + int(largura_linha), y0 + 6],
                             radius=3, fill=accent)
    # texto com sombra (0 4px 24px 0.6) e letterSpacing -1 (avanço por letra)
    texto = Image.new("RGBA", tela.size, (0, 0, 0, 0))
    dt = ImageDraw.Draw(texto)
    cx = float(x0)
    for ch in titulo:
        dt.text((cx, y0 + 6 + 16), ch, font=f_tit, fill=(255, 255, 255, 255))
        cx += dt.textlength(ch, font=f_tit) - 1.0
    _sombra(camada, texto, 0, 4, 24, 0.6)
    camada.alpha_composite(texto)
    tela.alpha_composite(_com_opacidade(camada, op))


def _pintar_callout(tela: Image.Image, item: dict, f: int, total: int,
                    accent: tuple[int, int, int]) -> None:
    pop = _clamp(_ease_out_back(f / 8.0), 0.01, 1.0)
    out = _clamp((total - f) / 8.0, 0.0, 1.0)
    op = min(_clamp(f / 5.0, 0.0, 1.0), out)
    if op <= 0.004:
        return
    texto = str(item.get("text") or "")
    f_txt = _fonte("Poppins-Black.ttf", 44)
    W, H = tela.size
    med = ImageDraw.Draw(tela)
    w_txt = int(math.ceil(med.textlength(texto, font=f_txt)))
    box_w, box_h = w_txt + 44, 44 + 20      # padding 22 / 10

    caixa = Image.new("RGBA", (box_w + 80, box_h + 80), (0, 0, 0, 0))
    dc = ImageDraw.Draw(caixa)
    forma = Image.new("RGBA", caixa.size, (0, 0, 0, 0))
    ImageDraw.Draw(forma).rounded_rectangle(
        [40, 40, 40 + box_w, 40 + box_h], radius=12, fill=(0, 0, 0, 255))
    _sombra(caixa, forma, 0, 10, 30, 0.4)
    dc.rounded_rectangle([40, 40, 40 + box_w, 40 + box_h], radius=12,
                         fill=accent)
    dc.text((40 + 22, 40 + 10), texto, font=f_txt, fill=(12, 13, 16, 255))
    if pop < 0.999:
        nw = max(1, int(round(caixa.width * pop)))
        nh = max(1, int(round(caixa.height * pop)))
        caixa = caixa.resize((nw, nh), Image.LANCZOS)
    caixa = _com_opacidade(caixa, op)
    cx = int(round(float(item.get("x", 0.5)) * W - caixa.width / 2))
    cy = int(round(float(item.get("y", 0.3)) * H - caixa.height / 2))
    tela.alpha_composite(caixa, (max(-caixa.width, cx), max(-caixa.height, cy)))


# ------------------------------------------------------------ orquestra
_DUR_PADRAO = {"chapters": 2.4, "lowerThirds": 4.0, "callouts": 3.0}
_PINTOR = {"chapters": _pintar_capitulo, "lowerThirds": _pintar_lower_third,
           "callouts": _pintar_callout}


def _eventos(ed: dict) -> list[dict]:
    evs: list[dict] = []
    for chave in ("chapters", "lowerThirds", "callouts"):
        for it in (ed.get(chave) or []):
            if not isinstance(it, dict):
                continue
            dur = float(it.get("dur") or _DUR_PADRAO[chave])
            evs.append({"tipo": chave, "item": it,
                        "start": max(0.0, float(it.get("start") or 0.0)),
                        "dur": max(0.1, dur)})
    return evs


def motivo_nao_elegivel(ed: dict) -> str | None:
    """None = o compose próprio dá conta; senão, o motivo (segue Remotion)."""
    if ed.get("broll"):
        return "b-roll (cutaway) ainda é do Remotion"
    if not (FONTES / "Poppins-Black.ttf").exists():
        return "fontes de render ausentes"
    try:
        float(ed.get("fps") or 0) > 0 and int(ed["width"]) and int(ed["height"])
    except (KeyError, TypeError, ValueError):
        return "edit-data sem geometria"
    return None


def _janelas(evs: list[dict], fps: float, total_f: int
             ) -> list[tuple[int, int]]:
    """Janelas de quadros a pintar (união dos elementos, mescladas)."""
    brutas = sorted(
        (int(math.floor(e["start"] * fps)),
         min(total_f, int(math.ceil((e["start"] + e["dur"]) * fps))))
        for e in evs)
    saida: list[tuple[int, int]] = []
    for a, b in brutas:
        if saida and a <= saida[-1][1]:
            saida[-1] = (saida[-1][0], max(saida[-1][1], b))
        else:
            saida.append((a, b))
    return [(a, b) for a, b in saida if b > a]


def _pintar_janela(evs: list[dict], fps: float, W: int, H: int,
                   accent: tuple[int, int, int], a: int, b: int,
                   pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for f_abs in range(a, b):
        tela = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for e in evs:
            ini = int(math.floor(e["start"] * fps))
            tot = int(round(e["dur"] * fps))
            if ini <= f_abs < ini + tot:
                _PINTOR[e["tipo"]](tela, e["item"], f_abs - ini, tot, accent)
        tela.save(pasta / f"{f_abs - a:06d}.png")


def _tem_nvenc() -> bool:
    try:
        p = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                           capture_output=True, text=True, timeout=20)
        return "h264_nvenc" in (p.stdout or "")
    except Exception:  # noqa: BLE001
        return False


def compor_longform(edit_dir: Path, public: Path, ed: dict,
                    destino: Path) -> dict:
    """Compõe o final.mp4 do longform sem Remotion. Levanta em falha."""
    fps = float(ed.get("fps") or 30.0)
    W, H = int(ed["width"]), int(ed["height"])
    dur = float(ed.get("durationSec") or 0.0)
    total_f = int(math.ceil(dur * fps))
    accent = _cor(str(ed.get("accent") or ""))
    cut = public / "cut.mp4"
    if not cut.exists():
        raise RuntimeError("cut.mp4 ausente no public/")

    evs = _eventos(ed)
    janelas = _janelas(evs, fps, total_f)
    quadros = sum(b - a for a, b in janelas)

    tmp = Path(tempfile.mkdtemp(prefix="lf-compose-",
                                dir=str(edit_dir)))
    try:
        # ---- vídeo: um input de PNGs por janela, overlay ancorado no tempo
        entradas: list[str] = ["-i", str(cut)]
        cadeia: list[str] = []
        atual = "[0:v]"
        for n, (a, b) in enumerate(janelas):
            pasta = tmp / f"win{n}"
            _pintar_janela(evs, fps, W, H, accent, a, b, pasta)
            entradas += ["-framerate", f"{fps}", "-start_number", "0",
                         "-i", str(pasta / "%06d.png")]
            idx = 1 + n
            s, e = a / fps, b / fps
            cadeia.append(
                f"[{idx}:v]format=rgba,setpts=PTS+{s:.6f}/TB[ov{n}];"
                f"{atual}[ov{n}]overlay=x=0:y=0:eof_action=pass"
                f":enable='between(t,{s:.6f},{e:.6f})'[v{n}]")
            atual = f"[v{n}]"
        cadeia.append(f"{atual}format=yuv420p[vout]")

        # ---- áudio: voz do cut + trilha com envelope + sfx dos elementos
        rotulos = ["[voz]"]
        cadeia.append("[0:a]anull[voz]")
        st = ed.get("soundtrack") or {}
        i_extra = 1 + len(janelas)
        if st.get("enabled") and (public / str(st.get("file") or "")).exists():
            vol = float(st.get("volume") or 0.1)
            fi, fo = 20.0 / fps, 40.0 / fps
            entradas += ["-i", str(public / str(st["file"]))]
            cadeia.append(
                f"[{i_extra}:a]volume={vol:.4f},afade=t=in:st=0:d={fi:.4f},"
                f"afade=t=out:st={max(0.0, dur - fo):.4f}:d={fo:.4f}[trilha]")
            rotulos.append("[trilha]")
            i_extra += 1
        # whoosh nos capítulos (0.08) e pop nos callouts (0.1), como o template
        for e in evs:
            nome, volume = (("whoosh.mp3", 0.08) if e["tipo"] == "chapters"
                            else ("pop.mp3", 0.10) if e["tipo"] == "callouts"
                            else (None, 0.0))
            sfx = public / "sfx" / (nome or "")
            if not nome or not sfx.exists():
                continue
            ms = int(round(e["start"] * 1000))
            entradas += ["-i", str(sfx)]
            cadeia.append(f"[{i_extra}:a]volume={volume},adelay={ms}|{ms}"
                          f"[sf{i_extra}]")
            rotulos.append(f"[sf{i_extra}]")
            i_extra += 1
        if len(rotulos) > 1:
            cadeia.append("".join(rotulos)
                          + f"amix=inputs={len(rotulos)}:normalize=0:"
                          "duration=first[aout]")
            mapa_a = "[aout]"
        else:
            mapa_a = "[voz]"

        def _rodar(codec: list[str]) -> subprocess.CompletedProcess:
            cmd = (["ffmpeg", "-y", *entradas,
                    "-filter_complex", ";".join(cadeia),
                    "-map", "[vout]", "-map", mapa_a, *codec,
                    "-colorspace", "bt709", "-color_primaries", "bt709",
                    "-color_trc", "bt709", "-color_range", "tv",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{dur:.6f}", "-movflags", "+faststart",
                    str(destino)])
            return subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")

        engine = "nvenc" if _tem_nvenc() else "x264"
        if engine == "nvenc":
            p = _rodar(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19",
                        "-b:v", "0"])
            if p.returncode != 0:
                engine = "x264"
        if engine == "x264":
            p = _rodar(["-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "18"])
        if p.returncode != 0 or not destino.exists():
            raise RuntimeError(
                f"ffmpeg do compose longform falhou: {(p.stderr or '')[-800:]}")
        return {"engine": engine, "quadrosPintados": quadros,
                "janelas": len(janelas)}
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
