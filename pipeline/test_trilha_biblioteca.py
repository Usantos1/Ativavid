# -*- coding: utf-8 -*-
"""Plano B da trilha: a biblioteca do usuario entra quando a IA falha.

Caso real (26/08): 346k creditos do ElevenLabs queimados, plano renova
08/09 — ate la TODA trilha falharia e o video sairia mudo com um aviso.
O plano B usa MP3s que o usuario deixou em ATIVAVID/Biblioteca/Trilhas.
"""
import json
import subprocess
from pathlib import Path

import pytest

import pipeline.run_fast as rf

RAIZ = Path(__file__).resolve().parent.parent


def _tem_ffmpeg() -> bool:
    try:
        subprocess.run([rf._ffmpeg_exe(), "-version"],
                       capture_output=True, check=True)
        return True
    except Exception:
        return False


def _faixa_seno(dest: Path, dur: float) -> None:
    subprocess.run(
        [rf._ffmpeg_exe(), "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={dur}",
         "-c:a", "libmp3lame", "-q:a", "6", str(dest)],
        capture_output=True, check=True)


@pytest.fixture()
def biblioteca(tmp_path, monkeypatch):
    """Home falsa com Biblioteca/Trilhas — nunca a pasta real do usuario."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    pasta = tmp_path / "ATIVAVID" / "Biblioteca" / "Trilhas"
    pasta.mkdir(parents=True)
    return pasta


def test_pasta_vazia_devolve_none_e_cria_a_pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    destino = tmp_path / "trilha.mp3"
    assert rf._trilha_da_biblioteca(destino, 30.0) is None
    assert (tmp_path / "ATIVAVID" / "Biblioteca" / "Trilhas").is_dir(), \
        "a pasta deve nascer na primeira falha para o usuario achar onde por"
    assert not destino.exists()


@pytest.mark.skipif(not _tem_ffmpeg(), reason="sem ffmpeg")
def test_faixa_curta_e_loopada_para_a_duracao_do_video(biblioteca, tmp_path):
    """Faixa de 3s, video de 20s: a saida tem ~22s (loop + margem)."""
    _faixa_seno(biblioteca / "lofi.mp3", 3.0)
    # padding p/ passar o filtro de 50KB (mp3 de seno e minusculo)
    with open(biblioteca / "lofi.mp3", "ab") as f:
        f.write(b"\x00" * 60_000)
    destino = tmp_path / "trilha.mp3"
    assert rf._trilha_da_biblioteca(destino, 20.0) == "lofi.mp3"
    probe = subprocess.run(
        [rf._ffprobe_exe(), "-v", "quiet", "-print_format", "json",
         "-show_format", str(destino)],
        capture_output=True, text=True, check=True)
    dur = float(json.loads(probe.stdout)["format"]["duration"])
    assert 20.5 <= dur <= 23.5, f"esperava ~22s, saiu {dur}"


@pytest.mark.skipif(not _tem_ffmpeg(), reason="sem ffmpeg")
def test_rodizio_nao_repete_a_mesma_faixa(biblioteca, tmp_path):
    for nome in ("a.mp3", "b.mp3"):
        _faixa_seno(biblioteca / nome, 2.0)
        with open(biblioteca / nome, "ab") as f:
            f.write(b"\x00" * 60_000)
    usados = [rf._trilha_da_biblioteca(tmp_path / f"t{i}.mp3", 4.0)
              for i in range(3)]
    assert usados[0] != usados[1], "duas gerações seguidas, mesma música"
    assert usados[2] == usados[0], "o rodízio deve dar a volta"
    assert (biblioteca / ".rodizio.txt").is_file()


def test_arquivo_que_nao_e_musica_e_ignorado(biblioteca, tmp_path):
    (biblioteca / "leia-me.txt").write_text("x" * 60_000)
    (biblioteca / "capa.jpg").write_bytes(b"\x00" * 60_000)
    assert rf._trilha_da_biblioteca(tmp_path / "trilha.mp3", 10.0) is None


def test_o_gancho_esta_no_ponto_de_falha_da_ia():
    """O plano B tem de rodar nas DUAS falhas (creditos e generica) e
    limpar o musicaSkip quando salva o video; sem faixa na pasta, o aviso
    ganha a dica de onde por os MP3s."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find('"créditos do ElevenLabs esgotados')
    assert i > 0
    trecho = s[i:i + 1800]
    assert "_trilha_da_biblioteca(" in trecho
    assert '_RENDER_META.pop("musicaSkip"' in trecho
    assert "Biblioteca/Trilhas" in trecho, "cade a dica no aviso?"
    assert '"musicaFonte"' in s.split("def _grava_timing")[0] or \
        'payload["musicaFonte"]' in s, "timing.json precisa levar a fonte"


