# -*- coding: utf-8 -*-
"""O cabeçalho do editor mostra o nome do vídeo editado (o nome do card).

Pedido de 03/09: o editor mostrava a manchete + "arquivo · duração ·
formato", mas não o nome pelo qual o vídeo aparece no hub ("G3 · C1 ·
CTA3"). O nome vem da MESMA regra do hub (displayTitle): o stem do arquivo
final, exceto os genéricos final/cut — e o preview já recebe finalVideo.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_o_nome_vem_do_arquivo_final_com_a_regra_do_hub():
    i = JS.index("function nomeDoVideoEditado")
    bloco = JS[i:JS.index("\n}", i)]
    assert "S.state.finalVideo" in bloco
    # mesma excecao do displayTitle do hub: final/cut genericos nao sao nome
    assert "/^(final|cut)$/i" in bloco
    hub = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "/^(final|cut)$/i" in hub, "a regra do hub mudou — espelhar aqui"


def test_o_cabecalho_pinta_o_nome_antes_do_resto():
    i = JS.index("function refreshProjectChrome")
    bloco = JS[i:JS.index("\nfunction nomeDoVideoEditado", i)]
    assert "nomeDoVideoEditado()" in bloco
    assert "'proj-nome'" in bloco
    # o nome entra nos DOIS ramos (com manchete e sem manchete)
    assert bloco.count("pintarMeta(") >= 2
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    assert ".proj-nome" in css
