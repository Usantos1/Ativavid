# -*- coding: utf-8 -*-
"""Guardas da auditoria de 31/08 — os consertos da Fase 1a.

Seis auditorias paralelas (dados da máquina, exceções/arquivos, licença,
front-end, paridade de motores, suíte) num dia. Este arquivo trava os
consertos de código Python; os visuais têm arquivo próprio.
"""
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
AE = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")
LIC = (REPO / "app" / "license.py").read_text(encoding="utf-8")


# ---- hardlinks: a família do WinError 32 ---------------------------------

def test_temp_install_nao_escreve_atraves_do_hardlink(tmp_path):
    """O "Liberar espaço" liga edit/cut e public/cut por hardlink; o apply
    copiava POR CIMA do live e truncava o inode compartilhado — a fonte da
    verdade virava o temporário não validado, para sempre, calado."""
    from app.apply_execute import _temp_install

    fonte = tmp_path / "cut.mp4"
    fonte.write_bytes(b"CORTE-BOM" * 100)
    live = tmp_path / "public_cut.mp4"
    os.link(fonte, live)                     # o que o Liberar espaço faz
    novo = tmp_path / "cut.apply.tmp.mp4"
    novo.write_bytes(b"TEMPORARIO-NAO-VALIDADO")
    with _temp_install([(live, novo)]):
        assert live.read_bytes() == b"TEMPORARIO-NAO-VALIDADO"
        # a FONTE não pode ter mudado junto
        assert fonte.read_bytes() == b"CORTE-BOM" * 100
    assert live.read_bytes() == b"CORTE-BOM" * 100, "restore devolve o live"
    assert fonte.read_bytes() == b"CORTE-BOM" * 100


def test_promote_nao_abre_janela_sem_arquivo():
    """unlink antes do replace: se o replace falhar, o projeto fica sem o
    final. os.replace sozinho ja substitui atomicamente."""
    i = AE.index("def _promote_file(")
    bloco = AE[i:AE.index("\ndef ", i + 10)]
    assert "dest.unlink()" not in bloco
    assert "src.replace(dest)" in bloco


def test_arquivo_em_uso_tem_frase_propria():
    from app.apply_execute import motivo_do_apply

    frase = motivo_do_apply("[WinError 32] O arquivo já está sendo usado")
    assert frase and "outro programa" in frase


def test_canario_nao_copia_sobre_o_proprio_inode():
    s = (REPO / "pipeline" / "canary_run.py").read_text(encoding="utf-8")
    i = s.index('pub_cut = edit_dir / "remotion" / "public" / "cut.mp4"')
    bloco = s[i:i + 600]
    assert "os.path.samefile(cut, pub_cut)" in bloco


# ---- escrita atômica de estado -------------------------------------------

def test_settings_e_canary_gravam_atomico():
    st = (REPO / "app" / "settings_store.py").read_text(encoding="utf-8")
    i = st.index("def save_settings(")
    bloco = st[i:i + 2600]
    assert "os.replace(tmp, SETTINGS_PATH)" in bloco

    oc = (REPO / "app" / "overlay_canary.py").read_text(encoding="utf-8")
    j = oc.index("def save_state(")
    bloco = oc[j:j + 1400]
    assert "os.replace(_tmp, STATE_PATH)" in bloco
    # e o read-modify-write dos escritores concorrentes passa pela trava
    assert oc.count("with _trava_do_estado():") >= 3


def test_canary_state_sobrevive_ao_processo_morto(tmp_path, monkeypatch):
    monkeypatch.setenv("ATIVAVID_CANARY_STATE", str(tmp_path / "canary.json"))
    import importlib

    from app import overlay_canary as oc
    importlib.reload(oc)
    st = oc.save_state({"paused": True, "pausedReason": "teste",
                        "pausedAt": "2026-08-31T20:00:00-03:00"})
    assert oc.load_state()["paused"] is True
    # arquivo .tmp nunca fica para tras
    assert not (tmp_path / "canary.json.tmp").exists()
    importlib.reload(oc)   # volta ao caminho real para os outros testes


