# -*- coding: utf-8 -*-
"""Os efeitos do app voltam a ser o padrao, e o botao de criar preset cria.

"refiz ele e ainda ta com uns efeitos sonoros nada a ver" (30/08) — a
segunda queixa em dois dias sobre a mesma troca automatica. O render das
18:51 ja rodava com o teto de 4.19, e um caso passava:

    cut-click do app    0,057 s
    teto de 4.19        0,657 s   (o piso `+0,6` domina um som de 57ms)
    corte--025.mp3      0,63  s   <- entrou, 11x o original

Duas mudancas: o piso vira `+0,15` (e ai a vaga `corte` fica sem
candidato na biblioteca dele), e a troca inteira passa a ser OPCIONAL,
desligada. Ela nasceu na 4.10 por iniciativa nossa e nunca foi pedida.

E "botao Criar preset novo, nao funciona": era um `data-view="estilo"`
que so trocava de tela.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import broll_library as bl  # noqa: E402

APP_SFX = REPO / "assets" / "shortform" / "public" / "sfx"
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _tom(destino: Path, segundos: float) -> Path:
    from app.ffmpeg_tools import ffmpeg_bin

    subprocess.run(
        [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"sine=frequency=900:duration={segundos}",
         "-af", "volume=-6dB", "-c:a", "libmp3lame", "-q:a", "5",
         str(destino)],
        check=True, capture_output=True, timeout=60)
    return destino


@pytest.fixture()
def mundo(tmp_path, monkeypatch):
    """Um projeto com os sons do app e uma biblioteca com um candidato."""
    raiz = tmp_path / "Projetos"
    (raiz / "p").mkdir(parents=True)
    lib = tmp_path / "Biblioteca" / "Efeitos"
    lib.mkdir(parents=True)
    monkeypatch.setattr(bl, "library_root", lambda *_a, **_k: lib.parent)
    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True)
    for f in APP_SFX.glob("*.mp3"):
        shutil.copy2(f, public / "sfx" / f.name)
    return {"lib": lib, "public": public, "raiz": raiz}


def _ligar(monkeypatch, valor: bool) -> None:
    from app import settings_store as ss

    monkeypatch.setattr(ss, "load_settings", lambda: {"sfxDoUsuario": valor})


def test_desligado_e_o_padrao():
    from app.settings_store import DEFAULTS

    assert DEFAULTS["sfxDoUsuario"] is False


def test_desligado_nao_troca_nada(mundo, monkeypatch):
    _ligar(monkeypatch, False)
    _tom(mundo["lib"] / "whoosh--meu.mp3", 0.40)
    assert bl.aplicar_sfx_do_usuario(mundo["public"], mundo["raiz"]) == []


def test_desligado_LIMPA_o_que_uma_troca_antiga_deixou(mundo, monkeypatch):
    """A parte que conserta os videos dele sem apagar nada: o projeto
    guarda o arquivo trocado, e sem esta volta ele ficaria para sempre."""
    _ligar(monkeypatch, False)
    _tom(mundo["public"] / "sfx" / "whoosh.mp3", 8.0)   # o erro de ontem
    bl.aplicar_sfx_do_usuario(mundo["public"], mundo["raiz"])
    d = bl._dur_seg(mundo["public"] / "sfx" / "whoosh.mp3")
    assert d is not None and d < 1.0, d


def test_ligado_volta_a_trocar(mundo, monkeypatch):
    _ligar(monkeypatch, True)
    _tom(mundo["lib"] / "whoosh--meu.mp3", 0.40)
    trocados = bl.aplicar_sfx_do_usuario(mundo["public"], mundo["raiz"])
    assert any("whoosh.mp3" in t for t in trocados), trocados


def test_o_teto_nao_deixa_um_clique_de_meio_segundo(mundo, monkeypatch):
    """`cut-click` do app tem 0,057s. Com o piso antigo (+0,6) cabia um
    som de 0,63s — 11x — e foi o que saiu no video das 18:51."""
    _ligar(monkeypatch, True)
    _tom(mundo["lib"] / "corte--longo.mp3", 0.63)
    trocados = bl.aplicar_sfx_do_usuario(mundo["public"], mundo["raiz"])
    assert not any("cut-click" in t for t in trocados), trocados
    d = bl._dur_seg(mundo["public"] / "sfx" / "cut-click.mp3")
    assert d is not None and d < 0.2, d


def test_um_clique_curto_ainda_entra(mundo, monkeypatch):
    """O teto nao pode fechar a vaga para todo mundo."""
    _ligar(monkeypatch, True)
    _tom(mundo["lib"] / "corte--curto.mp3", 0.09)
    trocados = bl.aplicar_sfx_do_usuario(mundo["public"], mundo["raiz"])
    assert any("cut-click" in t for t in trocados), trocados


def test_a_tela_nao_diz_que_toca_com_a_troca_desligada(tmp_path, monkeypatch):
    _ligar(monkeypatch, False)
    assert bl._sfx_do_usuario_ligado() is False
    i = (REPO / "app" / "broll_library.py").read_text(encoding="utf-8")
    j = i.index('"tocaNoVideo"')
    assert "_sfx_do_usuario_ligado()" in i[j:j + 200]


def test_o_interruptor_existe_e_grava():
    assert 'id="sfxDoUsuario"' in HTML
    assert 'id="sfxSwitch"' in HTML
    i = JS.index('const chkSfx = $("#sfxDoUsuario");')
    bloco = JS[i:i + 900]
    assert '"/api/settings"' in bloco
    assert "sfxDoUsuario: !!chkSfx.checked" in bloco
    # so na aba de efeitos
    assert 'swi.classList.toggle("hidden", aba !== "sfx")' in JS


# --------------------------------------------------------- criar preset

def test_o_botao_de_criar_preset_cria():
    """Era `data-view="estilo"`: trocava de tela e nao criava nada."""
    assert 'id="btnPresetNovo"' in HTML
    i = HTML.index('id="btnPresetNovo"')
    assert 'data-view="estilo"' not in HTML[i - 200:i + 200]
    j = JS.index('const btnNovo = $("#btnPresetNovo");')
    bloco = JS[j:j + 1400]
    assert 'presetAction("create"' in bloco
    assert 'api("/api/preset")' in bloco, "o preset novo nasce do estilo base"
    assert "state.editPresetId = novo.id" in bloco, "abre o editor no novo"
    assert "já virou o padrão" in bloco, (
        "criar troca o padrao no servidor — a tela tem de dizer"
    )
