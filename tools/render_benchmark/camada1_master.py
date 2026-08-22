"""Camada 1 — do original HDR até o master SDR. Não mede encode de entrega.

Aqui se decide o que acontece ANTES do cut: tonemap (npl), scaler e a ordem
entre escalar e tonemapar. É a camada onde a perda é irreversível — o que
estourar aqui não volta com bitrate nenhum depois.

MÉTRICA POR GRUPO (isto é o cerne do desenho):

  scaler e ordem  → VMAF/SSIM contra uma REFERÊNCIA de máxima qualidade.
                    Faz sentido porque o alvo é preservar detalhe: as duas
                    saídas têm a MESMA cor, muda só a nitidez.

  npl             → NÃO tem referência, e medir com VMAF seria enganoso.
                    Mudar npl muda a aparência DE PROPÓSITO; comparar contra
                    uma referência arbitrária só premiaria quem se parece com
                    ela, não quem está certo. Aqui medimos características
                    absolutas (luminância média, clipping de highlight, faixa
                    útil) e exportamos quadros para você decidir olhando.

A referência é o melhor caminho que a máquina consegue: tonemap em luz linear
na resolução cheia, depois downscale lanczos, gravado sem perda. Ela não é
"a verdade" — é o teto prático contra o qual medir o quanto cada atalho custa.

Uso:
    py tools/render_benchmark/camada1_master.py --fonte <original.MOV>
    py tools/render_benchmark/camada1_master.py --fonte X --inicio 8 --dur 10
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SAIDA = REPO / "tools" / "render_benchmark" / "results"

# O console do Windows entrega cp1252 quando a saída é capturada, e uma seta
# no meio de um print derrubava a medição inteira DEPOIS de 13 min esperando a
# fila esvaziar. Texto de relatório não pode custar a corrida.
for _fluxo in (sys.stdout, sys.stderr):
    if hasattr(_fluxo, "reconfigure"):
        try:
            _fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

ALTURA = 1920           # entrega vertical
NPL_ATUAL = 100         # o que o app usa hoje (helpers/render.py:471)
NPL_BT2408 = 203        # recomendação BT.2408 para HLG

# --- as peças da cadeia, parametrizadas -----------------------------------


def cadeia_tonemap(npl: int) -> str:
    """A cadeia do app, com npl aberto. Mantém hable/desat=0 para isolar npl."""
    return (
        f"zscale=t=linear:npl={npl},format=gbrpf32le,zscale=p=bt709,"
        "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
    )


def escala(flags: str | None) -> str:
    f = f":flags={flags}" if flags else ""
    return f"scale=-2:{ALTURA}{f}"


def vf_tonemap_depois(npl: int, flags: str | None) -> str:
    """Tonemap na resolução CHEIA, depois reduz. Tecnicamente correto."""
    return f"{cadeia_tonemap(npl)},{escala(flags)}"


def vf_escala_antes(npl: int, flags: str | None) -> str:
    """Reduz primeiro, tonemapa depois — o que o app faz hoje, por velocidade."""
    return f"{escala(flags)},{cadeia_tonemap(npl)}"


# --- execução -------------------------------------------------------------

def maquina_ocupada() -> list[str]:
    if sys.platform != "win32":
        return []
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe' or Name='python.exe'\" "
          "| ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.CommandLine }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=40)
    except Exception:  # noqa: BLE001
        return []
    ruins = []
    for linha in (r.stdout or "").splitlines():
        b = linha.lower()
        if ("ffmpeg.exe" in b or "run_fast" in b or "render.py" in b) and "camada1" not in b:
            ruins.append(linha.strip()[:110])
    return ruins


def roda(args: list[str]) -> tuple[float, str]:
    t = time.perf_counter()
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-stats_period", "9999", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-700:])
    return time.perf_counter() - t, (r.stderr or "")


def recorte(fonte: Path, inicio: float, dur: float) -> list[str]:
    return ["-ss", str(inicio), "-t", str(dur), "-i", str(fonte)]


def gera(fonte: Path, inicio: float, dur: float, vf: str, dest: Path,
         *, sem_perda: bool) -> float:
    """Grava o master. Sem perda para a referência; CRF 12 para as variantes.

    CRF 12 nas variantes existe para o arquivo não ficar absurdo — a 12 o
    encode não é o gargalo da comparação (o que muda entre elas é o filtro).
    """
    if sem_perda:
        enc = ["-c:v", "libx264", "-preset", "veryslow", "-qp", "0"]
    else:
        enc = ["-c:v", "libx264", "-preset", "slow", "-crf", "12"]
    t, _ = roda([*recorte(fonte, inicio, dur), "-vf", vf, *enc,
                 "-pix_fmt", "yuv420p",
                 "-color_primaries", "bt709", "-color_trc", "bt709",
                 "-colorspace", "bt709", "-color_range", "tv",
                 "-an", str(dest)])
    return t


def mede_contra(dis: Path, ref: Path) -> dict:
    log = dis.with_suffix(".vmaf.json")
    filtro = ("[0:v]setpts=PTS-STARTPTS[d];[1:v]setpts=PTS-STARTPTS[r];"
              f"[d][r]libvmaf=log_fmt=json:log_path={log.as_posix()}:"
              "feature=name=psnr|name=float_ssim")
    roda(["-i", str(dis), "-i", str(ref), "-lavfi", filtro, "-f", "null", "-"])
    pool = json.loads(log.read_text(encoding="utf-8")).get("pooled_metrics", {})

    def m(k, campo="mean"):
        v = pool.get(k, {}).get(campo)
        return round(float(v), 3) if v is not None else None

    return {"vmaf": m("vmaf"), "vmaf_min": m("vmaf", "min"),
            "ssim": m("float_ssim"), "psnr": m("psnr_y") or m("psnr")}


AMOSTRAS = 12          # quadros analisados por variante
BLOCO = 96             # lado do bloco ao procurar regiões de interesse
CROP = 320             # lado do recorte exportado


def _quadros_np(arq: Path, quantos: int = AMOSTRAS):
    """Amostra quadros espalhados e devolve como array RGB (numpy)."""
    import numpy as np
    from PIL import Image

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(arq)],
        capture_output=True, text=True).stdout.strip() or 1.0)
    saida = []
    for i in range(quantos):
        t = dur * (i + 0.5) / quantos
        png = arq.with_name(f"{arq.stem}_amostra{i}.png")
        roda(["-ss", f"{t:.3f}", "-i", str(arq), "-frames:v", "1", str(png)])
        saida.append((t, np.asarray(Image.open(png).convert("RGB"), dtype="float32")))
        png.unlink(missing_ok=True)
    return saida


def _luma(rgb):
    """Rec.709 — a mesma matriz que o pipeline usa."""
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def estatisticas_de_luz(arq: Path) -> dict:
    """O que decide npl, já que VMAF não decide.

    Percentis dizem para onde a imagem inteira andou (não só a média, que
    esconde o caso em que sombra sobe e highlight desce ao mesmo tempo).
    Clipping diz quanto detalhe de highlight foi embora de vez — 235 é o teto
    do limited range; acima disso não há informação, só branco.
    """
    import numpy as np

    quadros = _quadros_np(arq)
    lumas = np.concatenate([_luma(f).ravel() for _, f in quadros])
    pcts = {f"p{p}": round(float(np.percentile(lumas, p)), 1)
            for p in (1, 5, 25, 50, 75, 90, 95, 99)}

    # clipping: quanto da imagem está encostado ou colado no teto
    total = lumas.size
    quase = float((lumas >= 230).sum()) / total
    teto = float((lumas >= 235).sum()) / total
    # e quanto está esmagado embaixo
    piso = float((lumas <= 16).sum()) / total

    # histograma em 16 faixas, para ver a forma da distribuição
    hist, _ = np.histogram(lumas, bins=16, range=(0, 255))
    hist = [round(float(h) / total, 4) for h in hist]

    return {
        "luma_media": round(float(lumas.mean()), 2),
        "percentis": pcts,
        "frac_clip_alto_230": round(quase, 5),
        "frac_clip_teto_235": round(teto, 5),
        "frac_esmagado_16": round(piso, 5),
        "histograma_16": hist,
    }


def acha_regioes(arq: Path, seg: float) -> dict[str, tuple[int, int]]:
    """Escolhe UMA vez onde recortar, para os crops serem comparáveis.

    As coordenadas saem de um quadro só e depois são aplicadas iguais a todas
    as variantes — recortar "a região mais clara de cada uma" compararia
    lugares diferentes da cena e não diria nada sobre npl.
    """
    import numpy as np
    from PIL import Image

    png = arq.with_name("_ref_regiao.png")
    roda(["-ss", f"{seg:.3f}", "-i", str(arq), "-frames:v", "1", str(png)])
    rgb = np.asarray(Image.open(png).convert("RGB"), dtype="float32")
    png.unlink(missing_ok=True)
    h, w, _ = rgb.shape
    luma = _luma(rgb)

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # regra clássica de tom de pele em RGB; grosseira, mas suficiente para
    # escolher ONDE olhar — quem julga a pele é você, no recorte.
    pele = ((r > 95) & (g > 40) & (b > 20) & (r > g) & (r > b) &
            (np.abs(r - g) > 15)).astype("float32")

    def varre(mapa, modo: str):
        melhor, coord = None, (0, 0)
        for y in range(0, h - BLOCO, BLOCO):
            for x in range(0, w - BLOCO, BLOCO):
                v = float(mapa[y:y + BLOCO, x:x + BLOCO].mean())
                if melhor is None or (v > melhor if modo == "max" else v < melhor):
                    melhor, coord = v, (x, y)
        return coord, melhor

    (xl, yl), _ = varre(luma, "max")                       # luz forte / céu
    (xp, yp), score = varre(pele, "max")                   # pele
    # "área clara" sem ser o extremo: o bloco mais próximo do p85 da cena
    alvo = float(np.percentile(luma, 85))
    dist = np.abs(luma - alvo)
    (xc, yc), _ = varre(dist, "min")

    def ajusta(x, y):
        return (max(0, min(x + BLOCO // 2 - CROP // 2, w - CROP)),
                max(0, min(y + BLOCO // 2 - CROP // 2, h - CROP)))

    regioes = {"luz_forte": ajusta(xl, yl), "area_clara": ajusta(xc, yc)}
    if score and score > 0.15:
        regioes["pele"] = ajusta(xp, yp)
    return regioes


def quadro(arq: Path, seg: float, dest: Path,
           regioes: dict[str, tuple[int, int]] | None = None) -> None:
    """PNG do quadro inteiro e, se houver regiões, um PNG por recorte."""
    roda(["-ss", f"{seg:.3f}", "-i", str(arq), "-frames:v", "1",
          "-compression_level", "0", str(dest)])
    for nome, (x, y) in (regioes or {}).items():
        roda(["-ss", f"{seg:.3f}", "-i", str(arq), "-frames:v", "1",
              "-vf", f"crop={CROP}:{CROP}:{x}:{y}",
              "-compression_level", "0",
              str(dest.with_name(f"{dest.stem}__{nome}.png"))])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", required=True, help="ORIGINAL HDR (.MOV do iPhone)")
    ap.add_argument("--inicio", type=float, default=8.0)
    ap.add_argument("--dur", type=float, default=10.0)
    ap.add_argument("--forcar", action="store_true")
    args = ap.parse_args()

    fonte = Path(args.fonte).expanduser()
    if not fonte.exists():
        print(f"fonte não existe: {fonte}")
        return 1
    if not shutil.which("ffmpeg"):
        print("ffmpeg fora do PATH")
        return 1

    ocupada = maquina_ocupada()
    if ocupada and not args.forcar:
        print("MÁQUINA OCUPADA — medir agora dá número inflado. Rodando:")
        for p in ocupada[:6]:
            print("  ", p)
        return 2

    tmp = SAIDA / "_camada1"
    tmp.mkdir(parents=True, exist_ok=True)
    SAIDA.mkdir(parents=True, exist_ok=True)
    meio = args.dur / 2

    print(f"fonte : {fonte.name}")
    print(f"trecho: {args.inicio}s + {args.dur}s\n")

    # ---- referência: tonemap em resolução cheia + lanczos, sem perda -----
    print("referencia (tonemap na resolucao cheia + lanczos, sem perda)...")
    ref = tmp / "REF.mp4"
    t_ref = gera(fonte, args.inicio, args.dur,
                 vf_tonemap_depois(NPL_BT2408, "lanczos"), ref, sem_perda=True)
    print(f"  {t_ref:.1f}s | {ref.stat().st_size/1048576:.1f} MB\n")

    resultados: dict[str, list] = {"scaler": [], "ordem": [], "npl": []}

    # ---- GRUPO A: scaler (npl e ordem fixos) ----------------------------
    print("GRUPO A — scaler (npl=203, tonemap→scale)")
    for flags in ("bicubic", "bilinear", "lanczos", "spline"):
        arq = tmp / f"scaler_{flags}.mp4"
        t = gera(fonte, args.inicio, args.dur,
                 vf_tonemap_depois(NPL_BT2408, flags), arq, sem_perda=False)
        m = mede_contra(arq, ref)
        m.update({"variante": flags, "segundos": round(t, 1),
                  "mb": round(arq.stat().st_size / 1048576, 1)})
        resultados["scaler"].append(m)
        print(f"  {flags:10} VMAF {m['vmaf']:>7} | SSIM {m['ssim']} | {t:.1f}s")

    # ---- GRUPO B: ordem (scaler lanczos, npl 203) -----------------------
    print("\nGRUPO B — ordem entre escalar e tonemapar (lanczos, npl=203)")
    for nome, vf in (("tonemap_depois_do_scale (o app faz assim hoje)",
                      vf_escala_antes(NPL_BT2408, "lanczos")),
                     ("scale_depois_do_tonemap (correto)",
                      vf_tonemap_depois(NPL_BT2408, "lanczos"))):
        arq = tmp / f"ordem_{'antes' if 'hoje' in nome else 'depois'}.mp4"
        t = gera(fonte, args.inicio, args.dur, vf, arq, sem_perda=False)
        m = mede_contra(arq, ref)
        m.update({"variante": nome, "segundos": round(t, 1)})
        resultados["ordem"].append(m)
        print(f"  {nome[:44]:44} VMAF {m['vmaf']:>7} | {t:.1f}s")

    # ---- GRUPO C: npl (sem referência — medidas absolutas) --------------
    # Nenhum valor é favorito: 203 entra como candidato, não como resposta.
    print("\nGRUPO C - npl (lanczos, tonemap antes do scale). Sem VMAF: decide olhando.")
    rotulos = {NPL_ATUAL: " (o app usa hoje)", NPL_BT2408: " (BT.2408)"}
    arquivos_npl: dict[int, Path] = {}
    for npl in (NPL_ATUAL, 150, NPL_BT2408, 250):
        arq = tmp / f"npl_{npl}.mp4"
        t = gera(fonte, args.inicio, args.dur,
                 vf_tonemap_depois(npl, "lanczos"), arq, sem_perda=False)
        arquivos_npl[npl] = arq
        luz = estatisticas_de_luz(arq)
        luz.update({"variante": f"npl={npl}{rotulos.get(npl, '')}",
                    "npl": npl, "segundos": round(t, 1)})
        resultados["npl"].append(luz)
        p = luz["percentis"]
        print(f"  npl={npl:<4} luma {luz['luma_media']:>6} | p50 {p['p50']:>5} | p95 {p['p95']:>5}"
              f" | clip>=235 {luz['frac_clip_teto_235']:.4f} | escuro<=16 {luz['frac_esmagado_16']:.4f}")

    # recortes comparáveis: as MESMAS coordenadas em todas as variantes
    print("\n  recortes (mesmas coordenadas em todos os npl):")
    regioes = acha_regioes(arquivos_npl[NPL_BT2408], meio)
    for nome, (x, y) in regioes.items():
        print(f"    {nome:12} em ({x},{y}) {CROP}x{CROP}")
    for npl, arq in arquivos_npl.items():
        quadro(arq, meio, tmp / f"quadro_npl_{npl}.png", regioes)
    resultados["regioes_crop"] = {k: list(v) for k, v in regioes.items()}

    rel = SAIDA / "camada1_master.json"
    rel.write_text(json.dumps({
        "fonte": str(fonte), "inicio": args.inicio, "dur": args.dur,
        "referencia": "tonemap na resolucao cheia (npl=203) + lanczos, sem perda",
        "nota_npl": "npl não tem vencedor por métrica: decide olhando os quadros",
        "resultados": resultados,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nrelatorio: {rel}")
    print(f"quadros PNG: {tmp}\\quadro_npl_*.png")
    print("recortes   : quadro_npl_*__luz_forte.png / __area_clara.png / __pele.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
