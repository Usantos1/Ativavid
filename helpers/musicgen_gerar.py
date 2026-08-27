# -*- coding: utf-8 -*-
"""Compõe uma trilha com o MusicGen local (roda DENTRO do venv MotorMusica).

Este arquivo nunca é importado pelo app: o launcher (musicgen_local.py) o
executa com o Python do MotorMusica, o único que tem torch/transformers.
Exige GPU — na CPU desta classe de máquina a geração é 17x o tempo real
(medido em 26/08: 15s de áudio em 4min22) e travaria o pipeline; na GPU a
mesma máquina compôs 30s em 67s com pico de 1,9GB de VRAM.

O modelo compõe no máximo ~30s; pedidos maiores são fechados em loop com
fade pelo ffmpeg — o mesmo acabamento do plano B da biblioteca.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TETO_MODELO_S = 30
TOKENS_POR_S = 50


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vibe")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--length-sec", type=int, default=30)
    args = ap.parse_args()

    try:
        import torch
    except ImportError:
        sys.exit("torch ausente neste Python — rode pelo launcher (exit 4)")
    if not torch.cuda.is_available():
        sys.exit("sem GPU CUDA: geracao local seria 17x o tempo real")

    import scipy.io.wavfile
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    model = MusicgenForConditionalGeneration.from_pretrained(
        "facebook/musicgen-small", torch_dtype=torch.float16).to("cuda")
    processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
    sr = model.config.audio_encoder.sampling_rate

    gerar_s = min(TETO_MODELO_S, max(5, int(args.length_sec)))
    inputs = processor(text=[args.vibe], padding=True, return_tensors="pt")
    inputs = {k: v.to("cuda") for k, v in inputs.items()}
    audio = model.generate(**inputs, max_new_tokens=gerar_s * TOKENS_POR_S,
                           do_sample=True, guidance_scale=3.0)
    dur = audio.shape[-1] / sr
    print(f"[musicgen] {dur:.1f}s compostos na GPU", flush=True)

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "bruto.wav"
        scipy.io.wavfile.write(str(wav), sr, audio[0, 0].float().cpu().numpy())
        alvo = max(4.0, float(args.length_sec))
        subprocess.run(
            [ffmpeg, "-y", "-stream_loop", "-1", "-i", str(wav),
             "-t", f"{alvo:.2f}", "-vn",
             "-af", ("afade=t=in:st=0:d=0.6,"
                     f"afade=t=out:st={max(0.5, alvo - 1.8):.2f}:d=1.6"),
             "-c:a", "libmp3lame", "-q:a", "3", str(out)],
            capture_output=True, check=True)
    print(f"[musicgen] salvo: {out} ({out.stat().st_size // 1024} KB)",
          flush=True)


if __name__ == "__main__":
    main()
