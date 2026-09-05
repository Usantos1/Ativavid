# -*- coding: utf-8 -*-
"""5.0.55: transporte profissional na linha do tempo.

"Quero mais recursos profissionais na tela de edição, pra um cara que é
mais avançado, ali na timeline" (05/09).

J/K/L é a memória muscular de todo editor (Premiere, Resolve, Avid): L
acelera para frente a cada toque, J para trás, K para. O `<video>` não toca
ao contrário, então o J anda por passos no relógio do RASCUNHO — o mesmo
que a régua mostra. ↑/↓ pulam corte a corte (e selecionam o take), Home/End
vão às pontas, +/−/0 controlam o zoom com a agulha parada no lugar.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")


def test_jkl_existe_e_acelera_por_toque():
    assert "const VELOCIDADES_JKL = [1, 1.5, 2, 4];" in PJS
    i = PJS.index("function shuttle(dir)")
    corpo = PJS[i:PJS.index("\n/* Cortes do rascunho", i)]
    assert "_jkl.passo = Math.min(_jkl.passo + 1" in corpo, "cada toque acelera"
    assert "video.playbackRate = v" in corpo, "para frente e o proprio player"
    assert "setInterval" in corpo and "renderedToDraft(video.currentTime) - v / 10" in corpo, (
        "para tras o <video> nao toca — anda por passos no relogio do rascunho")
    assert "seekDraft(0); pararJkl()" in corpo, "no comeco, para"


def test_as_tres_teclas_estao_ligadas():
    for k, chamada in (("l", "shuttle(1)"), ("j", "shuttle(-1)")):
        i = PJS.index(f"e.key === '{k}' || e.key === '{k.upper()}'")
        assert chamada in PJS[i:i + 260], k
    i = PJS.index("e.key === 'k' || e.key === 'K'")
    assert "pararJkl()" in PJS[i:i + 260] and "video.pause()" in PJS[i:i + 260]
    # espaço tambem tem de zerar o shuttle, senao a velocidade fica presa
    j = PJS.index("if (e.code === 'Space')")
    assert "pararJkl()" in PJS[j:j + 200]


def test_ctrl_e_cmd_nao_viram_shuttle():
    """Ctrl+L / Cmd+J sao do navegador — nao podem virar transporte."""
    for k in ("l", "j", "k"):
        i = PJS.index(f"e.key === '{k}' || e.key === '{k.upper()}'")
        assert "!e.ctrlKey && !e.metaKey" in PJS[i:i + 120], k


def test_setas_pulam_corte_a_corte():
    assert "function bordasDoRascunho()" in PJS
    i = PJS.index("function irParaCorte(dir)")
    corpo = PJS[i:i + 900]
    assert "pontos.find((x) => x > t + 0.02)" in corpo
    assert "reverse().find((x) => x < t - 0.02)" in corpo
    assert "S.selected = i" in corpo, "o take sob a agulha fica selecionado"
    j = PJS.index("e.key === 'ArrowUp' || e.key === 'ArrowDown'")
    assert "irParaCorte(e.key === 'ArrowDown' ? 1 : -1)" in PJS[j:j + 200]


def test_home_end_e_zoom():
    i = PJS.index("e.key === 'Home'")
    assert "seekDraft(0)" in PJS[i:i + 160]
    j = PJS.index("e.key === 'End'")
    assert "draftTotal() - 1 / S.fps" in PJS[j:j + 200], "End para no ULTIMO frame, nao depois dele"
    assert "function zoomNaAgulha(fator)" in PJS
    k = PJS.index("function zoomNaAgulha(fator)")
    assert "applyZoom(S.pps * fator" in PJS[k:k + 420], "o zoom por tecla usa o mesmo caminho da roda"
    assert "zoomNaAgulha(1.35)" in PJS and "zoomNaAgulha(1 / 1.35)" in PJS


def test_a_ajuda_ensina_os_atalhos_novos():
    for texto in ("<kbd>J</kbd>", "<kbd>K</kbd>", "<kbd>L</kbd>",
                  "corte anterior / próximo", "começo / fim do vídeo",
                  "zoom da linha do tempo"):
        assert texto in HTML, texto
    assert 'id="jklChip"' in HTML, "a velocidade tem de aparecer na tela"
