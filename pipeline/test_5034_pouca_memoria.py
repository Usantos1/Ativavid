# -*- coding: utf-8 -*-
"""5.0.34: o Diagnóstico avisa quando a memória LIVRE é pouca.

A máquina de uma cliente (04/09): 7,6 GB de RAM com 0,9 livre. O render
abre um navegador inteiro para desenhar as legendas; com menos de ~2,5 GB
ele morre no meio sem dizer por quê, e o job cai para o caminho lento ou
falha. A IA de música já tinha uma guarda de memória; o render, nenhuma —
e a linha "Sistema" mostrava o número sem acusar nada.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "helpers") not in sys.path:
    sys.path.insert(0, str(REPO / "helpers"))


def _itens(monkeypatch, livre):
    import helpers.doutor as dt
    from app import system_info
    from app import performance

    m = {"os": "Windows", "osRelease": "11", "cores": 8, "ramGb": 7.6,
         "ramFreeGb": livre, "diskFreeGb": 190, "accel": {"preferredEncoder": "h264_qsv", "mode": "gpu"},
         "gpus": [{"name": "Intel(R) UHD Graphics", "vramGb": 2.0}]}
    monkeypatch.setattr(system_info, "detect_machine", lambda *a, **k: m)
    monkeypatch.setattr(performance, "profile_settings",
                        lambda *a, **k: {"label": "Econômico", "parallelJobs": 1, "encoder": "h264_qsv"})
    dt._itens.clear()
    dt.checar_sistema()
    return list(dt._itens)


def test_pouca_memoria_vira_aviso(monkeypatch):
    """O caso da cliente."""
    avisos = [i for i in _itens(monkeypatch, 0.9) if i["nivel"] == "aviso"]
    assert avisos and "0.9 GB" in avisos[0]["titulo"]
    assert "Feche" in avisos[0]["solucao"]


def test_memoria_suficiente_nao_avisa(monkeypatch):
    assert not [i for i in _itens(monkeypatch, 9.6)
                if "memória livre" in i["titulo"].lower()]


def test_medida_ausente_nao_inventa_aviso(monkeypatch):
    """`ramFreeGb` pode vir vazio (detecção falhou): zero não é pouco, é
    desconhecido."""
    assert not [i for i in _itens(monkeypatch, None)
                if "memória livre" in i["titulo"].lower()]
