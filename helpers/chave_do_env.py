"""Uma chave do `.env` do usuario — decifrando o que a 5.0.47 cifrou.

A 5.0.47 passou a guardar ELEVENLABS/FREEPIK/GROQ/PEXELS cifradas com a
DPAPI (`dpapi:...`) em `~/ATIVAVID/.env`. O app le por `load_env_keys`, que
decifra; os HELPERS de linha de comando (pexels_search, freepik_search,
auto_broll, elevenlabs_music) liam o arquivo cru e passaram a mandar
`dpapi:AQAAA...` como chave — as duas APIs responderam 401 e a busca de
imagem parou, calada, em 05/09. Este modulo e o unico lugar que sabe ler.

Sem o pacote `app` no caminho (helper rodando solto), devolve o valor cru:
num .env antigo, em texto claro, e exatamente o que ja funcionava.
"""
from __future__ import annotations

import os
from pathlib import Path

def candidatos() -> tuple[Path, ...]:
    """ORDEM DO APP: `%USERPROFILE%/ATIVAVID/.env` primeiro. Numa instalacao
    normal o codigo fica em Program Files (so leitura) e a tela de
    Integracoes grava no do usuario; o `.env` ao lado do codigo so existe na
    maquina de quem desenvolve.

    Calculado NA HORA de propriedade: congelado no import, ele apontava para
    a casa do processo que importou o modulo primeiro."""
    return (
        Path.home() / "ATIVAVID" / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path(".env"),
    )


def _decifrar(valor: str) -> str:
    if not valor.startswith("dpapi:"):
        return valor
    try:
        import sys

        raiz = str(Path(__file__).resolve().parent.parent)
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        from app import secret_store

        return secret_store.unprotect(valor)
    except Exception:  # noqa: BLE001 — helper solto: melhor vazio que lixo
        return ""


def chave(nome: str) -> str:
    """O valor de `nome` no .env do usuario (decifrado), ou do ambiente."""
    for arq in candidatos():
        try:
            if not arq.exists():
                continue
            for linha in arq.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                if k.strip() == nome:
                    val = _decifrar(v.strip().strip('"').strip("'"))
                    if val:
                        return val
        except OSError:
            continue
    return os.environ.get(nome, "")
