# -*- coding: utf-8 -*-
"""Launcher do motor local de música (MusicGen) — plano B do ElevenLabs.

O app NÃO carrega torch: o motor mora num venv próprio (pasta MotorMusica,
irmã da Biblioteca — ~2,5GB, instalado só nas máquinas que o querem) e este
launcher apenas o encontra e o executa. Sem o motor instalado, sai rápido
com código 3 e o pipeline cai para a biblioteca de trilhas — instalação de
cliente não paga nada por isso.

Ordem de busca do Python do motor:
  1. ATIVAVID_MUSICGEN_PY (env; caminho do python.exe)
  2. <--motor>/Scripts/python.exe (o pipeline passa a pasta irmã da
     Biblioteca real, resolvendo o junction dos Projetos)
  3. ~/ATIVAVID/MotorMusica/Scripts/python.exe
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 240  # compor 30s levou 67s na RTX 3050; 4x de folga


def achar_python(motor: str) -> Path | None:
    env = os.environ.get("ATIVAVID_MUSICGEN_PY", "").strip()
    cands = [Path(env)] if env else []
    if motor:
        cands.append(Path(motor) / "Scripts" / "python.exe")
        cands.append(Path(motor) / "bin" / "python")
    cands.append(Path.home() / "ATIVAVID" / "MotorMusica" / "Scripts"
                 / "python.exe")
    for c in cands:
        if c and c.is_file():
            return c
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vibe")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--length-sec", type=int, default=30)
    ap.add_argument("--motor", default="")
    args = ap.parse_args()

    py = achar_python(args.motor)
    if py is None:
        print("[musicgen] motor local não instalado (pasta MotorMusica) — "
              "seguindo para o próximo plano", flush=True)
        sys.exit(3)

    gerador = Path(__file__).resolve().parent / "musicgen_gerar.py"
    try:
        proc = subprocess.run(
            [str(py), str(gerador), args.vibe, "-o", args.output,
             "--length-sec", str(args.length_sec)],
            capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print(f"[musicgen] estourou {TIMEOUT_S}s — abortado", flush=True)
        sys.exit(5)
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
