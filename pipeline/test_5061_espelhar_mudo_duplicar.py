# -*- coding: utf-8 -*-
"""5.0.61: espelhar, emudecer e duplicar o take.

Três ajustes que o editor não tinha e que no CapCut ficam a um clique:

- **Espelhar**: inverte o take da esquerda para a direita. Casa a direção
  de dois takes filmados de lados opostos, e resolve o incômodo de quem se
  grava de frente e se vê invertido.
- **Mudo**: a imagem fica, o áudio some. É `-60 dB` — o `volume` do ffmpeg
  derruba o sinal a um milionésimo, abaixo de qualquer ruído de fundo.
- **Duplicar**: o take inteiro outra vez logo em seguida, com os mesmos
  ajustes. A cópia nasce com `srcIdx: null`, como as metades de um corte:
  ela não é o take original e não herda a geometria de J-cut dele.
"""
from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app.quick_corrections import _HERDAVEIS, _norm_range  # noqa: E402
from app.timeline_map import espelhar_do_range  # noqa: E402

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def test_o_campo_viaja_e_conta_como_mudanca():
    assert espelhar_do_range({}) is False
    assert espelhar_do_range({"flip": True}) is True
    assert espelhar_do_range("nao e dict") is False
    assert "flip" in _HERDAVEIS
    a = {"source": "s", "start": 0, "end": 1}
    assert _norm_range(a) != _norm_range({**a, "flip": True}), (
        "sem isto o Aplicar acharia que e o mesmo corte")
    assert RF.count('item["flip"] = True') == 2, "os DOIS leitores de EDL"


def test_o_espelho_vale_tambem_onde_o_crop_nao_entra():
    """`hflip` não muda tamanho nem relógio, então não fica preso ao
    `scale` como o reenquadramento — vale no longform também."""
    src = inspect.getsource(_extract())
    assert "flip" in inspect.signature(_extract()).parameters
    i_flip = src.index('if flip and streams != "a":')
    i_crop = src.index('if reframe and streams != "a" and scale:')
    assert i_crop < i_flip, "espelhar depois de recortar"
    assert 'and scale' not in src[i_flip:i_flip + 60]
    assert src.index('vf_parts.append("hflip")') < src.index('vf_parts.append(scale)')
    assert RENDER.count('flip=bool(r.get("flip"))') == 2, "os dois caminhos"


def test_a_chave_do_clipe_guardado_ve_o_espelho():
    i = RENDER.index("vkey = _seg_key(")
    assert 'bool(r.get("flip"))' in RENDER[i:i + 1500], (
        "sem isto o clipe guardado voltaria sem o espelho")


def test_mudo_e_silencio_de_verdade_no_ffmpeg():
    """-60 dB tem de sumir: um take 'mudo' que ainda se ouve é pior que
    nenhum botão."""
    if not _tem():
        pytest.skip("ffmpeg fora do PATH")
    niveis = {}
    for nome, af in (("normal", "volume=+0.00dB"), ("mudo", "volume=-60.00dB")):
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi",
             "-i", "sine=f=440:d=1", "-af", f"{af},volumedetect",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
        # volumedetect escreve no log; com -v error ele some, entao medimos
        # pelo astats, que sai no proprio filtro
        r2 = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "info", "-f", "lavfi",
             "-i", "sine=f=440:d=1", "-af", f"{af},astats=metadata=1",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
        linha = [x for x in r2.stderr.splitlines() if "RMS level dB" in x]
        assert linha, r2.stderr[-500:]
        niveis[nome] = float(linha[-1].split(":")[-1].strip())
        assert r.returncode == 0
    assert niveis["normal"] - niveis["mudo"] > 55, niveis
    assert niveis["mudo"] < -55, niveis


def test_o_editor_tem_os_tres_e_manda_o_espelho():
    assert "[-60, 'Mudo']" in PJS, "Mudo entra na fileira de volume"
    assert "esp.textContent = 'Espelhar';" in PJS
    assert "dup.textContent = 'Duplicar';" in PJS
    assert "if (r.flip) out.flip = true;" in PJS, "camposDoTake precisa mandar"
    assert "|| !!r.flip !== !!r.orig.flip);" in PJS, "senao o Aplicar nao acende"


def test_a_copia_nao_herda_a_geometria_do_original():
    bloco = PJS.split("dup.addEventListener", 1)[1][:700]
    assert "srcIdx: null" in bloco, (
        "com o srcIdx do original a copia puxaria o lead/tail do J-cut dele")
    assert "added: true" in bloco
    assert "...camposDoTake(r)" in bloco, "a copia leva os ajustes do take"
    assert "S.draft.splice(i + 1, 0," in bloco, "entra logo DEPOIS do original"


def test_espelhar_junto_com_reenquadrar(tmp_path):
    """Os dois no mesmo take: a saída é o espelho exato da região pedida, e
    no mesmo tamanho de sempre."""
    if not _tem():
        pytest.skip("ffmpeg fora do PATH")
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    from app.timeline_map import reenquadrar_vf

    fonte = tmp_path / "f.png"
    _roda(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "testsrc2=size=720x1280:rate=1:duration=1",
           "-frames:v", "1", str(fonte)])
    crop = reenquadrar_vf(2, -1, -1)          # quadrante de cima, a esquerda
    sem, com = tmp_path / "sem.png", tmp_path / "com.png"
    _roda(["ffmpeg", "-y", "-v", "error", "-i", str(fonte),
           "-vf", f"{crop},scale=-2:1280", str(sem)])
    _roda(["ffmpeg", "-y", "-v", "error", "-i", str(fonte),
           "-vf", f"{crop},hflip,scale=-2:1280", str(com)])
    a = np.asarray(Image.open(sem).convert("RGB"), dtype=float)
    b = np.asarray(Image.open(com).convert("RGB"), dtype=float)
    assert a.shape == b.shape == (1280, 720, 3), (a.shape, b.shape)
    assert float(np.abs(b - a[:, ::-1]).mean()) < 2.0, "nao e o espelho"
    assert float(np.abs(b - a).mean()) > 10.0, "espelhou nada"


def _roda(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-600:]
    return r


def _extract():
    import render
    return render.extract_segment


def _tem() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=25)
        return True
    except Exception:  # noqa: BLE001
        return False
