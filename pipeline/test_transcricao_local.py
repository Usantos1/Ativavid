# -*- coding: utf-8 -*-
"""A camada de transcrição local: contrato, plataforma, modelo e cancelamento.

Aqui ficam as partes determinísticas. O que depende de GPU, de modelo de 1,4 GB
e de áudio real foi medido à mão e está registrado no fim deste docstring —
não dá para rodar em suíte, mas também não pode ficar sem registro.

**Medido na máquina do usuário** (RTX 3050 4 GB), contra a verdade acústica do
próprio repo (`speech_regions.py`):

| motor | dentro da fala | pior desvio | velocidade |
|---|---|---|---|
| Scribe (nuvem, hoje) | 99,7% | 1,18s | ~22x tempo real |
| faster-whisper medium CUDA | 96,6% | 1,63s | 7x tempo real |
| whisper.cpp (já existia no repo) | 66% | 2,50s | — |

Sincronia entre Scribe e local, nas 328 palavras que casam no vídeo de 171s:
mediana 40 ms, p90 120 ms, **87% dentro de 100 ms**.

Casos de borda, todos executados de verdade: vídeo longo (386 palavras em
24,4s), nome com espaço e acento, silêncio puro (0 palavras, não inventou),
só música (**inventou 5 palavras** — alucinação conhecida do Whisper em áudio
sem fala), cancelamento (parou em 4,0s), modelo ausente, modelo corrompido,
cache HIT (24,4s → 1,4s) e **rede bloqueada** (transcreveu offline).
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transcricao import (  # noqa: E402
    Cancelado, Palavra, ResultadoDeTranscricao, Segmento,
)


# --- o contrato de dados ---------------------------------------------------

def _resultado() -> ResultadoDeTranscricao:
    return ResultadoDeTranscricao(
        texto="oi mundo",
        segmentos=[Segmento("oi mundo", 0.0, 1.5, -0.2, (
            Palavra("oi", 0.0, 0.4, 0.98),
            Palavra("mundo", 1.0, 1.5, 0.91),   # lacuna de 0,6s no meio
        ))],
        idioma="pt", duracao=1.5, motor="whisper-local",
        modelo="medium", backend="cuda",
    )


def test_a_saida_e_o_schema_que_o_app_ja_consome():
    """Dez módulos leem este formato. Mudá-lo seria reescrever o sistema de
    legendas, que é justamente o que a migração não pode exigir."""
    d = _resultado().para_schema_scribe()
    ws = d["words"]
    assert [w["type"] for w in ws] == ["word", "spacing", "word"]
    for w in ws:
        assert set(w) == {"text", "start", "end", "type", "speaker_id"}
    assert ws[0]["text"] == "oi" and ws[0]["start"] == 0.0


def test_a_lacuna_vira_spacing():
    """`pack_transcripts` e `timeline_view` detectam pausa pelas entradas
    `spacing`. Um transcript sem elas passa nos testes e degrada a detecção
    de silêncio sem avisar."""
    ws = _resultado().para_schema_scribe()["words"]
    espaco = [w for w in ws if w["type"] == "spacing"]
    assert len(espaco) == 1
    assert espaco[0]["start"] == pytest.approx(0.4)
    assert espaco[0]["end"] == pytest.approx(1.0)


def test_sem_lacuna_nao_inventa_spacing():
    r = ResultadoDeTranscricao(texto="a b", segmentos=[
        Segmento("a b", 0.0, 1.0, None,
                 (Palavra("a", 0.0, 0.5), Palavra("b", 0.5, 1.0)))])
    assert all(w["type"] == "word" for w in r.para_schema_scribe()["words"])


def test_o_schema_carrega_de_onde_veio():
    """Sem isso, um transcript do `small` seria indistinguível de um do
    `medium` — e o cache serviria um pelo outro."""
    d = _resultado().para_schema_scribe()
    assert d["_motor"] == "whisper-local"
    assert d["_modelo"] == "medium"
    assert d["_backend"] == "cuda"


def test_o_app_consegue_ler_a_saida():
    """Ponta a ponta com o leitor de verdade, não com um de mentira."""
    sys.path.insert(0, str(REPO / "helpers"))
    from helpers.captions_for_remotion import _word_items

    itens = _word_items(_resultado().para_schema_scribe())
    assert [i["text"] for i in itens] == ["oi", "mundo"]


# --- plataforma ------------------------------------------------------------

def test_o_backend_cai_para_cpu_sem_gpu(monkeypatch):
    """A aceleração nunca pode impedir a transcrição."""
    import app.transcricao.plataforma as plat

    plat.detectar.cache_clear()
    monkeypatch.setattr(plat, "_gpu_nvidia", lambda: ("", 0))
    monkeypatch.delenv("ATIVAVID_WHISPER_BACKEND", raising=False)
    m = plat.detectar()
    plat.detectar.cache_clear()
    assert m.backend == "cpu"
    assert m.compute_type == "int8"


def test_gpu_pequena_demais_nao_e_usada(monkeypatch):
    """4 GB é o teto da máquina do usuário e o encoder de vídeo divide a
    placa. GPU menor que o modelo não é aceleração, é falha na hora errada."""
    import app.transcricao.plataforma as plat

    plat.detectar.cache_clear()
    monkeypatch.setattr(plat, "_gpu_nvidia", lambda: ("GT 1030", 1024))
    monkeypatch.delenv("ATIVAVID_WHISPER_BACKEND", raising=False)
    m = plat.detectar()
    plat.detectar.cache_clear()
    assert m.backend == "cpu"
    assert "insuficiente" in m.motivo


def test_da_para_forcar_o_backend(monkeypatch):
    import app.transcricao.plataforma as plat

    plat.detectar.cache_clear()
    monkeypatch.setenv("ATIVAVID_WHISPER_BACKEND", "cpu")
    m = plat.detectar()
    plat.detectar.cache_clear()
    assert m.backend == "cpu" and "forçado" in m.motivo


def test_o_macos_nao_cai_no_ramo_do_windows(monkeypatch):
    """O ponto de organizar a detecção num lugar só: a versão macOS entra
    AQUI e o resto do programa não muda."""
    import app.transcricao.plataforma as plat

    plat.detectar.cache_clear()
    monkeypatch.setattr(plat.sys, "platform", "darwin")
    monkeypatch.setattr(plat.platform, "machine", lambda: "arm64")
    monkeypatch.delenv("ATIVAVID_WHISPER_BACKEND", raising=False)
    m = plat.detectar()
    plat.detectar.cache_clear()
    assert m.sistema == "darwin" and m.apple_silicon and m.backend == "cpu"


def test_os_modelos_moram_fora_do_projeto(monkeypatch):
    """Reinstalar o app não pode custar 1,4 GB de download de novo."""
    import app.transcricao.plataforma as plat

    monkeypatch.delenv("ATIVAVID_WHISPER_MODELS", raising=False)
    p = plat.pasta_de_modelos()
    assert "ATIVAVID" in str(p)
    assert str(REPO) not in str(p)


# --- escolha e integridade do modelo ---------------------------------------

def test_a_maquina_apertada_recebe_o_modelo_menor(monkeypatch):
    from app.transcricao.modelos import PADRAO, RESERVA, escolher_modelo

    monkeypatch.delenv("ATIVAVID_WHISPER_MODEL", raising=False)
    assert escolher_modelo(4096).chave == PADRAO      # a placa do usuário
    assert escolher_modelo(2048).chave == RESERVA
    assert escolher_modelo(0).chave == PADRAO         # VRAM desconhecida


def test_modelo_pela_metade_nao_conta_como_instalado(tmp_path, monkeypatch):
    """Sem isso, um download interrompido vira erro de formato na hora da
    transcrição — que não diz nada a quem está esperando a legenda."""
    import app.transcricao.modelos as mod

    monkeypatch.setattr(mod, "pasta_de_modelos", lambda: tmp_path)
    m = mod.CATALOGO["small"]
    d = tmp_path / "small"
    d.mkdir()
    (d / "model.bin").write_bytes(b"x" * 1000)
    assert not mod.instalado(m), "pasta sem selo passou por completa"

    (d / ".completo.json").write_text(json.dumps({"chave": "small", "bytes": 1000}))
    assert mod.instalado(m)

    # selo mentindo sobre o tamanho = arquivo truncado depois do download
    (d / ".completo.json").write_text(json.dumps({"chave": "small", "bytes": 99}))
    assert not mod.instalado(m), "modelo corrompido passou por bom"


def test_o_selo_de_outro_modelo_nao_vale(tmp_path, monkeypatch):
    import app.transcricao.modelos as mod

    monkeypatch.setattr(mod, "pasta_de_modelos", lambda: tmp_path)
    d = tmp_path / "small"
    d.mkdir()
    (d / "model.bin").write_bytes(b"x" * 1000)
    (d / ".completo.json").write_text(json.dumps({"chave": "medium", "bytes": 1000}))
    assert not mod.instalado(mod.CATALOGO["small"])


def test_cancelar_antes_de_baixar_nao_baixa(tmp_path, monkeypatch):
    import app.transcricao.modelos as mod

    monkeypatch.setattr(mod, "pasta_de_modelos", lambda: tmp_path)
    parar = threading.Event()
    parar.set()
    with pytest.raises(Cancelado):
        mod.garantir(mod.CATALOGO["small"], cancelar=parar)


# --- o motor não é chamado de fora da camada -------------------------------

def test_ninguem_chama_faster_whisper_direto():
    """O ponto da abstração: trocar de motor não pode significar caçar
    chamadas espalhadas pelo projeto."""
    from pipeline.leitura_de_codigo import apenas_codigo

    # Dois arquivos encostam no pacote do motor, os dois dentro da camada:
    # `whisper_local` para USAR, e `componentes` para saber se ele está
    # instalado e buscá-lo se não estiver. `primeiro_uso` só pergunta ao
    # `componentes` — de propósito, para a instalação de pacote ter um dono só.
    permitido = {Path("app/transcricao/whisper_local.py"),
                 Path("app/transcricao/componentes.py")}
    achados = []
    for pasta in ("app", "helpers", "pipeline"):
        for f in (REPO / pasta).rglob("*.py"):
            rel = f.relative_to(REPO)
            if rel in permitido or rel.name.startswith("test_"):
                continue
            try:
                texto = apenas_codigo(f)
            except Exception:  # noqa: BLE001
                # Arquivo que o tokenizer não engole (existe um assim no repo:
                # `pipeline/cut_arch_audit.py` nem compila). Cai para o texto
                # cru — que INCLUI comentários, ou seja, aperta a checagem em
                # vez de afrouxá-la. Para um teste de "não pode conter", errar
                # para o lado de acusar demais é o lado certo.
                texto = f.read_text(encoding="utf-8", errors="replace")
            if "faster_whisper" in texto:
                achados.append(str(rel))
    assert not achados, f"chamada direta ao motor fora da camada: {achados}"
