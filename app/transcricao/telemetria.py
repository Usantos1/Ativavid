# -*- coding: utf-8 -*-
"""O que aconteceu em cada transcrição — só números, nunca conteúdo.

Serve para acompanhar os primeiros usos reais e achar gargalo depois. Fica
tudo em disco, na máquina do usuário: **nenhum áudio, nenhum texto e nenhum
nome de arquivo saem daqui**, e nada é enviado a servidor nenhum. O identificador
do vídeo é um hash curto, que serve para agrupar linhas do mesmo material sem
guardar o nome.

Uma linha JSON por transcrição, em `~/ATIVAVID/transcricao-log.jsonl`. Formato
de linha e não um JSON grande de propósito: o arquivo pode ser lido enquanto o
app escreve, e uma linha corrompida não leva as outras junto.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TETO_LINHAS = 2000


def arquivo() -> Path:
    env = (os.environ.get("ATIVAVID_TRANSCRICAO_LOG") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "ATIVAVID" / "transcricao-log.jsonl"


def _vram_mb() -> int:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8)
        return max((int(x) for x in (r.stdout or "").split() if x.isdigit()),
                   default=0)
    except Exception:  # noqa: BLE001
        return 0


def _ram_mb() -> int:
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Process -Id {os.getpid()}).WorkingSet64"],
                capture_output=True, text=True, timeout=12)
            return int(int((r.stdout or "0").strip()) / 1e6)
        return int(int(Path(f"/proc/{os.getpid()}/statm").read_text().split()[1])
                   * os.sysconf("SC_PAGE_SIZE") / 1e6)
    except Exception:  # noqa: BLE001
        return 0


def identificador(video: Path) -> str:
    """Hash curto do NOME + tamanho. Não guarda o nome nem lê o conteúdo."""
    try:
        st = Path(video).stat()
        base = f"{Path(video).name}:{st.st_size}"
    except OSError:
        base = str(video)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


def registrar(**campos: Any) -> None:
    """Grava uma linha. Nunca levanta: telemetria não pode derrubar um vídeo."""
    try:
        linha = {
            "quando": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"),
            "ram_mb": _ram_mb(),
            "vram_mb": _vram_mb(),
            **campos,
        }
        p = arquivo()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        _podar(p)
    except Exception:  # noqa: BLE001
        pass


def _podar(p: Path) -> None:
    try:
        if p.stat().st_size < 400_000:
            return
        linhas = p.read_text(encoding="utf-8").splitlines()
        if len(linhas) > TETO_LINHAS:
            p.write_text("\n".join(linhas[-TETO_LINHAS:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def resumo(n: int = 20) -> list[dict]:
    """As últimas linhas, para olhar sem abrir o arquivo na mão."""
    try:
        linhas = arquivo().read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    saida = []
    for x in linhas:
        try:
            saida.append(json.loads(x))
        except ValueError:
            continue
    return saida
