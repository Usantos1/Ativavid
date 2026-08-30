# -*- coding: utf-8 -*-
"""O preview em localhost não tem mais buracos de rota.

O usuário usa o preview solto (`helpers/preview_server.py`) para marcar
trecho com **M** e salvar correção — não é só ambiente de conserto. Nele
três rotas não existiam, e cada uma tirava algo da tela:

    /api/health         rodapé "Versão sistema: —" e etiqueta "v?"
    /api/brand-presets  a aba Estilo não listava os presets da marca
    /api/events         a tela não recebia aviso e reconectava num 404

No app elas existem (o `desktop_server` repassa para o servidor do hub).
Aqui entram versões magras — este servidor serve UM projeto, não tem fila
nem trabalhador.

Verificado no navegador: a etiqueta passou de `v?` para `v4.08`, o rodapé
de `—` para `4.08`, e nenhum recurso da página responde erro.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
SHELL = (REPO / "assets" / "studio" / "shell.js").read_text(encoding="utf-8")


def test_as_tres_rotas_estao_no_do_GET():
    i = PS.index("def do_GET(self)")
    corpo = PS[i:PS.index("\n    def do_POST(", i)]
    for rota in ("/api/health", "/api/brand-presets", "/api/events"):
        assert f'path == "{rota}"' in corpo, rota


def test_health_devolve_a_versao():
    """É só isso que o rodapé e a etiqueta leem."""
    i = PS.index("def _health(self)")
    corpo = PS[i:PS.index("\n    def _brand_presets(", i)]
    assert "running_version()" in corpo and '"version"' in corpo
    assert "except Exception" in corpo, "queda aqui não pode derrubar a tela"


def test_a_tela_le_a_versao_daqui():
    """Se o cliente parar de ler, a rota vira enfeite."""
    i = SHELL.index('fetch("/api/health"')
    assert "h.version" in SHELL[i:i + 300]


def test_brand_presets_responde_como_o_hub():
    """A tela rotula os presets com `brandName`; sem ele dizia "Padrão"
    para os presets de outra marca."""
    i = PS.index("def _brand_presets(self)")
    corpo = PS[i:PS.index("\n    def _events(", i)]
    for campo in ('"brandName"', '"active"', "load_presets(bid)"):
        assert campo in corpo, campo


def test_events_e_so_batida_de_coracao():
    """Este servidor não tem fila: não há mudança de estado para avisar."""
    i = PS.index("def _events(self)")
    corpo = PS[i:PS.index("\n    def _versions_get(", i)]
    assert "text/event-stream" in corpo
    assert b": ping" .decode() in corpo
    assert "wait_for_change" not in corpo


def test_events_nao_derruba_quando_o_cliente_fecha():
    i = PS.index("def _events(self)")
    corpo = PS[i:PS.index("\n    def _versions_get(", i)]
    assert "BrokenPipeError" in corpo and "ConnectionResetError" in corpo