def test_pausa_fossil_e_limpa_ao_voltar_ao_canario(tmp_path, monkeypatch):
    """Pausa sem pausedAt e de antes do codigo que grava a data — um
    TRUE_PEAK de agosto nao pode bloquear um canario de dezembro."""
    monkeypatch.setenv("ATIVAVID_CANARY_STATE", str(tmp_path / "canary.json"))
    import importlib

    from app import overlay_canary as oc
    importlib.reload(oc)
    oc.save_state({"paused": True, "pausedReason": "TRUE_PEAK -0.9>-1.0"})
    monkeypatch.setattr("app.overlay_path.overlay_rollout", lambda: "canary")
    assert oc.canary_allows_attempt() is True
    assert oc.load_state()["paused"] is False
    # pausa COM data e recente continua valendo
    oc.save_state({"paused": True, "pausedReason": "x",
                   "pausedAt": "2026-08-31T00:00:00-03:00"})
    assert oc.canary_allows_attempt() is False
    importlib.reload(oc)


# ---- honestidade das respostas -------------------------------------------

def test_reverter_sem_versao_nao_diz_ok(tmp_path):
    from app import quick_corrections as qc

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / qc.FILE_NAME).write_text(json.dumps({
        "dirty": {"captions": True}, "revertVersionId": None,
    }), encoding="utf-8")
    r = qc.discard(edit)
    assert r["ok"] is False and "versão" in r["error"]
    # sem nada para reverter, ok continua ok (não vira erro gratuito)
    (edit / qc.FILE_NAME).write_text(json.dumps({"dirty": {}}), encoding="utf-8")
    assert qc.discard(edit)["ok"] is True


def test_delivery_pack_grava_atomico_e_loga():
    s = (REPO / "app" / "delivery_pack.py").read_text(encoding="utf-8")
    i = s.index('state["deliveryPack"]')
    bloco = s[i:i + 900]
    assert "os.replace(tmp, state_p)" in bloco
    assert "[warn] deliveryPack" in bloco


# ---- leituras e sondas ----------------------------------------------------

def test_edl_do_pipeline_tolera_BOM():
    """O PowerShell grava BOM por padrao; o EDL pode vir de sessao da skill.
    Cinco leituras usavam utf-8 puro e a Fase 2 morria seca."""
    assert 'read_text(encoding="utf-8")' not in RF.replace(
        'lock_path.read_text(encoding="utf-8")', "").replace(
        'marca.read_text(encoding="utf-8")', "").replace(
        '.read_text(encoding="utf-8").strip())', "")


def test_sondas_tem_timeout():
    fp = (REPO / "helpers" / "ffprobe_util.py").read_text(encoding="utf-8")
    assert "timeout=60" in fp
    rd = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
    assert rd.count("timeout=60") >= 4, "as sondas do render.py penduravam"


# ---- licença --------------------------------------------------------------

def test_gateway_llm_e_biblioteca_sao_gateados():
    """Bloqueado nao pode usar o app como proxy de LLM nem escrever na
    Biblioteca. As leituras da biblioteca sao GET e o gate so roda no POST."""
    from app.license import gate_free

    assert not gate_free("/v1/chat/completions")
    assert not gate_free("/api/library/add")
    assert not gate_free("/api/library/upload")
    # as saidas do bloqueio continuam livres
    assert gate_free("/api/license/refresh")
    assert gate_free("/api/auth/login")


def test_cache_sem_segredo_falha_fechado(monkeypatch):
    """O fallback antigo era a anon key — PUBLICA — e a assinatura virava
    forjavel num build que burlasse o build.ps1."""
    from app import license as lic
    from app import settings_store as ss

    monkeypatch.setattr(ss, "bundled_raw", lambda: {"supabaseAnonKey": "anon-publica"})
    monkeypatch.setattr(ss, "is_dev_install", lambda: False)
    assert lic._cache_key() is None
    assert lic._sign_cache({"cached": {"entitled": True}}) is None
    # em dev continua funcionando (la o cache nao protege nada mesmo)
    monkeypatch.setattr(ss, "is_dev_install", lambda: True)
    assert lic._cache_key() is not None


