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
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TIMEOUT_S = 240  # compor 30s levou 67s na RTX 3050; 4x de folga

# Medido em 27/08 (RTX 3050 4GB, i5-10300H): compor 60s consome ~4,2GB de
# RAM e 2,0GB dos 4GB de VRAM, com pico de 53% da GPU. Numa maquina ja
# apertada isso empurraria o render para o disco (swap) ou disputaria a
# VRAM do NVDEC/NVENC — a trilha nao vale um render lento. Sem folga, o
# launcher sai por aqui e o pipeline segue para o proximo plano.
RAM_LIVRE_MIN_GB = 5.5
VRAM_LIVRE_MIN_MB = 2600
LOCK = Path(tempfile.gettempdir()) / "ativavid-musicgen.lock"
LOCK_VALIDADE_S = 600


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


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_livre_gb() -> float:
    """-1 quando nao da para medir — nesse caso a guarda nao bloqueia."""
    try:
        m = _MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1e9
    except Exception:
        return -1.0


def vram_livre_mb() -> int:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15)
        total, usada = r.stdout.strip().splitlines()[0].split(", ")
        return int(total) - int(usada)
    except Exception:
        return -1


def outro_motor_rodando() -> bool:
    """Um motor por vez na maquina. Com parallelJobs=2 dois jobs pediriam
    trilha ao mesmo tempo: 8GB de RAM e 4GB de VRAM juntos — a mesma
    armadilha que o NVDEC disputado ja pregou. O lock guarda o PID e vence
    sozinho em 10 min, entao um processo morto nunca tranca o recurso."""
    try:
        if LOCK.is_file():
            idade = time.time() - LOCK.stat().st_mtime
            if idade < LOCK_VALIDADE_S:
                pid = int(LOCK.read_text(encoding="utf-8").strip() or 0)
                if pid and pid != os.getpid():
                    # 0x1000 = PROCESS_QUERY_LIMITED_INFORMATION
                    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                    if h:
                        ctypes.windll.kernel32.CloseHandle(h)
                        return True
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        return False
    return False


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

    ram = ram_livre_gb()
    if 0 <= ram < RAM_LIVRE_MIN_GB:
        print(f"[musicgen] só {ram:.1f} GB de RAM livre (mínimo "
              f"{RAM_LIVRE_MIN_GB}) — não vou disputar com o render",
              flush=True)
        sys.exit(6)
    vram = vram_livre_mb()
    if 0 <= vram < VRAM_LIVRE_MIN_MB:
        print(f"[musicgen] só {vram} MB de VRAM livre (mínimo "
              f"{VRAM_LIVRE_MIN_MB}) — a GPU está ocupada com o render",
              flush=True)
        sys.exit(6)
    if outro_motor_rodando():
        # Codigo PROPRIO (7): "so falta a vez" e diferente de "a maquina nao
        # tem folga" — quem espera a vez quase sempre consegue compor logo
        # depois, e o chamador pode ser mais paciente sem arriscar nada.
        print("[musicgen] outro vídeo já está compondo — esperando a vez",
              flush=True)
        sys.exit(7)

    gerador = Path(__file__).resolve().parent / "musicgen_gerar.py"
    try:
        proc = subprocess.run(
            [str(py), str(gerador), args.vibe, "-o", args.output,
             "--length-sec", str(args.length_sec)],
            capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        print(f"[musicgen] estourou {TIMEOUT_S}s — abortado", flush=True)
        LOCK.unlink(missing_ok=True)
        sys.exit(5)
    finally:
        try:
            if LOCK.is_file() and \
                    LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
                LOCK.unlink(missing_ok=True)
        except Exception:
            pass
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
