# -*- coding: utf-8 -*-
"""Uma passada com CANO DE FAIXA: transmite so o retangulo onde ha grafico.

A tela inteira sao 8,3 MB por quadro no cano; a faixa que de fato tem texto
(headline + legendas + texto do cartao) tem ~3 MB. Dim e flash precisam de
tela cheia — mas ambos sao gradientes SUAVES: vao num segundo fluxo de
270x480 (0,5 MB) que o ffmpeg escala para 1080x1920. Efeito visualmente
identico; upscale de gradiente nao inventa nada.

Fluxo: [0] cut  [1] faixa RGBA (pipe)  [2] efeitos 270x480 (arquivo pequeno,
pre-rendidos — sao 28 quadros de flash + 75 de dim, o resto e transparente).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"E:\Code\ativa-vid\tools\render_benchmark")
import numpy as np  # noqa: E402

import phase20_render_proprio as R  # noqa: E402
import phase22_recorte as RC  # noqa: E402
import phase23_video_inteiro as V  # noqa: E402
import phase24_elementos as E  # noqa: E402

S = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}
FX_W, FX_H = 272, 480          # multiplo de 16 para o encoder

pub = S / "prova_real" / "remotion" / "public"
cut = Path(r"E:\ATIVAVID\Projetos\20260816-002530_IMG_3912_9d41f4134e\edit\cut.mp4")

ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8-sig"))
R.usar_config(ed)
cor = ((ed.get("captions") or {}).get("circleAccent")) or RC.COR_PADRAO
d = json.loads((pub / "caption-cues.json").read_text(encoding="utf-8-sig"))
cues = d if isinstance(d, list) else d.get("cues")

camadas = []
hook = ed.get("hook") or {}
if hook.get("enabled"):
    camadas.append(E.montar_headline(hook, R.FPS))
camadas.extend(sorted((V.montar_cue(c, cor) for c in cues), key=lambda l: l.inicio_f))
ec = ed.get("endCard") or {}
dim_leg = None
if ec.get("enabled"):
    dim_leg = E.montar_endcard(ec, hook.get("accent"), 851, R.FPS)
    camadas.append(dim_leg)
flashes = [float(t["at"]) for t in (ed.get("transitions") or []) if t.get("type") == "flash"]

# ---- faixa: uniao das caixas de todas as camadas (texto), par e recortada --
x0 = max(0, min(R._caixa_leg(l)[0] for l in camadas) - 8)
y0 = max(0, min(R._caixa_leg(l)[1] for l in camadas) - 56)   # folga p/ sobe 46
x1 = min(R.W, max(R._caixa_leg(l)[2] for l in camadas) + 8)
y1 = min(R.H, max(R._caixa_leg(l)[3] for l in camadas) + 8)
if (x1 - x0) % 2:
    x1 -= 1
if (y1 - y0) % 2:
    y1 -= 1
BW, BH = x1 - x0, y1 - y0

# ---- passo 1: fluxo de efeitos 272x480 (dim + flash), pre-rendido ----------
dim_path = S / "fx_dim.mov"
flash_path = S / "fx_flash.mov"


def render_efeitos() -> float:
    """Dois fluxos 272x480: o DIM (fica SOB a faixa — na producao o texto do
    cartao nao e escurecido) e o FLASH (fica sobre tudo)."""
    t0 = time.perf_counter()
    from PIL import Image

    ff_d = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{FX_W}x{FX_H}", "-r", "30", "-i", "-",
         "-c:v", "qtrle", str(dim_path)], stdin=subprocess.PIPE, **NOWIN)
    ff_f = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{FX_W}x{FX_H}", "-r", "30", "-i", "-",
         "-c:v", "qtrle", str(flash_path)], stdin=subprocess.PIPE, **NOWIN)
    vazio = np.zeros((FX_H, FX_W, 4), dtype=np.uint8)
    for f in range(851):
        qd = vazio
        if dim_leg is not None and dim_leg.inicio_f <= f:
            fl = f - dim_leg.inicio_f
            t = min(1.0, max(0.0, fl / max(1, dim_leg.dim_fade)))
            a = dim_leg.dim * (1 - (1 - t) ** 3)
            if a > 0.004:
                qd = np.zeros((FX_H, FX_W, 4), dtype=np.uint8)
                qd[..., 3] = int(a * 255)
        ff_d.stdin.write(qd.tobytes())
        qf = vazio
        for at in flashes:
            m = E.flash_quadro(at, R.FPS, f)
            if m is not None:
                peq = np.asarray(Image.fromarray((m * 255).astype(np.uint8), "L")
                                 .resize((FX_W, FX_H), Image.BILINEAR), dtype=np.uint8)
                qf = np.zeros((FX_H, FX_W, 4), dtype=np.uint8)
                qf[..., :3] = 255
                qf[..., 3] = peq
        ff_f.stdin.write(qf.tobytes())
    ff_d.stdin.close(); ff_f.stdin.close()
    ff_d.wait(); ff_f.wait()
    return time.perf_counter() - t0


# ---- passo 2: passada principal com cano de faixa --------------------------
def uma_passada(saida: Path) -> tuple[float, int]:
    en_dim = dim_leg.inicio_f if dim_leg is not None else 999999
    janelas = []
    for at in flashes:
        c = round(at * R.FPS) + E.VIDEO_LAG
        janelas.append(f"between(n,{c - E.FLASH_LEAD},{c - E.FLASH_LEAD + E.FLASH_LEN - 1})")
    en_flash = "+".join(janelas) or "0"
    t0 = time.perf_counter()
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-i", str(cut),
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{BW}x{BH}", "-r", "30", "-i", "-",
         "-i", str(dim_path), "-i", str(flash_path),
         "-filter_complex",
         # ordem: video -> dim -> faixa (texto por cima do dim) -> flash.
         # `enable` limita cada overlay de tela cheia a sua janela — sem isso
         # os dois filtros processavam 1080x1920 nos 851 quadros e a passada
         # DOBROU (25s -> 47s).
         f"[2:v]scale={R.W}:{R.H}[dim];"
         f"[3:v]scale={R.W}:{R.H}[fla];"
         f"[0:v][dim]overlay=eof_action=pass:format=auto:"
         f"enable='gte(n,{en_dim})'[v0];"
         f"[v0][1:v]overlay=x={x0}:y={y0}:eof_action=endall:format=auto[v1];"
         f"[v1][fla]overlay=eof_action=pass:format=auto:"
         f"enable='{en_flash}',format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a?", "-c:a", "copy", "-frames:v", "851",
         "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", str(saida)],
        stdin=subprocess.PIPE, **NOWIN)
    buf = np.zeros((BH, BW, 4), dtype=np.uint8)
    sujo = [0, 0, 0, 0]

    def assinatura(f):
        chave = []
        for leg in camadas:
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
            chave.append((id(leg), round(op_cue, 3), round(dy_cue), round(blur_cue, 1),
                          tuple(estados)))
        return tuple(chave)

    ass_ant, bytes_ant, reusados = None, None, 0
    for f in range(851):
        ass = assinatura(f)
        if ass == ass_ant and bytes_ant is not None:
            ff.stdin.write(bytes_ant)
            reusados += 1
            continue
        ass_ant = ass
        if sujo[2] > sujo[0] and sujo[3] > sujo[1]:
            buf[sujo[1]:sujo[3], sujo[0]:sujo[2]] = 0
        sujo[:] = [0, 0, 0, 0]
        primeira = True
        for leg in camadas:
            if leg.inicio_f <= f <= leg.fim_f:
                if getattr(leg, "dim", 0.0):
                    # escurece o que JA esta na faixa (as legendas), como na
                    # producao — o texto do cartao entra depois, sem dim
                    E.aplicar_dim(buf, sujo, leg.dim, f - leg.inicio_f,
                                  leg.dim_fade)
                    primeira = False
                R.desenhar(leg, f - leg.inicio_f, buf, sujo, origem=(x0, y0),
                           mesclar=not primeira)
                primeira = False
        bytes_ant = buf.tobytes()
        ff.stdin.write(bytes_ant)
    ff.stdin.close()
    ff.wait()
    return time.perf_counter() - t0, reusados


if __name__ == "__main__":
    t_fx = render_efeitos()
    el, reus = uma_passada(S / "final_faixa.mp4")
    mb = BW * BH * 4 / 1024 / 1024
    print(f"FAIXA rodada {sys.argv[1]}: efeitos {t_fx:.1f}s + passada {el:.1f}s = "
          f"{t_fx + el:.1f}s ({851 / 30 / (t_fx + el):.1f}x tempo real) | "
          f"faixa {BW}x{BH} ({mb:.1f} MB/q) | {reus}/851 reusados")
