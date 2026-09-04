# -*- coding: utf-8 -*-
"""5.0.29: o pacote de trilhas e efeitos que o cliente baixa uma vez.

Ele (04/09): "Se a gente subir todas as nossas trilhas, e efeitos sonoros e
colocar um botao em config pra eles baixar?".

O problema que isso resolve: a IA local de música só roda em placa NVIDIA
(uma cliente com Intel UHD no mesmo dia), e o plano B sempre foi "deixe
MP3s em ATIVAVID/Biblioteca/Trilhas" — uma pasta que nasce VAZIA. Sem
placa e sem MP3s, o vídeo saía sem trilha nenhuma e ninguém sabia o que
fazer.

As duas regras que este arquivo guarda:

  1. NADA do usuário é sobrescrito. Quem já tem a pasta cheia recebe só o
     que falta, e rodar duas vezes não duplica.
  2. O ZIP vem da internet e NÃO manda no disco: caminho absoluto, `..` e
     pasta desconhecida são recusados (zip slip).
"""
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import biblioteca_pacote as bpk  # noqa: E402

SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")


def test_o_zip_nao_escreve_fora_da_biblioteca():
    for mau in ("../fora.mp3", "/etc/passwd", "C:/Windows/x.mp3",
                "Trilhas/../../fora.mp3", "Outra/x.mp3", "x.mp3"):
        assert bpk._seguro(mau) is None, f"`{mau}` passou"


def test_so_audio_entra():
    assert bpk._seguro("Trilhas/boa.mp3") is not None
    assert bpk._seguro("Efeitos/clique--001.mp3") is not None
    for mau in ("Trilhas/virus.exe", "Efeitos/script.bat", "Trilhas/a.dll"):
        assert bpk._seguro(mau) is None, f"`{mau}` passou"


def _zip(tmp_path, itens):
    z = tmp_path / "pacote.zip"
    with zipfile.ZipFile(z, "w") as f:
        for nome, dado in itens:
            f.writestr(nome, dado)
    return z


def test_instalar_traz_o_que_falta_e_nao_toca_no_que_existe(tmp_path, monkeypatch):
    biblio = tmp_path / "Biblioteca"
    (biblio / "Trilhas").mkdir(parents=True)
    minha = biblio / "Trilhas" / "minha.mp3"
    minha.write_bytes(b"a minha musica")

    z = _zip(tmp_path, [("Trilhas/minha.mp3", b"a do pacote"),
                        ("Trilhas/nova.mp3", b"nova"),
                        ("Efeitos/clique.mp3", b"clique"),
                        ("Trilhas/../fuga.mp3", b"fuga"),
                        ("Outra/x.mp3", b"fora")])
    monkeypatch.setattr(bpk, "pasta_da_biblioteca", lambda raiz=None: biblio)
    monkeypatch.setattr(bpk, "url_do_pacote", lambda: "https://exemplo/p.zip")
    monkeypatch.setattr(bpk.urllib.request, "urlopen",
                        lambda *a, **k: _resposta(z))
    r = bpk.instalar()
    assert r["ok"] and r["novos"] == 2, r
    assert minha.read_bytes() == b"a minha musica", "sobrescreveu a do usuário"
    assert (biblio / "Trilhas" / "nova.mp3").exists()
    assert (biblio / "Efeitos" / "clique.mp3").exists()
    assert not (tmp_path / "fuga.mp3").exists(), "escapou da Biblioteca"
    assert not (biblio / "Outra").exists()

    # de novo: nada novo, nada duplicado
    r2 = bpk.instalar()
    assert r2["ok"] and r2["novos"] == 0


class _resposta:
    """Um `urlopen` de mentira que devolve o ZIP do disco."""

    def __init__(self, caminho):
        self._f = open(caminho, "rb")
        self.headers = {"Content-Length": str(caminho.stat().st_size)}

    def read(self, n=-1):
        return self._f.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._f.close()


def test_sem_pacote_publicado_nao_promete_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(bpk, "url_do_pacote", lambda: "")
    monkeypatch.setattr(bpk, "pasta_da_biblioteca", lambda raiz=None: tmp_path)
    r = bpk.instalar()
    assert r["ok"] is False and "publicado" in r["error"]


def test_o_temporario_some_mesmo_quando_da_errado(tmp_path, monkeypatch):
    biblio = tmp_path / "Biblioteca"
    biblio.mkdir()
    ruim = tmp_path / "ruim.zip"
    ruim.write_bytes(b"isto nao e um zip")
    monkeypatch.setattr(bpk, "pasta_da_biblioteca", lambda raiz=None: biblio)
    monkeypatch.setattr(bpk, "url_do_pacote", lambda: "https://exemplo/p.zip")
    monkeypatch.setattr(bpk.urllib.request, "urlopen",
                        lambda *a, **k: _resposta(ruim))
    r = bpk.instalar()
    assert r["ok"] is False
    assert not (biblio / "_pacote.part").exists(), "deixou 370 MB de lixo"


def test_a_rota_existe_nos_dois_verbos():
    assert SRV.count('if path == "/api/biblioteca/pacote":') == 2, (
        "faltou o GET (estado) ou o POST (baixar)")
    i = SRV.index('if path == "/api/biblioteca/pacote":',
                  SRV.index('if path == "/api/biblioteca/pacote":') + 10)
    assert "\"baixar\"" in SRV[i:i + 500]
    assert "instalar_em_fundo" in SRV[i:i + 500], (
        "370 MB numa requisição síncrona derruba a tela")


def test_a_tela_tem_botao_barra_e_acompanhamento():
    assert 'id="btnBaixarPacote"' in HTML and 'id="pacoteBarra"' in HTML
    assert "function pintarPacoteBiblioteca()" in SJS
    assert "acompanharPacote()" in SJS, "sem poll, a barra congela"
    i = SJS.index("function pintarPacoteBiblioteca()")
    corpo = SJS[i:i + 2200]
    assert 'btn.classList.toggle("hidden", !d.url)' in corpo, (
        "botão aparece antes de o pacote existir e erra no clique")
