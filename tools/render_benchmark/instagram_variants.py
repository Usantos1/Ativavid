"""Benchmark do preset Instagram: qual arquivo sobrevive melhor à compressão deles.

O objetivo NÃO é o arquivo com maior bitrate — é o que fica melhor DEPOIS que o
Instagram recomprime. Como o Instagram não publica os parâmetros, medimos em
duas etapas:

    referência ──> variante (nosso encode) ──> recompressão simulada ──> métrica

A recompressão simulada é a parte aproximada, e está isolada em SIM_* para você
poder trocar quando tiver dados melhores. O que ela permite responder é a
pergunta comparativa ("20 Mbps sobrevive melhor que 12?"), que é estável mesmo
se os parâmetros exatos do Instagram forem outros — não a pergunta absoluta
("qual VMAF meu vídeo terá no feed").

Uso:
    py tools/render_benchmark/instagram_variants.py --ref <arquivo> [--rodadas 3]
    py tools/render_benchmark/instagram_variants.py --ref <arquivo> --so-listar

Regras desta máquina (aprendidas na marra):
  - só medir com a máquina livre; o script recusa rodar se achar ffmpeg/render
    de outra pessoa no ar, senão o número sai inflado e vira relatório errado;
  - variância de GPU aqui chega a 2,3x, então cada variante roda N vezes e
    reportamos a MEDIANA, não a melhor nem a média.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SAIDA = REPO / "tools" / "render_benchmark" / "results"

# --- a recompressão que tenta imitar o Instagram --------------------------
# Reels entrega perto de 1080x1920 com bitrate bem abaixo do que enviamos.
# Estes números são a hipótese, não medição do serviço deles.
SIM_BITRATE = "4M"
SIM_MAXRATE = "5M"
SIM_BUFSIZE = "10M"
SIM_PRESET = "medium"

# --- as variantes a comparar ---------------------------------------------
# `vf` extra fica separado para dar para testar scaler e sharpening sem
# duplicar a lista inteira.
VARIANTES: dict[str, dict] = {
    "A_12M": {"desc": "1080x1920 H.264 High ~12 Mbps (VBR limitado)",
              "args": ["-c:v", "libx264", "-profile:v", "high", "-b:v", "12M",
                       "-maxrate", "14M", "-bufsize", "24M", "-preset", "slow"]},
    "B_16M": {"desc": "1080x1920 H.264 High ~16 Mbps",
              "args": ["-c:v", "libx264", "-profile:v", "high", "-b:v", "16M",
                       "-maxrate", "19M", "-bufsize", "32M", "-preset", "slow"]},
    "C_20M": {"desc": "1080x1920 H.264 High ~20 Mbps",
              "args": ["-c:v", "libx264", "-profile:v", "high", "-b:v", "20M",
                       "-maxrate", "24M", "-bufsize", "40M", "-preset", "slow"]},
    "D_25M": {"desc": "1080x1920 H.264 High ~25 Mbps",
              "args": ["-c:v", "libx264", "-profile:v", "high", "-b:v", "25M",
                       "-maxrate", "30M", "-bufsize", "50M", "-preset", "slow"]},
    "E_CRF16": {"desc": "1080x1920 H.264 High CRF 16 (qualidade constante)",
                "args": ["-c:v", "libx264", "-profile:v", "high", "-crf", "16",
                         "-preset", "slow"]},
    "E2_CRF18": {"desc": "1080x1920 H.264 High CRF 18",
                 "args": ["-c:v", "libx264", "-profile:v", "high", "-crf", "18",
                          "-preset", "slow"]},
    "N_NVENC_CQ19": {"desc": "1080x1920 NVENC CQ19 p6 (GPU)",
                     "args": ["-c:v", "h264_nvenc", "-profile:v", "high", "-preset", "p6",
                              "-rc", "vbr", "-cq", "19", "-b:v", "0",
                              "-maxrate", "25M", "-bufsize", "50M"]},
    "N_NVENC_CQ23": {"desc": "1080x1920 NVENC CQ23 p4 (o que o app usa hoje no prep)",
                     "args": ["-c:v", "h264_nvenc", "-profile:v", "high", "-preset", "p4",
                              "-rc", "vbr", "-cq", "23", "-b:v", "0"]},
    "F_4K_CRF18": {"desc": "2160x3840 H.264 High CRF 18 (4K, para comparar)",
                   "args": ["-c:v", "libx264", "-profile:v", "high", "-crf", "18",
                            "-preset", "slow"],
                   "escala": "2160:3840"},
    "S_SHARP": {"desc": "1080x1920 CRF 18 + sharpening levíssimo",
                "args": ["-c:v", "libx264", "-profile:v", "high", "-crf", "18",
                         "-preset", "slow"],
                "vf_extra": "unsharp=5:5:0.3:5:5:0.0"},
    "L_LANCZOS": {"desc": "1080x1920 CRF 18 + scaler lanczos",
                  "args": ["-c:v", "libx264", "-profile:v", "high", "-crf", "18",
                           "-preset", "slow"],
                  "flags_scaler": "lanczos"},
}

COMUM = [
    "-pix_fmt", "yuv420p",
    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
    "-movflags", "+faststart",
    "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
]


def maquina_ocupada() -> list[str]:
    """Processos que roubariam CPU/GPU da medição — inclusive job real do app."""
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe' or Name='python.exe'\" "
        "| ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.CommandLine }"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=40)
    except Exception:  # noqa: BLE001
        return []
    ruins = []
    for linha in (r.stdout or "").splitlines():
        baixa = linha.lower()
        if "ffmpeg.exe" in baixa or "run_fast" in baixa or "render.py" in baixa:
            if "instagram_variants" not in baixa:
                ruins.append(linha.strip()[:110])
    return ruins


def ffmpeg(args: list[str]) -> float:
    t = time.perf_counter()
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "")[-800:])
    return time.perf_counter() - t


def gera_variante(ref: Path, nome: str, cfg: dict, dest: Path) -> float:
    escala = cfg.get("escala", "1080:1920")
    flags = cfg.get("flags_scaler")
    vf = f"scale={escala}" + (f":flags={flags}" if flags else "")
    if cfg.get("vf_extra"):
        vf += "," + cfg["vf_extra"]
    return ffmpeg(["-i", str(ref), "-vf", vf, *cfg["args"], *COMUM, str(dest)])


def recomprime_como_instagram(entrada: Path, dest: Path) -> float:
    """A etapa aproximada: o que o serviço faria com o arquivo enviado."""
    return ffmpeg([
        "-i", str(entrada),
        "-vf", "scale=1080:1920:flags=bicubic",
        "-c:v", "libx264", "-profile:v", "high", "-preset", SIM_PRESET,
        "-b:v", SIM_BITRATE, "-maxrate", SIM_MAXRATE, "-bufsize", SIM_BUFSIZE,
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        str(dest),
    ])


def mede(distorcido: Path, ref: Path) -> dict:
    """VMAF + SSIM + PSNR do arquivo contra a referência, ambos em 1080x1920."""
    log = distorcido.with_suffix(".vmaf.json")
    filtro = (
        "[0:v]scale=1080:1920:flags=bicubic,setpts=PTS-STARTPTS[dis];"
        "[1:v]scale=1080:1920:flags=bicubic,setpts=PTS-STARTPTS[ref];"
        f"[dis][ref]libvmaf=log_fmt=json:log_path={log.as_posix()}:"
        "feature=name=psnr|name=float_ssim"
    )
    ffmpeg(["-i", str(distorcido), "-i", str(ref), "-lavfi", filtro, "-f", "null", "-"])
    dados = json.loads(log.read_text(encoding="utf-8"))
    pool = dados.get("pooled_metrics", {})

    def m(chave: str, campo: str = "mean"):
        v = pool.get(chave, {}).get(campo)
        return round(float(v), 3) if v is not None else None

    return {
        "vmaf": m("vmaf"),
        "vmaf_min": m("vmaf", "min"),
        "ssim": m("float_ssim"),
        "psnr": m("psnr_y") or m("psnr"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="arquivo de referência (o master atual)")
    ap.add_argument("--rodadas", type=int, default=3, help="repetições por variante (mediana)")
    ap.add_argument("--so-listar", action="store_true")
    ap.add_argument("--forcar", action="store_true", help="mede mesmo com a máquina ocupada")
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    if args.so_listar:
        for k, v in VARIANTES.items():
            print(f"{k:16} {v['desc']}")
        return 0

    ref = Path(args.ref).expanduser()
    if not ref.exists():
        print(f"referência não existe: {ref}")
        return 1
    if not shutil.which("ffmpeg"):
        print("ffmpeg não encontrado no PATH")
        return 1

    ocupada = maquina_ocupada()
    if ocupada and not args.forcar:
        print("MÁQUINA OCUPADA — medir agora dá número inflado. Rodando:")
        for p in ocupada[:6]:
            print("  ", p)
        print("\nEspere terminar, ou use --forcar se souber o que está fazendo.")
        return 2

    tmp = Path(args.saida or (REPO / "tools" / "render_benchmark" / "results" / "_ig_tmp"))
    tmp.mkdir(parents=True, exist_ok=True)
    SAIDA.mkdir(parents=True, exist_ok=True)

    print(f"referência: {ref}")
    print(f"rodadas por variante: {args.rodadas} (reporta mediana)\n")

    linhas = []
    for nome, cfg in VARIANTES.items():
        print(f"-- {nome}: {cfg['desc']}")
        tempos = []
        arquivo = tmp / f"{nome}.mp4"
        try:
            for i in range(args.rodadas):
                tempos.append(gera_variante(ref, nome, cfg, arquivo))
                print(f"     encode {i+1}/{args.rodadas}: {tempos[-1]:.1f}s")
        except RuntimeError as e:
            print(f"     FALHOU: {e}")
            continue

        tam = arquivo.stat().st_size
        # métrica do arquivo COMO ENVIADO
        direto = mede(arquivo, ref)
        # e depois da recompressão que o serviço faria
        pos = tmp / f"{nome}.ig.mp4"
        recomprime_como_instagram(arquivo, pos)
        depois = mede(pos, ref)

        linhas.append({
            "variante": nome,
            "desc": cfg["desc"],
            "mb": round(tam / 1048576, 1),
            "encode_s": round(statistics.median(tempos), 1),
            "vmaf_enviado": direto["vmaf"],
            "vmaf_pos_instagram": depois["vmaf"],
            "vmaf_min_pos": depois["vmaf_min"],
            "ssim_pos": depois["ssim"],
            "psnr_pos": depois["psnr"],
        })
        print(f"     {tam/1048576:.1f} MB | VMAF enviado {direto['vmaf']} "
              f"| VMAF pós-IG {depois['vmaf']}\n")

    if not linhas:
        print("nenhuma variante concluiu")
        return 1

    linhas.sort(key=lambda x: (x["vmaf_pos_instagram"] or 0), reverse=True)
    print("\n" + "=" * 92)
    print(f"{'variante':16}{'MB':>8}{'encode':>9}{'VMAF env':>10}{'VMAF pós':>10}{'VMAF min':>10}{'SSIM':>9}")
    print("-" * 92)
    for l in linhas:
        print(f"{l['variante']:16}{l['mb']:>8}{l['encode_s']:>8}s"
              f"{str(l['vmaf_enviado']):>10}{str(l['vmaf_pos_instagram']):>10}"
              f"{str(l['vmaf_min_pos']):>10}{str(l['ssim_pos']):>9}")

    rel = SAIDA / "instagram_preset.json"
    rel.write_text(json.dumps({
        "referencia": str(ref),
        "rodadas": args.rodadas,
        "recompressao_simulada": {
            "bitrate": SIM_BITRATE, "maxrate": SIM_MAXRATE, "preset": SIM_PRESET,
            "aviso": "hipótese sobre o Instagram, não medição do serviço",
        },
        "resultados": linhas,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nrelatório: {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