# ---- avisos que chegam ao card -------------------------------------------

def test_cobertura_fraca_chega_a_ficha(tmp_path):
    i = RF.index('_RENDER_META["legendaCobertura"]')
    assert "0.8 * duration" in RF[i - 400:i]
    assert '"legendaCobertura"' in RF[RF.index("for campo in ("):RF.index("for campo in (") + 300]

    from app.jobs_view import _aviso_de_trilha

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "timing.json").write_text(json.dumps({
        "legendaCobertura": "as legendas cobrem só até 12s de 24s — confira no editor",
    }), encoding="utf-8")
    job: dict = {}
    _aviso_de_trilha(job, edit)
    assert "12s de 24s" in job["legendaNota"]
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "j.legendaNota" in js


def test_sessao_expirada_chega_a_ficha(tmp_path):
    assert '_RENDER_META["legendaIA"]' in RF
    from app.jobs_view import _aviso_de_trilha

    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "timing.json").write_text(json.dumps({
        "legendaIA": "a legenda do post saiu do modelo pronto: a sessão expirou",
    }), encoding="utf-8")
    job: dict = {}
    _aviso_de_trilha(job, edit)
    assert "sessão" in job["legendaNota"]


# ---- higiene --------------------------------------------------------------

def test_sessions_cifra_quando_da(tmp_path, monkeypatch):
    """Cookies de sessao dao o Gemini/ChatGPT inteiro de quem os ler — mesmo
    tratamento DPAPI do service role. Texto plano legado continua lendo."""
    import app.local_server as ls
    from app import secret_store

    monkeypatch.setattr(ls, "SESSIONS_PATH", tmp_path / "sessions.json")
    monkeypatch.setattr(ls, "_LEGACY_SESSIONS", tmp_path / "nao-existe.json")
    monkeypatch.setattr(ls, "USER_DIR", tmp_path)
    ls.save_session_capture("gemini-web", [{"name": "sid", "value": "segredo"}])
    bruto = (tmp_path / "sessions.json").read_text(encoding="utf-8")
    if secret_store.available():
        assert "segredo" not in bruto, "cookie em texto puro no disco"
        assert '"dpapi"' in bruto
    lido = ls.load_sessions()
    assert lido["providers"]["gemini-web"]["cookies"][0]["value"] == "segredo"
    # legado plano segue valendo (nunca invalidar o legado)
    (tmp_path / "sessions.json").write_text(json.dumps(
        {"providers": {"x": {"cookies": []}}}), encoding="utf-8")
    assert "x" in ls.load_sessions()["providers"]


def test_biblioteca_sem_argumento_resolve_pelo_projectsRoot(tmp_path, monkeypatch):
    from app import broll_library as bl

    raiz = tmp_path / "ATIVAVID" / "Projetos"
    raiz.mkdir(parents=True)
    monkeypatch.setattr("app.settings_store.load_settings",
                        lambda: {"projectsRoot": str(raiz)})
    root = bl.library_root(None)
    assert root == raiz.parent / "Biblioteca", \
        "cair no Path.home() cria a Biblioteca fantasma do C: de novo"


def test_apply_task_encerrada_envelhece(tmp_path, monkeypatch):
    from app import apply_tasks as at

    idx = {"velha": {"status": "failed", "finishedAt": "2026-07-01T10:00:00",
                     "interrupted": True, "editDir": ""},
           "nova": {"status": "failed", "finishedAt": "2026-08-31T10:00:00",
                    "editDir": ""}}
    monkeypatch.setattr(at, "_load_index", lambda root: dict(idx))
    gravado = {}
    monkeypatch.setattr(at, "_save_index",
                        lambda root, tasks: gravado.update(tasks) or gravado.clear() or gravado.update(tasks))
    at.sweep_stale_applies(tmp_path)
    assert "velha" not in gravado and "nova" in gravado


def test_pillow_getdata_saiu():
    assert "getdata()" not in RF.replace("# ImageStat em vez de getdata()", "")
