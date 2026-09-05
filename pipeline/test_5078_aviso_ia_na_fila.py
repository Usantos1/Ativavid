# -*- coding: utf-8 -*-
"""5.0.78: a Fila avisa quando a sessão da IA principal expirou.

A checagem (5.0.76) só fala quando ele abre Configurações. No lote de
04/09 foram 17 vídeos com plano via Groq e sem revisão antes de alguém
olhar. Agora o resumo da saúde (`llm-health.json`, gravado por cada
chamada real e pela sonda) viaja no `/api/jobs` — que o hub já pede a
cada poucos segundos — e vira uma faixa acima da área de trabalho, com
"Testar agora" (a mesma sonda do Doutor) e "Abrir IA".

Regra do aviso: só quando HÁ sessão capturada de Gemini/ChatGPT e a
última chamada real de TODAS elas falhou. Sem sessão nenhuma é escolha
(plano via Groq) e não gera faixa — a checagem cobre esse caso.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import llm_session as L  # noqa: E402


def _resumo(monkeypatch, capturadas, saude):
    ls = types.ModuleType("app.local_server")
    ls.load_sessions = lambda: {"providers": {p: {"capturedAt": "x"} for p in capturadas}}
    monkeypatch.setitem(sys.modules, "app.local_server", ls)
    monkeypatch.setattr(L, "saude_dos_provedores", lambda: saude)
    return L.ia_sessao_resumo()


def test_as_duas_mortas_avisa_com_o_erro(monkeypatch):
    r = _resumo(monkeypatch, ["gemini-web", "chatgpt-web", "claude-web"], {
        "gemini-web": {"ok": False, "erro": "Token Gemini ausente", "at": "2026-09-05T17:54:31Z"},
        "chatgpt-web": {"ok": False, "erro": "sem accessToken", "at": "2026-09-05T17:54:32Z"},
    })
    assert r["ok"] is False
    assert r["caidas"] == ["Gemini Web", "ChatGPT Web"] and r["vivas"] == []
    assert r["erro"] == "Token Gemini ausente" and r["at"] == "2026-09-05T17:54:32Z"


def test_uma_viva_nao_avisa(monkeypatch):
    r = _resumo(monkeypatch, ["gemini-web", "chatgpt-web"], {
        "gemini-web": {"ok": True}, "chatgpt-web": {"ok": False, "erro": "x"},
    })
    assert r["ok"] is True and r["caidas"] == ["ChatGPT Web"] and r["vivas"] == ["Gemini Web"]


def test_sem_sessao_capturada_e_escolha_nao_aviso(monkeypatch):
    assert _resumo(monkeypatch, [], {"gemini-web": {"ok": False}})["ok"] is True
    assert _resumo(monkeypatch, ["claude-web"], {})["ok"] is True


def test_sem_saude_gravada_ainda_nao_avisa(monkeypatch):
    """Sessao recem-capturada, nenhuma chamada ainda: nada a dizer."""
    assert _resumo(monkeypatch, ["gemini-web"], {})["ok"] is True


def test_o_resumo_viaja_no_api_jobs_dos_dois_servidores():
    for nome in ("local_server.py", "desktop_server.py"):
        s = (REPO / "app" / nome).read_text(encoding="utf-8")
        assert '"iaSessao": ia_sessao_resumo()' in s, nome


def test_a_sonda_tem_rota_e_passa_pelo_servidor_do_app():
    ls = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert 'if path == "/api/llm-proxy/sondar":' in ls
    i = ls.index('if path == "/api/llm-proxy/sondar":')
    assert "sondar(p) for p in PROVEDORES_DO_PLANO if stored.get(p)" in ls[i:i + 900]
    ds = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/llm-proxy/sondar",' in ds, "POST novo precisa entrar na lista repassada ao shim"


def test_o_hub_mostra_a_faixa_e_liga_os_botoes():
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="avisoIa" class="aviso-ia hidden"' in html
    assert 'id="avisoIaTestar"' in html and 'id="avisoIaAbrir"' in html
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "renderAvisoIa(data.iaSessao);" in js, "a cada poll da Fila"
    fn = js[js.index("function renderAvisoIa(ia)"):][:900]
    assert 'if (!ia || ia.ok !== false) { box.classList.add("hidden"); return; }' in fn
    assert "plano via Groq e sem a revisão do texto" in fn
    w = js[js.index("function wireAvisoIa()"):][:1200]
    assert 'api("/api/llm-proxy/sondar", { method: "POST"' in w
    assert 'setView("ia")' in w
    assert "  wireAvisoIa();\n" in js[js.index("async function boot() {"):][:200]
    css = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    assert ".aviso-ia {" in css and "var(--warn)" in css[css.index(".aviso-ia {"):][:500]
