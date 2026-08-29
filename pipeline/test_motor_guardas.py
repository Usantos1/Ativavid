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


# ---------- esperar a VEZ vale mais voltas que esperar folga (3.25) ----------

def test_fila_do_motor_tem_codigo_proprio():
    """"Outro video compondo" e "a maquina nao tem folga" pedem respostas
    diferentes: a vez chega em ~90s; a folga pode nao chegar."""
    s = LAUNCHER.read_text(encoding="utf-8")
    i = s.index("if outro_motor_rodando():")
    assert "sys.exit(7)" in s[i:i + 400], "a fila ainda sai com o codigo de recusa"


def test_na_fila_o_pipeline_espera_mais(monkeypatch, tmp_path):
    import pipeline.run_fast as rf
    voltas = []

    class R:  # noqa: N801
        returncode = rf._MOTOR_NA_FILA

    monkeypatch.setattr(rf, "_helper",
                        lambda *a, **k: (voltas.append(1), R())[1])
    monkeypatch.setattr(rf.time, "sleep", lambda s: None)
    rf._RENDER_META.clear()
    assert rf._tentar_musicgen(tmp_path / "t.mp3", "vibe", 30,
                               tmp_path / "Projetos", tentativas=2) is False
    assert len(voltas) == rf._MOTOR_TENTATIVAS_FILA, len(voltas)
    assert "ocupou o motor" in rf._RENDER_META.get("musicaMotorRecusa", "")


def test_sem_folga_de_memoria_nao_insiste_alem_do_pedido(monkeypatch, tmp_path):
    import pipeline.run_fast as rf
    voltas = []

    class R:  # noqa: N801
        returncode = rf._MOTOR_RECUSADO

    monkeypatch.setattr(rf, "_helper",
                        lambda *a, **k: (voltas.append(1), R())[1])
    monkeypatch.setattr(rf.time, "sleep", lambda s: None)
    rf._RENDER_META.clear()
    rf._tentar_musicgen(tmp_path / "t.mp3", "vibe", 30, tmp_path / "Projetos",
                        tentativas=3)
    assert len(voltas) == 3, len(voltas)
    assert "folga de memória" in rf._RENDER_META.get("musicaMotorRecusa", "")


def test_o_motivo_da_recusa_chega_ao_card(tmp_path):
    """"Veio da biblioteca" sozinho mandava procurar defeito onde so havia
    fila — o card passa a dizer o motivo que o pipeline gravou."""
    import json
    from app.jobs_view import _aviso_de_trilha
    (tmp_path / "timing.json").write_text(json.dumps({
        "musicaFonte": "viral--mg-20260828.mp3",
        "musicaMotorRecusa": "outro vídeo ocupou o motor até o fim da espera",
    }), encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "outro vídeo ocupou o motor" in job["trilhaNota"], job["trilhaNota"]


def test_sem_motivo_gravado_a_nota_nao_acusa_falha(tmp_path):
    import json
    from app.jobs_view import _aviso_de_trilha
    (tmp_path / "timing.json").write_text(
        json.dumps({"musicaFonte": "viral--x.mp3"}), encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "não compôs" in job["trilhaNota"]
    assert "falhou" not in job["trilhaNota"]


def test_a_espera_na_fila_cabe_no_prazo_do_render():
    """O render espera o fio antecipado por 240s (music_thread.join). Se a
    espera na fila passar disso, o esforco morre fora de hora: o render
    desiste com o fio ainda tentando, cai no caminho sincrono (uma
    tentativa so) e a trilha vem da biblioteca com o motor prestes a
    liberar."""
    import re
    import pipeline.run_fast as rf
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    prazos = {int(m) for m in re.findall(r"music_thread\.join\(timeout=(\d+)\)", s)}
    assert prazos, "nao achei o prazo do fio antecipado"
    espera = rf._MOTOR_TENTATIVAS_FILA * rf._MOTOR_ESPERA_S
    assert espera < min(prazos), f"espera {espera}s x prazo {min(prazos)}s"


def test_o_teto_do_motor_cabe_no_teto_do_pipeline():
    """O launcher desiste em 240s e o pipeline corta em 300s: o de dentro
    tem de ser sempre menor, senao quem mata e o de fora e a mensagem de
    erro fica errada."""
    import re
    import pipeline.run_fast as rf
    s = (RAIZ / "helpers" / "musicgen_local.py").read_text(encoding="utf-8")
    m = re.search(r"TIMEOUT_S = (\d+)", s)
    assert m
    assert int(m.group(1)) < rf._MOTOR_TETO_S
