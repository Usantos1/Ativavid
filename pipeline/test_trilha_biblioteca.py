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
    trecho = s[i:i + 2600]
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


# ---------- junction: a biblioteca REAL e a da raiz dos projetos (3.03) ----------

def test_a_pasta_vem_da_raiz_dos_projetos_nao_do_home(
        tmp_path, monkeypatch, _sem_ffmpeg_real):
    """Caso real 26/08: Projetos do usuario e um junction C:->E:. O home
    (C:) tinha uma biblioteca vazia; a do app (E:) tinha as 139 trilhas — e
    o plano B olhava o C:. A raiz dos projetos e a unica fonte de verdade."""
    home_falso = tmp_path / "disco-c"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home_falso))
    raiz = tmp_path / "disco-e" / "Projetos"
    trilhas = tmp_path / "disco-e" / "Biblioteca" / "Trilhas"
    trilhas.mkdir(parents=True)
    (trilhas / "viral--phonk.mp3").write_bytes(b"\x00" * 60_000)
    nome = rf._trilha_da_biblioteca(tmp_path / "t.mp3", 10.0, ct="viral",
                                    raiz_projetos=raiz)
    assert nome == "viral--phonk.mp3"
    assert not (home_falso / "ATIVAVID" / "Biblioteca" / "Trilhas"
                / "viral--phonk.mp3").exists()


def test_o_gancho_passa_a_raiz_dos_projetos():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("_nome_bib = _trilha_da_biblioteca(")
    assert i > 0
    assert "raiz_projetos=edit_dir.parents[1]" in s[i:i + 300], \
        "sem a raiz o plano B volta a olhar o home (junction C:->E:)"


# ---------- motor local de musica (3.04) ----------

def test_launcher_sem_motor_sai_rapido_com_3(tmp_path, monkeypatch):
    """Maquina de cliente sem o venv MotorMusica: o launcher sai com codigo
    3 em milissegundos e o pipeline cai para a biblioteca — instalacao de
    cliente nao paga nada pelo recurso."""
    import subprocess as sp
    import sys
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("ATIVAVID_MUSICGEN_PY", raising=False)
    r = sp.run([sys.executable, str(RAIZ / "helpers" / "musicgen_local.py"),
                "vibe qualquer", "-o", str(tmp_path / "t.mp3"),
                "--motor", str(tmp_path / "nao-existe")],
               capture_output=True, text=True, timeout=30)
    assert r.returncode == 3
    assert "motor local" in r.stdout


def test_ordem_dos_planos_elevenlabs_motor_biblioteca():
    """A retentativa sincrona tenta NESTA ordem: ElevenLabs -> motor local
    -> biblioteca; e a biblioteca so roda se a trilha ainda nao existe."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find('"créditos do ElevenLabs esgotados')
    assert i > 0
    trecho = s[i:i + 2600]
    i_motor = trecho.find("_tentar_musicgen(trilha")
    i_bib = trecho.find("_trilha_da_biblioteca(")
    assert 0 < i_motor < i_bib, "motor tem de vir antes da biblioteca"
    assert "if not trilha.exists():" in trecho[:i_bib + 50]


def test_fio_antecipado_tambem_tem_o_motor():
    """O caminho normal e o fio antecipado (paralelo ao prep): o motor tem
    de compor ali, senao todo video com ElevenLabs fora paga +90s no [7/9]."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("def _music_worker")
    assert i > 0
    trecho = s[i:i + 1200]
    assert "_tentar_musicgen(music_tmp" in trecho
    assert '_music_via["motor"] = True' in trecho


def test_o_card_conta_que_o_motor_compos(tmp_path):
    from app.jobs_view import _aviso_de_trilha
    (tmp_path / "timing.json").write_text(
        json.dumps({"musicaFonte": "motor: MusicGen local"}),
        encoding="utf-8")
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "IA local" in job["trilhaNota"]
    assert "biblioteca" not in job["trilhaNota"]


# ---------- motor local como PRINCIPAL (3.05) ----------

