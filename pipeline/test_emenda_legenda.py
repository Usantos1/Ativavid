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
    ini, fim, grupos = j
    assert ini == 4000 / 1000 * 30 - FOLGA_ANTES
    assert fim == 6000 / 1000 * 30 + FOLGA_DEPOIS
    # uma correcao so = um grupo so, igual a envolvente
    assert grupos == [(ini, fim)]


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
    # na forma multi-fatia todos os copies passam pelo `_copy`, que corta por
    # CONTAGEM (`-frames:v`) — nunca por tempo
    i = src.index("def _copy(")
    copia = src[i:i + 900]
    assert '"-frames:v", str(n_quadros)' in copia, "voltou a cortar por tempo"
    assert '"-t",' not in copia


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


# --- o motivo do pulo chega ao apply_history --------------------------------
#
# A emenda (10x mais rapida para trocar uma palavra) existiu por 3 dias sem
# disparar UMA vez em 14 applies de legenda reais — e o motivo ia so para o
# stdout do worker, que ninguem guarda. Explicar os "0 de 44" exigiu reproduzir
# o apply num projeto copiado. Causa real: a envolvente UNICA das correcoes
# estoura o teto de 45% quando elas sao espalhadas (mediana real: 70%).
# Com o motivo no history, a decisao de generalizar para multi-fatia saira dos
# dados de producao.


def test_motivo_do_pulo_e_devolvido(tmp_path):
    from app.emenda_legenda import FRACAO_MAXIMA

    assert 0 < FRACAO_MAXIMA < 1
    # o parametro existe e e opcional — o chamador antigo continua valido
    import inspect

    from app.emenda_legenda import emendar_legenda

    par = inspect.signature(emendar_legenda).parameters
    assert "motivo" in par and par["motivo"].default is None


def test_tentar_emenda_grava_emendaSkip(monkeypatch, tmp_path):
    from app import apply_execute as ax

    (tmp_path / "remotion" / "public").mkdir(parents=True)
    (tmp_path / "remotion" / "public" / "edit-data.json").write_text(
        '{"fps": 30, "width": 1080, "height": 1920, "captions": {}}', encoding="utf-8")
    (tmp_path / "remotion" / "public" / "caption-cues.json").write_text(
        '{"cues": [{"startMs": 0, "endMs": 500, "lines": [[{"text": "oi"}]]}]}',
        encoding="utf-8")
    (tmp_path / "caption_fixes.json").write_text(
        '[{"from": "oi", "to": "olá"}]', encoding="utf-8")

    def recusa(*a, motivo=None, **k):
        if motivo is not None:
            motivo.append("EMENDA_PULADA fatia=57% > 45%")
        return None
    import app.emenda_legenda as em
    monkeypatch.setattr(em, "emendar_legenda", recusa)
    import app.timeline as tl
    monkeypatch.setattr(tl, "timeline_from_edit_data",
                        lambda ed: {"durationInFrames": 300})
    plan = {"mode": "REUSE_CUT", "rebuildCut": False, "remapCaptions": False,
            "dirty": {"captions": True}}
    ok = ax._tentar_emenda(tmp_path, plan, cut=tmp_path / "cut.mp4",
                           dest=tmp_path / "s.mp4", log=lambda m: None)
    assert ok is False
    colhido = ax._colher(tmp_path)
    assert "fatia=57%" in str(colhido.get("emendaSkip")), colhido


# --- multi-fatia ------------------------------------------------------------
#
# A janela única (min..max de todas as correções) estourava o teto de 45% em
# 89% dos applies reais — o usuário corrige várias palavras espalhadas de uma
# vez e a envolvente cobre 70% do vídeo (mediana). Por grupo de correções
# próximas, a soma cai (~42%, ~3 fatias) e a emenda volta a disparar.
#
# Provado no projeto real que era recusado (envolvente 57%): EMENDA_OK em 3
# fatias, 40,9% dos quadros, 84s; PSNR médio 60 dB contra o caminho cheio, 85%
# dos quadros bit-idênticos e áudio byte-idêntico.


def _cues_ms(pares):
    return [_cue(i, a, b, ["palavra"]) for i, (a, b) in enumerate(pares)]


def test_correcoes_proximas_viram_um_grupo():
    from app.emenda_legenda import _agrupar_cues

    lista = _cues_ms([(1000, 2000), (2500, 3500)])
    grupos = _agrupar_cues(lista, {0, 1}, fps=30.0, frames=9000)
    assert len(grupos) == 1


def test_correcoes_afastadas_viram_grupos_separados():
    from app.emenda_legenda import GAP_JUNTA_MS, _agrupar_cues

    lista = _cues_ms([(1000, 2000), (2000 + GAP_JUNTA_MS + 500, 40000)])
    grupos = _agrupar_cues(lista, {0, 1}, fps=30.0, frames=9000)
    assert len(grupos) == 2
    # e os grupos vem em ordem, sem sobreposicao
    assert grupos[0][1] <= grupos[1][0]


def test_fracao_e_a_soma_das_fatias_nao_a_envolvente():
    """O motivo do multi-fatia existir: duas correcoes nas pontas do video
    tem envolvente ~100% mas soma pequena — e agora passam no teto."""
    from app.emenda_legenda import FRACAO_MAXIMA, _agrupar_cues

    frames = 9000                      # 5 min a 30fps
    lista = _cues_ms([(1000, 2000), (280000, 281000)])
    grupos = _agrupar_cues(lista, {0, 1}, fps=30.0, frames=frames)
    soma = sum(f - i for i, f in grupos) / frames
    envolvente = (grupos[-1][1] - grupos[0][0]) / frames
    assert envolvente > FRACAO_MAXIMA, "o caso de teste perdeu a graca"
    assert soma < FRACAO_MAXIMA, soma
