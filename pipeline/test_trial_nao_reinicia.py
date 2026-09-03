# -*- coding: utf-8 -*-
r"""Apagar arquivo nao da trial novo.

O trial e de 7 dias POR DEVICE (`v_days int := 7` no rpc_license.sql), e o
device e o `deviceId`. Se apagar o `license.json` gerasse um id novo, o
trial seria infinito: desinstala, apaga, mais 7 dias, para sempre.

A ordem que sustenta isso: license.json -> registro do Windows ->
MachineGuid -> (so entao) um uuid novo. Na maquina deste usuario o id
guardado e `win-...`, ou seja, veio do MachineGuid — que sobrevive a
desinstalar o app, apagar a pasta e limpar o registro do usuario.

Aqui nada toca o registro de verdade: as tres portas sao trocadas por
dubles. Chamar `device_id()` sem isso ESCREVE em HKCU\Software\ATIVAVID.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import license as lic  # noqa: E402


@pytest.fixture()
def maquina(tmp_path, monkeypatch):
    """Um PC de mentira: license.json em tmp e registro em memoria."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")
    reg: dict[str, str] = {}
    monkeypatch.setattr(lic, "_reg_device_id", lambda: reg.get("id"))
    monkeypatch.setattr(lic, "_reg_set_device_id",
                        lambda d: reg.__setitem__("id", d))
    monkeypatch.setattr(lic, "_machine_guid", lambda: "win-GUID-DA-MAQUINA")
    return tmp_path / "license.json", reg


def test_apagar_o_arquivo_nao_da_trial_novo(maquina):
    arquivo, _reg = maquina
    primeiro = lic.device_id()
    arquivo.unlink()
    assert lic.device_id() == primeiro, "id novo = 7 dias novos, para sempre"


def test_apagar_arquivo_E_registro_ainda_nao_da_trial_novo(maquina):
    arquivo, reg = maquina
    primeiro = lic.device_id()
    arquivo.unlink()
    reg.clear()
    assert lic.device_id() == primeiro, "o MachineGuid e a ultima ancora"
    assert primeiro == "win-GUID-DA-MAQUINA"


def test_o_registro_segura_quando_nao_ha_machineguid(maquina, monkeypatch):
    """Sem MachineGuid o id caia num uuid guardado so no arquivo."""
    arquivo, reg = maquina
    monkeypatch.setattr(lic, "_machine_guid", lambda: None)
    primeiro = lic.device_id()
    arquivo.unlink()
    assert lic.device_id() == primeiro
    assert reg.get("id") == primeiro


def test_o_trial_so_e_pedido_uma_vez_por_maquina():
    """'trial' CRIA trial no servidor: pedir a cada abertura renovaria os 7
    dias de quem ja venceu."""
    s = (REPO / "app" / "license.py").read_text(encoding="utf-8")
    # `_veredito` e o `_call` + bloqueio por maquina (4.39): a REGRA que
    # este teste guarda e "pedir trial uma vez so", nao o nome da funcao.
    # 4.94: a regra mora em `_acao_inicial` (e a recusa "crie sua conta"
    # NAO gasta o pedido — test_trial_so_com_cadastro cobre isso).
    assert 'return "trial" if not blob.get("trialAskedAt") else "status"' in s
    assert 'blob["trialAskedAt"] = _utc()' in s
    assert 'remote = _veredito(_acao_inicial(blob))' in s


def test_o_servidor_da_sete_dias_e_conta_do_inicio():
    sql = (REPO / "supabase" / "rpc_license.sql").read_text(encoding="utf-8")
    assert "v_days int := 7;" in sql
    # a conta e sobre started_at, nao sobre "ultimo acesso"
    assert "v_trial.started_at + make_interval(days => v_days) > now()" in sql
