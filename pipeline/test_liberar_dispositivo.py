# -*- coding: utf-8 -*-
"""Liberar acesso pelo ID do dispositivo, sem conta e sem chave digitada.

É o fluxo real de venda: o cliente lê o ID na tela de Licença, manda para o
admin, e depois de liberado clica em Atualizar. Antes disso o admin só sabia
criar chave ATIV- (que o cliente tinha de digitar) ou liberar por e-mail
(que exige conta).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license_admin as la  # noqa: E402

RPC_ADMIN = (REPO / "supabase" / "rpc_admin.sql").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_rpc_tem_a_acao():
    assert "p_action = 'grant_device'" in RPC_ADMIN


def test_rpc_exige_device_id():
    trecho = RPC_ADMIN[RPC_ADMIN.index("p_action = 'grant_device'"):]
    trecho = trecho[:trecho.index("p_action = 'release_device'")]
    assert "device_id_required" in trecho


def test_rpc_soma_em_vez_de_sobrescrever():
    """Renovar antes de vencer não pode encurtar o que o cliente já pagou —
    mesmo defeito que o account_access teve."""
    trecho = RPC_ADMIN[RPC_ADMIN.index("p_action = 'grant_device'"):]
    trecho = trecho[:trecho.index("p_action = 'release_device'")]
    assert "greatest(v_row.valid_until, now())" in trecho


def test_rpc_vincula_o_device_a_licenca():
    """Sem o vínculo em devices, o ativavid_license não enxerga a liberação."""
    trecho = RPC_ADMIN[RPC_ADMIN.index("p_action = 'grant_device'"):]
    trecho = trecho[:trecho.index("p_action = 'release_device'")]
    assert "insert into devices" in trecho
    assert "on conflict (device_id) do update" in trecho


def test_helper_recusa_device_vazio():
    out = la.grant_device(device_id="   ", days=30)
    assert out["ok"] is False
    assert out["error"] == "device_id_required"


def test_endpoint_aceita_grant():
    trecho = SERVER[SERVER.index('if path == "/api/admin/devices"'):]
    trecho = trecho[:trecho.index('if path == "/api/license/refresh"')]
    assert 'action == "grant"' in trecho
    assert "la.grant_device(" in trecho


def test_endpoint_exige_admin():
    trecho = SERVER[SERVER.index('if path == "/api/admin/devices"'):]
    trecho = trecho[:trecho.index('if path == "/api/license/refresh"')]
    assert "au.require_admin()" in trecho
    i_admin = trecho.index("au.require_admin()")
    i_grant = trecho.index("la.grant_device(")
    assert i_admin < i_grant, "gate de admin depois da ação"


def test_ui_tem_o_dialogo_e_os_botoes():
    assert 'id="dlgLicDevice"' in HTML
    assert 'id="adminDevId"' in HTML
    assert 'id="btnAdminGrantDevice"' in HTML
    assert 'id="btnLicDeviceOpen"' in HTML
    assert "btnAdminGrantDevice" in JS
    assert '"/api/admin/devices"' in JS
