# -*- coding: utf-8 -*-
"""5.0.25: o Diagnóstico diz o que falta instalar — e instala dali.

Ele (04/09, com print do painel): "aqui não deveria mostrar se a IA local
está instalada, se o motor próprio está instalado e tudo mais, porque assim
o cliente poderia baixar por aqui nessa checagem".

O instalador tem ~7 MB de propósito: transcrição local e IA de música são
baixadas depois, sob demanda. Quem nunca abriu Configurações não sabe que
existem — e o Diagnóstico, que é a primeira tela de quem desconfia que algo
não está certo, não falava delas.

`diz()` ganhou um campo `acao`: o ÚNICO que a tela transforma em botão. A
instalação em si é a mesma de Configurações → Música dos vídeos.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
# `doutor.py` importa `_utf8`, que mora na pasta dos helpers
if str(REPO / "helpers") not in sys.path:
    sys.path.insert(0, str(REPO / "helpers"))

DOUTOR = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _itens(monkeypatch, estado):
    import helpers.doutor as dt
    from app import musica_local

    monkeypatch.setattr(musica_local, "estado", lambda *a, **k: estado)
    dt._itens.clear()
    dt.checar_pecas_opcionais()
    return list(dt._itens)


BASE = {"instalado": False, "incompleta": False, "gpu": True, "gpuNome": "",
        "mbTotal": 4800, "gb": 0.0, "pasta": "X:/MotorMusica", "uv": True}


def test_instalada_aparece_como_ok_e_sem_botao(monkeypatch):
    it = _itens(monkeypatch, {**BASE, "instalado": True, "gb": 4.5})[0]
    assert it["nivel"] == "ok"
    assert "4.5 GB" in it["detalhe"]
    assert not it["acao"], "botão de instalar no que já está instalado"


def test_faltando_vira_aviso_com_botao(monkeypatch):
    it = _itens(monkeypatch, BASE)[0]
    assert it["nivel"] == "aviso"
    assert "4,8 GB" in it["detalhe"], "não diz o tamanho do download"
    assert it["acao"] == "instalar_musica" and it["acaoTexto"]


def test_pela_metade_oferece_continuar(monkeypatch):
    it = _itens(monkeypatch, {**BASE, "incompleta": True})[0]
    assert it["acao"] == "instalar_musica"
    assert "ontinuar" in it["acaoTexto"]


def test_sem_placa_nao_oferece_o_que_nao_da_para_instalar(monkeypatch):
    it = _itens(monkeypatch, {**BASE, "gpu": False,
                              "gpuNome": "AMD Radeon RX 6600"})[0]
    assert it["nivel"] == "aviso"
    assert "AMD Radeon RX 6600" in it["detalhe"], "não diz que placa achou"
    assert not it["acao"], "ofereceria um download que seria recusado"
    assert "Biblioteca/Trilhas" in it["solucao"], "não diz o plano B"


def test_a_verificacao_entra_na_rodada():
    i = DOUTOR.index("for fn in (checar_programas")
    assert "checar_pecas_opcionais" in DOUTOR[i:i + 300], (
        "a checagem existe mas nunca roda")


def test_um_check_quebrado_nao_derruba_o_diagnostico(monkeypatch):
    import helpers.doutor as dt
    from app import musica_local

    def explode(*a, **k):
        raise RuntimeError("sem disco")
    monkeypatch.setattr(musica_local, "estado", explode)
    dt._itens.clear()
    dt.checar_pecas_opcionais()
    assert dt._itens and dt._itens[0]["nivel"] == "aviso"


def test_a_tela_desenha_o_botao_e_chama_a_rota_certa():
    assert 'class="ghost-btn ghost-btn--sm doutor-acao"' in SJS
    assert 'data-acao="${escapeHtml(it.acao)}"' in SJS
    i = SJS.index("function wireAcoesDoDoutor(")
    corpo = SJS[i:i + 1400]
    assert '"/api/musica/motor"' in corpo, "o botão não instala nada"
    assert 'action: "instalar"' in corpo
    assert "acompanharMotorMusica()" in corpo, "sem progresso, parece travado"


def test_sem_uv_avisa_em_vez_de_oferecer_um_download_que_morre(monkeypatch):
    """Oferecer um botão que falha no meio é pior que não oferecer: o
    cliente espera gigabytes e recebe um erro."""
    it = _itens(monkeypatch, {**BASE, "uv": False})[0]
    assert not it["acao"]
    assert "uv" in it["detalhe"]
    assert "Reinstale" in it["solucao"]


def test_disco_cheio_avisa_antes_do_clique(monkeypatch):
    import helpers.doutor as dt

    monkeypatch.setattr(dt.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 3 * 1024 ** 3})())
    it = _itens(monkeypatch, {**BASE, "uv": True, "pasta": str(REPO)})[0]
    assert not it["acao"], "ofereceria 4,8 GB num disco com 3"
    assert "3.0 GB livres" in it["detalhe"]


def test_com_tudo_no_lugar_o_botao_aparece(monkeypatch):
    import helpers.doutor as dt

    monkeypatch.setattr(dt.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 40 * 1024 ** 3})())
    it = _itens(monkeypatch, {**BASE, "uv": True, "pasta": str(REPO)})[0]
    assert it["acao"] == "instalar_musica"


def test_biblioteca_de_trilhas_vazia_sem_ia_local_vira_aviso_com_botao(monkeypatch, tmp_path):
    """5.0.36: máquina sem NVIDIA e sem MP3 = vídeo mudo de música, e a tela
    não dizia isso em lugar nenhum. O botão baixa o pacote da 5.0.29."""
    from app import broll_library

    (tmp_path / "Biblioteca" / "Trilhas").mkdir(parents=True)
    monkeypatch.setattr(broll_library, "library_root", lambda *a, **k: tmp_path / "Biblioteca")
    itens = _itens(monkeypatch, {**BASE, "gpu": False, "gpuNome": "Intel(R) UHD Graphics"})
    vazia = [i for i in itens if "trilhas vazia" in i["titulo"].lower()]
    assert vazia and vazia[0]["acao"] == "baixar_pacote"


def test_com_trilhas_na_pasta_nao_avisa(monkeypatch, tmp_path):
    from app import broll_library

    p = tmp_path / "Biblioteca" / "Trilhas"
    p.mkdir(parents=True)
    (p / "uma.mp3").write_bytes(b"x" * 10)
    monkeypatch.setattr(broll_library, "library_root", lambda *a, **k: tmp_path / "Biblioteca")
    itens = _itens(monkeypatch, {**BASE, "gpu": False})
    assert not [i for i in itens if "trilhas vazia" in i["titulo"].lower()]


def test_com_ia_local_instalada_a_pasta_vazia_nao_importa(monkeypatch, tmp_path):
    from app import broll_library

    (tmp_path / "Biblioteca" / "Trilhas").mkdir(parents=True)
    monkeypatch.setattr(broll_library, "library_root", lambda *a, **k: tmp_path / "Biblioteca")
    itens = _itens(monkeypatch, {**BASE, "instalado": True, "gb": 4.5})
    assert not [i for i in itens if "trilhas vazia" in i["titulo"].lower()]


def test_a_tela_liga_o_botao_do_pacote_e_o_cabecalho_ao_diagnostico():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function wireAcoesDoDoutor(")
    corpo = js[i:i + 2200]
    assert '"baixar_pacote"' in corpo and '"/api/biblioteca/pacote"' in corpo
    j = js.index("const topo = $(\"#sysStatusLine\")")
    assert "veja o Diagnóstico" in js[j:j + 500], "o cabeçalho continua discordando do cartão"
