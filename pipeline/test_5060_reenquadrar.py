# -*- coding: utf-8 -*-
"""5.0.60: reenquadrar o take na mão — o "reframe" do CapCut.

"Quero mais recursos profissionais na tela de edição, pra um cara que é
mais avançado" (05/09). Aproximar um take e escolher que pedaço do quadro
fica na tela é o ajuste que mais se usa depois da velocidade.

O corte recorta a FONTE e só então escala: 2x numa fonte 4K ainda entrega
1080p de detalhe real. Recortar depois do `scale` seria ampliar pixel já
jogado fora.

Junto vai o conserto que a leitura encontrou: a chave do clipe guardado
(caminho J-cut) olhava só o `grade` GLOBAL do EDL. Cor por take (5.0.54),
velocidade (5.0.56) e congelar (5.0.58) não mudavam a chave — o corte era
refeito e cada trecho voltava do cache SEM o ajuste, calado.
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app.quick_corrections import _HERDAVEIS, _norm_range  # noqa: E402
from app.timeline_map import (  # noqa: E402
    REENQ_MAX, reenquadrar_do_range, reenquadrar_vf,
)

RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def test_o_que_a_tela_manda_e_normalizado():
    assert reenquadrar_do_range({}) == (1.0, 0.0, 0.0)
    assert reenquadrar_do_range({"reframe": "2x"}) == (1.0, 0.0, 0.0)
    assert reenquadrar_do_range({"reframe": {"z": 2, "x": -1, "y": 0.5}}) == (2.0, -1.0, 0.5)
    # fora da faixa entra na faixa, e nao derruba o corte
    assert reenquadrar_do_range({"reframe": {"z": 99, "x": 7, "y": -7}}) == (REENQ_MAX, 1.0, -1.0)
    assert reenquadrar_do_range({"reframe": {"z": "abc"}}) == (1.0, 0.0, 0.0)
    assert reenquadrar_do_range({"reframe": {"z": float("nan")}}) == (1.0, 0.0, 0.0)
    # z de 1 zera a posicao: sem aproximacao nao ha para onde mover
    assert reenquadrar_do_range({"reframe": {"z": 1, "x": 0.8}}) == (1.0, 0.0, 0.0)


def test_o_filtro_so_existe_quando_ha_aproximacao():
    assert reenquadrar_vf(1.0) == ""
    assert reenquadrar_vf(1.0005, 0.5, 0.5) == ""
    assert reenquadrar_vf(2.0).startswith("crop=")


def test_o_recorte_sai_par_nas_duas_medidas():
    """Crop ímpar faz o ffmpeg devolver uma altura a menos, e uma dimensão
    inesperada derruba o motor rápido do vídeo inteiro (460x865 -> 460x864)."""
    f = reenquadrar_vf(1.7, 0.3, -0.2)
    assert f.count("trunc(") == 4 and f.count("/2)*2") == 4


def test_o_reenquadramento_entra_ANTES_do_scale():
    src = inspect.getsource(_extract())
    assert "reframe" in inspect.signature(_extract()).parameters
    assert src.index("vf_parts.append(reframe)") < src.index("vf_parts.append(scale)"), (
        "recortar depois de escalar seria ampliar pixel ja descartado")
    assert 'if reframe and streams != "a" and scale:' in src, (
        "sem scale (longform) o crop mudaria a resolucao de saida")
    assert RENDER.count("reframe=reframe_vf") == 2, "o caminho normal e o do J-cut"


def test_a_chave_do_clipe_guardado_ve_o_ajuste_do_take():
    """O defeito que este arquivo conserta: cor, velocidade, congelar e
    enquadramento por take não entravam na chave, então o render seguinte
    reusava o clipe antigo e o ajuste sumia."""
    i = RENDER.index('vkey = _seg_key(')
    chave = RENDER[i:i + 1400]
    for campo in ('str(r.get("grade") or "")', "_velocidade_key(r)",
                  "_congelar_key(r)", "_reenq_key(r)"):
        assert campo in chave, campo


def test_o_campo_viaja_no_trecho():
    assert "reframe" in _HERDAVEIS
    a = {"source": "s", "start": 0, "end": 1}
    b = {"source": "s", "start": 0, "end": 1, "reframe": {"z": 2}}
    assert _norm_range(a) != _norm_range(b), (
        "sem isto o apply acharia que e o mesmo corte e nao refaria nada")
    assert _norm_range(b) == _norm_range({**b, "reframe": {"z": 2, "x": 0, "y": 0}})


def test_o_pipeline_grava_o_campo_no_EDL():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert rf.count('item["reframe"] = {"z": _rq[0], "x": _rq[1], "y": _rq[2]}') == 2, (
        "os DOIS leitores de EDL")


def test_o_editor_manda_e_compara():
    assert "const REENQ_DO_TAKE" in PJS
    assert "out.reframe = { z:" in PJS, "camposDoTake precisa mandar"
    assert "JSON.stringify(reenqDoTake(r)) !== JSON.stringify(reenqDoTake(r.orig))" in PJS, (
        "sem isto o botao Aplicar nao acende")
    assert PJS.count("reframe: r.reframe || null") >= 4, "hidratacao + orig"


# --------------------------------------------------------- prova no ffmpeg
def test_o_recorte_mostra_o_pedaco_certo_da_fonte(tmp_path):
    """Prova em pixel: cada enquadramento entrega EXATAMENTE a região pedida
    da fonte, e no mesmo tamanho de saída de um take sem reenquadramento."""
    if not _tem(["ffmpeg", "-version"]):
        pytest.skip("ffmpeg fora do PATH")
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")

    fonte = tmp_path / "fonte.png"
    _roda(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", "testsrc2=size=720x1280:rate=1:duration=1",
           "-frames:v", "1", str(fonte)])
    f = np.asarray(Image.open(fonte).convert("RGB"), dtype=float)
    H, W = f.shape[:2]
    casos = {
        "topo_esq": ((2, -1, -1), f[0:H // 2, 0:W // 2]),
        "centro": ((2, 0, 0), f[H // 4:3 * H // 4, W // 4:3 * W // 4]),
        "base_dir": ((2, 1, 1), f[H // 2:H, W // 2:W]),
    }
    for nome, ((z, x, y), esperado) in casos.items():
        alvo = tmp_path / f"{nome}.png"
        _roda(["ffmpeg", "-y", "-v", "error", "-i", str(fonte),
               "-vf", f"{reenquadrar_vf(z, x, y)},scale=-2:1280", str(alvo)])
        saida = np.asarray(Image.open(alvo).convert("RGB"), dtype=float)
        assert saida.shape[:2] == (1280, 720), f"{nome}: {saida.shape}"
        quer = np.asarray(
            Image.fromarray(esperado.astype("uint8")).resize((720, 1280)),
            dtype=float)
        erro = float(np.abs(saida - quer).mean())
        assert erro < 2.0, f"{nome}: erro medio {erro:.2f} de 255"


def _extract():
    import render  # helpers/render.py
    return render.extract_segment


def _tem(cmd) -> bool:
    try:
        subprocess.run(cmd, capture_output=True, timeout=25)
        return True
    except Exception:  # noqa: BLE001
        return False


def _roda(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-600:]
    return r


def test_o_json_do_edl_aceita_o_campo(tmp_path):
    """Ida e volta pelo arquivo: o que a tela grava é o que o corte lê."""
    from app.quick_corrections import write_edl_ranges

    edit = tmp_path / "edit"
    edit.mkdir()
    write_edl_ranges(edit, [
        {"source": "A", "start": 0, "end": 2, "reframe": {"z": 2, "x": -0.5, "y": 0}},
        {"source": "A", "start": 3, "end": 4},
    ])
    alvo = next(p for p in edit.rglob("*.json") if "edl" in p.name)
    rs = json.loads(alvo.read_text(encoding="utf-8"))["ranges"]
    assert reenquadrar_do_range(rs[0]) == (2.0, -0.5, 0.0)
    assert reenquadrar_do_range(rs[1])[0] == 1.0
