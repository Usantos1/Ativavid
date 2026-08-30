# -*- coding: utf-8 -*-
"""O editor precisa poder perguntar se o vídeo leve existe.

Cada projeto tem uma cópia leve do corte — `cut_proxy.mp4` — feita para o
arrasto na linha do tempo ficar fluido. Nos projetos do usuário:

    cut.mp4  45 MB  ->  cut_proxy.mp4  2 MB   (22x)
    cut.mp4 124 MB  ->  cut_proxy.mp4  9 MB   (13x)

186 projetos têm a cópia. **Nenhum a usava.** O editor pergunta com
`fetch(..., {method: 'HEAD'})` e nenhum servidor implementava HEAD: o
`BaseHTTPRequestHandler` responde *501 Unsupported method*, `r.ok` é
falso, e o editor cai no arquivo cheio — 4K HDR, que é o que ele grava.

Sem erro na tela: o vídeo toca, só pesado.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
LOCAL = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
APP = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_o_editor_pergunta_por_head():
    """Se o cliente parar de usar HEAD, o servidor vira enfeite."""
    i = APP.index("async function detectProxy()")
    corpo = APP[i:i + 400]
    assert "method: 'HEAD'" in corpo and "cut_proxy.mp4" in corpo


def test_os_dois_servidores_respondem_head():
    for nome, fonte in (("preview_server", PS), ("local_server", LOCAL)):
        assert "def do_HEAD(self)" in fonte, nome


def test_head_de_arquivo_devolve_o_tamanho():
    i = PS.index("def do_HEAD(self)")
    corpo = PS[i:PS.index("\n    def do_GET", i)]
    assert "Content-Length" in corpo
    assert "/media/" in corpo


def test_head_em_rota_de_api_e_recusado():
    """Rodar o trabalho de um GET para jogar a resposta fora seria pior
    que não atender."""
    i = PS.index("def do_HEAD(self)")
    corpo = PS[i:PS.index("\n    def do_GET", i)]
    assert "405" in corpo


def test_head_nao_escapa_da_pasta():
    """Mesma guarda do GET: `_safe` resolve e confere a raiz."""
    i = PS.index("def do_HEAD(self)")
    corpo = PS[i:PS.index("\n    def do_GET", i)]
    assert corpo.count("self._safe(") >= 3
    assert "is_file()" in corpo


def test_o_app_herda_do_preview_server():
    """O app não tem servidor próprio para o editor — herda este."""
    desk = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert re.search(r"class DesktopHandler\(ps\.Handler\)", desk)
    assert "def do_HEAD" not in desk, "sobrescrever aqui perderia o do pai"
