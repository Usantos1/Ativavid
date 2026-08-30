# -*- coding: utf-8 -*-
"""A seção do CHANGELOG de uma versão, para virar o corpo da release.

    py tools/notas_da_versao.py            # a versão do VERSION
    py tools/notas_da_versao.py 4.09       # uma versão específica

Por que existe: o app pergunta ao GitHub o que há de novo e mostra no
aviso de atualização. Conferido na máquina do usuário com ele na 4.07 e a
4.09 publicada, `notes` vinha **vazio** — o corpo das releases era uma
frase corrida e o resumo só entendia lista. O texto certo já existia, no
CHANGELOG, escrito para ele.

    gh release create v4.10 ... --notes "$(py tools/notas_da_versao.py)"
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def secao(versao: str, changelog: str | None = None) -> str:
    """O trecho entre `## <versao>` e o próximo `## `. Vazio se não achar."""
    texto = changelog if changelog is not None else (
        REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    v = re.escape(str(versao).strip().lstrip("vV"))
    m = re.search(rf"^##\s+{v}\s*$(.*?)(?=^##\s|\Z)", texto,
                  re.M | re.S)
    return (m.group(1).strip() if m else "")


def main() -> int:
    versao = (sys.argv[1] if len(sys.argv) > 1
              else (REPO / "VERSION").read_text(encoding="utf-8")).strip()
    corpo = secao(versao)
    if not corpo:
        print(f"ERRO: CHANGELOG.md não tem seção `## {versao}`", file=sys.stderr)
        return 1
    sys.stdout.write(corpo + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
