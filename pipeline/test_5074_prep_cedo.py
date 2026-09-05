# -*- coding: utf-8 -*-
"""5.0.74: a fonte HDR é preparada durante o plano, não dentro do corte.

`prepared_source` (escala + tonemap + grade, uma vez por fonte) é o passo
caro do corte numa fonte HDR — e 63% das fontes dele são HDR. Ele rodava
depois do plano da IA, com a CPU parada durante o plano (5,9 s de mediana,
10,8 s nos últimos 40 jobs). Agora `helpers/prep_source.py` roda ao fim da
análise de cada take, em paralelo com o plano; o corte acha o arquivo pela
MESMA chave (PREPARED_SOURCE HIT) e `PREP_WAIT` mede só o que sobrou.

O que este arquivo tranca: (1) o helper usa exatamente a regra de escala e
de grade do corte — uma chave diferente seria um MISS silencioso e o prep
feito duas vezes; (2) SDR e grade `auto` saem na hora; (3) o pipeline
dispara por fonte, fora do longform e do job-mãe de clipes, e espera antes
do corte; (4) o helper nunca levanta.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers", REPO / "pipeline"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

RUN_FAST = REPO / "pipeline" / "run_fast.py"
RENDER = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")


def _rodar(monkeypatch, capsys, argv, *, hdr=True, portrait=True, grade="marca",
           pronto=True, explode=False):
    import prep_source
    import render

    chamadas = []

    def fake_prepared(video, scale, grade_filter, *, permitir_nvdec=True, **k):
        chamadas.append((video, scale, grade_filter, permitir_nvdec))
        if explode:
            raise RuntimeError("ffmpeg caiu")
        return Path("x.prep.mp4") if pronto else None

    monkeypatch.setattr(render, "prepared_source", fake_prepared)
    monkeypatch.setattr(render, "is_hdr_source", lambda v: hdr)
    monkeypatch.setattr(render, "is_portrait_source", lambda v: portrait)
    monkeypatch.setattr(sys, "argv", ["prep_source.py", *argv])
    prep_source.main()
    return chamadas, capsys.readouterr().out


def test_o_helper_prepara_com_a_regra_exata_do_corte(monkeypatch, capsys, tmp_path):
    v = tmp_path / "IMG_3935.MOV"
    v.write_bytes(b"x")
    chamadas, saida = _rodar(monkeypatch, capsys, [str(v), "--grade-field", "marca"])
    assert len(chamadas) == 1
    video, scale, grade, nvdec = chamadas[0]
    assert video == v.resolve()
    assert scale == "scale=-2:1920", "retrato: a mesma escala do corte"
    import render
    assert grade == render.resolve_grade_filter("marca")
    assert nvdec is True
    assert re.search(r"PREP_CEDO pronto IMG_3935\.MOV em [\d.]+s", saida)


def test_paisagem_e_varios_takes_seguem_a_regra(monkeypatch, capsys, tmp_path):
    v = tmp_path / "a.mov"
    v.write_bytes(b"x")
    chamadas, _ = _rodar(monkeypatch, capsys, [str(v), "--grade-field", "marca", "--sem-nvdec"],
                         portrait=False)
    assert chamadas[0][1] == "scale=1920:-2"
    assert chamadas[0][3] is False, "varios takes: o NVDEC fica com um so"


def test_sdr_e_auto_saem_na_hora(monkeypatch, capsys, tmp_path):
    v = tmp_path / "a.mov"
    v.write_bytes(b"x")
    chamadas, saida = _rodar(monkeypatch, capsys, [str(v), "--grade-field", "marca"], hdr=False)
    assert chamadas == [] and "PREP_CEDO pulado: a.mov nao e HDR" in saida
    chamadas, saida = _rodar(monkeypatch, capsys, [str(v), "--grade-field", "auto"])
    assert chamadas == [] and "PREP_CEDO pulado: grade auto" in saida


def test_o_helper_nunca_levanta(monkeypatch, capsys, tmp_path):
    v = tmp_path / "a.mov"
    v.write_bytes(b"x")
    _, saida = _rodar(monkeypatch, capsys, [str(v), "--grade-field", "marca"], explode=True)
    assert "PREP_CEDO falhou RuntimeError: ffmpeg caiu" in saida


def test_a_regra_de_escala_e_a_mesma_nos_dois_lugares():
    """Se alguém mudar a escala do corte, o prep cedo tem de mudar junto —
    senão a chave nunca bate e o prep é feito duas vezes."""
    regra = '"scale=-2:1920" if is_portrait_source('
    assert RENDER.count(regra) >= 2, "as duas trilhas do corte usam a regra"
    helper = (REPO / "helpers" / "prep_source.py").read_text(encoding="utf-8")
    assert 'scale = "scale=-2:1920" if is_portrait_source(video) else "scale=1920:-2"' in helper
    assert 'else "scale=1920:-2"' in RENDER


def test_o_pipeline_dispara_por_fonte_e_espera_antes_do_corte():
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    fn = s[s.index("def _preparar_cedo("):][:1400]
    assert '"prep_source.py", str(src_), "--grade-field", grade_field_' in fn
    assert '"--sem-nvdec"] if len(sources) > 1' in fn
    assert "check=False" in fn, "um prep que falha nao derruba o job"
    assert 'os.environ.get("ATIVAVID_PREP_CEDO", "").strip() == "0"' in fn, "valvula de escape"
    assert "daemon=True" in fn
    # o gatilho: depois de `grade_field` existir, fora do longform e dos clipes
    i = s.index("_preparar_cedo(src, grade_field)")
    assert 'if not is_longform and intent_mode != "clips":' in s[i - 200:i]
    assert s.index("grade_field = g") < i
    # a espera: antes do corte, fora do CUT
    j = s.index("_fechar_preps()\n    _t_cut = time.perf_counter()")
    assert j > s.index("def _fechar_preps()")
    fn2 = s[s.index("def _fechar_preps()"):][:900]
    assert '_timing_mark("PREP_WAIT", t0)' in fn2
    assert '"PREP_CEDO" in linha or "PREPARED_SOURCE" in linha' in fn2, (
        "as linhas do prep chegam ao pipeline.log")
    assert "if not _preps:\n            return" in fn2, "idempotente"


def test_dois_preps_por_vez_como_no_corte():
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    assert "_prep_vagas = _threading_rev.Semaphore(2)" in s
    fn = s[s.index("def _preparar_cedo("):][:1400]
    assert "with _prep_vagas:" in fn
