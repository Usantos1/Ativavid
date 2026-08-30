# -*- coding: utf-8 -*-
"""Registro de aberturas e o contato do dono da solucao.

Pedido de 30/08: "todo mundo que baixar e abrir gerar log pra gente
bloquear o computador em caso de compartilhamento ilegal" e "colocar o
numero da Prime camp como dona da solucao e suporte ... pode deixar bem
escondido esse numero, apenas pra quem for pagar".

O log tem duas pontas porque uma so nao serve: a LOCAL funciona sem
internet e sem servidor (e o arquivo que o suporte pede), e a do SERVIDOR
so liga quando o SQL de `supabase/registro_de_uso.sql` for aplicado — ate
la o aviso e ignorado sem quebrar nada.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import registro_de_uso as reg  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SQL = (REPO / "supabase" / "registro_de_uso.sql").read_text(encoding="utf-8")


def test_a_abertura_vira_uma_linha(tmp_path, monkeypatch):
    monkeypatch.setattr(reg, "LOG_PATH", tmp_path / "aberturas.jsonl")
    linha = reg.anotar("abriu")
    for campo in ("quando", "device", "maquina", "usuario", "so", "versao",
                  "licenca", "evento"):
        assert campo in linha, campo
    assert len(reg.ler()) == 1


def test_o_log_nao_cresce_para_sempre(tmp_path, monkeypatch):
    """E arquivo para o suporte ler, nao banco de dados."""
    monkeypatch.setattr(reg, "LOG_PATH", tmp_path / "aberturas.jsonl")
    monkeypatch.setattr(reg, "LIMITE_BYTES", 2000)
    for _ in range(80):
        reg.anotar("abriu")
    assert (tmp_path / "aberturas.jsonl").stat().st_size <= 6000


def test_pasta_sem_permissao_nao_derruba_a_abertura(tmp_path, monkeypatch):
    """Registro de uso nao vale um app que nao abre."""
    monkeypatch.setattr(reg, "LOG_PATH", tmp_path / "nao" / "existe" / "x.jsonl")
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("sem permissao")))
    assert reg.anotar("abriu")["evento"] == "abriu"


def test_o_aviso_ao_servidor_nao_bloqueia_nem_derruba(monkeypatch):
    """Se a funcao ainda nao existe no Supabase, o 404 e ignorado."""
    from app import license as lic

    chamou = {}

    def _falha(payload, fn="ativavid_license"):
        chamou["fn"] = fn
        raise RuntimeError("404")

    monkeypatch.setattr(lic, "_http_rpc", _falha)
    monkeypatch.setattr(lic, "configured", lambda: True)
    reg._avisar_servidor({"device": "X", "versao": "1", "maquina": "M"})
    assert chamou["fn"] == "ativavid_open", "tem de ser funcao propria"


def test_o_aviso_nao_sai_sem_supabase_configurado(monkeypatch):
    from app import license as lic

    monkeypatch.setattr(lic, "configured", lambda: False)
    monkeypatch.setattr(lic, "_http_rpc", lambda *a, **k: 1 / 0)
    reg._avisar_servidor({"device": "X"})   # nao pode nem tentar


def test_o_app_registra_ao_abrir():
    src = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    i = src.index("def main() -> None:")
    bloco = src[i:i + 1200]
    assert "registrar_abertura()" in bloco
    # antes de servir, e em segundo plano
    assert bloco.index("registrar_abertura()") < bloco.index("serve_forever")
    assert "threading.Thread" in (REPO / "app" / "registro_de_uso.py").read_text(
        encoding="utf-8")


def test_o_sql_do_servidor_esta_no_repo():
    assert "create table if not exists public.aberturas" in SQL
    assert "create or replace function public.ativavid_open" in SQL
    assert "blocked_at" in SQL
    assert "ativavid_device_blocked" in SQL
    # bloquear/desbloquear nao pode ficar aberto para o app do cliente
    assert "revoke execute on function public.ativavid_block_device" in SQL


# ------------------------------------------------------------- o suporte

def test_o_numero_so_aparece_para_quem_paga():
    i = JS.index("function renderSuporte(")
    bloco = JS[i:i + 900]
    assert 'modo === "licensed" || modo === "account"' in bloco
    assert "lic.entitled" in bloco
    assert "box.hidden = !pago" in bloco
    # e o cartao nasce escondido no HTML
    i = HTML.index('id="licSuporte"')
    assert "hidden" in HTML[i:i + 120]


def test_o_numero_e_o_dono_estao_certos():
    i = JS.index("const SUPORTE = {")
    bloco = JS[i:i + 260]
    assert '"Prime Camp"' in bloco
    assert "5519987680453" in bloco, "faltou o 55 do Brasil no link do WhatsApp"
    assert "(19) 98768-0453" in bloco


def test_a_mensagem_ja_leva_a_maquina():
    """E a primeira coisa que o suporte pergunta e o cliente nao sabe
    onde achar."""
    i = JS.index("function renderSuporte(")
    bloco = JS[i:i + 1200]
    assert "lic.deviceId" in bloco
    assert "wa.me/" in bloco


def test_renderLicense_chama_o_suporte():
    i = JS.index("function renderLicense(lic) {")
    assert "renderSuporte(lic);" in JS[i:i + 200]
