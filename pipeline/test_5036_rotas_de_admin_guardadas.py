# -*- coding: utf-8 -*-
"""Toda rota /api/admin/* passa pela guarda de admin — e vai continuar.

Auditoria de 04/09 (depois de dois casos de tela de dono aberta em PC de
cliente): as oito rotas de admin do `local_server` chamam `require_admin()`
antes de responder. Este teste lê o arquivo e cobra isso de qualquer rota
que nascer com o prefixo — a guarda por exclusão que
[[licenca-gate-fail-closed]] já pede para as rotas de licença.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


def _rotas_admin():
    for m in re.finditer(r'if path == "(/api/admin/[^"]+)":', SRV):
        bloco = SRV[m.end(): m.end() + 900]
        fim = bloco.find("\n        if path ==")
        yield m.group(1), (bloco if fim < 0 else bloco[:fim])


def test_ha_rotas_de_admin():
    assert len(list(_rotas_admin())) >= 8


def test_toda_rota_de_admin_confere_a_sessao_no_servidor():
    sem = [r for r, bloco in _rotas_admin()
           if "require_admin()" not in bloco and "_e_admin()" not in bloco]
    assert not sem, f"rota(s) de admin sem guarda: {sem}"


def test_a_guarda_responde_403_e_nao_dados():
    for rota, bloco in _rotas_admin():
        i = bloco.find("require_admin()")
        if i < 0:
            i = bloco.find("_e_admin()")
        assert "403" in bloco[i:i + 400], f"{rota}: a guarda existe mas não recusa"
