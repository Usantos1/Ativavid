# -*- coding: utf-8 -*-
"""5.0.75: o proxy do corte é feito numa thread, em paralelo com o render.

`cut_proxy.mp4` (720p) existe para o editor rolar leve — só serve DEPOIS
do job. Mas era feito sequencialmente dentro de SEGMENTS: 8,6 s num corte
real de 30 s (medido), a maior parte da fase (11,6 s de mediana nos
últimos 40 jobs). Agora a thread nasce logo depois do corte — pronto e
normalizado, e só DEPOIS do try/except do zoom, que pode refazer o
cut.mp4 — e o job espera por ela no fim (`PROXY_WAIT`), inclusive na
saída da Fase 1 (`cut_ready`), porque o editor abre o corte pelo proxy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "pipeline"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

RUN_FAST = REPO / "pipeline" / "run_fast.py"


def _codigo() -> str:
    from leitura_de_codigo import apenas_codigo

    return apenas_codigo(RUN_FAST)


def test_o_proxy_nasce_depois_do_corte_e_do_fallback_do_zoom():
    s = _codigo()
    i = s.index('_timing_mark("CUT", _t_cut)')
    j = s.index('target=_maybe_proxy, args=(cut_path, edit_dir), daemon=True')
    assert j > i, "a thread tem de comecar depois do corte fechado"
    assert "FALLBACK_FULL_REMOTION" in s[:i], "o fallback do zoom refaz o cut antes"
    assert s.count("_maybe_proxy(cut_path, edit_dir)") == 0, (
        "a chamada sequencial em SEGMENTS saiu")


def test_o_job_espera_o_proxy_no_fim_e_na_fase_1():
    s = _codigo()
    fn = s[s.index("def _fechar_proxy()"):][:500]
    assert '_timing_mark("PROXY_WAIT", t0)' in fn
    assert '_proxy_box["thread"] = None' in fn, "idempotente"
    # antes do timing.json (junto das revisoes adiadas)
    assert "_fechar_revisoes()\n    _fechar_proxy()\n    other = " in s
    # e na saida da Fase 1
    k = s.index('status["status"] = "cut_ready"')
    assert "_fechar_proxy()" in s[k - 300:k]


def test_o_proxy_continua_sendo_o_mesmo_arquivo_que_o_editor_le():
    s = _codigo()
    fn = s[s.index("def _maybe_proxy("):][:900]
    assert 'dest = edit_dir / "cut_proxy.mp4"' in fn
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert re.search(r"rel = 'cut_proxy\.mp4'", js), "o editor troca cut.mp4 pelo proxy"
