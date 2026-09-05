# -*- coding: utf-8 -*-
"""Pedido salvo e nunca aplicado aparece — e só quando é de verdade.

O painel de projetos contava isso; a Fila e os Concluídos, não — e é neles
que ele olha. Trabalho que ele fez no editor e que não chegou ao vídeo,
sem nada na tela dizendo.

E o painel contava demais: marcava "pendente" por **existir o arquivo**.
Dos 12 projetos do usuário que ele acusava, **10 tinham o pedido mais
velho que a entrega** — já aplicados, arquivo esquecido. Com a mesma regra
nas duas telas: 2 de 187.

Duas telas dizendo coisas diferentes sobre o mesmo projeto é pior que uma
só.
"""
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

from app.jobs_view import _pedido_nao_aplicado  # noqa: E402
from preview_server import _pedido_e_novo  # noqa: E402


def _projeto(tmp_path: Path, *, pedido_mais_novo: bool) -> Path:
    ed = tmp_path / "edit"
    ed.mkdir(parents=True)
    (ed / "state.json").write_text(json.dumps({"finalVideo": "final.mp4"}),
                                   encoding="utf-8")
    (ed / "final.mp4").write_bytes(b"x" * 5000)
    ped = ed / "preview_edits.json"
    ped.write_text(json.dumps({"notes": [{"text": "arrumar aqui"}]}),
                   encoding="utf-8")
    agora = time.time()
    os.utime(ed / "final.mp4", (agora, agora))
    quando = agora + 60 if pedido_mais_novo else agora - 60
    os.utime(ped, (quando, quando))
    return ed


def test_pedido_mais_novo_que_o_video_avisa(tmp_path):
    j = {}
    _pedido_nao_aplicado(j, _projeto(tmp_path, pedido_mais_novo=True))
    assert "não foram aplicadas" in j["pedidoNota"]


def test_pedido_mais_velho_e_sobra(tmp_path):
    j = {}
    _pedido_nao_aplicado(j, _projeto(tmp_path, pedido_mais_novo=False))
    assert "pedidoNota" not in j


def test_sem_pedido_nao_avisa(tmp_path):
    ed = _projeto(tmp_path, pedido_mais_novo=True)
    (ed / "preview_edits.json").unlink()
    j = {}
    _pedido_nao_aplicado(j, ed)
    assert "pedidoNota" not in j


def test_o_painel_usa_a_mesma_regra(tmp_path):
    ed = _projeto(tmp_path, pedido_mais_novo=False)
    entrega = {"name": "final.mp4"}
    assert not _pedido_e_novo(ed / "preview_edits.json", entrega, ed)
    agora = time.time() + 120
    os.utime(ed / "preview_edits.json", (agora, agora))
    assert _pedido_e_novo(ed / "preview_edits.json", entrega, ed)


def test_sem_entrega_o_pedido_esta_mesmo_pendente(tmp_path):
    ed = _projeto(tmp_path, pedido_mais_novo=False)
    assert _pedido_e_novo(ed / "preview_edits.json", None, ed)


def test_a_tela_mostra_a_linha():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'linhas.push(["Pendente", j.pedidoNota])' in js
    assert 'j.pedidoNota || "",' in js


# ---------------------------------------------------------------- 5.0.38
# As correções RÁPIDAS (texto de legenda, manchete, trecho) moram em
# `corrections.json`, não em `preview_edits.json` — e nunca entravam na
# regra. Medido em 05/09: 7 projetos reais com `dirty` ligado e o arquivo
# mais novo que o vídeo entregue, o mais velho de 18/08; nenhum aparecia.


def _com_correcoes(tmp_path: Path, *, dirty: dict, mais_novo: bool,
                   final_stale: bool = False) -> Path:
    ed = _projeto(tmp_path, pedido_mais_novo=False)
    (ed / "preview_edits.json").unlink()
    c = ed / "corrections.json"
    c.write_text(json.dumps({"dirty": dirty, "finalStale": final_stale}),
                 encoding="utf-8")
    t = (ed / "final.mp4").stat().st_mtime + (60 if mais_novo else -60)
    os.utime(c, (t, t))
    return ed


def test_correcao_rapida_suja_e_mais_nova_avisa(tmp_path):
    j = {}
    _pedido_nao_aplicado(j, _com_correcoes(
        tmp_path, dirty={"captions": True, "edl": False}, mais_novo=True))
    assert "correções rápidas" in j["pedidoNota"]


def test_corrections_limpo_nao_e_pedido(tmp_path):
    # O render reescreve o arquivo (relógio) — existir não diz nada.
    j = {}
    _pedido_nao_aplicado(j, _com_correcoes(
        tmp_path, dirty={"captions": False, "edl": False}, mais_novo=True))
    assert "pedidoNota" not in j


def test_correcao_suja_mas_mais_velha_que_o_video_ja_foi(tmp_path):
    j = {}
    _pedido_nao_aplicado(j, _com_correcoes(
        tmp_path, dirty={"headline": True}, mais_novo=False))
    assert "pedidoNota" not in j


def test_final_stale_sozinho_basta(tmp_path):
    j = {}
    _pedido_nao_aplicado(j, _com_correcoes(
        tmp_path, dirty={}, mais_novo=True, final_stale=True))
    assert "correções rápidas" in j["pedidoNota"]
