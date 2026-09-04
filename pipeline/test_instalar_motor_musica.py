# -*- coding: utf-8 -*-
"""O CLIENTE precisa conseguir instalar a IA local de música.

Ela é a única peça do app que nasceu só na máquina do desenvolvedor: 4,8 GB
(PyTorch com CUDA + modelo) que não cabem no instalador de 6 MB. Sem uma
porta na tela, o cliente escolhia "IA local primeiro" e nada acontecia — o
launcher saía com "motor não instalado" e a trilha vinha da nuvem, calado.
"""
import threading
from pathlib import Path

from app import musica_local

RAIZ = Path(__file__).resolve().parent.parent


def test_a_pasta_do_motor_e_irma_da_biblioteca(tmp_path):
    """Mesma raiz que o resto do app usa — resolve o junction quando os
    Projetos moram em outro disco (caso real do usuário: C: -> E:)."""
    projetos = tmp_path / "disco" / "Projetos"
    assert musica_local.pasta_motor(projetos) == \
        tmp_path / "disco" / "MotorMusica"


def test_sem_gpu_nao_oferece_e_nao_instala(monkeypatch, tmp_path):
    """Na CPU a trilha levaria ~9 minutos (medido 27/08) — prometer isso
    seria pior que não oferecer.

    5.0.24: quem decide passou a ser `gpu_do_motor()`, que devolve
    (tem?, nome da placa). Enquanto isto travava só o `tem_gpu_nvidia`,
    a instalação de VERDADE rodava aqui: 4,3 GB dentro do tmp do pytest,
    a cada rodada da suíte nesta máquina (que tem a placa).
    """
    monkeypatch.setattr(musica_local, "gpu_do_motor", lambda: (False, ""))
    travar = [False]
    monkeypatch.setattr(musica_local, "_rodar",
                        lambda *a, **k: (travar.__setitem__(0, True), (True, "ok"))[1])
    ok, motivo = musica_local.instalar(raiz_projetos=tmp_path / "Projetos")
    assert not ok
    assert "NVIDIA" in motivo
    assert not travar[0], "sem placa, nada pode ser baixado"


def test_ja_instalado_nao_baixa_de_novo(monkeypatch, tmp_path):
    monkeypatch.setattr(musica_local, "instalado", lambda raiz=None: True)
    chamou = []
    monkeypatch.setattr(musica_local, "_rodar",
                        lambda *a, **k: (chamou.append(1), (True, "ok"))[1])
    ok, motivo = musica_local.instalar(raiz_projetos=tmp_path)
    assert ok and motivo == "já instalado"
    assert not chamou, "baixou de novo o que já estava lá"


def test_cancelar_para_antes_de_baixar(monkeypatch, tmp_path):
    monkeypatch.setattr(musica_local, "tem_gpu_nvidia", lambda: True)
    monkeypatch.setattr(musica_local, "_uv", lambda: "uv")
    ev = threading.Event()
    ev.set()
    ok, motivo = musica_local.instalar(raiz_projetos=tmp_path, cancelar=ev)
    assert not ok and motivo == "cancelado"


def test_modelo_que_falha_e_falha_de_instalacao(monkeypatch, tmp_path):
    """A 3.23 dava isto por bom ("o modelo vem na primeira musica"). A
    auditoria mostrou o custo: o modelo pesa 2,3 GB e o launcher desiste em
    240s — sem ele, a primeira musica de TODO video estoura o prazo, a
    trilha cai para a biblioteca e parece que o motor nao funciona. Melhor
    dizer que faltou, com reparo pela mesma tela."""
    monkeypatch.setattr(musica_local, "pasta_motor",
                        lambda raiz=None: tmp_path / "MotorMusica")
    monkeypatch.setattr(musica_local, "tem_gpu_nvidia", lambda: True)
    monkeypatch.setattr(musica_local, "_uv", lambda: "uv")
    monkeypatch.setattr(musica_local, "instalado", lambda raiz=None: False)
    passos = []

    def falso(cmd, minutos=60):
        passos.append(cmd[0])
        return (False, "sem rede") if "-c" in cmd else (True, "ok")
    monkeypatch.setattr(musica_local, "_rodar", falso)
    ok, motivo = musica_local.instalar(raiz_projetos=tmp_path)
    assert not ok, motivo
    assert "modelo" in motivo


def test_o_progresso_e_pesado_pelo_tamanho():
    """PyTorch é a maior parte da espera: a barra não pode andar em passos
    iguais e mentir por minutos."""
    s = (RAIZ / "app" / "musica_local.py").read_text(encoding="utf-8")
    i = s.index("passo(0.06")
    j = s.index("passo(0.55")
    assert i < j, "o passo do torch tem de ser o maior intervalo"


def test_as_rotas_existem_nos_dois_servidores():
    for nome in ("app/local_server.py", "app/desktop_server.py"):
        s = (RAIZ / nome).read_text(encoding="utf-8")
        assert "/api/musica/motor" in s, nome


def test_a_instalacao_roda_em_fundo_e_nao_na_requisicao():
    s = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    i = s.index("def _musica_instalar_em_fundo")
    corpo = s[i:i + 1500]
    assert "threading.Thread" in corpo, "4,8 GB numa requisição = tela travada"
    assert "_MUSICA_INSTALL[\"rodando\"]" in corpo, "sem trava, dois downloads"


def test_o_render_nunca_dispara_a_instalacao():
    """Baixar gigabytes no meio do [7/9] seguraria o vídeo — o render só usa
    o motor se ele JÁ estiver pronto."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "musica_local" not in s


def test_a_tela_mostra_estado_e_acompanha_o_download():
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnInstalarMotorMusica"' in html
    assert 'id="musicMotorEstado"' in html and 'id="musicMotorBarra"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "function pintarMotorMusica" in js
    assert "acompanharMotorMusica" in js
    assert "setInterval" in js[js.index("function acompanharMotorMusica"):
                               js.index("function acompanharMotorMusica") + 600]
