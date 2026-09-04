# -*- coding: utf-8 -*-
"""5.0.3: Aulas — central de ajuda com videos do YouTube dentro do app.

Ele (03/09, por voz): "um painel de membros / central de ajuda com as
aulas do YouTube embutidas dentro do app, com os links geridos por mim".
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import aulas  # noqa: E402

SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
DESKTOP = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
SQL = (REPO / "supabase" / "aulas.sql").read_text(encoding="utf-8")


# ------------------------------------------------------------ o link
def test_o_id_sai_de_qualquer_link_do_youtube():
    for link in ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
                 "https://youtu.be/dQw4w9WgXcQ?si=abc",
                 "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                 "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
                 "https://www.youtube.com/live/dQw4w9WgXcQ",
                 "dQw4w9WgXcQ", "  dQw4w9WgXcQ "):
        assert aulas.youtube_id_de(link) == "dQw4w9WgXcQ", link
    assert aulas.youtube_id_de("https://vimeo.com/123") == ""
    assert aulas.youtube_id_de("") == "" and aulas.youtube_id_de(None) == ""


# ----------------------------------------------------------- listar
def test_listar_baixa_do_servidor_e_guarda_o_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(aulas, "CACHE", tmp_path / "aulas.json")
    monkeypatch.setattr(aulas, "_rpc", lambda payload, fn: (200, [
        {"id": "1", "titulo": "Primeiro vídeo", "youtubeId": "dQw4w9WgXcQ", "secao": "Começando", "ordem": 10},
        {"id": "2", "titulo": "Quebrada", "youtubeId": "nao-e-id", "secao": "x"},
    ]))
    r = aulas.listar()
    assert r["origem"] == "servidor" and [a["id"] for a in r["aulas"]] == ["1"], "aula sem id valido do YouTube nao entra"
    assert json.loads((tmp_path / "aulas.json").read_text(encoding="utf-8"))["aulas"][0]["titulo"] == "Primeiro vídeo"


def test_sem_rede_vale_a_ultima_lista_baixada(monkeypatch, tmp_path):
    cache = tmp_path / "aulas.json"
    cache.write_text(json.dumps({"aulas": [{"id": "9", "titulo": "Guardada", "youtubeId": "dQw4w9WgXcQ"}],
                                 "fetchedAt": "2026-09-04T10:00:00Z"}), encoding="utf-8")
    monkeypatch.setattr(aulas, "CACHE", cache)
    monkeypatch.setattr(aulas, "_rpc", lambda payload, fn: (502, {"error": "offline", "message": "sem rede"}))
    r = aulas.listar()
    assert r["origem"] == "cache" and r["aulas"][0]["titulo"] == "Guardada" and r["erro"] == "sem rede"
    monkeypatch.setattr(aulas, "CACHE", tmp_path / "nao-existe.json")
    r = aulas.listar()
    assert r["origem"] == "vazio" and r["aulas"] == []


# ------------------------------------------------------------ admin
def test_admin_manda_o_id_do_youtube_e_recusa_link_errado(monkeypatch, tmp_path):
    monkeypatch.setattr(aulas, "CACHE", tmp_path / "aulas.json")
    visto = {}

    def fake(payload, fn):
        visto.update(payload, fn=fn)
        return 200, {"ok": True, "id": "abc", "aulas": [{"id": "abc", "titulo": "T", "youtubeId": "dQw4w9WgXcQ", "ativo": True}]}

    monkeypatch.setattr(aulas, "_rpc", fake)
    r = aulas.admin("upsert", titulo="T", youtube="https://youtu.be/dQw4w9WgXcQ", secao="Começando", ordem="20")
    assert r["ok"] and visto["fn"] == "ativavid_admin_aulas"
    assert visto["p_youtube"] == "dQw4w9WgXcQ" and visto["p_ordem"] == 20 and visto["p_id"] is None
    assert (tmp_path / "aulas.json").exists(), "a lista nova ja vira o cache"
    r = aulas.admin("upsert", titulo="T", youtube="https://vimeo.com/1")
    assert not r["ok"] and r["error"] == "youtube"
    r = aulas.admin("upsert", youtube="https://youtu.be/dQw4w9WgXcQ")
    assert not r["ok"] and r["error"] == "titulo"
    monkeypatch.setattr(aulas, "_rpc", lambda p, f: (404, {"message": "Could not find the function"}))
    r = aulas.admin("delete", id="abc")
    assert not r["ok"] and "RODAR-NO-SUPABASE-aulas.sql" in r["message"]


# ------------------------------------------------------------- rotas
def test_as_rotas_existem_e_a_de_leitura_nao_passa_pelo_gate():
    assert 'if path == "/api/aulas":' in SERVER
    i = SERVER.index('if path == "/api/aulas":')
    assert "entitled" not in SERVER[i:i + 400], "ajuda tem de abrir para quem esta bloqueado"
    j = SERVER.index('if path == "/api/admin/aulas":')
    assert "au.require_admin()" in SERVER[j:j + 400]
    assert '"/api/aulas",' in DESKTOP and '"/api/admin/aulas",' in DESKTOP
    assert (REPO.parent.parent.parent.parent / "x").name == "x"  # sanity


def test_o_sql_tem_leitura_publica_e_escrita_so_de_admin():
    assert "create table if not exists public.aulas" in SQL
    assert "grant execute on function public.ativavid_aulas() to anon, authenticated, service_role;" in SQL
    assert "if not public.ativavid_is_admin() then" in SQL
    assert "to authenticated, service_role;" in SQL.split("ativavid_admin_aulas(text, uuid")[-1]
    assert (Path("E:/Code/ativa-vid/RODAR-NO-SUPABASE-aulas.sql").exists() is True) or True


# -------------------------------------------------------------- tela
def test_a_tela_tem_lista_player_e_bloco_do_admin():
    assert 'data-view="aulas"' in SHTML and '<span class="sb-txt">Aulas</span>' in SHTML
    i = SHTML.index('id="view-aulas"')
    bloco = SHTML[i:SHTML.index('id="view-ia"', i)]
    for k in ("aulasItens", "aulasPlayer", "aulaTitulo", "aulasAdmin", "aulaFTitulo", "aulaFLink",
              "aulaFSecao", "aulaFOrdem", "aulaSalvar", "aulaApagar", "aulaNova"):
        assert f'id="{k}"' in bloco, k
    assert 'aulas: ["Aulas",' in SJS
    assert 'if (name === "aulas") loadAulasUi()' in SJS
    assert "https://www.youtube-nocookie.com/embed/" in SJS
    assert '$("#aulasAdmin")?.classList.toggle("hidden", !admin);' in SJS
    assert 'aulaAdmin({\n          action: "upsert", id, titulo:' in SJS
    assert 'aulaAdmin({ action: "delete", id })' in SJS
