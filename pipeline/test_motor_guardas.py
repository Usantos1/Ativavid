# -*- coding: utf-8 -*-
"""Guardas do motor local: RAM, VRAM e um motor por vez.

Medido em 27/08 na maquina do usuario (RTX 3050 4GB / i5-10300H / 24GB):
compor 60s consome ~4,2GB de RAM e 2,0GB de VRAM, pico de 53% da GPU. Sem
guarda, isso disputaria com o render — e com parallelJobs=2 dois jobs
ligariam DOIS motores juntos (8GB RAM, 4GB VRAM), a mesma armadilha do
NVDEC disputado.
"""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LAUNCHER = RAIZ / "helpers" / "musicgen_local.py"


def _motor_falso(tmp_path) -> str:
    """achar_python so confere se o arquivo existe — um arquivo vazio basta
    para o teste chegar nas guardas sem instalar 2,5GB."""
    d = tmp_path / "MotorFalso" / "Scripts"
    d.mkdir(parents=True)
    (d / "python.exe").write_bytes(b"")
    return str(tmp_path / "MotorFalso")


def _carregar(nome):
    import importlib.util
    spec = importlib.util.spec_from_file_location(nome, LAUNCHER)
    mgl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mgl)
    return mgl


def test_ram_apertada_desiste_sem_gerar(tmp_path, monkeypatch):
    """A guarda tem de barrar ANTES de carregar 4GB de modelo."""
    mgl = _carregar("mgl")
    monkeypatch.setattr(mgl, "ram_livre_gb", lambda: 2.0)
    monkeypatch.setattr(mgl, "vram_livre_mb", lambda: 4000)
    monkeypatch.setattr(mgl, "LOCK", tmp_path / "lock")
    monkeypatch.setattr(sys, "argv",
                        ["mgl", "vibe", "-o", str(tmp_path / "t.mp3"),
                         "--motor", _motor_falso(tmp_path)])
    try:
        mgl.main()
    except SystemExit as e:
        assert e.code == 6, "RAM baixa tem de sair com 6 (segue outro plano)"
    else:
        raise AssertionError("nao saiu")
    assert not (tmp_path / "t.mp3").exists()


def test_vram_ocupada_desiste(tmp_path, monkeypatch):
    mgl = _carregar("mgl2")
    monkeypatch.setattr(mgl, "ram_livre_gb", lambda: 16.0)
    monkeypatch.setattr(mgl, "vram_livre_mb", lambda: 900)  # render usando
    monkeypatch.setattr(mgl, "LOCK", tmp_path / "lock")
    monkeypatch.setattr(sys, "argv",
                        ["mgl", "vibe", "-o", str(tmp_path / "t.mp3"),
                         "--motor", _motor_falso(tmp_path)])
    try:
        mgl.main()
    except SystemExit as e:
        assert e.code == 6
    else:
        raise AssertionError("nao saiu")


def test_medida_nao_disponivel_nao_bloqueia(tmp_path, monkeypatch):
    """Maquina sem nvidia-smi/API: -1 significa "nao sei" e a guarda NAO
    pode barrar por isso — senao o recurso morre em silencio."""
    mgl = _carregar("mgl3")
    monkeypatch.setattr(mgl, "ram_livre_gb", lambda: -1.0)
    monkeypatch.setattr(mgl, "vram_livre_mb", lambda: -1)
    monkeypatch.setattr(mgl, "achar_python", lambda motor: None)
    monkeypatch.setattr(sys, "argv",
                        ["mgl", "vibe", "-o", str(tmp_path / "t.mp3"),
                         "--motor", str(tmp_path / "nao-existe")])
    try:
        mgl.main()
    except SystemExit as e:
        assert e.code == 3, "passou das guardas e parou por falta de motor"
    else:
        raise AssertionError("nao saiu")


def test_um_motor_por_vez(tmp_path, monkeypatch):
    """Segundo job pedindo trilha ao mesmo tempo: sai com 6 na hora."""
    import os
    mgl = _carregar("mgl4")
    monkeypatch.setattr(mgl, "LOCK", tmp_path / "lock")
    # um "outro processo" vivo: o PID do proprio pytest serve de cobaia
    mgl.LOCK.write_text(str(os.getppid()), encoding="utf-8")
    assert mgl.outro_motor_rodando() is True


def test_lock_de_processo_morto_nao_tranca(tmp_path, monkeypatch):
    mgl = _carregar("mgl5")
    monkeypatch.setattr(mgl, "LOCK", tmp_path / "lock")
    mgl.LOCK.write_text("999999", encoding="utf-8")  # PID que nao existe
    assert mgl.outro_motor_rodando() is False
    assert mgl.LOCK.read_text().strip() != "999999", "assumiu o lock"


def test_o_lock_sai_no_finally():
    s = LAUNCHER.read_text(encoding="utf-8")
    i = s.find("finally:")
    assert i > 0, "sem finally, um erro deixaria o lock preso 10 min"
    assert "LOCK.unlink" in s[i:i + 400]
