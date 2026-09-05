# -*- coding: utf-8 -*-
"""5.0.46: quatro rodadas pequenas.

1. Canary-state não cresce para sempre (804 jobs, 229 KB por render).
2. O card diz O QUE está pendente e oferece "Aplicar correções pendentes".
3. `/` foca a busca, `Esc` limpa.
4. App aberto dias seguidos avisa o servidor uma vez por dia.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


# ------------------------------------------------------------------ R1
def test_canary_guarda_so_os_ultimos(monkeypatch, tmp_path):
    from app import overlay_canary as oc

    monkeypatch.setattr(oc, "STATE_PATH", tmp_path / "canary-state.json")
    monkeypatch.setattr(oc, "JOBS_GUARDADOS", 5)
    st = oc.load_state() if hasattr(oc, "load_state") else {"jobs": []}
    st["jobs"] = [{"project": f"p{i}"} for i in range(5)]
    oc.save_state(st)
    oc.record_canary_job({"project": "novo", "renderPath": "OVERLAY", "fallbackUsed": False})
    dados = json.loads((tmp_path / "canary-state.json").read_text(encoding="utf-8"))
    nomes = [j["project"] for j in dados["jobs"]]
    assert len(nomes) == 5 and nomes[-1] == "novo" and "p0" not in nomes


# ------------------------------------------------------------------ R2
def _projeto_com_correcao(tmp_path):
    ed = tmp_path / "edit"
    ed.mkdir(parents=True)
    (ed / "state.json").write_text(json.dumps({"finalVideo": "final.mp4"}), encoding="utf-8")
    (ed / "final.mp4").write_bytes(b"x" * 5000)
    c = ed / "corrections.json"
    c.write_text(json.dumps({"dirty": {"captions": True}}), encoding="utf-8")
    t = time.time() + 60
    os.utime(c, (t, t))
    return ed


def test_card_diz_o_tipo_do_pendente(tmp_path):
    from app.jobs_view import _pedido_nao_aplicado

    j = {}
    _pedido_nao_aplicado(j, _projeto_com_correcao(tmp_path))
    assert j["pedidoTipo"] == "correcoes"
    ed = _projeto_com_correcao(tmp_path / "b")
    (ed / "corrections.json").unlink()
    p = ed / "preview_edits.json"
    p.write_text("{}", encoding="utf-8")
    t = time.time() + 60
    os.utime(p, (t, t))
    j = {}
    _pedido_nao_aplicado(j, ed)
    assert j["pedidoTipo"] == "marcacoes"


def test_menu_do_card_aplica_pendentes():
    assert 'j.pedidoTipo === "correcoes"' in JS
    assert 'data-act="aplicar-pendentes"' in JS
    i = JS.index('act === "aplicar-pendentes"')
    trecho = JS[i:i + 900]
    assert "/api/corrections" in trecho and '{ op: "apply" }' in trecho
    assert "refreshJobs" in trecho


# ------------------------------------------------------------------ R3
def test_barra_foca_a_busca_e_esc_limpa():
    i = JS.index('e.key === "/"')
    trecho = JS[i - 400:i + 900]
    assert "digitando" in trecho, "nao pode roubar a barra de quem digita num campo"
    assert "#projSearch" in trecho and "#doneSearch" in trecho
    assert 'new Event("input", { bubbles: true })' in trecho, "limpar tem de disparar a busca"


# ------------------------------------------------------------------ R4
def test_app_aberto_avisa_uma_vez_por_dia(monkeypatch, tmp_path):
    from app import license as lic
    from app import registro_de_uso as reg

    monkeypatch.setattr(reg, "LOG_PATH", tmp_path / "aberturas.jsonl")
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(reg, "dados_da_maquina", lambda: {"device": "D", "versao": "5.0.46"})
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ATIVAVID_SEM_PING_DIARIO", raising=False)
    eventos = []
    monkeypatch.setattr(lic, "_http_rpc", lambda payload, fn="x": (eventos.append(payload.get("p_device_id")) or (200, {})))
    dormidas = []

    class _Chega(Exception):
        pass

    def _sleep(s):
        dormidas.append(s)
        if len(dormidas) >= 2:
            raise _Chega()

    monkeypatch.setattr(reg.time, "sleep", _sleep)
    reg.registrar_abertura()
    for t in threading.enumerate():
        if t.name == "registro-abertura":
            t.join(timeout=10)
    assert dormidas[0] == reg.INTERVALO_DIARIO_S == 86400
    assert len(eventos) == 2, "abertura + um aviso diario antes de 'dormir' de novo"
    linhas = [json.loads(x) for x in (tmp_path / "aberturas.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [ln["evento"] for ln in linhas] == ["abriu", "diario"]


def test_sob_pytest_nao_fica_dormindo():
    src = (REPO / "app" / "registro_de_uso.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PYTEST_CURRENT_TEST")' in src
