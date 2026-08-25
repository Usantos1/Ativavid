# -*- coding: utf-8 -*-
"""O CUDA da transcricao sobrevive a atualizacao do app.

Caso real (25/08): o setup.ps1 rodava `uv sync --extra transcricao` (CPU) a
cada instalacao, e o sync REMOVE o que nao esta no lock — apos ~6 updates o
nvidia-cublas-cu12 sumiu do venv (o cudnn sobrou). O check `cuda_presente`
aceitava qualquer pasta CUDA, dizia "ja instalado", e o job morria em
"Library cublas64_12.dll is not found".
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def test_o_instalador_escolhe_o_extra_pela_gpu():
    s = (RAIZ / "installer" / "setup.ps1").read_text(encoding="utf-8")
    assert "transcricao-cuda" in s, \
        "setup.ps1 voltou a sincronizar so o extra CPU — o sync desinstala o cublas"
    assert "nvidia-smi" in s, "a escolha do extra tem que olhar a GPU"


def test_cuda_presente_exige_cublas_E_cudnn(monkeypatch):
    """cudnn sozinho nao pode passar — foi exatamente o buraco."""
    import app.transcricao.plataforma as plat
    from app.transcricao.componentes import cuda_presente

    monkeypatch.setattr(plat, "registrar_dlls_cuda",
                        lambda: ["nvidia/cudnn/bin"])
    assert plat.dlls_cuda_completas() is False
    monkeypatch.setattr(
        plat, "registrar_dlls_cuda",
        lambda: ["nvidia/cublas/bin", "nvidia/cudnn/bin"])
    assert plat.dlls_cuda_completas() is True


def test_motor_cai_para_cpu_quando_a_gpu_quebra_no_runtime():
    """A construcao do modelo passa e o primeiro encode explode (gerador
    preguicoso). A queda para CPU da carga nao cobria; o job morria."""
    s = (RAIZ / "app" / "transcricao" / "whisper_local.py").read_text(
        encoding="utf-8")
    assert "_queda_para_cpu_no_runtime" in s
    i = s.find("def _queda_para_cpu_no_runtime")
    corpo = s[i:i + 1200]
    for gatilho in ('"dll"', '"cublas"', '"cudnn"', '"cuda"'):
        assert gatilho in corpo, f"gatilho {gatilho} sumiu da queda de runtime"
    assert 'backend == "cpu" or not de_gpu' in corpo, \
        "RuntimeError que nao e de aceleracao tem que subir"
    # o consumo do gerador esta protegido (e o primeiro item nao se perde)
    assert "primeiro = next(segs_it, None)" in s
    assert "_it.chain([primeiro], segs_it)" in s
