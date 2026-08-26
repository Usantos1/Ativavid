# -*- coding: utf-8 -*-
"""Modo "Sem cortes" e o relatório do corte.

Sem cortes: pedido direto do usuário (24-25/08, "quero o mais original
possível") — o mínimo que existia (Vídeo completo) ainda tira silêncio e
repetição. Relatório: toda a auditoria dessa semana foi abrir EDL +
transcrição na mão; agora o pipeline grava o que saiu e por quê.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.editing_intent import DEFAULTS, INTENTS, guard_ranges, normalize  # noqa: E402


def test_intact_e_um_modo_de_verdade():
    assert "intact" in INTENTS
    assert "intact" in DEFAULTS
    d = normalize({"editingIntent": "intact", "contentType": "humor"})
    assert d["editingIntent"] == "intact", \
        "normalize rebaixou o intact para outro modo"


def test_guard_nao_mexe_no_video_inteiro():
    ranges = [{"source": "SRC", "start": 0.0, "end": 121.0, "beat": "HOOK"}]
    out = guard_ranges([dict(r) for r in ranges],
                       preset={"editingIntent": "intact"},
                       regions=[(0.0, 100.0)], duration_s=121.0)
    assert out == ranges, "a guarda mexeu num EDL que e o video inteiro"


def test_o_pipeline_tem_o_ramo_sem_cortes():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert '"sem_cortes"' in s, "o backend sem_cortes sumiu do run_fast"
    assert '== "intact"' in s
    # o teto de formato nao pode derrubar um video inteiro
    assert 'intent_mode not in ("complete", "intact")' in s


def test_a_ui_oferece_o_sem_cortes():
    est = (RAIZ / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'value="intact"' in est, "opcao Sem cortes sumiu da tela de Estilo"
    imp = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'data-intent="intact"' in imp, "card Sem cortes sumiu do importar"
    srv = (RAIZ / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert '"intact"' in srv, "preview_server nao aceita o modo intact"


def test_jobs_view_rotula_o_sem_cortes():
    from app.jobs_view import _MODO_LABEL

    assert _MODO_LABEL.get("intact") == "Sem cortes"


# --- relatório do corte ------------------------------------------------------


def _preparar(tmp_path: Path) -> None:
    (tmp_path / "transcripts").mkdir()
    words = [
        {"type": "word", "start": 1.0, "end": 1.5, "text": "Oi,"},
        {"type": "word", "start": 1.5, "end": 2.0, "text": "mocinha!"},
        # 10-14: refrão repetido (frase sancionada)
        {"type": "word", "start": 10.2, "end": 13.8, "text": "A sua mão que me sustenta."},
        # 20-22: fala removida pela IA sem sanção
        {"type": "word", "start": 20.2, "end": 21.8, "text": "esse trecho a IA achou lento"},
    ]
    (tmp_path / "transcripts" / "SRC.json").write_text(
        json.dumps({"words": words}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "takes_packed.md").write_text(
        "## SRC\n"
        "  [005.00-008.00] S0 A sua mão que me sustenta.\n"
        "  [010.00-014.00] S0 A sua mão que me sustenta.\n",
        encoding="utf-8")


def test_relatorio_classifica_os_gaps(tmp_path):
    from app.corte_relatorio import gerar

    _preparar(tmp_path)
    ranges = [
        {"source": "SRC", "start": 0.0, "end": 9.0},    # gap 9-10? nao: kept
        {"source": "SRC", "start": 14.5, "end": 20.0},  # 9-14.5 removido
        {"source": "SRC", "start": 22.5, "end": 30.0},  # 20-22.5 removido
    ]
    d = gerar(tmp_path, duration_s=35.0, ranges=ranges, stem="SRC",
              mode="dynamic", backend="gemini-web")
    assert d is not None
    classes = {(it["start"], it["classe"]) for it in d["itens"]}
    assert (9.0, "repetition") in classes, d["itens"]
    assert (20.0, "estilo") in classes, d["itens"]
    assert (30.0, "silence") in classes, d["itens"]     # cauda sem fala
    assert "repetição" in d["resumo"] and "silêncio" in d["resumo"]
    assert (tmp_path / "corte_relatorio.json").is_file()


def test_relatorio_do_video_inteiro_diz_nada(tmp_path):
    from app.corte_relatorio import gerar

    _preparar(tmp_path)
    d = gerar(tmp_path, duration_s=35.0, mode="intact", stem="SRC",
              ranges=[{"source": "SRC", "start": 0.0, "end": 35.0}])
    assert d["removedSec"] == 0
    assert d["itens"] == []


def test_relatorio_recusa_multi_take(tmp_path):
    from app.corte_relatorio import gerar

    _preparar(tmp_path)
    d = gerar(tmp_path, duration_s=35.0, mode="dynamic", stem="SRC", ranges=[
        {"source": "A", "start": 0.0, "end": 5.0},
        {"source": "B", "start": 0.0, "end": 5.0},
    ])
    assert d is None, "gap entre fontes de tempos locais nao e remocao"


def test_gerar_versoes_roda_os_cinco_modos():
    """Uso real (24/08): o usuario importou o MESMO video seis vezes trocando
    modo/estilo na mao. Comecou com 3 versoes; ele pediu mais ("falta mais",
    25/08): agora sao 5 — os tres niveis de tesoura + Shorts + Viral."""
    imp = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnImportTrio"' in imp, "o botao Gerar versoes sumiu"
    assert "Gerar 5 vers" in imp, "o rotulo do botao nao diz 5 versoes"
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.find("btnTrio.onclick")
    assert i > 0
    bloco = js[i:i + 1600]
    for m in ('"dynamic"', '"complete"', '"intact"', '"shorts"'):
        assert f"editingIntent: {m}" in bloco, f"versao {m} sumiu do lote"
    assert 'contentType: "viral"' in bloco, "o pacote Viral sumiu do lote"


def test_knobs_de_corte_viajam_no_job_intent():
    """Ritmo do corte e Limpeza de fala escolhidos na importacao chegam ao
    preset do planejador (sao _CUT_STYLE_KEYS: mudar replaneja). Invalido ou
    vazio = None = o estilo decide."""
    from app.editing_intent import merge_into_preset

    d = normalize({"editingIntent": "dynamic", "rhythm": "cirurgico",
                   "speechClean": "forte"})
    assert d["rhythm"] == "cirurgico" and d["speechClean"] == "forte"
    p2 = merge_into_preset({"rhythm": "dinamico"}, d)
    assert p2["rhythm"] == "cirurgico" and p2["speechClean"] == "forte"
    d2 = normalize({"editingIntent": "dynamic", "rhythm": "banana"})
    assert d2["rhythm"] is None
    p3 = merge_into_preset({"rhythm": "dinamico"}, d2)
    assert p3["rhythm"] == "dinamico", "knob vazio nao pode apagar o do estilo"
    imp = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="importRhythm"' in imp and 'id="importSpeechClean"' in imp


def test_comparar_versoes_existe(tmp_path):
    """"Gerar 5 versoes" cria 5 projetos irmaos; o Comparar mostra os finais
    lado a lado. O agrupamento vem do fonteStem (state.json project) que o
    jobs_view expoe."""
    from app.jobs_view import _fonte_do_video

    (tmp_path / "state.json").write_text(json.dumps(
        {"project": "A001_08221139_C002.mov"}), encoding="utf-8")
    job = {}
    _fonte_do_video(job, tmp_path)
    assert job["fonteStem"] == "A001_08221139_C002"

    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "versoesDaFonte" in js and "abrirComparar" in js
    assert 'data-act="compare"' in js, "o item Comparar sumiu do menu do card"
    assert "const nome = String(v.final).split(/[" + "\\" * 2 + "/]/)" in js, \
        "o basename do final tem que separar por barra E contrabarra (Windows)"
    html = (RAIZ / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="dlgCompare"' in html and 'id="cmpGrid"' in html


def test_score_respeita_o_contrato_do_modo():
    """A regua "abertura ideal 1,2-3,4s" punia 92 de 157 projetos — muitos de
    modos cujo CONTRATO e preservar (complete/intact/light). Abertura longa
    num Sem cortes nao e defeito; a dica era ruido contra a promessa do
    proprio modo. No dynamic a regua continua valendo."""
    import sys as _sys
    _sys.path.insert(0, str(RAIZ / "helpers"))
    from video_score import score_structural

    ranges = [
        {"start": 0.0, "end": 8.0, "beat": "HOOK", "quote": "abertura longa de proposito"},
        {"start": 8.0, "end": 20.0, "beat": "B1", "quote": "meio comprido tambem"},
        {"start": 20.0, "end": 24.0, "beat": "CTA", "quote": "me segue ai"},
    ]
    sc_int = score_structural(duration=24.0, ranges=ranges, mode="intact",
                              spoken="x" * 100)
    blob = " ".join(sc_int["tips"])
    assert "abertura" not in blob.lower(), sc_int["tips"]
    assert "longos" not in blob.lower(), sc_int["tips"]
    sc_dyn = score_structural(duration=24.0, ranges=ranges, mode="dynamic",
                              spoken="x" * 100)
    assert sc_dyn["hook"] < sc_int["hook"], \
        "no dynamic a abertura de 8s tem que pesar contra"
