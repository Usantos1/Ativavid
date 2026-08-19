# -*- coding: utf-8 -*-
"""Sonda de stream que não se engana com arquivo de câmera.

O ffprobe 9 imprime o MESMO stream duas vezes no formato de texto quando o
arquivo tem um *stream group*: uma vez dentro de `[STREAM_GROUP]` e outra
solto. O `noprint_wrappers=1` tira os marcadores, mas não a repetição:

    ffprobe -select_streams v:0 -show_entries stream=r_frame_rate \
            -of default=nokey=1:noprint_wrappers=1 camera.mov
    24/1
    24/1

Quem lia isso como um valor só quebrava. Em produção deu
`could not convert string to float: '1\\n24/1'` e derrubou o vídeo: o
`split("/", 1)` de "24/1\\n24/1" devolve b="1\\n24/1".

Arquivos de iPhone não têm stream group e não mostravam o problema — mas
material de câmera tem, e o nosso próprio corte herda a estrutura.

A saída em JSON não repete. É isto que este módulo usa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def _default_runner(argv: Sequence[str]) -> str:
    r = subprocess.run(list(argv), capture_output=True, text=True, **NOWIN)
    return r.stdout or ""


def stream_fields(
    path: Path | str,
    entries: Sequence[str],
    *,
    select: str | None = "v:0",
    exe: str | None = None,
    runner: Callable[[Sequence[str]], str] | None = None,
) -> dict[str, Any]:
    """Campos do primeiro stream que casar. `{}` se não der para ler.

    Nunca levanta: o pipeline decide o padrão dele quando falta informação.
    """
    argv = [exe or shutil.which("ffprobe") or "ffprobe", "-v", "error"]
    if select:
        argv += ["-select_streams", select]
    argv += ["-show_entries", "stream=" + ",".join(entries), "-of", "json", str(path)]
    try:
        data = json.loads((runner or _default_runner)(argv) or "{}")
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    streams = data.get("streams") or []
    return streams[0] if streams else {}


def fps_of(path: Path | str, *, default: float = 0.0, exe: str | None = None,
           runner: Callable[[Sequence[str]], str] | None = None) -> float:
    """Quadros por segundo do vídeo. `default` quando não dá para saber."""
    rate = str(stream_fields(path, ["r_frame_rate"], exe=exe, runner=runner)
               .get("r_frame_rate") or "")
    return parse_rate(rate, default=default)


def parse_rate(rate: str, *, default: float = 0.0) -> float:
    """Avalia "30000/1001". Tolera lixo — inclusive a linha repetida."""
    rate = (rate or "").strip().splitlines()[0].strip() if rate and rate.strip() else ""
    if not rate:
        return default
    num, _, den = rate.partition("/")
    try:
        n = float(num)
        d = float(den) if den else 1.0
    except ValueError:
        return default
    return n / d if d else default


def size_of(path: Path | str, *, exe: str | None = None,
            runner: Callable[[Sequence[str]], str] | None = None) -> tuple[int, int]:
    """(largura, altura) do vídeo; (0, 0) quando não dá para saber."""
    s = stream_fields(path, ["width", "height"], exe=exe, runner=runner)
    try:
        return int(s.get("width") or 0), int(s.get("height") or 0)
    except (TypeError, ValueError):
        return 0, 0


def first_record(saida: str) -> str:
    """Primeiro registro da saída de texto do ffprobe.

    Com stream group o ffprobe repete o bloco inteiro; para quem pede N campos
    de UM stream, o primeiro registro é a resposta. Serve tanto para uma linha
    ("24/1") quanto para csv ("1080,1920").
    """
    for linha in (saida or "").splitlines():
        if linha.strip():
            return linha.strip()
    return ""


def all_records(saida: str, campos: int) -> list[str]:
    """Os `campos` primeiros valores, um por linha, sem as repetições."""
    linhas = [l.strip() for l in (saida or "").splitlines() if l.strip()]
    return linhas[:campos]
