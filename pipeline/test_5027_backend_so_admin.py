# -*- coding: utf-8 -*-
"""5.0.27: o cliente não pode ver nem trocar o backend.

Ele, com o print da tela de um cliente (04/09): "Cliente nao pode ver isso
caralho — Avançado: Supabase e teste de desempenho".

Estavam ali, editáveis, a URL do Supabase, a anon key e o link de checkout.
Trocar qualquer um deles quebra a licença daquela máquina, e o dono nem
saberia por quê.

Duas camadas, porque esconder na tela não é o mesmo que proteger:
  1. o bloco nasce `hidden` no HTML — se o JS falhar antes de rodar, o
     cliente continua sem ver; mostrar é que exige ser admin;
  2. a rota `/api/settings` recusa os três campos sem sessão de admin.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.local_server import CAMPOS_DO_BACKEND, _e_admin  # noqa: E402

HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


def _rota_post_settings() -> str:
    """O handler do POST. `/api/settings` aparece DUAS vezes no arquivo (GET
    e POST) e pegar a primeira mede o handler errado."""
    i = SRV.index('if path == "/api/settings":')
    j = SRV.index('if path == "/api/settings":', i + 10)
    return SRV[j:j + 1100]


def test_o_bloco_nasce_escondido_no_html():
    """O estado de PARTIDA é oculto: JS que não roda não pode expor."""
    i = HTML.index('id="sysBackendCfg"')
    assert "hidden" in HTML[i:i + 40], "nasce visível — basta o JS falhar"


def test_os_tres_campos_estao_dentro_do_bloco():
    i = HTML.index('<div id="sysBackendCfg"')
    fim = HTML.index("<h4>Reinstalar o aplicativo</h4>", i)
    bloco = HTML[i:fim]
    for campo in ("supabaseUrlInput", "supabaseAnonInput", "checkoutUrlInput",
                  "btnSaveLicenseCfg"):
        assert campo in bloco, f"`{campo}` ficou fora do bloco escondido"


def test_so_o_admin_ve():
    i = SJS.index("function ajustarAvancadoParaOPerfil()")
    corpo = SJS[i:i + 700]
    assert "state.auth && state.auth.isAdmin" in corpo
    assert "bloco.hidden = !admin" in corpo
    j = SJS.index("async function loadSistema() {")
    assert "ajustarAvancadoParaOPerfil();" in SJS[j:j + 200], (
        "a tela de Configuracoes abre sem aplicar o perfil")


def test_o_subtitulo_nao_anuncia_o_que_o_cliente_nao_tem():
    assert "Reinstalar e teste de desempenho" in HTML, (
        "o subtítulo ainda promete Supabase para quem não pode vê-lo")


def test_a_rota_recusa_os_campos_do_backend_sem_admin():
    bloco = _rota_post_settings()
    assert "CAMPOS_DO_BACKEND" in bloco and "_e_admin()" in bloco
    assert "403" in bloco, "recusar tem de ser recusa, não silêncio"
    assert CAMPOS_DO_BACKEND == ("supabaseUrl", "supabaseAnonKey", "checkoutUrl")


def test_erro_ao_checar_conta_como_nao_admin(monkeypatch):
    """A guarda fecha, não abre."""
    from app import auth as au

    def explode():
        raise RuntimeError("sem rede")
    monkeypatch.setattr(au, "ensure_session", explode)
    assert _e_admin() is False


def test_admin_de_verdade_passa(monkeypatch):
    from app import auth as au

    monkeypatch.setattr(au, "ensure_session", lambda: {"isAdmin": True})
    assert _e_admin() is True
    monkeypatch.setattr(au, "ensure_session", lambda: {"isAdmin": False})
    assert _e_admin() is False


def test_as_outras_configuracoes_continuam_livres():
    """A guarda é só para os três campos — pasta de projetos, perfil de
    desempenho e o resto continuam salvando sem conta."""
    bloco = _rota_post_settings()
    assert "proibido = [k for k in CAMPOS_DO_BACKEND if k in body]" in bloco
    assert "if proibido and not _e_admin():" in bloco
