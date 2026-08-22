# -*- coding: utf-8 -*-
"""O pipeline transcreve com o Scribe, que é o plano que o usuário paga.

`transcribe.py` era chamado sem `--backend`, então usava `auto` — e `auto` só
escolhe ElevenLabs para fonte acima de **5 minutos**. Nenhuma fonte do usuário
chega perto: das **149 medidas no disco dele, a mais longa tem 2,8 min**.
Resultado: **149 de 149 foram para o Groq**, e o plano pago nunca foi usado no
vídeo curto — que é todo o trabalho dele.

Não é só qualidade de transcrição. O Groq gratuito responde 429 sob carga, e o
cliente espera 5, 10, 20, 40, 60, 60s por tentativa. É isso que aparece na
fase ANALYZE: medido por período nos projetos dele, o custo por segundo de
fonte foi **2,27 na manhã de 20/08** (lote grande, muito 429) contra **0,12 na
tarde do mesmo dia** — 19x de espalhamento sem uma linha de código mudar.

Forçar um provedor traz um risco novo: se ele cair, o job cai junto. Por isso
o ElevenLabs agora desce para o Groq em tempo de execução — que é exatamente
o caminho que o `auto` já usava para fonte curta, ou seja a queda leva ao
comportamento antigo e não a um desconhecido.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

RUN_FAST = REPO / "pipeline" / "run_fast.py"


def test_nenhum_ponto_que_transcreve_cai_no_auto():
    """O invariante, que sobreviveu à chegada dos três modos: nenhuma chamada
    pode omitir o `--backend`.

    Antes os três pontos fixavam `"elevenlabs"`; agora leem
    `_backend_transcricao()`, que resolve o modo. O que não pode voltar é a
    chamada SEM backend, que cai no `auto` — e o `auto` do `transcribe.py`
    manda fonte curta para o Groq.

    Lê o CÓDIGO, não o arquivo: o comentário que explica a decisão cita
    "elevenlabs", e uma versão anterior deste teste passava por causa dele.
    """
    from pipeline.leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    pontos = [m.start() for m in re.finditer(r'"transcribe\.py"', s)]
    assert len(pontos) == 3, f"achei {len(pontos)} chamadas; o arquivo mudou"
    for i in pontos:
        trecho = s[i:i + 300]
        assert "--backend" in trecho, (
            "chamada sem `--backend` — cai no `auto`, que manda fonte curta "
            "para o Groq: " + " ".join(trecho.split())[:110]
        )


def test_todos_os_pontos_usam_o_MESMO_motor_no_mesmo_job():
    """O transcript da fonte e o do cut têm de vir do mesmo motor: tempos de
    palavra de motores diferentes não conversam."""
    from pipeline.leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    # `[^\)\n]+` para na primeira `)`, então a chamada sai truncada em
    # `_backend_transcricao(` — o que basta para comparar os três entre si.
    usados = set(re.findall(r'"--backend",\s*([^\)\n]+)', s))
    assert len(usados) == 1, f"pontos usando motores diferentes: {usados}"
    assert "_backend_transcricao" in next(iter(usados))
    # e a resolução é em cache, senão dois pontos podem divergir se a
    # configuração mudar no meio do job
    i = s.index("def _backend_transcricao(")
    assert "lru_cache" in s[max(0, i - 200):i]


def test_a_resolucao_nunca_devolve_auto_nem_groq(monkeypatch):
    """`auto` e `groq` são exatamente o que a mudança veio tirar do caminho."""
    from app.transcricao.modo import AUTO, LOCAL, SCRIBE, backend_para_o_pipeline

    for pedido in ("", AUTO, LOCAL, SCRIBE, "lixo"):
        if pedido:
            monkeypatch.setenv("ATIVAVID_TRANSCRICAO", pedido)
        else:
            monkeypatch.delenv("ATIVAVID_TRANSCRICAO", raising=False)
        assert backend_para_o_pipeline() in (LOCAL, SCRIBE)


def test_auto_resolve_para_o_motor_local():
    """A chave virou em 21/08/2026, com a decisão tomada sobre os benchmarks.

    Este teste existia ao contrário — travando `AUTO` no Scribe — enquanto a
    decisão não estava tomada. Agora ele trava o novo padrão: `AUTO` não pode
    voltar a mandar transcrição para serviço pago sem alguém decidir isso.
    """
    from app.transcricao.modo import AUTO_RESOLVE_PARA, LOCAL

    assert AUTO_RESOLVE_PARA == LOCAL


def test_local_indisponivel_nao_manda_para_o_servico_pago(monkeypatch):
    """A queda automática para o Scribe foi RETIRADA de propósito.

    Ela existia enquanto o local era experimental. Com o local como padrão,
    cair no Scribe sozinho gastaria a cota de um serviço pago sem o usuário
    pedir — e nenhum motivo de o local faltar se resolve com ele: componentes
    não baixados e download falhado precisam da mesma rede que o Scribe
    precisaria; GPU indisponível já cai para CPU dentro do motor.

    Quando falta componente, quem resolve é o preparo do primeiro uso; se nem
    isso der, o job falha com mensagem em vez de gerar cobrança silenciosa.
    """
    import app.transcricao.modo as modo

    monkeypatch.setenv("ATIVAVID_TRANSCRICAO", modo.LOCAL)

    class Quebrado:
        def disponivel(self):
            return False, "faster-whisper não instalado"

    import app.transcricao.whisper_local as wl
    monkeypatch.setattr(wl, "MotorWhisperLocal", lambda *a, **k: Quebrado())
    assert modo.backend_para_o_pipeline() == modo.LOCAL, (
        "voltou a mandar para o serviço pago por conta própria")


def test_o_limiar_do_auto_esta_acima_das_fontes_do_usuario():
    """Documenta POR QUE o explícito é necessário: se um dia o limiar cair
    abaixo de ~3 min, o `auto` passaria a servir, e este teste avisa."""
    from transcribe import LONG_SOURCE_SECONDS

    MAIS_LONGA_DO_USUARIO = 171      # 2,8 min, medida nas 149 fontes
    assert LONG_SOURCE_SECONDS > MAIS_LONGA_DO_USUARIO, (
        "o limiar do `auto` desceu abaixo das fontes do usuário — reveja se o "
        "`--backend` explícito ainda é necessário"
    )


def _fonte(tmp_path: Path) -> Path:
    p = tmp_path / "IMG_9999.mov"
    p.write_bytes(b"abcd" * 50_000)
    return p


def _armar(monkeypatch, tmp_path, tr):
    monkeypatch.setattr(tr, "CACHE_ENTRE_PROJETOS", tmp_path / "cache")
    monkeypatch.setattr(tr, "_probe_duration", lambda p: 100.0)   # curta: `auto` diria Groq
    monkeypatch.setattr(tr, "extract_audio", lambda v, d: d.write_bytes(b"x" * 2048))


def test_a_queda_do_elevenlabs_nao_derruba_o_job(tmp_path, monkeypatch):
    import transcribe as tr

    _armar(monkeypatch, tmp_path, tr)
    tentados: list[str] = []

    def falso(audio, key, modelo, lang, verbose, *, backend, **k):
        tentados.append(backend)
        if backend == "elevenlabs":
            raise RuntimeError("503 Service Unavailable")
        return {"words": [{"text": "oi", "start": 0.0, "end": 0.3, "type": "word"}]}

    monkeypatch.setattr(tr, "_transcribe_audio", falso)
    saida = tr.transcribe_one(
        _fonte(tmp_path), tmp_path / "edit", api_key="gsk_x",
        elevenlabs_key="el_x", backend="elevenlabs", verbose=False)
    assert saida.is_file(), "o job caiu junto com o provedor"
    assert tentados == ["elevenlabs", "groq"], tentados


def test_sem_chave_do_groq_a_falha_do_scribe_sobe(tmp_path, monkeypatch):
    """Sem para onde cair, esconder o erro seria pior: o usuário ficaria sem
    saber por que a legenda não saiu."""
    import transcribe as tr

    _armar(monkeypatch, tmp_path, tr)

    def falso(audio, key, modelo, lang, verbose, *, backend, **k):
        raise RuntimeError("503 Service Unavailable")

    monkeypatch.setattr(tr, "_transcribe_audio", falso)
    with pytest.raises(RuntimeError):
        tr.transcribe_one(_fonte(tmp_path), tmp_path / "edit", api_key="",
                          elevenlabs_key="el_x", backend="elevenlabs", verbose=False)


def test_o_groq_nao_sobe_para_o_elevenlabs(tmp_path, monkeypatch):
    """A queda é de mão única. Subir de provedor por trás de quem pediu o Groq
    gastaria a cota paga sem ninguém autorizar."""
    import transcribe as tr

    _armar(monkeypatch, tmp_path, tr)
    tentados: list[str] = []

    def falso(audio, key, modelo, lang, verbose, *, backend, **k):
        tentados.append(backend)
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(tr, "_transcribe_audio", falso)
    with pytest.raises(RuntimeError):
        tr.transcribe_one(_fonte(tmp_path), tmp_path / "edit", api_key="gsk_x",
                          elevenlabs_key="el_x", backend="groq", verbose=False)
    assert tentados == ["groq"], tentados


def test_o_resultado_da_queda_e_guardado_como_groq(tmp_path, monkeypatch):
    """Senão a próxima importação leria um transcript do Groq acreditando ser
    do Scribe — degradação silenciosa, que é o defeito que o cache evita."""
    import transcribe as tr

    _armar(monkeypatch, tmp_path, tr)
    payload = {"words": [{"text": "oi", "start": 0.0, "end": 0.3, "type": "word"}]}

    def falso(audio, key, modelo, lang, verbose, *, backend, **k):
        if backend == "elevenlabs":
            raise RuntimeError("503")
        return payload

    monkeypatch.setattr(tr, "_transcribe_audio", falso)
    fonte = _fonte(tmp_path)
    tr.transcribe_one(fonte, tmp_path / "edit", api_key="gsk_x",
                      elevenlabs_key="el_x", backend="elevenlabs", verbose=False)
    assert tr.buscar_no_cache(fonte, "groq", tr.DEFAULT_MODEL) == payload
    assert tr.buscar_no_cache(fonte, "elevenlabs", tr.ELEVENLABS_MODEL) is None
