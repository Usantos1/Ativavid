# -*- coding: utf-8 -*-
"""A pasta de trabalho do overlay é POR PROJETO.

`edit_dir.name` é sempre "edit". Usando só isso, TODO projeto compartilhava
`%TEMP%/ativavid_overlay_work/edit` — conferido no disco da máquina do
usuário: existia uma pasta só, para 113 projetos.

Os arquivos lá dentro têm nome fixo (`overlay.mov`, `_incr_old_00.mov`,
`_incr_concat.txt`), e `prepare_overlay_remotion` faz `rmtree` na pasta antes
de copiar o `public/` (edit-data.json, captions, cues) DO SEU projeto.

O lock exclusivo `try_acquire_overlay_slot` serializa render × render, mas o
quick apply chama `try_overlay_final` SEM pegar o slot — só `run_fast.py` e
`canary_run.py` pegam. Então um render na fila e uma correção no editor, ao
mesmo tempo, se atropelavam: a correção apagava o scaffold do render em
curso, ou um projeto renderizava o edit-data do outro. O usuário roda dois
jobs em paralelo e corrige no editor enquanto a fila anda.

O mesmo defeito já tinha sido encontrado e corrigido para o diretório de
CACHE (`_cache_dir_for` documentava exatamente isso) — e ficou aqui.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.overlay_path import _cache_dir_for, etiqueta_do_projeto  # noqa: E402


def test_projetos_diferentes_ganham_pastas_diferentes():
    a = Path(r"C:\proj\20260820-1_IMG_4131_aaa\edit")
    b = Path(r"C:\proj\20260820-2_IMG_4129_bbb\edit")
    assert etiqueta_do_projeto(a) != etiqueta_do_projeto(b)
    # e o nome ainda diz de quem é, para dar para achar na mão
    assert "IMG_4131" in etiqueta_do_projeto(a)


def test_o_mesmo_projeto_sempre_recai_na_mesma_pasta():
    """O `overlay.mov` da pasta de trabalho é REUSADO entre execuções quando o
    cache bate — a etiqueta tem de ser estável."""
    a = Path(r"C:\proj\job\edit")
    assert etiqueta_do_projeto(a) == etiqueta_do_projeto(Path(r"C:\PROJ\job\EDIT"))


def test_cache_e_trabalho_usam_a_mesma_etiqueta():
    a = Path(r"C:\proj\job\edit")
    assert _cache_dir_for(a).name == etiqueta_do_projeto(a)


def test_a_pasta_de_trabalho_nao_usa_mais_o_nome_do_edit_dir():
    """Guarda contra a volta do defeito: `edit_dir.name` ali é sempre "edit"."""
    s = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")
    # a ATRIBUIÇÃO, não a primeira menção — o comentário acima dela também
    # cita o caminho antigo. Pego a linha e as duas seguintes, que é onde a
    # expressão cabe em qualquer das duas formas (uma linha ou quebrada).
    linhas = s.splitlines()
    i = next((k for k, l in enumerate(linhas) if l.strip().startswith("work = ")), None)
    assert i is not None, "não achei a atribuição de `work`"
    trecho = "\n".join(linhas[i:i + 3])
    assert "edit_dir.name" not in trecho, trecho
    assert "etiqueta_do_projeto" in trecho, trecho


def test_so_o_render_pega_o_slot_exclusivo():
    """Isto documenta o que sobra: o apply NÃO serializa atrás do render (de
    propósito — a correção não pode esperar um render de 20 minutos). É por
    isso que separar as pastas era o conserto, e não o lock."""
    apply_s = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")
    run_s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "try_acquire_overlay_slot" in run_s
    assert "try_acquire_overlay_slot" not in apply_s
    # e o apply de fato chama o caminho do overlay
    assert re.search(r"try_overlay_final\s*\(", apply_s)
