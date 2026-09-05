# -*- coding: utf-8 -*-
"""5.0.65: a cor cara do corte vira uma tabela.

MEDIÇÃO (take de 21,13 s de um projeto real, 1080p60 HEVC, melhor de 2):

    decode sozinho ............................. 6,18 s
    + fps/scale + encode NVENC ................. 7,07 s
    + eq ....................................... 7,22 s   (+0,15)
    + curves ................................... 9,40 s   (+2,33)
    + colorbalance ............................ 19,15 s  (+12,08)
    a cadeia inteira do look .................. 21,17 s

O `colorbalance` do ffmpeg não tem caminho vetorizado: sozinho custa mais
que o decode e o encode somados. É ~56% da extração, a extração é 85% do
corte e o corte é 29% do job.

Com a tabela no lugar do trecho RGB: **19,19 → 15,32 s (1,25x)**, e a cor
é a mesma — |d| médio 0,18 a 0,68 de 255 e PIOR PIXEL 2, medido nos
quadros em yuv420p cru, que é o que o encoder recebe.

Esta é a segunda tentativa. A primeira foi descartada por um "viés de
−1,5 a −2,5" que não existia: a comparação passava os dois lados por uma
conversão EXTRA para rgb24, e era ela que escurecia. `test_a_comparacao_
justa` fixa a lição — a mesma cadeia com a ida e volta explícita é
byte-idêntica à implícita.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

import render  # noqa: E402
from grade import PRESETS  # noqa: E402

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
WARM = PRESETS["warm_cinematic"]
RGB_DO_WARM = ("colorbalance=rs=0.02:gs=0.0:bs=-0.03:rm=0.04:gm=0.01:bm=-0.02:"
               "rh=0.08:gh=0.02:bh=-0.05,"
               "curves=master='0/0 0.25/0.22 0.75/0.78 1/1'")


def test_a_quebra_respeita_as_aspas():
    """`curves=master='0/0 0.25/0.22 ...'` não pode virar dois filtros."""
    partes = render._quebrar_filtros(WARM)
    assert len(partes) == 3, partes
    assert partes[2].startswith("curves=") and partes[2].endswith("'")
    assert render._quebrar_filtros("") == []


def test_o_trecho_e_o_RUN_em_volta_do_colorbalance():
    antes, trecho, depois = render._trecho_rgb(WARM)
    assert antes == "eq=contrast=1.12:brightness=-0.02:saturation=0.88"
    assert trecho == RGB_DO_WARM
    assert depois == ""
    # `marca` e `eq, colorbalance, hue`: com regra de SUFIXO o `hue` no fim
    # deixaria o filtro caro de fora — e `marca` e o look mais usado.
    a, t, d = render._trecho_rgb(PRESETS["marca"])
    assert t.startswith("colorbalance=") and "," not in t
    assert a.startswith("eq=") and d.startswith("hue=")


def test_sem_colorbalance_nao_vale_a_troca():
    for nome in ("subtle", "neutral_punch"):
        assert render._trecho_rgb(PRESETS[nome])[1] == "", nome
        assert render.acelerar_grade(PRESETS[nome]) == PRESETS[nome], nome


def test_o_caminho_leva_DOIS_escapes():
    v = render._escapar_para_filtro(Path("E:/Temp/x/y.cube"))
    assert v == "E\\\\:/Temp/x/y.cube", v


def test_da_para_desligar():
    os.environ["ATIVAVID_GRADE_LUT"] = "0"
    try:
        assert render.acelerar_grade(WARM) == WARM
    finally:
        os.environ.pop("ATIVAVID_GRADE_LUT", None)
    assert render.acelerar_grade("") == ""


def test_o_extract_usa_a_versao_acelerada():
    assert "vf_parts.append(acelerar_grade(grade_filter))" in RENDER


# --------------------------------------------------------- provas no ffmpeg
def test_a_comparacao_justa(tmp_path):
    """A lição que custou a primeira tentativa: comparar no formato de
    SAÍDA. A mesma cadeia, com a ida e volta para RGB escrita à mão, é
    byte-idêntica à que o ffmpeg monta sozinho — mas parece escurecida se
    a comparação passar por um rgb24 a mais."""
    if not _tem_ffmpeg():
        pytest.skip("ffmpeg fora do PATH")
    fonte = _fonte(tmp_path)
    a = _yuv(fonte, f"format=yuv420p,{RGB_DO_WARM}")
    b = _yuv(fonte, f"format=yuv420p,format=rgb24,{RGB_DO_WARM},format=yuv420p")
    assert a == b, "a ida e volta explicita nao pode mudar um byte"


def test_a_tabela_da_a_MESMA_cor_em_todo_preset(tmp_path):
    if not _tem_ffmpeg():
        pytest.skip("ffmpeg fora do PATH")
    np = pytest.importorskip("numpy")
    fonte = _fonte(tmp_path)
    vistos = 0
    for nome, cadeia in sorted(PRESETS.items()):
        if "colorbalance" not in cadeia:
            continue
        vistos += 1
        nova = render.acelerar_grade(cadeia)
        assert "lut3d=" in nova, nome
        a = np.frombuffer(_yuv(fonte, f"format=yuv420p,{cadeia}"),
                          dtype=np.uint8).astype(float)
        b = np.frombuffer(_yuv(fonte, f"format=yuv420p,{nova}"),
                          dtype=np.uint8).astype(float)
        assert a.shape == b.shape, nome
        d = abs(b - a)
        assert d.max() <= 4, f"{nome}: pior pixel {d.max():.0f} de 255"
        assert d.mean() < 1.0, f"{nome}: |d| medio {d.mean():.3f} de 255"
    assert vistos >= 5, f"so {vistos} presets com colorbalance"


def test_a_tabela_muda_alguma_coisa(tmp_path):
    """Uma tabela que nao pinta nada passaria em todos os testes acima."""
    if not _tem_ffmpeg():
        pytest.skip("ffmpeg fora do PATH")
    np = pytest.importorskip("numpy")
    fonte = _fonte(tmp_path)
    crua = np.frombuffer(_yuv(fonte, "format=yuv420p"), dtype=np.uint8).astype(float)
    com = np.frombuffer(_yuv(fonte, f"format=yuv420p,{render.acelerar_grade(WARM)}"),
                        dtype=np.uint8).astype(float)
    assert abs(com - crua).mean() > 3, "a tabela nao pintou nada"


def test_a_tabela_e_guardada_e_reaproveitada():
    cube = render._tabela_de_cor(RGB_DO_WARM)
    if cube is None:
        pytest.skip("tabela indisponivel nesta maquina")
    assert cube.is_file()
    n = render._LUT_LADO
    linhas = cube.read_text(encoding="utf-8").splitlines()
    assert linhas[1] == f"LUT_3D_SIZE {n}"
    assert len(linhas) == 2 + n ** 3, len(linhas)
    antes = cube.stat().st_mtime_ns
    assert render._tabela_de_cor(RGB_DO_WARM) == cube
    assert cube.stat().st_mtime_ns == antes, "gerou de novo em vez de reusar"
    # a chave carrega o TAMANHO: trocar `_LUT_NIVEL` nao pode reusar a velha
    outro = render._tabela_de_cor(RGB_DO_WARM.replace("rs=0.02", "rs=0.03"))
    assert outro != cube


def _fonte(tmp_path) -> Path:
    f = tmp_path / "f.png"
    if not f.exists():
        _roda(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
               "-i", "testsrc2=size=640x360:rate=1:duration=1",
               "-frames:v", "1", str(f)])
    return f


def _yuv(fonte: Path, vf: str) -> bytes:
    return _roda(["ffmpeg", "-v", "error", "-i", str(fonte), "-vf", vf,
                  "-frames:v", "1", "-pix_fmt", "yuv420p",
                  "-f", "rawvideo", "-"]).stdout


def _tem_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=25)
        return True
    except Exception:  # noqa: BLE001
        return False


def _roda(cmd):
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    assert r.returncode == 0, r.stderr[-600:]
    return r
