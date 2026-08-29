# -*- coding: utf-8 -*-
"""Trecho que pede tempo inexistente na fonte não chega ao vídeo.

Isto nunca dá erro: o ffmpeg, pedido a partir de um instante que não
existe, entrega silêncio e quadro congelado, e o vídeo sai "pronto". Caso
real (29/08, job de 3 partes): `Parte 1.mov` tem 6,1s e o EDL trazia 12
trechos dessa fonte indo até 137,5s. O vídeo saiu com 28s, 23,4s deles
mudos e travados, e o usuário procurou defeito na gravação dele.

A causa daquele caso (casamento de take por nome) foi corrigida à parte —
este guarda pega a FAMÍLIA: qualquer engano de relógio entre takes.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.run_fast import _RENDER_META, _aparar_fora_da_fonte  # noqa: E402

DUR = {"Parte_1": 6.15, "parte_2": 138.13}


def _r(fonte, ini, fim):
    return {"source": fonte, "start": ini, "end": fim, "beat": "B",
            "quote": "", "reason": "x", "gain_db": 0.0}


def test_trecho_todo_fora_e_removido():
    _RENDER_META.clear()
    out = _aparar_fora_da_fonte([_r("Parte_1", 13.18, 19.41)], DUR)
    assert out == [], out
    assert _RENDER_META.get("trechosForaDaFonte"), "o motivo tem de sobrar"


def test_trecho_que_passa_do_fim_e_aparado():
    _RENDER_META.clear()
    out = _aparar_fora_da_fonte([_r("Parte_1", 5.0, 8.0)], DUR)
    assert len(out) == 1 and abs(out[0]["end"] - 6.15) < 0.01, out


def test_o_que_cabe_no_arquivo_passa_intacto():
    _RENDER_META.clear()
    bons = [_r("Parte_1", 1.36, 5.93), _r("parte_2", 2.3, 7.7)]
    out = _aparar_fora_da_fonte([dict(r) for r in bons], DUR)
    assert out == bons, out
    assert not _RENDER_META.get("trechosForaDaFonte")


def test_fonte_sem_duracao_conhecida_nao_e_mexida():
    """Não saber a duração não autoriza jogar trecho fora."""
    _RENDER_META.clear()
    r = _r("desconhecida", 0.0, 999.0)
    assert _aparar_fora_da_fonte([dict(r)], DUR) == [r]


def test_aparo_de_apenas_uma_folga_nao_conta_como_defeito():
    """O relógio do ffprobe e o do corte divergem em milissegundos."""
    _RENDER_META.clear()
    out = _aparar_fora_da_fonte([_r("Parte_1", 1.0, 6.18)], DUR)
    assert len(out) == 1 and out[0]["end"] == 6.18, out
    assert not _RENDER_META.get("trechosForaDaFonte")


def test_a_ficha_conta_o_que_aconteceu():
    """Um defeito que o app conserta calado vira o próximo mistério."""
    import json
    import shutil
    import tempfile

    from app.jobs_view import _aviso_de_trilha

    edit = Path(tempfile.mkdtemp())
    try:
        (edit / "timing.json").write_text(json.dumps({
            "trechosForaDaFonte": [
                {"fonte": "Parte_1", "de": 13.18, "ate": 19.41,
                 "acao": "removido"},
                {"fonte": "Parte_1", "de": 24.68, "ate": 26.65,
                 "acao": "removido"},
            ]}), encoding="utf-8")
        job: dict = {}
        _aviso_de_trilha(job, edit)
        nota = job.get("corteNota") or ""
        assert "2 trechos" in nota and "Parte_1" in nota, nota
    finally:
        shutil.rmtree(edit, ignore_errors=True)
