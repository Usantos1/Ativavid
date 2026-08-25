# -*- coding: utf-8 -*-
"""O instalador fecha o app antes de copiar — e nao se mata no processo.

Caso real (24/08): instalar por cima do app aberto deixou o servidor Python
velho na memoria. As telas (lidas do disco a cada acesso) mostravam os campos
novos; o servidor ignorava o que nao conhecia. O usuario mandou o modo de
edicao tres vezes e o job_intent.json nunca mudou — "instalei mas continua
igual". CloseApplications=force nao cobre: pythonw nao mantem os .py abertos.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ISS = RAIZ / "installer" / "ativa-vid.iss"


def _iss() -> str:
    return ISS.read_text(encoding="utf-8-sig")


def test_o_instalador_derruba_o_app_antes_de_copiar():
    s = _iss()
    assert "PrepareToInstall" in s, "o passo que fecha o app sumiu do .iss"
    bloco = s[s.find("PrepareToInstall"):]
    assert "Stop-Process" in bloco
    # so processos do DIRETORIO DE INSTALACAO — nunca um python qualquer da
    # maquina (o usuario tem outros Pythons).
    assert "{app}" in bloco and "CommandLine" in bloco


def test_o_kill_nao_mata_o_proprio_powershell():
    """A cmdline do proprio PowerShell contem o caminho do app (esta no
    filtro). Sem excluir $PID ele se encaixa no proprio criterio e se mata no
    meio do trabalho — mesma armadilha do kill por substring que ja derrubou
    o run_fast (bug-pipeline-se-matava-sozinho)."""
    s = _iss()
    bloco = s[s.find("PrepareToInstall"):]
    assert "$PID" in bloco, "filtro de auto-preservacao sumiu do kill"
