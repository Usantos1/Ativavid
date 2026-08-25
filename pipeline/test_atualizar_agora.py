# -*- coding: utf-8 -*-
""""Atualizar agora": o app baixa e executa o instalador sozinho.

O ciclo manual (aviso -> navegador -> download -> achar o exe -> rodar)
fazia o usuario pedir o instalador no chat a cada release ("cade o
instalador final?"). O servidor baixa o exe da politica de versao e o abre;
o proprio instalador derruba o app e o reabre.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _preparar(monkeypatch, tmp_path, url, corpo=b"x" * 2_000_000):
    import app.update_check as uc

    monkeypatch.setattr(uc, "check_update", lambda: {"downloadUrl": url})
    monkeypatch.setattr(uc.sys, "platform", "win32")
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    import urllib.request

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda u, timeout=0: _Resp(corpo))
    abertos = []
    monkeypatch.setattr(uc.os, "startfile", lambda p: abertos.append(p),
                        raising=False)
    return uc, abertos


def test_baixa_e_abre_o_instalador(monkeypatch, tmp_path):
    uc, abertos = _preparar(
        monkeypatch, tmp_path,
        "https://github.com/x/y/releases/download/v9/Instalar.ATIVAVID.9.99.exe")
    r = uc.baixar_e_instalar()
    assert r["ok"], r
    assert abertos and abertos[0].endswith("Instalar.ATIVAVID.9.99.exe")
    assert Path(abertos[0]).is_file()


def test_recusa_download_que_nao_e_exe(monkeypatch, tmp_path):
    uc, abertos = _preparar(monkeypatch, tmp_path, "https://x/pagina.html")
    r = uc.baixar_e_instalar()
    assert not r["ok"] and not abertos


def test_recusa_download_pequeno_demais(monkeypatch, tmp_path):
    """Pagina de erro salva como .exe nao pode ser executada."""
    uc, abertos = _preparar(monkeypatch, tmp_path,
                            "https://x/Instalar.ATIVAVID.9.99.exe",
                            corpo=b"<html>404</html>")
    r = uc.baixar_e_instalar()
    assert not r["ok"] and not abertos


def test_a_rota_e_o_botao_existem():
    srv = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    assert 'action == "instalar"' in srv
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnUpdInstalar"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert '"instalar"' in js.replace("'", '"')
