# -*- coding: utf-8 -*-
"""5.0.72: a revisão textual da IA sai do caminho crítico do job.

MEDIDO na telemetria real (`~/ATIVAVID/transcricao-log.jsonl`, 79 jobs):
a revisão custava 13 s de mediana em dias normais e 24 s num lote de 24
vídeos, com casos de 84 s — tudo com o job PARADO esperando, sendo que só
as legendas usam as palavras revisadas. Num cProfile de uma transcrição
fria de 41 s, 23 s eram a revisão.

Agora o helper devolve o Whisper puro (`--revisao depois`) e a revisão roda
numa segunda chamada (`--revisao so`), em paralelo com o plano e o corte;
`_fechar_revisoes()` espera por ela dentro de `_write_caps_from_edl` (as
legendas) e, por segurança, antes do `timing.json`.

O plano lê o texto puro: as correções são de grafia ("Paramicup" → "Prime
Camp" no C005 real) e não mudam onde cortar; o EDL guarda TEMPOS, não
texto, então as legendas saem das palavras revisadas como antes. Validado
no laboratório com o C005 real: o `so` produziu palavra por palavra o
mesmo transcript que a produção produziu em 04/09 pelo caminho antigo.

Os fakes (motor, Gemini, cache) são os de `test_revisao_cache.py`.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers", REPO / "pipeline"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from test_revisao_cache import (  # noqa: E402,F401  (o fixture `mundo` vem junto)
    CORRIGIDO, SUF, TEXTO, _MotorFalso, mundo,
)

RUN_FAST = REPO / "pipeline" / "run_fast.py"


def _rodar(m, modo: str, td: Path | None = None) -> dict:
    td = td or m.td
    td.mkdir(parents=True, exist_ok=True)
    return json.loads(m.tr._transcrever_local(
        m.video, td, td / "v.json", language="pt", verbose=False, revisao=modo,
    ).read_text(encoding="utf-8"))


# ------------------------------------------------------------- o helper

def test_depois_devolve_o_puro_agora_e_avisa(mundo, capsys):
    mundo.ligar("gemini")
    mundo.gemini()
    d = _rodar(mundo, "depois")
    assert d["text"] == TEXTO, "o puro sai AGORA; a revisao fica para depois"
    assert "marca=local-medium\n" in mundo.sig() + "\n" and SUF not in mundo.sig()
    assert mundo.contador["gemini"] == 0, "chamou a IA no caminho critico"
    assert "REVISAO_ADIADA" in capsys.readouterr().out


def test_so_revisa_o_que_o_depois_deixou(mundo, capsys):
    mundo.ligar("gemini")
    mundo.gemini()
    _rodar(mundo, "depois")
    d = _rodar(mundo, "so")
    assert d["text"] == CORRIGIDO
    assert f"marca=local-medium{SUF}" in mundo.sig()
    assert mundo.marcas() == [f"local-medium{SUF}-medium", "local-medium-medium"]
    assert _MotorFalso.chamadas == 1, "o `so` acordou a GPU"
    assert mundo.contador["gemini"] == 1
    assert "REVISAO_GEMINI ok" in capsys.readouterr().out
    # de novo: nada a fazer, e sem pagar a IA outra vez
    _rodar(mundo, "so")
    assert mundo.contador["gemini"] == 1
    assert "REVISAO_JA_FEITA" in capsys.readouterr().out


def test_revisado_ja_no_cache_nao_adia_nada(mundo, capsys):
    """Outro projeto já revisou esta fonte: o `depois` serve o revisado
    direto, sem a segunda chamada."""
    mundo.ligar("gemini")
    mundo.gemini()
    _rodar(mundo, "junto")
    td2 = mundo.td.parent / "p2" / "transcripts"
    d = _rodar(mundo, "depois", td2)
    assert d["text"] == CORRIGIDO
    assert "REVISAO_ADIADA" not in capsys.readouterr().out
    assert mundo.contador["gemini"] == 1


def test_com_a_revisao_desligada_o_depois_e_o_junto(mundo, capsys):
    mundo.ligar("off")
    a = _rodar(mundo, "junto")
    b = _rodar(mundo, "depois", mundo.td.parent / "p2" / "transcripts")
    assert {k: v for k, v in a.items() if not k.startswith("_seg")} == \
           {k: v for k, v in b.items() if not k.startswith("_seg")}
    saida = capsys.readouterr().out
    assert "REVISAO_ADIADA" not in saida
    _rodar(mundo, "so")
    assert "REVISAO_DESLIGADA" in capsys.readouterr().out
    assert "marca=local-medium" in mundo.sig() and SUF not in mundo.sig()


def test_so_que_falha_deixa_o_puro_e_tenta_de_novo_depois(mundo, capsys):
    """A regra do veneno continua: revisão que falhou não grava a marca
    revisada, e a próxima passada tenta de novo sem retranscrever."""
    mundo.ligar("gemini")
    mundo.gemini(quebrado=True)
    _rodar(mundo, "depois")
    d = _rodar(mundo, "so")
    assert d["text"] == TEXTO
    assert SUF not in mundo.sig()
    assert mundo.marcas() == ["local-medium-medium"]
    assert "REVISAO_GEMINI_FALHOU" in capsys.readouterr().out
    mundo.gemini()
    d = _rodar(mundo, "so")
    assert d["text"] == CORRIGIDO and f"marca=local-medium{SUF}" in mundo.sig()
    assert _MotorFalso.chamadas == 1


def test_a_troca_do_transcript_e_atomica(mundo, monkeypatch):
    """O `so` reescreve o arquivo enquanto o pipeline pode estar lendo: vai
    num temporário e troca de uma vez, insistindo se o Windows disser que o
    arquivo está aberto."""
    alvo = mundo.td / "v.json"
    alvo.write_text('{"words": []}', encoding="utf-8")
    real = os.replace
    tentativas = {"n": 0}

    def teimoso(a, b):
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            raise PermissionError("em uso")
        real(a, b)

    monkeypatch.setattr(os, "replace", teimoso)
    monkeypatch.setattr(mundo.tr.time, "sleep", lambda s: None)
    mundo.tr._gravar_json_atomico(alvo, {"words": [{"text": "ok"}]})
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"words": [{"text": "ok"}]}
    assert tentativas["n"] == 3
    assert not list(mundo.td.glob("*.tmp*")), "temporario ficou para tras"


def test_transcribe_one_nao_sai_cedo_no_so(mundo, monkeypatch):
    """`transcript_cache_hit` é verdadeiro no `so` por definição (o puro está
    lá): a saída antecipada deixaria o transcript sem revisão para sempre."""
    tr = mundo.tr
    chamadas = []
    monkeypatch.setattr(tr, "transcript_cache_hit", lambda *a, **k: True)
    monkeypatch.setattr(tr, "_probe_duration", lambda v: 2.0)
    monkeypatch.setattr(
        tr, "_transcrever_local",
        lambda video, td, out, **k: chamadas.append(k.get("revisao")) or out)
    edit = mundo.td.parent / "edit"
    tr.transcribe_one(mundo.video, edit, api_key="", backend="local",
                      verbose=False, revisao="so")
    tr.transcribe_one(mundo.video, edit, api_key="", backend="local",
                      verbose=False, revisao="depois")
    assert chamadas == ["so"], "o `depois` com cache quente sai cedo; o `so` nunca"


def test_o_kwarg_novo_existe_nas_duas_assinaturas():
    """`duck=` numa função sem o parâmetro derrubou o caminho rápido por 3
    dias, calado (5.0.57). O helper é chamado por subprocesso, então aqui a
    conferência é direta: quem recebe `revisao=` declara `revisao`."""
    import transcribe as tr

    assert "revisao" in inspect.signature(tr._transcrever_local).parameters
    assert "revisao" in inspect.signature(tr.transcribe_one).parameters


def test_a_cli_conhece_os_tres_modos():
    import transcribe as tr

    src = inspect.getsource(tr.main)
    assert '"--revisao"' in src
    assert 'choices=["junto", "depois", "so"]' in src
    assert 'default="junto"' in src.split('"--revisao"', 1)[1][:200]
    assert "revisao=args.revisao" in src


# ------------------------------------------------------------ o pipeline

def test_o_pipeline_pede_o_puro_e_dispara_a_revisao_em_paralelo():
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    i = s.index('_helper, "transcribe.py", str(src)')
    assert '"--revisao", "depois"' in s[i:i + 400], "a fonte e transcrita sem adiar"
    fn = s[s.index("def _revisar_em_paralelo("):][:1400]
    assert '"--revisao", "so", check=False' in fn, (
        "a segunda chamada tem de ser `so` e nao pode derrubar o job se falhar")
    assert "daemon=True" in fn, "thread que segura o processo no fim do job"
    # o gatilho e o marcador do helper — nas duas saidas
    assert re.search(r'"REVISAO_ADIADA" in \(\(getattr\(_proc_tr, "stdout"', s)
    assert "_revisar_em_paralelo(src, stem, key)" in s


def test_as_legendas_esperam_e_o_fim_do_job_tambem():
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    caps = s[s.index("def _write_caps_from_edl()"):][:500]
    assert caps.index("_fechar_revisoes()") < caps.index('"captions_for_remotion.py"'), (
        "as legendas sao a unica etapa que precisa das palavras revisadas")
    fim = s[:s.index("write_timing(edit_dir)")]
    assert "_fechar_revisoes()" in fim[-600:], "rede de seguranca antes do timing.json"
    fn = s[s.index("def _fechar_revisoes()"):][:1200]
    assert '_timing_mark("REVISAO_WAIT", t0)' in fn
    assert 'if item["stem"] != item["key"]' in fn and "shutil.copy2(a, b)" in fn, (
        "captions_for_remotion prefere <key>.json — a copia era do puro")
    assert "if not _revisoes:\n            return" in fn, "idempotente"


def test_a_espera_da_revisao_nao_conta_duas_vezes_no_total(tmp_path):
    """REVISAO_WAIT e marcado dentro da janela de CAPTIONS: o total do
    timing.json nao pode soma-lo de novo (lab de 05/09: 23,2 + 22,8 s
    para 23 s de relogio)."""
    import run_fast as rf

    rf._TIMING.clear()
    rf._TIMING.update({"CAPTIONS": 23.2, "REVISAO_WAIT": 22.8, "CUT": 10.0,
                       "CUT_extrair": 8.0})
    try:
        payload = rf.write_timing(tmp_path)
    finally:
        rf._TIMING.clear()
    assert payload["totalSec"] == 33.2
    assert payload["stages"]["REVISAO_WAIT"]["sec"] == 22.8, "a marca continua la"


def test_os_marcadores_novos_chegam_ao_log_do_job():
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    i = s.index("_MARCADORES_TRANSCRICAO = (")
    bloco = s[i:s.index(")", i)]
    for m in ("REVISAO_ADIADA", "REVISAO_JA_FEITA", "REVISAO_SEM_BASE",
              "REVISAO_DESLIGADA"):
        assert f'"{m}"' in bloco, m


def test_o_cut_continua_transcrito_junto():
    """O transcript do CORTE (fallback do remap e longform) fica como está:
    ele é lido logo em seguida, não há o que adiar."""
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(RUN_FAST)
    pontos = [m.start() for m in re.finditer(r'"transcribe\.py", str\(cut_path\)', s)]
    assert len(pontos) == 2
    for i in pontos:
        assert "--revisao" not in s[i:i + 300]
