# -*- coding: utf-8 -*-
"""O painel de projetos não faz esperar 31 segundos.

`/api/projects` monta uma linha por projeto e mede a duração do vídeo
entregue de cada um — um `ffprobe` por projeto. Medido com os 187
projetos do usuário:

    1ª chamada (frio):  **31,5 s**
    2ª chamada (quente):  0,2 s

O cache já existia e funcionava; quem pagava os 31 segundos era sempre
quem abriu a tela. É trabalho de leitura que não depende de nada da tela.

Mesmo remédio (e mesma razão) do `/api/espaco`, esquentado assim desde a
4.02.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
DS = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")


def test_a_funcao_existe_e_e_de_fundo():
    i = PS.index("def esquentar_painel(")
    corpo = PS[i:PS.index("\ndef probe_duration_cached(", i)]
    assert "daemon=True" in corpo
    assert "probe_duration_cached(" in corpo


def test_nao_mede_o_corte_nem_a_copia_leve():
    """São arquivos de trabalho, não entrega — e o proxy é grande."""
    i = PS.index("def esquentar_painel(")
    corpo = PS[i:PS.index("\ndef probe_duration_cached(", i)]
    for nome in ("cut.mp4", "base.mp4", "cut_proxy.mp4"):
        assert nome in corpo, nome


def test_falhar_nao_derruba_o_servidor():
    i = PS.index("def esquentar_painel(")
    corpo = PS[i:PS.index("\ndef probe_duration_cached(", i)]
    assert "except Exception" in corpo


def test_o_preview_esquenta_no_arranque():
    i = PS.index("srv = ThreadingHTTPServer(")
    assert "esquentar_painel(" in PS[i - 300:i]


def test_o_app_tambem_esquenta():
    """O app tem `main` próprio; herdar o Handler não herda o arranque."""
    i = DS.index("srv = QuietThreadingHTTPServer(")
    assert "esquentar_painel(" in DS[i - 400:i]


def test_esquentar_de_verdade_nao_levanta(tmp_path):
    import preview_server as ps

    t = ps.esquentar_painel([tmp_path, tmp_path / "nao-existe"])
    del t
