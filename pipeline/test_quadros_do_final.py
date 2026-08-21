# -*- coding: utf-8 -*-
"""O final tem de sair com os quadros que a timeline pede.

`FRAMES 2424!=2426` foi a segunda maior causa de queda para o Remotion
completo (a maior era o pico de áudio). O mecanismo, medido no `cut.mp4` do
projeto que falhou em 20/08/2026:

  - o `cut.mp4` tem um BURACO no próprio relógio: 2424 quadros ocupando 2426
    posições. Nos 8 últimos cuts do usuário, 2 têm isso — sempre um salto de
    3 quadros no fim
  - a timeline conta POSIÇÕES (ela deriva de `durationSec`), então pede 2426
  - a composição percebe a diferença e pede `tpad` de 2 quadros — certo
  - mas o `tpad` acrescenta DEPOIS do último quadro, que já está na posição
    2425: os clones caem em 2426 e 2427, e o `-t duration_sec` corta ali

Resultado: o vídeo saía com os 2 quadros que o `tpad` acabou de criar
faltando, e o job inteiro voltava para o Remotion.

Medido, no arquivo real:

| variante | quadros | duração | buracos |
|---|---|---|---|
| `tpad` só, como era | 2424 | 80,866667 | 2 |
| `tpad` sem `-t` | 2426 | 80,933333 | 0 |
| PTS renumerado | 2426 | 80,866667 | 0 |
| **`tpad` + `fps=`** | **2426** | **80,866667** | **0** |

Entre as duas últimas, `fps=` PREENCHE o buraco duplicando quadro; renumerar
o PTS o FECHARIA, adiantando 67 ms tudo que vem depois dele.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}
FPS = 30.0


def _cut_com_buraco(tmp: Path, posicoes: int, buraco_em: int) -> Path:
    """Um cut.mp4 com a MESMA forma do que quebrou: N-2 quadros ocupando N
    posições no relógio.

    `select` deixa o PTS original de cada quadro que passa, então descartar
    dois no meio abre um BURACO — é isso que o concat do corte produz, e o
    que uma fixture "N quadros seguidos" não reproduz. Sem o buraco o teste
    passava dos dois lados, sem medir nada."""
    out = tmp / "cut.mp4"
    dur = (posicoes + 30) / FPS
    r = subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=s=120x214:r={FPS:g}:d={dur:.3f}",
        "-f", "lavfi", "-i", f"sine=r=48000:d={dur:.6f}",
        "-map", "0:v", "-map", "1:a",
        # `trim` ANTES do `select`: depois dele o `end_frame` contaria os
        # sobreviventes e o arquivo sairia com as posições todas ocupadas
        "-vf", (f"trim=end_frame={posicoes},"
                f"select='not(between(n,{buraco_em},{buraco_em + 1}))'"),
        "-af", f"atrim=0:{posicoes / FPS:.6f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k",
        "-fps_mode", "passthrough", str(out)], capture_output=True, text=True, **NOWIN)
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"ffmpeg não montou a fixture: {(r.stderr or '')[-200:]}")
    n, _ = _quadros_e_dur(out)
    if n != posicoes - 2:
        pytest.skip(f"a fixture não ficou com o buraco: {n} quadros")
    return out


def _compoe(cut: Path, dest: Path, frames: int, cut_v: str) -> None:
    dur = frames / FPS
    fc = (f"{cut_v};[1:v]setpts=PTS-STARTPTS[ov];"
          "[cutv][ov]overlay=eof_action=pass:format=auto,format=yuv420p[vid];"
          "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
          f"atrim=0:{dur:.6f},asetpts=PTS-STARTPTS[pre]")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(cut),
        "-f", "lavfi", "-i",
        f"color=c=black@0.0:s=120x214:r={FPS:g}:d={dur + 1:.3f},format=rgba",
        "-filter_complex", fc, "-map", "[vid]", "-map", "[pre]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40",
        "-c:a", "aac", "-b:a", "64k", "-frames:v", str(frames),
        "-t", f"{dur:.6f}", str(dest)], capture_output=True, **NOWIN)


def _quadros_e_dur(p: Path) -> tuple[int, float]:
    # por CHAVE, não por posição: o csv sai na ordem dos campos do stream,
    # que não é a ordem em que foram pedidos
    r = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=nb_frames,duration", "-of", "default=nw=1", str(p)],
        capture_output=True, text=True, **NOWIN)
    d = dict(l.split("=", 1) for l in (r.stdout or "").strip().splitlines() if "=" in l)
    return int(d["nb_frames"]), float(d["duration"])


def test_o_buraco_do_cut_e_preenchido_e_a_contagem_bate(tmp_path):
    """O caso real: 300 quadros ocupando 302 posições, timeline pedindo 302."""
    cut = _cut_com_buraco(tmp_path, 302, 200)
    novo = tmp_path / "novo.mp4"
    _compoe(cut, novo, 302,
            f"[0:v]tpad=stop_mode=clone:stop=2,fps={FPS:g},"
            "setpts=PTS-STARTPTS[cutv]")
    n, dur = _quadros_e_dur(novo)
    assert n == 302, f"{n} quadros, esperado 302"
    assert abs(dur - 302 / FPS) < 0.005, dur


def test_o_jeito_antigo_realmente_perdia_os_quadros(tmp_path):
    """Sem isto o teste acima poderia estar passando por acaso.

    O `tpad` sozinho acrescenta DEPOIS do último quadro, que já está na
    posição 301 — os clones caem em 302 e 303, e o `-t` corta ali."""
    cut = _cut_com_buraco(tmp_path, 302, 200)
    velho = tmp_path / "velho.mp4"
    _compoe(cut, velho, 302,
            "[0:v]tpad=stop_mode=clone:stop=2,setpts=PTS-STARTPTS[cutv]")
    n, _ = _quadros_e_dur(velho)
    assert n == 300, f"o defeito não reproduziu: {n} quadros"


def test_preencher_nao_adianta_o_que_vinha_depois_do_buraco(tmp_path):
    """`fps` DUPLICA quadro para tapar o buraco; renumerar o PTS o FECHARIA,
    e tudo depois dele adiantaria 67 ms — fora de sincronia com o áudio.

    Nos cuts do usuário o buraco cai sempre no último quadro, mas não há
    garantia disso, então a diferença importa."""
    cut = _cut_com_buraco(tmp_path, 302, 100)   # buraco no MEIO

    def fim(cadeia: str, nome: str) -> tuple[int, float]:
        p = tmp_path / f"{nome}.mp4"
        _compoe(cut, p, 302, cadeia)
        n, _ = _quadros_e_dur(p)
        r = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, **NOWIN)
        ts = sorted(float(x) for x in (r.stdout or "").replace(",", " ").split() if x)
        return n, ts[-1]

    n_fps, fim_fps = fim(f"[0:v]fps={FPS:g},setpts=PTS-STARTPTS[cutv]", "fps")
    n_ren, fim_ren = fim(f"[0:v]setpts=N/({FPS:g}*TB)[cutv]", "renumerado")

    # `fps` preenche: o último quadro continua na posição 301
    assert n_fps == 302, n_fps
    assert abs(fim_fps - 301 / FPS) < 0.002, fim_fps
    # renumerar fecha o buraco: o mesmo quadro sobe para a 299 — 67 ms mais
    # cedo que o áudio, que não foi renumerado junto
    assert abs(fim_ren - 299 / FPS) < 0.002, fim_ren
    assert fim_fps - fim_ren > 0.05, (fim_fps, fim_ren)


def test_os_dois_motores_normalizam_o_relogio():
    """A correção mora em dois arquivos — os dois caminhos de composição."""
    for arq, quem in (("app/render_proprio.py", "uma passada"),
                      ("app/overlay_compose.py", "compose em dois passos")):
        s = (REPO / arq).read_text(encoding="utf-8")
        i = s.index("tpad=stop_mode=clone")
        bloco = s[max(0, i - 400):i + 300]
        assert "fps={fps" in bloco or "fps={fps_f" in bloco, f"{quem} ({arq}) sem o fps="
        assert "PTS-STARTPTS[cutv]" not in bloco, quem
