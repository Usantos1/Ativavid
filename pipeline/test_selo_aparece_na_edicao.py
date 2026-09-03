# -*- coding: utf-8 -*-
"""O selo e o capítulo do longform aparecem TAMBÉM na Edição.

Pedido de 02/09 ("no visual mostra mas em edicao nao mostra segue
ativavid"): eles só existiam queimados no vídeo final — a Edição (cut cru)
não tinha bloco na timeline nem cartão no preview. Agora viram bloco na
faixa de texto e cartão vivo no preview, com a mesma regra naFinal dos
outros elementos (no Visual, com o final pronto, o cartão NÃO desenha por
cima do que já está queimado).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_o_loader_cria_os_blocos():
    i = JS.index("function buildInsertsDraft")
    bloco = JS[i:JS.index("async function loadWave", i)]
    assert "(d.lowerThirds || []).forEach" in bloco
    assert "(d.chapters || []).forEach" in bloco
    assert "kind: 'lower'" in bloco and "kind: 'chapter'" in bloco


def test_os_blocos_entram_na_edicao_e_na_faixa_de_texto():
    i = JS.index("const visiveis = soManuais")
    assert "'lower'" in JS[i:i + 320] and "'chapter'" in JS[i:i + 320]
    j = JS.index("const isText = (c) =>")
    assert "'lower'" in JS[j:j + 220] and "'chapter'" in JS[j:j + 220]
    k = JS.index("const temManual = S.insertsDraft.some")
    assert "'lower'" in JS[k:k + 260], "sem midia manual a faixa ficaria oculta"


def test_o_cartao_desenha_no_preview_menos_sobre_o_final():
    assert "(c.kind === 'lower' || c.kind === 'chapter') && !naFinal" in JS
    i = JS.index("if (c.kind === 'lower' || c.kind === 'chapter')")
    bloco = JS[i:i + 1500]
    assert "lf-previa-selo" in bloco and "lf-previa-capitulo" in bloco
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    assert ".lf-previa-selo" in css and ".lf-previa-capitulo" in css