def test_preferencia_le_o_settings_e_rejeita_valor_estranho(monkeypatch):
    import app.settings_store as ss
    for valor, esperado in (("local", "local"), ("nuvem", "nuvem"),
                            ("auto", "auto"), ("banana", "auto"),
                            (None, "auto")):
        monkeypatch.setattr(ss, "load_settings",
                            lambda v=valor: {"musicEngine": v})
        assert rf._preferencia_motor_musica() == esperado


def test_settings_tem_a_chave_com_padrao_nuvem_primeiro():
    """O padrao NAO pode mudar sozinho: maquina de cliente nao tem o motor
    local, e "local" ali faria toda trilha esperar o launcher falhar."""
    from app.settings_store import DEFAULTS
    assert DEFAULTS["musicEngine"] == "auto"


def test_com_local_primeiro_o_motor_roda_antes_da_nuvem():
    """Ordem dentro do fio antecipado: em "local", _local() vem antes de
    _nuvem(); em "auto", o contrario."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("def _music_worker")
    assert i > 0
    corpo = s[i:i + 1800]
    ramo_local = corpo[corpo.find('if _pref_musica == "local":'):]
    assert ramo_local.find("_local()") < ramo_local.find("_nuvem()"), \
        "com a preferencia local, a IA local tem de compor primeiro"
    ramo_auto = corpo[corpo.find("else:"):]
    assert ramo_auto.find("_nuvem()") < ramo_auto.find("_local()")


def test_so_nuvem_nao_chama_o_motor_na_retentativa():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find('_preferencia_motor_musica() != "nuvem"')
    assert i > 0, "a retentativa sincrona ignora a preferencia 'nuvem'"
    assert "_tentar_musicgen(trilha" in s[i:i + 300]


def test_a_tela_de_configuracoes_deixa_escolher_o_motor():
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="musicEngine"' in html and 'value="local"' in html
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "btnSaveMusicEngine" in js
    assert "musicEngine" in js.split("loadSistema")[0] or "musicEngine" in js


# ---------- toda trilha gerada vai para a Biblioteca (3.07) ----------

def test_trilha_gerada_e_arquivada_com_a_etiqueta_do_clima(tmp_path):
    raiz = tmp_path / "Projetos"
    trilha = tmp_path / "trilha.mp3"
    trilha.write_bytes(b"\x00" * 40_000)
    nome = rf._arquivar_trilha(trilha, "sales", raiz, "mg")
    assert nome.startswith("venda--mg-"), nome
    guardada = tmp_path / "Biblioteca" / "Trilhas" / nome
    assert guardada.is_file() and guardada.stat().st_size == 40_000


def test_tipo_vazio_vira_padrao(tmp_path):
    trilha = tmp_path / "t.mp3"
    trilha.write_bytes(b"\x00" * 1000)
    assert rf._arquivar_trilha(trilha, "", tmp_path / "Projetos",
                               "ia").startswith("padrao--ia-")


def test_arquivar_nunca_derruba_o_render(tmp_path):
    """Origem inexistente: devolve string vazia, sem excecao — a trilha do
    video ja esta pronta e um erro de arquivo nao pode matar o job."""
    assert rf._arquivar_trilha(tmp_path / "nao-existe.mp3", "viral",
                               tmp_path / "Projetos", "mg") == ""


def test_reaproveitada_e_a_da_biblioteca_nao_voltam_para_o_acervo():
    """Sem esta condicao, refazer a Fase 2 encheria a Biblioteca de copias
    da MESMA musica a cada rodada."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("_fonte_atual = str(_RENDER_META.get")
    assert i > 0
    trecho = s[i:i + 900]
    assert "if not reuso" in trecho, "trilha reaproveitada nao pode arquivar"
    assert 'startswith("motor:")' in trecho, \
        "trilha vinda da biblioteca nao pode voltar para a biblioteca"
    assert "_arquivar_trilha(" in trecho


def test_a_origem_distingue_motor_de_nuvem():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find("_arquivar_trilha(\n")
    assert i > 0
    assert '"mg" if _fonte_atual.startswith("motor:") else "ia"' in \
        s[i:i + 300], "o nome do arquivo tem de dizer quem compos"
