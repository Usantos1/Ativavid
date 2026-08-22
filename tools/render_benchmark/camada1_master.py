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


def estatisticas_de_luz(arq: Path) -> dict:
    """Luminância e clipping — o que decide npl, já que VMAF não decide.

    YAVG diz se escureceu. YMAX perto de 235 (limited) com muitos quadros
    significa highlight estourado: detalhe que não volta.
    """
    _, err = roda(["-i", str(arq), "-vf",
                   "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                   "-f", "null", "-"])
    yavg = [float(m) for m in re.findall(r"YAVG=([0-9.]+)", err)]
    _, err2 = roda(["-i", str(arq), "-vf",
                    "signalstats,metadata=print:key=lavfi.signalstats.YMAX:file=-",
                    "-f", "null", "-"])
    ymax = [float(m) for m in re.findall(r"YMAX=([0-9.]+)", err2)]
    # fração de quadros cujo pico encosta no teto do limited range
    estourados = sum(1 for v in ymax if v >= 234) / len(ymax) if ymax else None
    return {
        "luma_media": round(statistics.mean(yavg), 2) if yavg else None,
        "luma_mediana": round(statistics.median(yavg), 2) if yavg else None,
        "pico_medio": round(statistics.mean(ymax), 2) if ymax else None,
        "frac_quadros_no_teto": round(estourados, 3) if estourados is not None else None,
    }


def quadro(arq: Path, seg: float, dest: Path) -> None:
    roda(["-ss", str(seg), "-i", str(arq), "-frames:v", "1", "-q:v", "2", str(dest)])


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
    print("referência (tonemap full-res → lanczos, sem perda)…")
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
    print("\nGRUPO C — npl (lanczos, tonemap→scale). Sem VMAF: veja os quadros.")
    for npl in (NPL_ATUAL, NPL_BT2408, 250):
        arq = tmp / f"npl_{npl}.mp4"
        t = gera(fonte, args.inicio, args.dur,
                 vf_tonemap_depois(npl, "lanczos"), arq, sem_perda=False)
        luz = estatisticas_de_luz(arq)
        luz.update({"variante": f"npl={npl}" + (" (atual)" if npl == NPL_ATUAL else
                                                " (BT.2408)" if npl == NPL_BT2408 else ""),
                    "npl": npl, "segundos": round(t, 1)})
        resultados["npl"].append(luz)
        quadro(arq, meio, tmp / f"quadro_npl_{npl}.jpg")
        print(f"  npl={npl:<4} luma média {luz['luma_media']:>6} | pico {luz['pico_medio']:>6}"
              f" | quadros no teto {luz['frac_quadros_no_teto']}")

    rel = SAIDA / "camada1_master.json"
    rel.write_text(json.dumps({
        "fonte": str(fonte), "inicio": args.inicio, "dur": args.dur,
        "referencia": "tonemap full-res (npl=203) → lanczos, sem perda",
        "nota_npl": "npl não tem vencedor por métrica: decide olhando os quadros",
        "resultados": resultados,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nrelatório: {rel}")
    print(f"quadros para comparar: {tmp}\\quadro_npl_*.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
