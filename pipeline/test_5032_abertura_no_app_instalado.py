# -*- coding: utf-8 -*-
"""5.0.32: o registro de abertura passa a acontecer no app INSTALADO.

Print do painel de Licença (04/09): todos os clientes com 0 aberturas e
versão "—"; só a máquina do dono tinha 30. Ele: "nao ta salvando as
versoes dos outros clientes".

O único chamador de `registrar_abertura()` era o `main()` do
`desktop_server` — e o app instalado entra por `app/launcher.py`, que chama
`build_server()` direto e nunca passa pelo `main()`. O recurso da 4.27
nunca funcionou no app de verdade. As 30 aberturas do dono vinham de outra
entrada que passa pelo `main()` (servidores de laboratório/dev com a versão
do worktree — por isso batiam com cada release do dia).

Agora o registro mora em `build_server()`, por onde toda entrada passa.
E a coluna de status conta o que o admin quer saber (trial, mensal, anual,
vencido, bloqueado) em vez de "quanto trial sobra".
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DS = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
LN = (REPO / "app" / "launcher.py").read_text(encoding="utf-8")
RU = (REPO / "app" / "registro_de_uso.py").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_registro_mora_no_caminho_que_o_launcher_usa():
    i = DS.index("def build_server(")
    fim = DS.index("\ndef main(", i)
    assert "registrar_abertura()" in DS[i:fim], (
        "voltou para o main(), que o app instalado nao usa")
    assert "ds.build_server(" in LN, "o launcher deixou de passar pelo build_server"


def test_o_main_nao_registra_duas_vezes():
    i = DS.index("\ndef main(")
    assert "registrar_abertura()" not in DS[i:], (
        "rodar pelo main() registraria a mesma abertura duas vezes")


def test_o_aviso_ao_servidor_nao_desiste_no_primeiro_erro(monkeypatch):
    """Com e-mail, o app tentava `p_email` e so caia no jeito antigo no 404.
    Um 401 (JWT vencido numa maquina bloqueada) perdia a abertura."""
    from app import registro_de_uso as ru
    from app import license as lic

    chamadas = []

    def falso(payload, fn=""):
        chamadas.append(dict(payload))
        return (401, {"error": "jwt"}) if "p_email" in payload else (200, {"ok": True})
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_http_rpc", falso)
    ru._avisar_servidor({"device": "d", "versao": "5.0.32", "email": "x@y"})
    assert len(chamadas) == 2, "desistiu no 401 sem tentar o jeito antigo"
    assert "p_email" not in chamadas[1]


def test_com_sucesso_nao_manda_duas_vezes(monkeypatch):
    from app import registro_de_uso as ru
    from app import license as lic

    chamadas = []
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "_http_rpc",
                        lambda payload, fn="": chamadas.append(1) or (200, {"ok": True}))
    ru._avisar_servidor({"device": "d", "versao": "5.0.32", "email": "x@y"})
    assert len(chamadas) == 1


def _plano(m, dono):
    from app.license_admin import _plano_da_maquina
    return _plano_da_maquina(m, dono)


def test_status_anual_para_quem_pagou_um_ano():
    p = _plano({"bloqueado": False, "trialDias": 0},
               {"validoAte": "2027-09-03T22:00:36+00:00",
                "liberadoEm": "2026-09-03T22:00:36+00:00"})
    assert p["tipo"] == "licenca" and p["rotulo"] == "anual", p
    assert p["ate"] == "2027-09-03"


def test_status_mensal():
    p = _plano({"bloqueado": False}, {"validoAte": "2026-10-04T00:00:00+00:00",
                                      "liberadoEm": "2026-09-04T00:00:00+00:00"})
    assert p["rotulo"] == "mensal"


def test_trial_acabado_so_aparece_para_quem_nao_pagou():
    """O caso do print: trial acabou, mas a conta e anual — o status e anual."""
    pago = _plano({"bloqueado": False, "trialDias": -3},
                  {"validoAte": "2027-08-27T01:36:49+00:00",
                   "liberadoEm": "2026-08-27T01:36:49+00:00"})
    assert pago["tipo"] == "licenca"
    sem = _plano({"bloqueado": False, "trialDias": -3}, {})
    assert sem["tipo"] == "trial_fim"


def test_bloqueado_vence_tudo():
    p = _plano({"bloqueado": True, "trialDias": 5},
               {"validoAte": "2027-01-01T00:00:00+00:00"})
    assert p["tipo"] == "bloqueado"


def test_vencido():
    p = _plano({"bloqueado": False}, {"validoAte": "2025-01-01T00:00:00+00:00",
                                      "liberadoEm": "2024-01-01T00:00:00+00:00"})
    assert p["tipo"] == "vencido"


def test_a_tela_mostra_status_e_nao_trial():
    assert '<th class="col-trial">Status</th>' in SJS
    assert "const status = (m) =>" in SJS
    assert "trial(m)" not in SJS, "a coluna antiga ainda e usada"
