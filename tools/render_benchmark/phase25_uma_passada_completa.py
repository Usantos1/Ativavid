# -*- coding: utf-8 -*-
"""Uma passada COMPLETA (headline+legendas+cartao+flashes) ate o MP4 final."""
import json, subprocess, sys, time
sys.path.insert(0, r"E:\Code\ativa-vid\tools\render_benchmark")
import numpy as np
from pathlib import Path
import phase20_render_proprio as R
import phase22_recorte as RC
import phase23_video_inteiro as V
import phase24_elementos as E

S = Path(r"E:\Temp\claude\E--Code-ativa-vid\82d36fa4-0bd4-4030-a656-a054a8ce0e05\scratchpad")
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}
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
if ec.get("enabled"):
    camadas.append(E.montar_endcard(ec, hook.get("accent"), 851, R.FPS))
flashes = [float(t["at"]) for t in (ed.get("transitions") or []) if t.get("type") == "flash"]

saida = S / "final_completo_limpo.mp4"
t0 = time.perf_counter()
ff = subprocess.Popen(
    ["ffmpeg", "-y", "-v", "error", "-i", str(cut),
     "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{R.W}x{R.H}", "-r", "30", "-i", "-",
     "-filter_complex", "[0:v][1:v]overlay=eof_action=endall:format=auto,format=yuv420p[v]",
     "-map", "[v]", "-map", "0:a?", "-c:a", "copy", "-frames:v", "851",
     "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", str(saida)],
    stdin=subprocess.PIPE, **NOWIN)
buf = np.zeros((R.H, R.W, 4), dtype=np.uint8)
sujo = [0, 0, 0, 0]


def assinatura(f):
    """Estado visual do quadro. Igual ao anterior = quadro identico = nao
    recompoe nada, so reenvia os mesmos bytes. A maior parte dos quadros e
    texto PARADO — recompor era o desperdicio que o perfil apontou."""
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
                estados.append(1)                    # assentada
            else:
                estados.append(round(fl * 2) / 2)    # em animacao: muda a cada quadro
        chave.append((id(leg), round(op_cue, 3), round(dy_cue), round(blur_cue, 1),
                      tuple(estados)))
    for at in flashes:
        c = round(at * R.FPS) + E.VIDEO_LAG
        if c - E.FLASH_LEAD <= f < c - E.FLASH_LEAD + E.FLASH_LEN:
            chave.append(("flash", f))
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
            d_val = getattr(leg, 'dim', 0.0)
            if d_val:
                E.aplicar_dim(buf, sujo, d_val, f - leg.inicio_f,
                              getattr(leg, 'dim_fade', 10))
                primeira = False
            # Mesclar contra buffer VAZIO e copiar com passos a mais: a
            # primeira camada do quadro escreve direto (o driver ja limpou).
            R.desenhar(leg, f - leg.inicio_f, buf, sujo, mesclar=not primeira)
            primeira = False
    for at in flashes:
        a = E.flash_quadro(at, R.FPS, f)
        if a is not None:
            E.aplicar_flash(buf, sujo, a)
    bytes_ant = buf.tobytes()
    ff.stdin.write(bytes_ant)
ff.stdin.close(); ff.wait()
el = time.perf_counter() - t0
print(f"UMA PASSADA COMPLETA rodada {sys.argv[1]}: {el:.1f}s = {el/851*1000:.0f} ms/quadro ({851/30/el:.1f}x tempo real) | {reusados}/851 quadros reusados")
