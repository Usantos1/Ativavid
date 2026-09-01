# -*- coding: utf-8 -*-
"""A aba Visual toca uma copia leve, como a Edicao ja fazia.

Relato dele em 31/08, com a 4.34 instalada: "com lag gigante no video e
dando umas travadas ainda". Antes disso: "se eu abrir a pasta e abrir em
outro player, mesmo com 10 videos na fila, nao trava".

Medido no video dele que estava na tela (1:30, 1080x1920, 13,9 Mbps,
159 MB):

  * decodificar o arquivo entregue em UMA thread leva 50,1 s para 90,2 s
    de video — 1,8x o tempo real, ou seja, quase sem folga;
  * a copia de 720 de altura leva 2,6 s — 35x o tempo real, e o arquivo
    cai de 159 MB para 10,6 MB;
  * o servidor entrega faixas de 256 KB em 2,3 ms: a entrega nunca foi o
    problema.

O player externo dele manda o decodificador do hardware; a janela do app
nem sempre. O quadro do player tem ~500 px de largura — os 1080 nunca
apareceram na tela.

A armadilha que esta mudanca cria (e que este arquivo guarda): a copia
nasce DEPOIS do entregue e vira o `.mp4` mais novo da pasta. Todo lugar
que escolhe "o mp4 mais novo e o video entregue" tem de pula-la, senao o
app passa a tratar a copia de 720 como o produto — no card, no "abrir
pasta", no pacote de publicacao.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")


@pytest.fixture()
def video(tmp_path):
    """Como o final REAL: 3 fluxos — video + audio + CAPA (attached_pic
    1080x1920, mesma resolucao do video). A fixture de 2 fluxos passava por
    padrao: o mapeamento default do ffmpeg diante do attached_pic nunca era
    exercitado, e e exatamente ele que decide se a copia leve sai com o
    fluxo certo (ver overlay_compose, que anexa a capa no final)."""
    from app.ffmpeg_tools import ffmpeg_bin

    capa = tmp_path / "capa.jpg"
    subprocess.run(
        [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=red:size=1080x1920:duration=0.1",
         "-frames:v", "1", str(capa)],
        check=True, capture_output=True, timeout=60)
    f = tmp_path / "entregue.mp4"
    subprocess.run(
        [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-i", str(capa),
         "-map", "0:v", "-map", "1:a", "-map", "2",
         "-c:v:0", "libx264", "-crf", "30", "-preset", "ultrafast",
         "-c:a", "aac", "-c:v:1", "mjpeg",
         "-disposition:v:1", "attached_pic", "-shortest", str(f)],
        check=True, capture_output=True, timeout=120)
    return f


def test_a_fixture_tem_os_3_fluxos_do_final_real(video):
    """Se a capa sumir da fixture, os testes abaixo voltam a passar por
    padrao — este aqui garante que o cenario e o do arquivo de verdade."""
    from app.ffmpeg_tools import ffprobe_bin

    r = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries",
                        "stream=codec_type", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, timeout=30)
    tipos = [ln.split(",")[0] for ln in r.stdout.split() if ln]
    assert tipos.count("video") == 2 and "audio" in tipos, tipos


def test_a_copia_do_final_leva_o_som(video, tmp_path):
    """A copia da Fase 1 e muda de proposito (a timeline tem a onda). A do
    final NAO pode ser: ele abre a Visual para conferir trilha e efeito."""
    from make_proxy import make_cut_proxy

    dest = tmp_path / "final_proxy.mp4"
    assert make_cut_proxy(video, dest, height=360, com_audio=True)
    from app.ffmpeg_tools import ffprobe_bin

    r = subprocess.run([ffprobe_bin(), "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                        str(dest)], capture_output=True, text=True, timeout=30)
    assert "audio" in r.stdout, "a copia do final saiu muda"


def test_a_copia_do_corte_continua_muda(video, tmp_path):
    from make_proxy import make_cut_proxy
    from app.ffmpeg_tools import ffprobe_bin

    dest = tmp_path / "cut_proxy.mp4"
    assert make_cut_proxy(video, dest, height=360)
    r = subprocess.run([ffprobe_bin(), "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                        str(dest)], capture_output=True, text=True, timeout=30)
    assert "audio" not in r.stdout


@pytest.mark.parametrize("arquivo,marca", [
    ("helpers/preview_server.py", 'skip = {"cut.mp4"'),
    ("app/local_server.py", 'skip = {"cut.mp4"'),
    ("app/local_server.py", "_IMPORT_SKIP_FILES = {"),
    ("app/delivery_pack.py", "_SKIP_MP4 = {"),
])
def test_a_copia_nao_pode_virar_o_video_entregue(arquivo, marca):
    s = (REPO / arquivo).read_text(encoding="utf-8")
    i = s.index(marca)
    bloco = s[i:s.index("}", i)]
    assert "final_proxy.mp4" in bloco, f"{arquivo}: {marca} nao pula a copia"


def test_o_servidor_recusa_a_copia_atrasada():
    """Copia mais velha que o entregue nao e copia: mostrar isso seria pior
    que lento — ele veria um video que ja nao existe."""
    i = PS.index("def _proxy_final_util(")
    bloco = PS[i:PS.index("\n    def ", i + 10)]
    assert "st_mtime < final.stat().st_mtime" in bloco
    assert "_refazer_proxy_final(final)" in bloco
    # e as duas portas (GET e HEAD) tem de concordar
    assert PS.count('name == "final_proxy.mp4"') == 2


def test_a_copia_nasce_sozinha_na_primeira_abertura():
    """Os 186 projetos que ja existem nao tem a copia."""
    i = PS.index("def _refazer_proxy_final(")
    bloco = PS[i:PS.index("\n    def ", i + 10)]
    assert "_PROXY_REFAZENDO" in bloco, "sem registro, cada pergunta abre um ffmpeg"
    assert "proxy_do_final" in bloco


def test_a_tela_toca_a_copia_na_aba_visual():
    i = JS.index("function updateVideoSrc()")
    bloco = JS[i:JS.index("\nasync function", i)]
    assert "if (wantFinal && S.hasFinalProxy && !S.finalProxyFailed) rel = 'final_proxy.mp4';" in bloco


def test_a_tela_cai_no_arquivo_cheio_se_a_copia_falhar():
    i = JS.index("function wireProxyFallback()")
    bloco = JS[i:i + 1200]
    assert "rel.includes('final_proxy')" in bloco
    assert "S.finalProxyFailed = true" in bloco


def test_a_tela_volta_a_perguntar_ate_a_copia_ficar_pronta():
    i = JS.index("function esperarCopiaDoFinal(")
    bloco = JS[i:JS.index("\nasync function detectProxy", i)]
    assert "if (esperaDaCopia) return" in bloco, "sem trava vira enxurrada de timers"
    assert "--tentativas > 0" in bloco, "a espera tem de acabar"
    assert "S.tab !== 2" in bloco, "parar quando ele sai da aba"


def test_a_copia_nao_toma_a_maquina_enquanto_ele_assiste():
    """A copia roda EM SEGUNDO PLANO, enquanto ele ve o video — com as
    threads soltas o ffmpeg tomava a maquina e a copia que existe para
    destravar o player o travava por 10 a 30 s."""
    s = (REPO / "helpers" / "make_proxy.py").read_text(encoding="utf-8")
    i = s.index("def _cmd(e: str)")
    assert '"-threads", "2"' in s[i:i + 700]
    assert "_ABAIXO_DO_NORMAL = 0x00004000" in s
    assert "hide = _fundo(hide_console_kwargs())" in s
