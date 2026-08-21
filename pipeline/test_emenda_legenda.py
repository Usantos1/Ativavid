# -*- coding: utf-8 -*-
"""A emenda parcial: corrigir uma palavra sem redesenhar o vídeo inteiro.

Medido no mesmo projeto real, os dois caminhos INTERCALADOS: 41,5 s no caminho
normal contra 11,9 s na emenda — 3,5x, redesenhando 148 de 1243 quadros.

Aqui só a lógica pura (janela, costura, limites), que é onde os enganos moram.
O fim a fim é medido à mão com `scratchpad/medir_emenda.py`, porque precisa de
ffmpeg, GPU e um projeto de verdade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _cue(i: int, ini_ms: int, fim_ms: int, palavras: list[str]) -> dict:
    passo = (fim_ms - ini_ms) // max(1, len(palavras))
    return {
        "i": i, "startMs": ini_ms, "endMs": fim_ms, "preset": "STACK_MIXED",
        "lines": [[{"text": t, "fromMs": ini_ms + k * passo,
                    "toMs": ini_ms + (k + 1) * passo}
                   for k, t in enumerate(palavras)]],
    }


CUES = [
    _cue(0, 0, 2000, ["moço", "nossa"]),
    _cue(1, 2000, 4000, ["capinha", "do"]),
    _cue(2, 4000, 6000, ["celular", "aqui"]),
    _cue(3, 6000, 8000, ["ficou", "boa"]),
]


def test_a_janela_sai_da_cue_corrigida(tmp_path):
    from app.emenda_legenda import FOLGA_ANTES, FOLGA_DEPOIS, janela_das_correcoes

    fix = {"from": "celular", "to": "aparelho", "startMs": 4000, "endMs": 5000}
    cues = [_cue(0, 0, 2000, ["moço", "nossa"]),
            _cue(1, 2000, 4000, ["capinha", "do"]),
            _cue(2, 4000, 6000, ["aparelho", "aqui"]),
            _cue(3, 6000, 8000, ["ficou", "boa"])]
    j = janela_das_correcoes(cues, [fix], fps=30.0, frames=240)
    assert j is not None
    ini, fim = j
    assert ini == 4000 / 1000 * 30 - FOLGA_ANTES
    assert fim == 6000 / 1000 * 30 + FOLGA_DEPOIS


def test_sem_conseguir_localizar_a_janela_e_None():
    """Recusar é sempre seguro: o apply segue pelo caminho normal."""
    from app.emenda_legenda import janela_das_correcoes

    assert janela_das_correcoes(CUES, [], fps=30.0, frames=240) is None
    assert janela_das_correcoes([], [{"from": "x", "to": "y"}], fps=30.0, frames=240) is None
    # texto que não está nas cues
    assert janela_das_correcoes(
        CUES, [{"from": "a", "to": "guarda-chuva"}], fps=30.0, frames=240) is None


def test_apagar_nao_tenta_emendar():
    """Um apagar não deixa texto para localizar; a janela seria adivinhada."""
    from app.emenda_legenda import janela_das_correcoes

    j = janela_das_correcoes(
        CUES, [{"from": "celular", "to": "", "delete": True}], fps=30.0, frames=240)
    assert j is None


def test_palavra_repetida_sem_tempo_e_recusada():
    """É por isso que os tempos passaram a ser guardados junto da correção:
    sem eles, uma palavra que aparece duas vezes é ambígua — e eram 15 dos 35
    projetos do usuário."""
    from app.emenda_legenda import janela_das_correcoes

    cues = [_cue(0, 0, 2000, ["tela", "nova"]),
            _cue(1, 2000, 4000, ["tela", "velha"])]
    assert janela_das_correcoes(
        cues, [{"from": "x", "to": "tela"}], fps=30.0, frames=120) is None
    # com o tempo, resolve
    j = janela_das_correcoes(
        cues, [{"from": "x", "to": "tela", "startMs": 2000, "endMs": 3000}],
        fps=30.0, frames=120)
    assert j is not None


def test_a_costura_nao_parte_a_manchete_nem_o_cartao():
    from app.emenda_legenda import _alargar_ate_nao_partir, _intervalos_desenhados

    ed = {"hook": {"enabled": True, "endSec": 4.0},
          "endCard": {"enabled": True, "lastSec": 2.5}}
    elementos = _intervalos_desenhados(CUES, ed, dur=60.0)
    assert (0.0, 4.0) in elementos
    assert (57.5, 60.0) in elementos

    # costura caindo NO MEIO da manchete: tem de alargar até cobri-la
    r = _alargar_ate_nao_partir(elementos, t_ini=2.0, t_fim=10.0, dur=60.0)
    assert r == (0.0, 10.0)
    # e no meio do cartão final
    r = _alargar_ate_nao_partir(elementos, t_ini=50.0, t_fim=58.0, dur=60.0)
    assert r == (50.0, 60.0)
    # longe dos dois: fica como está
    r = _alargar_ate_nao_partir(elementos, t_ini=20.0, t_fim=30.0, dur=60.0)
    assert r == (20.0, 30.0)


def test_as_legendas_ficam_de_fora_da_guarda_de_costura():
    """As cues são CONTÍGUAS — folga zero em 48 de 48 no projeto do usuário.
    Exigir que a costura caia entre elas é impossível por construção: a
    primeira tentativa alargava em cadeia e a fatia ia a 71% do vídeo."""
    from app.emenda_legenda import _intervalos_desenhados

    elementos = _intervalos_desenhados(CUES, {}, dur=60.0)
    assert elementos == [], "as cues voltaram para a guarda e vão travar tudo"


def test_o_limite_cai_em_keyframe_dos_dois_lados():
    from app.emenda_legenda import _limites_em_keyframe

    kfs = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    r = _limites_em_keyframe(kfs, ini_f=100, fim_f=160, fps=30.0, dur=12.0)
    assert r == (2.0, 6.0), r          # 3,33s..5,33s -> keyframes 2,0 e 6,0

    # fatia que vai até o fim: não há cauda para copiar, e isso é válido
    r = _limites_em_keyframe(kfs, ini_f=300, fim_f=360, fps=30.0, dur=12.0)
    assert r == (10.0, 12.0)

    # sem keyframe à direita e sem chegar ao fim: não dá para emendar
    assert _limites_em_keyframe([0.0, 2.0], ini_f=100, fim_f=160,
                                fps=30.0, dur=12.0) is None
    assert _limites_em_keyframe([], ini_f=0, fim_f=10, fps=30.0, dur=12.0) is None


def test_a_emenda_so_entra_quando_apenas_a_legenda_mudou():
    from app.apply_execute import _so_legenda_mudou

    assert _so_legenda_mudou({"mode": "REUSE_CUT", "dirty": {"captions": True}})
    for extra in ("headline", "edl", "style"):
        assert not _so_legenda_mudou(
            {"mode": "REUSE_CUT", "dirty": {"captions": True, extra: True}}
        ), f"{extra} sujo deveria recusar a emenda"
    assert not _so_legenda_mudou(
        {"mode": "REBUILD_CUT", "rebuildCut": True, "dirty": {"edl": True}})
    assert not _so_legenda_mudou(
        {"mode": "REUSE_CUT", "remapCaptions": True, "dirty": {"captions": True}})


def test_a_cabeca_e_cortada_por_quadro_nao_por_tempo():
    """Com `-c copy` o corte por TEMPO acontece no pacote e passa do ponto:
    medido, `-t 19,4667` deu 586 quadros onde a fatia começa no 584 — dois
    quadros duplicados, e a conferência reprovava o arquivo."""
    src = (REPO / "app" / "emenda_legenda.py").read_text(encoding="utf-8")
    i = src.index("if t_ini > 1e-6:")
    cabeca = src[i:i + 700]
    assert '"-frames:v", str(kf_ini_f)' in cabeca, "voltou a cortar por tempo"
    assert '"-t", f"{t_ini' not in cabeca


def test_a_cadeia_de_cor_e_a_mesma_do_caminho_normal():
    """Sem `scale=in_range=full:out_range=limited` o trecho emendado sai com
    nível diferente do resto, que é copiado — costura visível. Só apareceu
    porque dois renders completos aqui são bit a bit idênticos."""
    emenda = (REPO / "app" / "emenda_legenda.py").read_text(encoding="utf-8")
    proprio = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    for filtro in ("format=yuv420p", "scale=in_range=full:out_range=limited",
                   "setparams=color_primaries=bt709"):
        assert filtro in emenda, f"a emenda perdeu {filtro!r}"
        assert filtro in proprio, f"o caminho normal perdeu {filtro!r}"
