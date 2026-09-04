# -*- coding: utf-8 -*-
"""5.0.28: quem decide a aceleração é a PLACA, não a lista do ffmpeg.

Print da máquina de uma cliente (04/09), Intel(R) UHD Graphics e mais nada:
o Diagnóstico dizia "Aceleração de vídeo: h264_nvenc · Modo gpu" e, dois
cartões adiante, "Perfil automático: Econômico · encoder=libx264". Os dois
não podem estar certos — e foi essa contradição que o usuário viu.

A causa: `ffmpeg -encoders` lista o que foi COMPILADO, não o que a máquina
aceita. A build que o app usa traz os três (medido):

    h264_nvenc True · h264_qsv True · h264_amf True

Com `nvidia = ... or "h264_nvenc" in encoders`, toda máquina virava NVIDIA.

A lista de encoders só volta a decidir quando não há lista de placas — aí a
consulta ao Windows falhou e o palpite antigo é melhor que nada.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import app.system_info as si  # noqa: E402

TODOS = {"h264_nvenc", "h264_qsv", "h264_amf", "libx264"}


def _accel(monkeypatch, placas, encoders=TODOS):
    monkeypatch.setattr(si, "_gpu_windows", lambda: [{"name": n} for n in placas])
    monkeypatch.setattr(si, "_ffmpeg_encoders", lambda: set(encoders))
    monkeypatch.setattr(si, "_ffmpeg_cmd", lambda: "ffmpeg")
    monkeypatch.setattr(si, "versao" if hasattr(si, "versao") else "_run",
                        lambda *a, **k: "ffmpeg version 9")
    m = si._detect_machine_inner(None, probe_encoders=False, quick=False)
    return m.get("accel") or {}


def test_maquina_so_com_intel_nao_anuncia_nvenc(monkeypatch):
    """O caso da cliente."""
    a = _accel(monkeypatch, ["Intel(R) UHD Graphics"])
    assert a["nvenc"] is False, "volta a mentir que tem NVIDIA"
    assert a["preferredEncoder"] == "h264_qsv", "Intel encoda por QSV"


def test_maquina_com_nvidia_continua_no_nvenc(monkeypatch):
    """O notebook do usuário lista a Intel JUNTO com a NVIDIA."""
    a = _accel(monkeypatch, ["NVIDIA GeForce RTX 3050 Laptop GPU",
                             "Intel(R) UHD Graphics"])
    assert a["nvenc"] is True and a["preferredEncoder"] == "h264_nvenc"


def test_maquina_amd(monkeypatch):
    a = _accel(monkeypatch, ["AMD Radeon RX 6600"])
    assert a["amf"] is True and a["preferredEncoder"] == "h264_amf"
    assert a["nvenc"] is False


def test_sem_lista_de_placas_o_ffmpeg_volta_a_decidir(monkeypatch):
    """A consulta ao Windows falha (timeout de 4s): melhor o palpite antigo
    que cravar CPU numa máquina que talvez acelere."""
    a = _accel(monkeypatch, [])
    assert a["preferredEncoder"] == "h264_nvenc"


def test_placa_desconhecida_nao_inventa_aceleracao(monkeypatch):
    a = _accel(monkeypatch, ["Microsoft Basic Display Adapter"])
    assert a["preferredEncoder"] == "libx264"
    assert not any(a[k] for k in ("nvenc", "qsv", "amf"))
