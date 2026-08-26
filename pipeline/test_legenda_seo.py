# -*- coding: utf-8 -*-
"""Hashtags fixas + SEO/GEO na legenda do post (pedido 26/08).

O dono define a lista de hashtags (sai EXATAMENTE ela) e os termos de busca
locais (a IA tece cidade+termos no corpo — posicionamento no Google, nao so
resumo do video).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def test_knobs_viajam_no_preset():
    from app.brand_presets import STYLE_KEYS

    assert "postHashtags" in STYLE_KEYS and "postSeo" in STYLE_KEYS
    html = (RAIZ / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="autoPostTags"' in html and 'id="autoPostSeo"' in html


def test_hashtags_fixas_mandam_no_rascunho(tmp_path):
    from pipeline.run_fast import _legenda_from_edl

    (tmp_path / "edl.json").write_text(json.dumps({
        "llm": {"hook": "Olha esse conserto"},
        "ranges": [{"beat": "HOOK", "quote": "Troca de tela na hora"}],
    }), encoding="utf-8")
    preset = {"postHashtags": "#primecamp, assistenciatecnica #campinas",
              "endCardCopy": {"line1": "Segue @primecamp"}}
    out = _legenda_from_edl(tmp_path, "fala do video", preset)
    ultima = out.strip().splitlines()[-1]
    assert ultima == "#primecamp #assistenciatecnica #campinas", ultima
    assert "#reels" not in out and "#shorts" not in out, \
        "com lista fixa o palpite automatico nao entra"
    # sem a lista, o comportamento antigo continua
    out2 = _legenda_from_edl(tmp_path, "fala do video", {"endCardCopy": {}})
    assert "#" in out2


def test_polish_exige_e_conserta_as_fixas(monkeypatch):
    import pipeline.run_fast as rf

    preset = {"postHashtags": "#primecamp #campinas",
              "postSeo": "Campinas SP; conserto de celular",
              "endCardCopy": {}}
    capturado = {}

    def chat_falso(messages, model=None):
        capturado["system"] = messages[0]["content"]
        capturado["user"] = messages[1]["content"]
        # IA derrapou: devolveu hashtags proprias
        return ("Gancho forte aqui\nCorpo da legenda.\n\n#viral #fy", "gemini-web")

    import app.llm_session as ls
    monkeypatch.setattr(ls, "chat", chat_falso)
    out = rf._llm_polish_legenda("rascunho", spoken="fala", preset=preset)
    assert out is not None
    assert "SEO LOCAL" in capturado["system"], "sem instrucao de SEO no prompt"
    assert "Campinas SP" in capturado["user"]
    ultima = out.strip().splitlines()[-1]
    assert ultima == "#primecamp #campinas", \
        f"a IA derrapou e o conserto nao entrou: {ultima!r}"
