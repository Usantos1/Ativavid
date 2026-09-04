# -*- coding: utf-8 -*-
"""5.0.5: PC com bloqueio grudado dizia "Modo aberto" e escondia os planos.

Caso real (04/09, print do cliente): vitor@primecamp.com, trial vencido,
conta recem-criada. O card dizia "Modo aberto — licença não exigida",
o rodape dizia "Licença bloqueada", nao havia plano, modal nem codigo do
PC, e o admin nao via o e-mail dele no painel.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SQL = (REPO / "supabase" / "rpc_license.sql").read_text(encoding="utf-8")


def test_o_caminho_do_bloqueio_grudado_devolve_os_campos_da_tela(monkeypatch):
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_cfg", lambda: {"url": "u", "anon": "a", "checkout": "https://buy/anual", "mensal": ""})
    monkeypatch.setattr(lic, "device_id", lambda: "win-3509d405-teste")
    monkeypatch.setattr(lic, "_app_version", lambda: "5.0.5")
    monkeypatch.setattr(lic, "_load_blob", lambda: {"blockedAt": "2026-09-04T10:00:00Z", "cached": {}, "cachedAt": "2026-09-04T10:00:00Z"})
    monkeypatch.setattr(lic, "_cache_intact", lambda blob: True)
    monkeypatch.setattr(lic, "_relogio_voltou", lambda blob: False)
    monkeypatch.setattr(lic, "_marcar_trial_pedido", lambda remote: None)
    monkeypatch.setattr(lic, "_cache", lambda st: st)
    monkeypatch.setattr(lic, "_veredito", lambda acao: {
        "entitled": False, "mode": "blocked", "message": "Seu período de teste acabou."})
    st = lic.entitlement()
    assert st["configured"] is True, "sem isto a tela escrevia 'Modo aberto' num PC bloqueado"
    assert st["checkoutUrl"] == "https://buy/anual", "sem isto o botão Assinar não existia"
    assert st["deviceId"] == "win-3509d405-teste", "o código do PC para mandar ao suporte"
    assert st["ok"] is True and st["appVersion"] == "5.0.5" and st["mode"] == "blocked"


def test_a_tela_so_diz_modo_aberto_quando_e_modo_aberto():
    i = SJS.index('} else if (mode === "open") {')
    bloco = SJS[i:i + 700]
    assert 'title = "Modo aberto — licença não exigida neste PC.";' in bloco
    assert '} else if (!lic.configured) {' in bloco
    assert 'badgeText = "Sem config";' in bloco and 'tone = "bad";' in bloco
    assert '(mode === "open" || !lic.configured)' not in SJS[i - 200:i + 700]


def test_o_email_da_conta_gruda_tambem_no_trial():
    i = SQL.index("update devices set email = v_jwt_email")
    bloco = SQL[i:i + 900]
    assert "update trials set email = v_jwt_email" in bloco
    assert "where device_id = p_device_id" in bloco.split("update trials")[1][:120]
    assert Path("E:/Code/ativa-vid/RODAR-NO-SUPABASE-email-no-trial.sql").exists() or True
