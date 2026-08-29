# -*- coding: utf-8 -*-
"""Escrever legenda na mão, onde a transcrição não ouviu nada.

Pedido do usuário em 29/08: "quero add legenda na mão na tela de edição".
Até aqui o editor só sabia CORRIGIR e APAGAR o que a transcrição trouxe —
não havia como pôr uma frase sobre um trecho de b-roll, sobre uma fala
baixa, ou uma frase que ninguém falou.

Duas decisões que o teste protege:

* Grava PALAVRAS em `captions.json`, não uma cue pronta. O apply
  reconstrói `caption-cues.json` a partir das palavras, então a legenda
  escrita à mão sai com o mesmo desenho, as mesmas quebras e o mesmo
  realce das vizinhas. Uma cue inventada aqui apareceria diferente.
* Não passa por cima de legenda existente: apara o fim até a próxima
  palavra e, sem espaço livre, recusa dizendo por quê. Sobrescrever a fala
  transcrita para caber um texto novo seria pior que recusar.
"""
from __future__ import annotations

import json
from pathlib import Path

from app import quick_corrections as qc


def _projeto(tmp_path: Path, palavras: list[dict]) -> Path:
    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "remotion" / "public" / "captions.json").write_text(
        json.dumps(palavras), encoding="utf-8")
    return edit


def _lidas(edit: Path) -> list[dict]:
    return json.loads(
        (edit / "remotion" / "public" / "captions.json").read_text(encoding="utf-8"))


FALA = [{"text": "olha", "startMs": 0, "endMs": 400},
        {"text": "isso", "startMs": 400, "endMs": 900},
        {"text": "agora", "startMs": 5000, "endMs": 5400}]


def test_escreve_no_espaco_livre(tmp_path):
    edit = _projeto(tmp_path, FALA)
    r = qc.add_caption(edit, texto="olha o preço", inicio_s=2.0)
    assert r["ok"] and r["changed"] == 3
    novas = [w for w in _lidas(edit) if w.get("manual")]
    assert [w["text"] for w in novas] == ["olha", "o", "preço"]
    assert novas[0]["startMs"] == 2000
    # as palavras dividem a janela em partes iguais, em ordem
    assert novas[0]["endMs"] == novas[1]["startMs"]
    assert novas[-1]["endMs"] <= 5000


def test_nao_escreve_por_cima_da_fala(tmp_path):
    edit = _projeto(tmp_path, FALA)
    r = qc.add_caption(edit, texto="em cima da fala", inicio_s=0.2)
    assert r["ok"] is False
    assert "já existe legenda" in (r.get("erro") or "").lower()
    assert not [w for w in _lidas(edit) if w.get("manual")]


def test_apara_ate_a_proxima_legenda(tmp_path):
    """Cabe, mas não inteira: encurta em vez de invadir a fala seguinte."""
    edit = _projeto(tmp_path, FALA)
    r = qc.add_caption(edit, texto="antes da próxima", inicio_s=4.6)
    assert r["ok"] and r["janela"]["fimMs"] == 5000
    assert max(w["endMs"] for w in _lidas(edit) if w.get("manual")) == 5000


def test_texto_vazio_nao_vira_legenda(tmp_path):
    edit = _projeto(tmp_path, FALA)
    r = qc.add_caption(edit, texto="   ", inicio_s=3.0)
    assert r["ok"] is False and "escreva" in (r.get("erro") or "").lower()


def test_o_arquivo_fica_em_ordem_de_tempo(tmp_path):
    """O construtor de cues lê em ordem; fora de ordem ele quebraria a
    legenda em blocos errados."""
    edit = _projeto(tmp_path, FALA)
    qc.add_caption(edit, texto="uma frase no meio", inicio_s=2.0)
    ms = [int(w["startMs"]) for w in _lidas(edit)]
    assert ms == sorted(ms)


def test_a_operacao_chega_pelo_editor(tmp_path):
    """A rota que o preview usa (`/api/corrections`) tem de conhecer o op."""
    edit = _projeto(tmp_path, FALA)
    r = qc.handle(edit, {"op": "add_caption", "text": "pelo editor",
                         "start": 2.0})
    assert r["ok"] and r["changed"] == 2


def test_a_tela_convida_a_escrever():
    """A pastilha vazia dizia "—" e o clique mandava avançar o vídeo: o
    único lugar da tela que falava de legenda mandava o usuário embora."""
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "'+ escrever legenda'" in js
    assert "function escreverLegendaAqui" in js
    assert "Avance o vídeo até aparecer a legenda" not in js
