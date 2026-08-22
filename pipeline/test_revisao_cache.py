# -*- coding: utf-8 -*-
"""`ATIVAVID_REVISAO=off` é rollback de verdade, sem apagar arquivo na mão.

Dois problemas que este arquivo tranca, e que juntos são a diferença entre um
interruptor e uma migração sem volta:

**Rollback.** Um transcript revisado já gravado em `transcripts/*.json` não
pode continuar dando cache hit e voltar a ser servido como se fosse Whisper
puro. A assinatura carrega a marca do processo que produziu o arquivo, e a
marca é comparada com o que está pedido agora.

**Cache envenenado.** Se a revisão falhou, o Whisper puro que saiu no lugar
NÃO pode ser gravado como `+rev1`. Se fosse, uma queda de rede de dez
segundos marcaria o vídeo como já processado e a próxima chance de revisá-lo
só voltaria quando a versão virasse `rev2`.

Ninguém purga nada: as duas variantes convivem no disco e o interruptor
escolhe qual é servida.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.transcricao import Palavra, Segmento, ResultadoDeTranscricao, revisao

PALAVRAS = [Palavra("eu", 0.0, 0.2), Palavra("vendi", 0.2, 0.7),
            Palavra("na", 0.7, 0.85), Palavra("praimcamp", 0.85, 1.6),
            Palavra("ontem", 1.6, 2.0)]
TEXTO = "eu vendi na praimcamp ontem"
CORRIGIDO = "eu vendi na Prime Camp ontem"
CORRECAO = [{"indice": 3, "de": "praimcamp", "para": "Prime Camp"}]


class _MotorFalso:
    """Conta quantas vezes o Whisper foi realmente acordado."""

    chamadas = 0

    def __init__(self, modelo=None):
        self.modelo = types.SimpleNamespace(chave="medium")

    def disponivel(self):
        return True, ""

    def transcrever(self, *a, **k):
        type(self).chamadas += 1
        return ResultadoDeTranscricao(
            texto=TEXTO, idioma="por", duracao=2.0, motor="whisper-local",
            modelo="medium", backend="cuda", tempos={"transcrever": 1.0},
            segmentos=[Segmento(TEXTO, 0.0, 2.0, palavras=tuple(PALAVRAS))])


@pytest.fixture()
def mundo(tmp_path, monkeypatch):
    """Um projeto, um vídeo, um cache — todos descartáveis."""
    import transcribe as tr

    monkeypatch.setattr(tr, "CACHE_ENTRE_PROJETOS", tmp_path / "cache")
    monkeypatch.setattr(tr, "_extrair_wav16k", lambda v, d: d.write_bytes(b"RIFF"))

    mod = types.ModuleType("app.transcricao.whisper_local")
    mod.MotorWhisperLocal = _MotorFalso
    monkeypatch.setitem(sys.modules, "app.transcricao.whisper_local", mod)
    pu = types.ModuleType("app.transcricao.primeiro_uso")
    pu.ja_pronto = lambda: True
    monkeypatch.setitem(sys.modules, "app.transcricao.primeiro_uso", pu)

    _MotorFalso.chamadas = 0
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 200_000)
    td = tmp_path / "transcripts"
    td.mkdir()

    contador = {"gemini": 0}

    def gemini(correcoes=CORRECAO, quebrado=False):
        def fn(p, t):
            contador["gemini"] += 1
            if quebrado:
                raise revisao.RevisaoIndisponivel("gateway: sessão expirada")
            return list(correcoes)
        monkeypatch.setattr(revisao, "pedir_correcoes", fn)

    def rodar():
        return json.loads(tr._transcrever_local(
            video, td, td / "v.json", language="pt", verbose=False,
        ).read_text(encoding="utf-8"))

    def marcas():
        return sorted(p.name.split(".", 1)[1].removesuffix(".json")
                      for p in (tmp_path / "cache").glob("*.json"))

    def sig():
        return (td / "v.srcsig").read_text(encoding="utf-8")

    return types.SimpleNamespace(
        tr=tr, video=video, td=td, out=td / "v.json", rodar=rodar,
        marcas=marcas, sig=sig, gemini=gemini, contador=contador,
        ligar=lambda v: monkeypatch.setenv("ATIVAVID_REVISAO", v))


# ------------------------------------------------------ o caminho normal

def test_revisao_off_grava_a_marca_pura(mundo):
    mundo.ligar("off")
    d = mundo.rodar()
    assert d["text"] == TEXTO
    assert "marca=local-medium" in mundo.sig() and "+rev1" not in mundo.sig()
    assert mundo.marcas() == ["local-medium-medium"]


def test_revisao_on_grava_as_duas_variantes(mundo):
    mundo.ligar("gemini")
    mundo.gemini()
    d = mundo.rodar()
    assert d["text"] == CORRIGIDO
    assert "marca=local-medium+rev1" in mundo.sig()
    assert mundo.marcas() == ["local-medium+rev1-medium", "local-medium-medium"]
    assert d["_revisao"] == revisao.VERSAO


def test_ligar_a_revisao_nao_retranscreve(mundo):
    """O Whisper puro já está no cache: falta só a revisão.

    É o que torna barato ligar a revisão numa base já transcrita — e, no
    caminho inverso, ter tentado revisar e falhado.
    """
    mundo.ligar("off")
    mundo.rodar()
    assert _MotorFalso.chamadas == 1

    mundo.ligar("gemini")
    mundo.gemini()
    d = mundo.rodar()
    assert d["text"] == CORRIGIDO
    assert _MotorFalso.chamadas == 1, "acordou a GPU para refazer o que já tinha"


def test_segunda_passada_com_a_revisao_ligada_nao_chama_ninguem(mundo):
    mundo.ligar("gemini")
    mundo.gemini()
    mundo.rodar()
    mundo.rodar()
    assert _MotorFalso.chamadas == 1
    assert mundo.contador["gemini"] == 1, "pagou a revisão duas vezes"


# --------------------------------------------------------- Ajuste 1: veneno

def test_revisao_que_falha_nao_grava_marca_revisada(mundo):
    """O teste do cache envenenado.

    Gemini caiu, o job seguiu com Whisper puro — e o arquivo NÃO pode sair
    marcado como revisado.
    """
    mundo.ligar("gemini")
    mundo.gemini(quebrado=True)
    d = mundo.rodar()

    assert d["text"] == TEXTO, "não era para ter revisado nada"
    assert "+rev1" not in mundo.sig(), "assinou como revisado um Whisper puro"
    assert mundo.marcas() == ["local-medium-medium"], (
        "gravou `+rev1` no cache entre projetos com conteúdo não revisado")
    assert "_revisao" not in d


def test_falha_temporaria_e_tentada_de_novo_depois(mundo):
    """O motivo de o teste acima existir: a falha tem de ser temporária.

    Gemini cai, volta, e a próxima passada revisa — sem retranscrever.
    """
    mundo.ligar("gemini")
    mundo.gemini(quebrado=True)
    assert mundo.rodar()["text"] == TEXTO

    mundo.gemini()
    d = mundo.rodar()
    assert d["text"] == CORRIGIDO, "desistiu de revisar para sempre"
    assert _MotorFalso.chamadas == 1


def test_revisao_descartada_pelo_freio_tambem_nao_vira_rev1(mundo, monkeypatch):
    """Retranscrever não é revisar, e o resultado não pode se dizer revisado.

    O freio só vale com amostra suficiente — num trecho de 3 palavras, uma
    correção já daria 33%. Aqui a amostra mínima é baixada para 3 porque o
    vídeo do teste tem 5 palavras; o que está sendo testado é a consequência
    no cache, não o limiar (esse fica em `test_revisao_timestamps.py`).
    """
    from app.transcricao import alinhar

    monkeypatch.setattr(alinhar, "AMOSTRA_MINIMA_PARA_FREIO", 3)
    mundo.ligar("gemini")
    mundo.gemini(correcoes=[{"indice": i, "para": f"x{i}"} for i in range(5)])
    d = mundo.rodar()
    assert d["text"] == TEXTO
    assert "+rev1" not in mundo.sig()
    assert mundo.marcas() == ["local-medium-medium"]


# --------------------------------------------------------- Ajuste 2: rollback

def test_transcript_revisado_nao_e_servido_como_puro(mundo):
    """O coração do rollback. Sem isto, `off` não desliga nada."""
    mundo.ligar("gemini")
    mundo.gemini()
    mundo.rodar()
    assert mundo.tr.transcript_cache_hit(mundo.out, mundo.video) is True

    mundo.ligar("off")
    assert mundo.tr.transcript_cache_hit(mundo.out, mundo.video) is False, (
        "serviria o transcript revisado como se fosse Whisper puro")


def test_rollback_devolve_o_texto_puro_sem_retranscrever(mundo):
    mundo.ligar("gemini")
    mundo.gemini()
    assert mundo.rodar()["text"] == CORRIGIDO

    mundo.ligar("off")
    d = mundo.rodar()
    assert d["text"] == TEXTO, "o rollback não voltou o texto"
    assert "+rev1" not in mundo.sig()
    assert _MotorFalso.chamadas == 1, "o rollback custou uma transcrição nova"


def test_o_rollback_nao_purga_nada(mundo):
    """As duas variantes convivem. Voltar a ligar não paga a revisão de novo."""
    mundo.ligar("gemini")
    mundo.gemini()
    mundo.rodar()
    mundo.ligar("off")
    mundo.rodar()
    assert mundo.marcas() == ["local-medium+rev1-medium", "local-medium-medium"]

    mundo.ligar("gemini")
    d = mundo.rodar()
    assert d["text"] == CORRIGIDO
    assert mundo.contador["gemini"] == 1, "pagou a revisão de novo depois do rollback"


# ----------------------------------------- a comparação é estreita de propósito

def test_assinatura_legada_nunca_invalida(mundo):
    """Escrita antes de a marca existir, então é Whisper puro.

    Invalidar em massa retranscreveria a base inteira do usuário para não
    corrigir nada.
    """
    mundo.out.write_text(json.dumps({"words": [], "text": TEXTO}), encoding="utf-8")
    mundo.tr.write_source_signature(mundo.td, mundo.video)      # sem marca
    for modo in ("off", "gemini"):
        mundo.ligar(modo)
        assert mundo.tr.transcript_cache_hit(mundo.out, mundo.video) is True


@pytest.mark.parametrize("marca", ["elevenlabs-scribe_v1", "groq-whisper-large-v3"])
def test_transcript_de_outro_backend_nunca_invalida(mundo, marca):
    """Um transcript do Scribe custou dinheiro. Jogá-lo fora porque um
    interruptor do motor local mudou seria cobrar do usuário por uma decisão
    que não é sobre ele."""
    mundo.out.write_text(json.dumps({"words": [], "text": TEXTO}), encoding="utf-8")
    mundo.tr.write_source_signature(mundo.td, mundo.video, marca)
    for modo in ("off", "gemini"):
        mundo.ligar(modo)
        assert mundo.tr.transcript_cache_hit(mundo.out, mundo.video) is True


def test_fonte_trocada_ainda_invalida(mundo):
    """A regra antiga continua valendo: outro tamanho/mtime é outro vídeo."""
    mundo.ligar("off")
    mundo.rodar()
    mundo.video.write_bytes(b"y" * 300_000)
    assert mundo.tr.transcript_cache_hit(mundo.out, mundo.video) is False
