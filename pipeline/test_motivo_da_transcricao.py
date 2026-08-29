# -*- coding: utf-8 -*-
"""Quando a transcrição falha, o app diz O QUE está errado no áudio.

Caso real (29/08): três jobs pararam na Fila com a mesma frase —
"Transcrição ruim ou vazia — confira o áudio" — e as causas eram
diferentes: dois vídeos com o áudio quase mudo (média -42 dB e -53 dB,
quando fala normal fica perto de -20 dB) e um de 3 segundos com uma
palavra só. A frase genérica não diz o que conferir.

Os testes injetam a MEDIÇÃO em vez de gerar áudio: o `sine` do ffmpeg sai
baixo e uma fixture sintética passaria por "quase mudo" sem querer — o
que se quer travar aqui é a DECISÃO, não o medidor.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline import run_fast  # noqa: E402


def _motivo(monkeypatch, *, media, pico, dur, texto=""):
    monkeypatch.setattr(run_fast, "_nivel_do_audio",
                        lambda src: (media, pico))
    monkeypatch.setattr(run_fast, "_ffprobe_duration", lambda src: dur)
    return run_fast.motivo_da_transcricao_ruim(Path("x.mov"), texto)


def test_audio_quase_mudo_manda_olhar_o_microfone(monkeypatch):
    m = _motivo(monkeypatch, media=-53.3, pico=-32.8, dur=34.0)
    assert "quase mudo" in m and "-53 dB" in m and "microfone" in m, m


def test_video_curto_demais_diz_a_duracao(monkeypatch):
    m = _motivo(monkeypatch, media=-21.4, pico=0.0, dur=3.0, texto="Não!")
    assert "3s" in m and "curto demais" in m, m
    assert "microfone" not in m, "nivel esta normal, nao e caso de microfone"


def test_audio_bom_e_sem_fala_reconhecida(monkeypatch):
    m = _motivo(monkeypatch, media=-20.0, pico=-3.0, dur=40.0)
    assert "nenhuma fala" in m and "idioma" in m, m


def test_transcricao_quebrada_mostra_o_que_saiu(monkeypatch):
    m = _motivo(monkeypatch, media=-18.0, pico=-2.0, dur=25.0, texto="?? ?!")
    assert "quebrada" in m and "?? ?!" in m, m


def test_sem_medicao_nao_inventa_diagnostico(monkeypatch):
    """ffmpeg indisponível devolve (0, 0): não pode virar "quase mudo"."""
    m = _motivo(monkeypatch, media=0.0, pico=0.0, dur=30.0)
    assert "quase mudo" not in m, m


def test_a_fila_mostra_o_motivo_em_vez_do_rotulo_generico():
    s = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = s.index('label = REASON_LABELS.get(reason, reason)')
    trecho = s[i:i + 600]
    assert 'reason == "bad_transcript" and detail' in trecho, trecho[:300]
