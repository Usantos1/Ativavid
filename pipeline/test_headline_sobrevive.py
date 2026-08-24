# -*- coding: utf-8 -*-
"""A headline da IA sobrevive ao reprocesso.

Ela só chega em `llm_meta` quando o planejador roda. Reaproveitar o corte —
reaplicar do editor, `manual_edl`, modo leve, várias fontes — pula o
planejador de propósito, e aí o título caía para as primeiras palavras da fala.

Medido nos 147 projetos do usuário: 37 tinham plano ok e nenhuma headline —
13/13 dos `manual_edl`, 4/4 dos `preview_edits`, 2/2 do modo leve. O efeito é
visível num vídeo que ele reprocessou três vezes:

    1º render  "Chip e Carregador na PrimeCamp"
    2º render  "Chip e carregador potente na loja"
    3º render  "Meu filho, você tem chip aí nessa loja?"   <- fala crua
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "helpers"))

from pipeline.run_fast import headline_preservada  # noqa: E402


def test_plano_com_headline_grava_para_o_proximo(tmp_path):
    fora = headline_preservada(
        tmp_path, {"ok": True, "backend": "gemini-web",
                   "headline": "Chip e carregador potente na loja"})
    assert fora["headline"] == "Chip e carregador potente na loja"
    d = json.loads((tmp_path / "headline_ia.json").read_text(encoding="utf-8"))
    assert d["headline"] == "Chip e carregador potente na loja"
    assert d["backend"] == "gemini-web"


def test_reprocesso_sem_plano_reaproveita(tmp_path):
    """O caso dos 37 jobs: cortar de novo nao pode perder o titulo."""
    headline_preservada(tmp_path, {"ok": True, "backend": "gemini-web",
                                   "headline": "Chip e carregador potente na loja"})
    fora = headline_preservada(tmp_path, {"ok": True, "backend": "manual_edl"})
    assert fora["headline"] == "Chip e carregador potente na loja"


def test_tres_reprocessos_seguidos_nao_degradam(tmp_path):
    """O efeito CATRACA que aconteceu de verdade: a cada reprocesso o titulo
    piorava um passo. Aqui os tres seguidos tem de devolver o mesmo."""
    headline_preservada(tmp_path, {"ok": True, "headline": "Chip e carregador potente na loja"})
    atual = {"ok": True, "backend": "manual_edl"}
    for _ in range(3):
        atual = headline_preservada(tmp_path, dict(atual))
        assert atual["headline"] == "Chip e carregador potente na loja"


def test_plano_novo_vence_o_guardado(tmp_path):
    """Grava antes de reler. Se fosse ao contrario, a headline nunca mudaria —
    nem quando o usuario pedisse outra de proposito."""
    headline_preservada(tmp_path, {"ok": True, "headline": "titulo antigo"})
    fora = headline_preservada(tmp_path, {"ok": True, "headline": "titulo novo"})
    assert fora["headline"] == "titulo novo"
    d = json.loads((tmp_path / "headline_ia.json").read_text(encoding="utf-8"))
    assert d["headline"] == "titulo novo"


def test_sem_nada_guardado_devolve_como_veio(tmp_path):
    """Primeiro render de um projeto sem plano: a fala crua ainda e o recurso."""
    meta = {"ok": True, "backend": "multi_take_concat"}
    fora = headline_preservada(tmp_path, meta)
    assert "headline" not in fora
    assert not (tmp_path / "headline_ia.json").exists()


@pytest.mark.parametrize("conteudo", ["", "{", "{}", '{"headline": ""}',
                                      '{"headline": null}', "[]"])
def test_arquivo_corrompido_nao_derruba_o_render(tmp_path, conteudo):
    (tmp_path / "headline_ia.json").write_text(conteudo, encoding="utf-8")
    fora = headline_preservada(tmp_path, {"ok": True, "backend": "manual_edl"})
    assert not fora.get("headline")


def test_nao_altera_o_dicionario_recebido(tmp_path):
    """`llm_meta` vai para o result.json e para o edl; mexer nele por
    referencia esconderia a origem do titulo."""
    headline_preservada(tmp_path, {"ok": True, "headline": "guardada"})
    entrada = {"ok": True, "backend": "manual_edl"}
    fora = headline_preservada(tmp_path, entrada)
    assert "headline" not in entrada
    assert fora["headline"] == "guardada"


def test_espaco_em_branco_nao_conta_como_headline(tmp_path):
    headline_preservada(tmp_path, {"ok": True, "headline": "boa"})
    fora = headline_preservada(tmp_path, {"ok": True, "headline": "   "})
    assert fora["headline"] == "boa", "espaco nao pode sobrescrever a guardada"


def test_o_titulo_avulso_tambem_fica_guardado():
    """A última rede pede o título quando nem o plano nem a memória têm — e o
    resultado tem de ir para a memória, senão o próximo reprocesso chama a IA
    de novo e o título pode MUDAR entre reprocessos. Visto na validação real
    de 24/08: título certo, headline_ia.json vazio."""
    from pipeline.leitura_de_codigo import apenas_codigo

    codigo = apenas_codigo(Path(__file__).resolve().parents[1] / "pipeline" / "run_fast.py")
    i = codigo.find("hl_av = headline_apenas(cut_spoken, preset)")
    assert i > 0
    trecho = codigo[i:i + 1400]
    assert "headline_preservada(edit_dir, llm_meta)" in trecho, (
        "o título avulso não é gravado na memória do projeto")
