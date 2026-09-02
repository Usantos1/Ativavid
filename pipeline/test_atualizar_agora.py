# -*- coding: utf-8 -*-
""""Atualizar agora": o app baixa e executa o instalador sozinho.

O ciclo manual (aviso -> navegador -> download -> achar o exe -> rodar)
fazia o usuario pedir o instalador no chat a cada release ("cade o
instalador final?"). O servidor baixa o exe da politica de versao e o abre;
o proprio instalador derruba o app e o reabre.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _preparar(monkeypatch, tmp_path, url, corpo=b"x" * 2_000_000):
    import app.update_check as uc

    monkeypatch.setattr(uc, "check_update", lambda: {"downloadUrl": url})
    monkeypatch.setattr(uc.sys, "platform", "win32")
    import tempfile
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    import urllib.request

    class _Resp(io.BytesIO):
        # `headers` porque o download passou a ler Content-Length: e dele que
        # sai a porcentagem da barra de progresso.
        headers = {"Content-Length": str(len(corpo))}

        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda u, timeout=0: _Resp(corpo))
    abertos = []
    monkeypatch.setattr(uc.os, "startfile", lambda p: abertos.append(p),
                        raising=False)
    return uc, abertos


def test_baixa_e_abre_o_instalador(monkeypatch, tmp_path):
    uc, abertos = _preparar(
        monkeypatch, tmp_path,
        "https://github.com/x/y/releases/download/v9/Instalar.ATIVAVID.9.99.exe")
    r = uc.baixar_e_instalar()
    assert r["ok"], r
    assert abertos and abertos[0].endswith("Instalar.ATIVAVID.9.99.exe")
    assert Path(abertos[0]).is_file()


def test_recusa_download_que_nao_e_exe(monkeypatch, tmp_path):
    uc, abertos = _preparar(monkeypatch, tmp_path, "https://x/pagina.html")
    r = uc.baixar_e_instalar()
    assert not r["ok"] and not abertos


def test_recusa_download_pequeno_demais(monkeypatch, tmp_path):
    """Pagina de erro salva como .exe nao pode ser executada."""
    uc, abertos = _preparar(monkeypatch, tmp_path,
                            "https://x/Instalar.ATIVAVID.9.99.exe",
                            corpo=b"<html>404</html>")
    r = uc.baixar_e_instalar()
    assert not r["ok"] and not abertos


def test_a_rota_e_o_botao_existem():
    srv = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    assert 'action == "instalar"' in srv
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnUpdInstalar"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert '"instalar"' in js.replace("'", '"')


# ---------- Ajustes tambem atualiza sem navegador (3.08) ----------

def test_o_botao_de_ajustes_instala_no_app_e_nao_abre_o_navegador():
    """Ate a 3.07 a tela de Configuracoes mandava SEMPRE para o GitHub
    ("Baixar atualizacao" -> action release), enquanto a janela de aviso ja
    baixava e instalava sozinha. Dois caminhos para a mesma coisa, e o pior
    deles no lugar onde o usuario procura ("a atualizacao deve baixar sem
    navegador, tudo no app"). O navegador continua existindo — mas so
    depois do download falhar."""
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.find('const btnUpdateOpen = $("#btnUpdateOpen");')
    assert i > 0
    assert "instalarAtualizacao(btnUpdateOpen)" in js[i:i + 300], \
        "o botao de Ajustes saiu do caminho unico"
    # e o caminho unico tenta instalar primeiro; navegador so no catch.
    # A funcao INTEIRA, nao janela fixa: a guarda da fila (4.78) cresceu o
    # comeco e 1400 chars cortavam o catch.
    j = js.find("async function instalarAtualizacao(")
    corpo = js[j:js.find("\nasync function", j + 10)]
    i_instalar = corpo.find('action: "instalar"')
    i_navegador = corpo.find("openUpdateDownload(")
    assert 0 < i_instalar < i_navegador, \
        "o navegador tem de ser a RESERVA, nunca a primeira tentativa"
    assert "Baixando…" in corpo, "sem retorno visual durante o download"


def test_TODAS_as_portas_de_atualizar_instalam_no_app():
    """3.08 consertou UMA porta e a pastilha de versao na barra de titulo
    continuou mandando para o GitHub ("o botao ao lado do sol e lua ainda
    baixa em navegador" — 27/08), porque a logica estava COPIADA em tres
    lugares. Agora existe uma funcao so; toda porta chama ela."""
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert js.count("async function instalarAtualizacao(") == 1
    for porta in ("btnUpdateOpen.onclick = () => instalarAtualizacao(",
                  "btnUpdInstalar.onclick = () => instalarAtualizacao("):
        assert porta in js, f"porta fora do caminho unico: {porta}"
    # pastilha de versao (barra de titulo)
    i = js.find("if (up.updateAvailable) {")
    assert i > 0
    trecho = js[i:i + 900]
    assert "instalarAtualizacao()" in trecho, "a pastilha nao instala no app"
    assert 'body: JSON.stringify({ url:' not in trecho,         "a pastilha ainda abre o navegador"


def test_nao_ha_botao_de_navegador_na_janela_de_aviso():
    """Pedido direto: "ali nao quero pelo navegador"."""
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert "Baixar pelo navegador" not in html
    assert 'id="btnUpdDownload"' not in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'btnUpdDownload' not in js, "sobrou fio solto para o botao removido"


def test_o_navegador_continua_como_rede_de_seguranca():
    """Sem botao, mas o abridor segue existindo para quando o download
    falhar (proxy de empresa, antivirus) — senao o usuario fica sem saida."""
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.find("async function instalarAtualizacao(")
    corpo = js[i:js.find("\nasync function", i + 10)]
    assert "catch" in corpo and "openUpdateDownload(" in corpo


def test_o_rotulo_do_botao_promete_o_que_ele_faz():
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert '"Atualizar agora" : "Reinstalar a última versão"' in js
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert "Baixar última versão" not in html, \
        "o rotulo antigo prometia download, nao instalacao"
