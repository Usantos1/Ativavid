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


def test_setup_refresca_o_path_depois_do_winget():
    """Maquina NOVA (caso real, 26/08): o winget instala o uv mas grava o
    PATH no REGISTRO — o processo do setup nao ve e morria em 'uv nao
    encontrado' em TODA primeira instalacao. Refresh-Path recarrega
    Machine+User em processo, e o uv ainda tem o instalador oficial como
    reserva."""
    s = (RAIZ / "installer" / "setup.ps1").read_text(encoding="utf-8")
    assert "function Refresh-Path" in s
    assert s.count("Refresh-Path") >= 4, "refresh some do fluxo do uv"
    assert "astral.sh/uv/install.ps1" in s, "a reserva do uv sumiu"
    assert "GetEnvironmentVariable(\"Path\", \"Machine\")" in s
    assert (".local" + chr(92) + "bin") in s, \
        "a barra do .local/bin foi comida de novo"
    assert "FECHE e reabra o PowerShell" not in s, \
        "conselho impossivel num script que roda uma vez pelo instalador"


def test_do_post_tem_o_involucro_de_higiene_do_socket():
    """Cliente em trial (26/08): rota respondeu 403 sem ler o corpo e o
    keep-alive seguinte nasceu quebrado ('Bad request syntax ...mp4"]}POST').
    Segunda mordida da mesma classe (a primeira foi o Unsupported method do
    llm-proxy). O involucro pre-le o corpo para buffer e restaura o rfile
    no finally — rota nenhuma consegue mais envenenar a conexao."""
    for nome in ("app/local_server.py", "app/desktop_server.py"):
        s = (RAIZ / nome).read_text(encoding="utf-8")
        assert "def _do_POST_rotas" in s, f"{nome}: involucro sumiu"
        i = s.find("def do_POST")
        corpo = s[i:s.find("def _do_POST_rotas")]
        assert "BytesIO" in corpo and "finally" in corpo, f"{nome}: buffer/restauro"
        assert "close_connection = True" in corpo, \
            f"{nome}: multipart grande precisa fechar a conexao"
        assert "self._do_POST_rotas()" in corpo
