# -*- coding: utf-8 -*-
"""A ficha registra o pico do vídeo ENTREGUE, não o da tentativa.

Quando o motor rápido é reprovado (pico alto, por exemplo) o job cai para
o Remotion, que refaz tudo e no fim conserta o áudio. O pico medido na
tentativa que falhou continuava na ficha: o job de 27/08 ficou gravado em
−0,7 dBTP com o arquivo entregue em −1,3.

Isso não é detalhe de log. Em 29/08 varri os 170 projetos pela própria
ficha e concluí que 14 vídeos tinham saído acima do limite; ao medir os
arquivos, o mais recente estava certo — a ficha é que mentia. Uma ficha
que descreve a tentativa, e não a entrega, faz perder tempo atrás de
defeito que não existe (e esconde o que existe).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FONTE = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _trecho_do_caminho_completo() -> str:
    """O bloco que fecha o caminho FULL, depois do encode final."""
    i = FONTE.index("from app.overlay_compose import garantir_true_peak",
                    FONTE.index("_timing_mark(\"FINAL_ENCODE\"", 1000))
    return FONTE[i - 400:i + 900]


def test_o_caminho_completo_conserta_o_pico():
    """Sem isto o mesmo app entrega em dois padrões de áudio: o rápido
    corrigido, o completo com o que o loudnorm deixou (até −0,3 dBTP)."""
    assert "garantir_true_peak(final)" in FONTE


def test_o_pico_de_depois_do_conserto_vai_para_a_ficha():
    bloco = _trecho_do_caminho_completo()
    assert re.search(r"_au_final\s*=\s*garantir_true_peak\(final\)", bloco), bloco[-500:]
    assert '_RENDER_META["truePeak"] = _au_final' in bloco
    assert '_RENDER_META["LUFS"] = _au_final' in bloco


def test_o_conserto_devolve_a_medicao_final():
    """O ajudante só troca o arquivo quando melhora, e devolve o que mediu
    depois — é esse número que a ficha tem de guardar."""
    ajuda = (REPO / "app" / "overlay_compose.py").read_text(encoding="utf-8")
    i = ajuda.index("def garantir_true_peak")
    corpo = ajuda[i:ajuda.index("\ndef ", i + 10)]
    assert "return depois" in corpo
    # e mantém o original quando a renormalização não melhora
    assert "TRUE_PEAK_CONSERTO_NAO_MELHOROU" in corpo
