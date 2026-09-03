# -*- coding: utf-8 -*-
"""Uma transcrição local por vez NA MÁQUINA.

Caso real de 03/09: perfil "performance" roda 2 jobs em paralelo; dois
Whisper `medium` (2,66 GB de VRAM cada) disputaram a placa de 4 GB e os
dois rastejaram — vídeos de 21 s parados 45 min em "Ouvindo o que foi
falado". A `_TRAVA` só valia dentro do processo. A vaga é um arquivo com o
PID (padrão do motor de música): vence sozinha quando o dono morreu.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _usar_vaga_temporaria(monkeypatch, tmp_path: Path):
    from app.transcricao import whisper_local as wl

    monkeypatch.setattr(wl, "VAGA", tmp_path / "vaga.lock")
    return wl


def test_vaga_de_processo_morto_e_tomada_na_hora(monkeypatch, tmp_path):
    wl = _usar_vaga_temporaria(monkeypatch, tmp_path)
    wl.VAGA.write_text("999999", encoding="utf-8")   # PID que não existe
    t0 = time.time()
    assert wl._vaga_pegar(teto_s=5) is True
    assert time.time() - t0 < 2
    assert wl.VAGA.read_text(encoding="utf-8").strip() == str(os.getpid())
    wl._vaga_soltar()
    assert not wl.VAGA.exists()


def test_vaga_de_processo_vivo_faz_esperar(monkeypatch, tmp_path):
    wl = _usar_vaga_temporaria(monkeypatch, tmp_path)
    outro = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        wl.VAGA.write_text(str(outro.pid), encoding="utf-8")
        avisos: list[str] = []
        t0 = time.time()
        pegou = wl._vaga_pegar(progresso=lambda f, m: avisos.append(m), teto_s=3)
        assert time.time() - t0 >= 3, "não esperou pela vez"
        assert pegou is False, "no teto ela segue SEM a vaga, nunca trava"
        assert avisos and "esperando a vez" in avisos[0]
        # e quem não pegou não apaga a vaga do outro
        wl._vaga_soltar()
        assert wl.VAGA.read_text(encoding="utf-8").strip() == str(outro.pid)
    finally:
        outro.kill()


def test_vaga_liberada_pelo_dono_passa_para_o_proximo(monkeypatch, tmp_path):
    wl = _usar_vaga_temporaria(monkeypatch, tmp_path)
    outro = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
    wl.VAGA.write_text(str(outro.pid), encoding="utf-8")
    t0 = time.time()
    assert wl._vaga_pegar(teto_s=30) is True     # espera o outro morrer (~2s)
    assert 1 <= time.time() - t0 < 10
    wl._vaga_soltar()


def test_cancelar_solta_a_espera(monkeypatch, tmp_path):
    wl = _usar_vaga_temporaria(monkeypatch, tmp_path)
    outro = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        wl.VAGA.write_text(str(outro.pid), encoding="utf-8")
        ev = threading.Event()
        threading.Timer(1.0, ev.set).start()
        t0 = time.time()
        assert wl._vaga_pegar(cancelar=ev, teto_s=30) is False
        assert time.time() - t0 < 5
    finally:
        outro.kill()


def test_transcrever_pega_e_solta_a_vaga():
    s = (REPO / "app" / "transcricao" / "whisper_local.py").read_text(encoding="utf-8")
    i = s.index("    def transcrever(")
    bloco = s[i:s.index("    def _transcrever_com_a_vaga(", i)]
    assert "_vaga_pegar(" in bloco and "finally:" in bloco and "_vaga_soltar()" in bloco