def test_o_card_conta_que_a_trilha_veio_da_biblioteca(tmp_path):
    from app.jobs_view import _aviso_de_trilha
    (tmp_path / "timing.json").write_text(
        json.dumps({"musicaFonte": "lofi.mp3"}), encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "biblioteca" in job["trilhaNota"]
    assert "lofi.mp3" in job["trilhaNota"]
    # e o "sem trilha" continua mandando quando as DUAS coisas falharam
    (tmp_path / "timing.json").write_text(
        json.dumps({"musicaFonte": "x.mp3", "musicaSkip": "tudo caiu"}),
        encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert job["trilhaNota"].startswith("Sem trilha sonora")


# ---------- escolha por clima (3.02) ----------

def _faixa_falsa(pasta, nome):
    (pasta / nome).write_bytes(b"\x00" * 60_000)


@pytest.fixture()
def _sem_ffmpeg_real(monkeypatch, tmp_path):
    """A selecao acontece ANTES do ffmpeg; um subprocess falso que so copia
    a faixa escolhida deixa testar a escolha sem gerar audio de verdade."""
    import shutil as _sh

    def fake_run(cmd, **kw):
        src = cmd[cmd.index("-i") + 1]
        dest = cmd[-1]
        _sh.copyfile(src, dest)
        class R:  # noqa: N801
            returncode = 0
        return R()
    monkeypatch.setattr(rf.subprocess, "run", fake_run)


def test_video_viral_pega_trilha_viral(biblioteca, tmp_path, _sem_ffmpeg_real):
    _faixa_falsa(biblioteca, "educacional--calma.mp3")
    _faixa_falsa(biblioteca, "viral--phonk.mp3")
    _faixa_falsa(biblioteca, "solta.mp3")
    assert rf._trilha_da_biblioteca(tmp_path / "t.mp3", 10.0,
                                    ct="viral") == "viral--phonk.mp3"


def test_tipo_em_ingles_casa_com_etiqueta_em_portugues(
        biblioteca, tmp_path, _sem_ffmpeg_real):
    """O contentType interno e "educational"; a etiqueta do arquivo e
    "educacional--". A traducao e da funcao, nao do usuario."""
    _faixa_falsa(biblioteca, "educacional--piano.mp3")
    _faixa_falsa(biblioteca, "viral--phonk.mp3")
    assert rf._trilha_da_biblioteca(tmp_path / "t.mp3", 10.0,
                                    ct="educational") == "educacional--piano.mp3"


def test_sem_faixa_do_tipo_cai_no_mesmo_clima(
        biblioteca, tmp_path, _sem_ffmpeg_real):
    """Video "sales" (agitado) sem faixa venda--: pega viral-- (agitado),
    nunca a educacional-- (calma)."""
    _faixa_falsa(biblioteca, "educacional--piano.mp3")
    _faixa_falsa(biblioteca, "viral--phonk.mp3")
    assert rf._trilha_da_biblioteca(tmp_path / "t.mp3", 10.0,
                                    ct="sales") == "viral--phonk.mp3"


def test_rodizio_roda_dentro_do_clima(biblioteca, tmp_path, _sem_ffmpeg_real):
    _faixa_falsa(biblioteca, "viral--a.mp3")
    _faixa_falsa(biblioteca, "viral--b.mp3")
    _faixa_falsa(biblioteca, "educacional--c.mp3")
    usados = [rf._trilha_da_biblioteca(tmp_path / f"t{i}.mp3", 5.0, ct="viral")
              for i in range(3)]
    assert usados == ["viral--a.mp3", "viral--b.mp3", "viral--a.mp3"]


def test_longform_e_calmo(biblioteca, tmp_path, _sem_ffmpeg_real):
    _faixa_falsa(biblioteca, "viral--phonk.mp3")
    _faixa_falsa(biblioteca, "institucional--pads.mp3")
    assert rf._trilha_da_biblioteca(tmp_path / "t.mp3", 60.0,
                                    ct="longform") == "institucional--pads.mp3"


def test_o_gancho_passa_o_tipo_do_video():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("_nome_bib = _trilha_da_biblioteca(")
    assert i > 0
    antes = s[max(0, i - 600):i]
    assert "normalize_content_type" in antes
    assert '"longform" if is_longform' in antes


# ---------- Biblioteca: musicas no acervo e na tela ----------

def test_list_assets_inclui_trilhas_e_broll_nao_as_pega(tmp_path):
    from app import broll_library as bl
    projetos = tmp_path / "Projetos"
    projetos.mkdir()
    root = bl.library_root(projetos)
    (root / "images" / "produto.jpg").write_bytes(b"x" * 10)
    (root / "Trilhas" / "viral--phonk.mp3").write_bytes(b"x" * 10)
    kinds = {i["name"]: i["kind"] for i in bl.list_assets(projetos)["items"]}
    assert kinds == {"produto.jpg": "image", "viral--phonk.mp3": "track"}
    # musica NUNCA vira b-roll: um video sobre "phonk viral" nao pode
    # receber um mp3 como imagem de apoio
    achados = bl.pick_for_query("phonk viral", projetos)
    assert all(a["kind"] != "track" for a in achados)


def test_upload_de_musica_cai_em_trilhas_e_preserva_etiqueta(tmp_path):
    from app import broll_library as bl
    projetos = tmp_path / "Projetos"
    projetos.mkdir()
    out = bl.add_bytes("Viral--Minha Musica!.mp3", b"\x00" * 10,
                       projects_root=projetos)
    assert out["kind"] == "track"
    assert out["rel"].startswith("Trilhas/")
    assert out["name"].startswith("viral--"), \
        "a etiqueta do usuario nao pode ser comida pelo slug"


def test_a_tela_da_biblioteca_mostra_as_trilhas():
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnLibraryUploadMusic"' in html
    assert 'id="libraryTracks"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "renderLibraryTracks" in js
    assert 'kind === "track"' in js
    css = (RAIZ / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    assert ".lib-track" in css
