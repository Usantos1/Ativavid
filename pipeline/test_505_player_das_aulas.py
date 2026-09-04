# -*- coding: utf-8 -*-
"""5.0.5: player proprio nas Aulas (sem links do YouTube), minutagem e
descricao legivel.

Ele (04/09, print): "legenda fica uma merda e o player deve ser embedado
sem links clicaveis do YouTube e mostrar a minutagem da aula".
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import aulas  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SCSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")


# ---------------------------------------------------------- minutagem
def test_a_duracao_sai_da_pagina_do_video():
    assert aulas.duracao_no_html('... "lengthSeconds":"754", ...') == 754
    assert aulas.duracao_no_html('"approxDurationMs":"61500"') == 62
    assert aulas.duracao_no_html("nada") is None


def test_listar_poe_a_minutagem_do_cache_e_busca_o_que_falta(monkeypatch, tmp_path):
    cache = tmp_path / "aulas.json"
    cache.write_text(json.dumps({"duracoes": {"dQw4w9WgXcQ": 213}}), encoding="utf-8")
    monkeypatch.setattr(aulas, "CACHE", cache)
    monkeypatch.setattr(aulas, "_rpc", lambda p, f: (200, [
        {"id": "1", "titulo": "A", "youtubeId": "dQw4w9WgXcQ"},
        {"id": "2", "titulo": "B", "youtubeId": "AAAAAAAAAAA"},
    ]))
    pedidos = []

    class ThreadNaHora:
        def __init__(self, target=None, args=(), **k):
            self.t, self.a = target, args
        def start(self):
            self.t(*self.a)

    monkeypatch.setattr(aulas.threading, "Thread", ThreadNaHora)
    monkeypatch.setattr(aulas, "_duracao_youtube", lambda yid: pedidos.append(yid) or 95)
    # outro teste do mesmo processo pode ter deixado uma busca "em andamento"
    monkeypatch.setattr(aulas, "_DUR_EM_ANDAMENTO", False)
    r = aulas.listar()
    assert {a["id"]: a["duracaoSeg"] for a in r["aulas"]} == {"1": 213, "2": 0}, "a conhecida vem na hora"
    assert r["duracoesPendentes"] == 1 and pedidos == ["AAAAAAAAAAA"], "so busca a que falta"
    guardado = json.loads(cache.read_text(encoding="utf-8"))
    assert guardado["duracoes"] == {"dQw4w9WgXcQ": 213, "AAAAAAAAAAA": 95}, "cache une, nao apaga"
    assert guardado["aulas"][0]["titulo"] == "A", "a lista continua no mesmo arquivo"
    r = aulas.listar()
    assert [a["duracaoSeg"] for a in r["aulas"]] == [213, 95] and r["duracoesPendentes"] == 0


# ------------------------------------------------------------- tela
def test_o_player_e_proprio_e_a_capa_bloqueia_o_youtube():
    i = SHTML.index('id="aulasPlayer"')
    bloco = SHTML[i:SHTML.index('class="aulas-sobre"', i)]
    for k in ("aulasYt", "aulasCapa", "aulasPlay", "aulasTempo", "aulasBarra", "aulasMudo", "aulasTela", "aulasProxima"):
        assert f'id="{k}"' in bloco, k
    assert "<iframe" not in bloco and 'id="aulaAbrir"' not in SHTML, "nenhum link do YouTube na tela"
    assert "controls: 0, rel: 0, modestbranding: 1, iv_load_policy: 3, fs: 0" in SJS
    assert ".aulas-capa { position: absolute; inset: 0; cursor: pointer;" in SCSS, "a capa cobre o embed inteiro"
    assert 'if (e.target.closest("#aulasCtl") || e.target.closest("#aulasFim") || e.target.closest("#aulasMenu")) return;' in SJS
    assert 'if (state.aulas.menu) { aulaMenu(false); return; }\n      aulaToggle();' in SJS
    assert "https://www.youtube.com/iframe_api" in SJS
    assert "function fmtRelogio(seg)" in SJS and 'fmtRelogio(a.duracaoSeg)' in SJS, "minutagem na lista"
    assert "min no total" in SJS


@pytest.mark.skipif(shutil.which("node") is None, reason="precisa de node")
def test_a_descricao_vira_paragrafos_e_lista(tmp_path):
    """Roda `descricaoHtml` de verdade no node, com a descricao que ele colou."""
    def fn(nome):
        m = re.search(rf"\nfunction {nome}\(.*?\n}}\n", SJS, re.S)
        assert m, nome
        return m.group(0)

    texto = ("Com o AtivaVid, você transforma vídeos. A plataforma conta com: "
             "✅ Edição automática ✅ Legendas e transcrição ✅ Cortes de podcasts\n\n"
             "O que é o AtivaVid?\nA ideia é simples: você grava. O AtivaVid edita.")
    js = fn("escapeHtml") + fn("descricaoHtml") + f"\nconsole.log(descricaoHtml({json.dumps(texto)}));"
    (tmp_path / "t.js").write_text(js, encoding="utf-8")
    out = subprocess.run(["node", str(tmp_path / "t.js")], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    html = out.stdout.strip()
    assert html.startswith("<p>Com o AtivaVid, você transforma vídeos. A plataforma conta com:</p>")
    assert "<ul><li>Edição automática</li><li>Legendas e transcrição</li><li>Cortes de podcasts</li></ul>" in html
    assert "<p>O que é o AtivaVid?<br>A ideia é simples: você grava. O AtivaVid edita.</p>" in html
    assert "✅" not in html


# ------------------------------------------- pedidos do meio da tarde
def test_sair_da_aba_pausa_e_a_lista_fica_parada():
    assert 'else aulasPausar();' in SJS and "function aulasPausar()" in SJS
    assert "position: sticky; top: 0; align-self: start;" in SCSS.split(".aulas-lista {")[1][:300]
    assert "overflow: auto; overscroll-behavior: contain;" in SCSS.split(".aulas-itens {")[1][:200]


def test_engrenagem_legenda_desligada_anterior_proxima_e_concluir():
    for k in ("aulasAnterior", "aulasProxima", "aulasEngren", "aulasMenu", "aulasVel", "aulasCc", "aulaConcluir", "aulasConcluirFim"):
        assert f'id="{k}"' in SHTML, k
    assert 'p.unloadModule("captions"); p.unloadModule("cc");' in SJS, "legenda do YouTube sempre desligada"
    assert 'data-cc="0" class="on"' in SHTML
    assert "p.setPlaybackRate(state.aulas.vel || 1)" in SJS
    assert 'localStorage.setItem(AULAS_FEITAS_KEY' in SJS and "function aulaAnterior()" in SJS
    assert "if (st === YTS.ENDED && state.aulas.atualId && !aulaConcluida(state.aulas.atualId)) aulaMarcar(state.aulas.atualId, true);" in SJS
    assert "Qualidade" in SHTML and "Automática" in SHTML, "a qualidade e explicada, nao prometida"
