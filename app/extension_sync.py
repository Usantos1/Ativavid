"""Extensão de cookies — cópia estável em %USERPROFILE%\\ATIVAVID\\extension.

O Chrome/Edge carrega a pasta sem compactação. Se apontar para Program Files,
cada update do instalador invalida a extensão. A cópia do usuário sobrevive.
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
USER_DIR = Path.home() / "ATIVAVID"
USER_EXT = USER_DIR / "extension" / "llm-session"
REPO_EXT = REPO / "extension" / "llm-session"


def extension_dir() -> Path:
    """Pasta que o usuário deve carregar no Chrome/Edge."""
    sync_extension()
    return USER_EXT if USER_EXT.exists() else REPO_EXT


def sync_extension() -> Path:
    """Copia/atualiza a extensão para a pasta do usuário. Retorna o path final."""
    USER_EXT.mkdir(parents=True, exist_ok=True)
    if not REPO_EXT.is_dir():
        return USER_EXT
    for src in REPO_EXT.iterdir():
        if not src.is_file():
            continue
        dest = USER_EXT / src.name
        try:
            if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime and dest.stat().st_size == src.stat().st_size:
                continue
            shutil.copy2(src, dest)
        except OSError:
            try:
                shutil.copyfile(src, dest)
            except OSError:
                pass
    # Marcador para o usuário achar fácil (sempre atualiza)
    readme = USER_EXT / "LEIA-ME.txt"
    try:
        readme.write_text(
            "ATIVAVID Session — extensão de cookies\n\n"
            "1. Abra chrome://extensions (ou edge://extensions)\n"
            "2. Ative Modo do desenvolvedor\n"
            "3. Carregar sem compactação → selecione ESTA pasta\n"
            "4. Fixe o ícone na barra (quebra-cabeça → pin) para não sumir\n"
            "5. Depois de atualizar o ATIVAVID: Recarregar a extensão\n"
            "6. Cookies: %USERPROFILE%\\ATIVAVID\\sessions.json\n"
            "7. Deixe o ATIVAVID na bandeja (X não encerra o servidor)\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return USER_EXT
