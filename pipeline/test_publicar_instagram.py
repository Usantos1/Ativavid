# -*- coding: utf-8 -*-
"""Publicar Reels no Instagram direto do app (infra da 2.93).

Publicar e para FORA: so acontece com clique + confirmacao do usuario.
O upload e RESUMAVEL (binario local direto, sem URL publica).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))


def test_fluxo_completo_com_meta_falsa(monkeypatch, tmp_path):
    import publicar_instagram as pi

    video = tmp_path / "final.mp4"
    video.write_bytes(b"v" * 200_000)
    chamadas = []

    class _Resp:
        def __init__(self, payload, status=200):
            self._p = payload; self.status_code = status
        def json(self): return self._p

    def post(url, data=None, headers=None, timeout=0):
        chamadas.append(("POST", url))
        if url.endswith("/media"):
            assert data["media_type"] == "REELS"
            assert data["upload_type"] == "resumable"
            return _Resp({"id": "C1", "uri": "https://rupload.facebook.com/x"})
        if "rupload" in url:
            assert headers["Authorization"].startswith("OAuth ")
            assert headers["file_size"] == str(video.stat().st_size)
            return _Resp({"success": True})
        if url.endswith("/media_publish"):
            assert data["creation_id"] == "C1"
            return _Resp({"id": "M9"})
        raise AssertionError(url)

    estados = iter([{"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"},
                    {"permalink": "https://instagram.com/reel/abc"}])

    def get(url, params=None, timeout=0):
        chamadas.append(("GET", url))
        return _Resp(next(estados))

    import requests
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(pi.time, "sleep", lambda s: None)

    r = pi.publicar_reel(video, "legenda #primecamp", ig_user_id="123",
                         token="tok")
    assert r["ok"] and r["permalink"].endswith("/reel/abc"), r
    assert [c[0] for c in chamadas] == ["POST", "POST", "GET", "GET", "POST", "GET"]


def test_recusa_da_meta_vira_erro_legivel(monkeypatch, tmp_path):
    import publicar_instagram as pi

    video = tmp_path / "final.mp4"
    video.write_bytes(b"v" * 200_000)

    class _Resp:
        status_code = 400
        def json(self):
            return {"error": {"message": "Invalid OAuth", "code": 190}}

    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())
    r = pi.publicar_reel(video, "x", ig_user_id="1", token="ruim")
    assert not r["ok"] and "token" in r["error"].lower()


def test_rotas_chaves_e_card():
    srv = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    assert '"/api/jobs/publicar-instagram"' in srv
    assert '"IG_USER_ID", "META_ACCESS_TOKEN"' in srv
    assert 'which == "instagram"' in srv
    ds = (RAIZ / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/jobs/publicar-instagram"' in ds
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="keyIgId"' in html and 'id="keyMeta"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'data-act="publicar-ig"' in js
    assert "window.confirm" in js, \
        "publicar e para FORA — confirmacao explicita sempre"


def test_card_mostra_o_estado(tmp_path):
    from app.jobs_view import _estado_de_publicacao

    (tmp_path / "publicacao.json").write_text(json.dumps(
        {"estado": "ok", "permalink": "https://instagram.com/reel/x"}),
        encoding="utf-8")
    job = {}
    _estado_de_publicacao(job, tmp_path)
    assert job["publicadoLink"].endswith("/reel/x")
