# -*- coding: utf-8 -*-
"""O render tem prazo por quadro compatível com a máquina do usuário.

O padrão do Remotion é 30s por `delayRender()`. Um quadro que demora mais
que isso derruba o RENDER INTEIRO — e demorar é normal aqui: a máquina
edita vídeo com o Chrome e o Cursor abertos, e o quadro pede decode de 4K
HDR. Visto em 29/08: um render de 3,5 min morreu em "delayRender ... não
liberado após 28000ms" buscando UM quadro do cut.mp4.

Teto alto não atrasa render saudável — ele só muda quanto tempo se espera
antes de desistir.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_o_render_completo_passa_o_prazo():
    s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.index('"render",')
    trecho = s[i:i + 1800]
    assert '"--timeout=120000"' in trecho, trecho[:400]


def test_a_flag_existe_na_versao_do_remotion():
    """`--timeout` inválido derrubaria TODO render. A prova mora no
    próprio pacote: a opção declara `cliFlag: "timeout"`."""
    import json
    cache = Path.home() / "ATIVAVID" / "remotion-cache"
    if not cache.is_dir():
        return          # máquina sem o cache montado: nada a checar
    for pkg in cache.glob("*/node_modules/@remotion/renderer/package.json"):
        d = pkg.parent / "dist" / "client.d.ts"
        if not d.is_file():
            continue
        assert 'cliFlag: "timeout"' in d.read_text(
            encoding="utf-8", errors="replace"), (
            f"@remotion/renderer {json.loads(pkg.read_text(encoding='utf-8'))['version']}"
            " nao tem a flag --timeout")
        return
