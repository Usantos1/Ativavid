# -*- coding: utf-8 -*-
"""As regras que o harness congelado tem de respeitar.

Cada uma existe porque a alternativa produziria um número enganoso na matriz
que decide a arquitetura de produção.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra
from tools.bench_transcricao.impacto import Cortes, conferir_karaoke, divergencia_do_plano
from tools.bench_transcricao.motores import Saida, guardar_bruto


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


def S(pal):
    return Saida(motor="t", palavras=pal, texto=" ".join(p.texto for p in pal))


# 1 --------------------------------------------------- corpus sintético
def test_relatorio_recusa_corpus_sintetico(tmp_path):
    """Voz de espeak valida encanamento; não decide arquitetura."""
    from tools.bench_transcricao import relatorio

    (tmp_path / "estado.json").write_text(
        json.dumps({"_sintetico": True, "videos": {}}), encoding="utf-8")
    argv = sys.argv
    sys.argv = ["relatorio", "--saida", str(tmp_path)]
    try:
        assert relatorio.main() == 3
    finally:
        sys.argv = argv


def test_relatorio_aceita_corpus_real(tmp_path):
    from tools.bench_transcricao import relatorio

    (tmp_path / "estado.json").write_text(
        json.dumps({"_sintetico": False, "videos": {}}), encoding="utf-8")
    argv = sys.argv
    sys.argv = ["relatorio", "--saida", str(tmp_path)]
    try:
        assert relatorio.main() != 3        # segue para a falta de referência
    finally:
        sys.argv = argv


# 3 ------------------------------------------- reparo é defeito temporal
def test_reparo_reportado_como_defeito_com_distribuicao():
    ruim = S([P("a", 1.0, 1.2), P("b", 0.3, 0.5), P("c", 0.31, 0.32),
              P("d", 0.4, 0.6)])
    k = conferir_karaoke(ruim)
    assert not k.intacto
    assert k.deslocamento_mediano_ms > 0
    assert (k.deslocamento_mediano_ms <= k.deslocamento_p95_ms
            <= k.deslocamento_maximo_ms)
    assert k.deslocamento_total_ms >= k.deslocamento_maximo_ms   # soma, não máx
    assert any("DEFEITO TEMPORAL" in x for x in k.problemas)


def test_transcript_sadio_nao_tem_defeito_temporal():
    k = conferir_karaoke(S([P("cê", 0.0, 0.2), P("tá", 0.2, 0.5)]))
    assert k.intacto
    assert (k.deslocamento_total_ms == k.deslocamento_mediano_ms
            == k.deslocamento_p95_ms == k.deslocamento_maximo_ms == 0.0)


# 4 ------------------------------------------------ divergência ≠ qualidade
def test_divergencia_e_zero_para_planos_iguais():
    a = Cortes(n=2, trechos=[(0.0, 10.0), (20.0, 30.0)])
    assert divergencia_do_plano(a, a) == 0.0


def test_divergencia_e_um_para_planos_disjuntos():
    a = Cortes(n=1, trechos=[(0.0, 10.0)])
    b = Cortes(n=1, trechos=[(50.0, 60.0)])
    assert divergencia_do_plano(a, b) == 1.0


# 5 ------------------------------------------------------ brutos guardados
def test_bruto_e_gravado_intocado(tmp_path):
    payload = {"words": [{"text": "oi", "start": 0.0, "end": 0.3}]}
    p = guardar_bruto(tmp_path, "scribe", payload)
    assert p.parent.name == "bruto"
    assert json.loads(p.read_text(encoding="utf-8")) == payload


def test_bruto_aceita_texto_cru(tmp_path):
    """A resposta do Gemini vai verbatim: cerca de código, prosa e tudo."""
    cru = '```json\n{"correcoes": []}\n```\nEspero ter ajudado!'
    p = guardar_bruto(tmp_path, "gemini_audio_resposta", cru, ext="txt")
    assert p.read_text(encoding="utf-8") == cru


# 2 ------------------------------------------ tempo humano por motor
def test_tempo_humano_so_conta_para_quem_errou(tmp_path):
    """Quem propôs o que a pessoa confirmou não teria gerado trabalho ali."""
    from tools.bench_transcricao.relatorio import tempo_humano_por_motor

    v = tmp_path / "validacao"
    v.mkdir()
    (v / "propostas_v1.json").write_text(json.dumps({
        "00:01.550": {"whisper_local": "praimcamp", "scribe": "Prime Camp",
                      "gemini_audio": "PrimeCamp"}}), encoding="utf-8")
    (v / "validacao_v1.json").write_text(json.dumps({
        "video": "v1", "decisoes": {"00:01.550": "PrimeCamp"},
        "telemetria": {"00:01.550": {"ms": 9000, "digitou": True}}}),
        encoding="utf-8")

    r = tempo_humano_por_motor(tmp_path, "v1")
    assert r["gemini_audio"]["ms"] == 0          # acertou
    assert r["gemini_audio"]["intervencoes"] == 0
    assert r["whisper_local"]["ms"] == 9000      # errou: custaria o trecho
    assert r["whisper_local"]["intervencoes"] == 1
    assert r["scribe"]["intervencoes"] == 1
    assert r["whisper_local"]["digitou"] == 1


def test_ponto_nao_validado_nao_conta_para_ninguem(tmp_path):
    from tools.bench_transcricao.relatorio import tempo_humano_por_motor

    v = tmp_path / "validacao"
    v.mkdir()
    (v / "propostas_v1.json").write_text(json.dumps({
        "00:01.550": {"whisper_local": "a", "scribe": "b"}}), encoding="utf-8")
    (v / "validacao_v1.json").write_text(json.dumps({
        "video": "v1", "decisoes": {}, "telemetria": {}}), encoding="utf-8")
    assert tempo_humano_por_motor(tmp_path, "v1") == {}


def test_as_tres_medidas_nao_se_confundem():
    """WER, corridas de erro e tempo humano medem coisas diferentes."""
    from tools.bench_transcricao.metricas import evaluate_text

    ref = "eu vendi quinze mil na PrimeCamp ontem à noite pra dois clientes"
    grudados = "eu vendi quinze mil no prime camp ontem à noite pra dois clientes"
    espalhados = "eu vendo quinze mil na PrimeCamp ontem à noites pra dois cliente"
    a, b = evaluate_text(ref, grudados), evaluate_text(ref, espalhados)
    assert a.counts.wer == b.counts.wer           # precisão textual: igual
    assert a.edits_100w == b.edits_100w           # operações: igual
    assert a.correcoes_100w < b.correcoes_100w    # concentração: diferente
