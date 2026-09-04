# -*- coding: utf-8 -*-
"""5.0.30: "Verificar" dizia "sem atualização" com a versão nova publicada.

Print dele (04/09), na 5.0.27, com a 5.0.29 no ar há minutos:

    Você está em 5.0.27 — sem atualização.

O `check_update` ENTRAVA no ramo do Supabase porque comparou e viu que a
política era mais nova que a instalada — e então copiava `updateAvailable`
da flag gravada no cache da licença, calculada antes da release, False.
Sabia que havia versão nova e dizia que não.

Dois consertos:
  1. `updateAvailable` sai da comparação que acabou de ser feita;
  2. `/api/update/check` renova a licença antes de responder — quem clicou
     em Verificar quer a resposta de agora, não a do cache de 30 minutos
     (que também escondia o `min_version` recém-subido).
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import update_check as uc  # noqa: E402

SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


def _com_politica(monkeypatch, *, atual, politica, repo="Usantos1/Ativavid"):
    from app import license as lic

    monkeypatch.setattr(uc, "current_version", lambda: atual)
    monkeypatch.setattr(uc, "configured_repo", lambda: repo)
    monkeypatch.setattr(lic, "configured", lambda: True)
    monkeypatch.setattr(lic, "public_status", lambda: {"update": politica})
    return uc.check_update()


def test_versao_nova_no_cache_com_flag_velha_ainda_e_atualizacao(monkeypatch):
    """O caso do print: latest 5.0.28, instalada 5.0.27, flag False."""
    r = _com_politica(monkeypatch, atual="5.0.27", politica={
        "latestVersion": "5.0.28", "updateAvailable": False, "force": False,
        "downloadUrl": "https://x/Instalar.ATIVAVID.exe"})
    assert r["source"] == "supabase"
    assert r["updateAvailable"] is True, "sabe que há versão nova e diz que não"
    assert "5.0.28" in r["message"] and "sem atualização" not in r["message"]


def test_mesma_versao_continua_sem_atualizacao(monkeypatch):
    """Sem novidade no Supabase o `check_update` cai no ramo do GitHub, que
    consulta a internet DE VERDADE — e o "latest" real anda: este teste
    passou na 5.0.30 e quebrou na 5.0.31 porque a 5.0.30 tinha sido
    publicada no meio. Aqui o GitHub fica fora: o que se prova é que a
    politica igual a instalada nao inventa atualizacao."""
    r = _com_politica(monkeypatch, atual="5.0.29", politica={
        "latestVersion": "5.0.29", "updateAvailable": False, "force": False})
    assert r["source"] != "supabase", "politica igual nao devia mandar"

    r2 = _com_politica(monkeypatch, atual="5.0.29", politica={
        "latestVersion": "5.0.29", "updateAvailable": False, "force": False},
        repo="")
    assert r2["updateAvailable"] is False


def test_force_no_cache_continua_obrigatorio(monkeypatch):
    r = _com_politica(monkeypatch, atual="5.0.27", politica={
        "latestVersion": "5.0.29", "updateAvailable": False, "force": True,
        "message": "Atualize."})
    assert r["force"] is True and r["updateAvailable"] is True


def test_verificar_renova_a_licenca_antes_de_responder():
    i = SRV.index('if path == "/api/update/check":')
    bloco = SRV[i:i + 700]
    assert "lic.entitlement(refresh=True)" in bloco, (
        "Verificar responde com o cache de 30 min — min_version novo fica invisível")
    assert "except Exception" in bloco, "sem rede, Verificar não pode explodir"
