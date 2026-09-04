# -*- coding: utf-8 -*-
"""5.0.24: achar a placa NVIDIA sem depender do nvidia-smi no PATH.

Ele, sobre a máquina de um cliente onde a trilha não era composta (04/09):
"ele tem placa de vídeo sim". A tela dizia "precisa de placa NVIDIA" —
`subprocess.run(["nvidia-smi", ...])` levanta OSError quando o executável
não está no PATH, e a resposta virava "sem GPU" sem dizer que placa havia.

Duas correções: procurar o nvidia-smi onde o driver o instala e, se ainda
assim não achar, perguntar ao mesmo detector que a tela Sistema usa
(Win32_VideoController + encoders do ffmpeg). E a tela passa a dizer QUAL
placa foi encontrada, para o caso de ser mesmo de outra marca.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import musica_local as m  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _limpa():
    m._GPU_CACHE.clear()
    yield
    m._GPU_CACHE.clear()


def test_procura_o_nvidia_smi_onde_o_driver_instala(monkeypatch, tmp_path):
    """Fora do PATH ele ainda tem de ser achado onde o driver o poe."""
    monkeypatch.setattr(m.shutil, "which", lambda _: None)
    assert m._nvidia_smi() == "" or Path(m._nvidia_smi()).is_file()

    falso = tmp_path / "nvidia-smi.exe"
    falso.write_text("", encoding="utf-8")
    monkeypatch.setattr(m, "_NVIDIA_SMI", (str(tmp_path / "nao-existe.exe"),
                                           str(falso)))
    assert m._nvidia_smi() == str(falso), "parou no primeiro caminho que faltou"


def test_os_caminhos_do_driver_apontam_para_o_nvidia_smi():
    assert m._NVIDIA_SMI, "a lista de caminhos do driver ficou vazia"
    for c in m._NVIDIA_SMI:
        assert c.lower().endswith("nvidia-smi.exe"), c


def test_sem_nvidia_smi_a_placa_vem_do_detector_do_app(monkeypatch):
    monkeypatch.setattr(m, "_nvidia_smi", lambda: "")
    monkeypatch.setattr(m, "_placa_pelo_sistema",
                        lambda: (True, "NVIDIA GeForce RTX 4060"))
    tem, nome = m.gpu_do_motor()
    assert tem is True, "placa NVIDIA real dada como inexistente"
    assert nome == "NVIDIA GeForce RTX 4060"


def test_placa_de_outra_marca_aparece_pelo_nome(monkeypatch):
    monkeypatch.setattr(m, "_nvidia_smi", lambda: "")
    monkeypatch.setattr(m, "_placa_pelo_sistema",
                        lambda: (False, "AMD Radeon RX 6600"))
    tem, nome = m.gpu_do_motor()
    assert tem is False
    assert nome == "AMD Radeon RX 6600", "a tela não teria o que mostrar"
    assert m.estado()["gpuNome"] == "AMD Radeon RX 6600"


def test_a_deteccao_e_perguntada_uma_vez_so(monkeypatch):
    """O poll da tela pergunta de 3 em 3 segundos."""
    n = []
    monkeypatch.setattr(m, "_nvidia_smi", lambda: n.append(1) or "")
    monkeypatch.setattr(m, "_placa_pelo_sistema", lambda: (False, ""))
    for _ in range(3):
        m.gpu_do_motor()
    assert len(n) == 1


def test_o_motivo_da_recusa_diz_o_que_achou(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "gpu_do_motor", lambda: (False, "Intel UHD Graphics"))
    ok, motivo = m.instalar(raiz_projetos=tmp_path)
    assert ok is False
    assert "Intel UHD Graphics" in motivo and "NVIDIA" in motivo


def test_a_tela_mostra_a_placa_encontrada():
    i = JS.index('precisa de placa NVIDIA "')
    bloco = JS[i - 400:i + 400]
    assert "d.gpuNome" in bloco, "a tela volta a só dizer o que falta"
    assert "não encontrei placa aqui" in bloco


def test_a_nvidia_e_achada_mesmo_listada_depois_da_integrada(monkeypatch):
    """O notebook lista a Intel primeiro e a NVIDIA depois."""
    import app.system_info as si

    monkeypatch.setattr(si, "detect_machine", lambda *a, **k: {"gpus": [
        {"name": "Intel(R) UHD Graphics"},
        {"name": "NVIDIA GeForce RTX 3050 Laptop GPU"},
    ]})
    tem, nome = m._placa_pelo_sistema()
    assert tem is True
    assert nome == "NVIDIA GeForce RTX 3050 Laptop GPU", (
        "a tela diria o nome da placa integrada")


def test_o_estado_diz_quanto_espaco_ha_no_disco_do_motor(tmp_path, monkeypatch):
    """5.0.26: 4,8 GB de espera para terminar em erro é pior que não
    oferecer. O cartão precisa saber ANTES do clique."""
    monkeypatch.setattr(m, "pasta_motor", lambda raiz=None: tmp_path / "MotorMusica")
    monkeypatch.setattr(m, "instalado", lambda raiz=None: False)
    e = m.estado()
    assert e["livreGb"] > 0, "sem a medida o cartão não tem como avisar"
    assert e["precisaGb"] == 7


def test_o_espaco_e_medido_na_pasta_que_existe(tmp_path, monkeypatch):
    """A pasta do motor ainda NÃO existe antes de instalar — medir nela
    daria erro e a resposta viraria zero, escondendo o botão sem motivo."""
    fundo = tmp_path / "a" / "b" / "c" / "MotorMusica"
    monkeypatch.setattr(m, "pasta_motor", lambda raiz=None: fundo)
    monkeypatch.setattr(m, "instalado", lambda raiz=None: False)
    assert m.estado()["livreGb"] > 0


def test_o_cartao_esconde_o_botao_quando_o_download_morreria():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("IA local não instalada — são ${gb} GB")
    bloco = js[i - 900:i + 400]
    assert "d.livreGb" in bloco and "d.precisaGb" in bloco
    assert "!d.uv" in bloco, "sem o uv o download morre no primeiro passo"
    assert 'btn.classList.toggle("hidden", !!falta)' in bloco
