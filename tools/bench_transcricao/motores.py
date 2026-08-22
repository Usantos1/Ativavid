# -*- coding: utf-8 -*-
"""Os cinco cenários, cada um chamando o código de produção que já existe.

Nada de motor novo aqui. `helpers/transcribe.py` continua sendo a porta de
entrada de A e B, com o cache, o schema do Scribe e a conversão que dez
módulos consomem; `app/transcricao/whisper_local.py` continua sendo o motor
local, com a guarda e a queda para CPU. Este arquivo só **chama** e cronometra.

    A  scribe                  helpers/transcribe.py backend="elevenlabs"
    B  whisper_local           helpers/transcribe.py backend="local"
    C  gemini_audio            gemini_api.py  (única integração nova)
    D  whisper_gemini          B + revisão do Gemini OUVINDO o áudio
    E  whisper_gemini_texto    B + revisão do Gemini SEM o áudio

MEDIÇÃO A FRIO: o cache entre projetos é ótimo para o produto e péssimo para
cronometrar. `ATIVAVID_TRANSCRIPT_CACHE` já existe e aponta a pasta do cache,
então o benchmark manda cada rodada para uma pasta descartável e mede o custo
real. Nenhuma linha de produção muda para isso acontecer.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
if str(RAIZ / "helpers") not in sys.path:
    sys.path.insert(0, str(RAIZ / "helpers"))

from app.transcricao import Palavra                      # noqa: E402
from tools.bench_transcricao import alinhar              # noqa: E402

# Granularidade REAL de timestamp entregue. Nunca promovida: um motor que só
# deu frase é registrado como frase, e as métricas por palavra ficam vazias
# para ele. Interpolar seria inventar o número que o benchmark foi medir.
PALAVRA, FRASE, SEGMENTO = "palavra", "frase", "segmento"


class MotorIndisponivel(RuntimeError):
    """Falta chave, componente ou GPU. Nunca devolva resultado sintético:
    uma linha estimada na matriz final vale menos que uma linha vazia."""


@dataclass
class Saida:
    motor: str
    palavras: list[Palavra] = field(default_factory=list)
    texto: str = ""
    granularidade: str = PALAVRA
    tempos: dict[str, float] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def para_json(self) -> dict:
        return {
            "motor": self.motor,
            "granularidade": self.granularidade,
            "texto": self.texto,
            "tempos": self.tempos,
            "meta": self.meta,
            "palavras": [{"texto": p.texto, "inicio": p.inicio, "fim": p.fim,
                          "confianca": p.confianca} for p in self.palavras],
        }

    @staticmethod
    def de_json(d: dict) -> "Saida":
        return Saida(
            motor=d["motor"], granularidade=d.get("granularidade", PALAVRA),
            texto=d.get("texto", ""), tempos=d.get("tempos", {}),
            meta=d.get("meta", {}),
            palavras=[Palavra(texto=p["texto"], inicio=p["inicio"],
                              fim=p["fim"], confianca=p.get("confianca"))
                      for p in d.get("palavras", [])])

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(self.para_json(), ensure_ascii=False,
                                      indent=2), encoding="utf-8")


def _palavras_do_schema(bruto: dict) -> list[Palavra]:
    """Lê o schema do Scribe — o formato que o ATIVAVID inteiro consome."""
    return [Palavra(texto=(w.get("text") or "").strip(),
                    inicio=float(w["start"]), fim=float(w["end"]),
                    confianca=w.get("confidence"))
            for w in (bruto.get("words") or [])
            if w.get("type", "word") == "word" and w.get("start") is not None
            and (w.get("text") or "").strip()]


def _rodar_transcribe(video: Path, trabalho: Path, backend: str,
                      modelo: str | None = None) -> tuple[dict, float]:
    """Chama `helpers/transcribe.py` como o produto chama, e cronometra."""
    from transcribe import transcribe_one

    edit = trabalho / backend
    edit.mkdir(parents=True, exist_ok=True)
    # Cache a frio: pasta descartável por rodada.
    antigo = os.environ.get("ATIVAVID_TRANSCRIPT_CACHE")
    os.environ["ATIVAVID_TRANSCRIPT_CACHE"] = str(edit / "cache")
    try:
        t0 = time.perf_counter()
        saida = transcribe_one(
            video, edit, api_key=os.environ.get("GROQ_API_KEY", ""),
            language="pt", backend=backend, verbose=False,
            elevenlabs_key=os.environ.get("ELEVENLABS_API_KEY"),
            whisper_model=modelo)
        dt = time.perf_counter() - t0
    finally:
        if antigo is None:
            os.environ.pop("ATIVAVID_TRANSCRIPT_CACHE", None)
        else:
            os.environ["ATIVAVID_TRANSCRIPT_CACHE"] = antigo
    return json.loads(Path(saida).read_text(encoding="utf-8")), dt


def aplicar_correcoes(palavras: list[Palavra], correcoes: list[dict]
                      ) -> tuple[list[str], list[dict], list[dict]]:
    """Aplica as correções do Gemini sobre os tokens do Whisper.

    Devolve (tokens, aplicadas, ignoradas). Não toca em tempo: quem reconcilia
    a linha do tempo depois é `alinhar.aplicar`.

    DE TRÁS PARA FRENTE, sempre: aplicar em ordem crescente faria a segunda
    correção errar o alvo assim que a primeira mudasse a quantidade de
    palavras (uma divisão desloca todo o resto do array).

    Duas proteções contra o modelo errar a conta:

      **índice fora do intervalo** — descartado.

      **âncora** — a correção declara `de`, e se o texto naquele índice não
      bate, ela é descartada. Este é o erro mais perigoso do conjunto: o
      modelo acerta QUAL palavra está errada e erra ONDE ela está. Sem a
      âncora, "praimcamp → PrimeCamp" no índice 0 sobrescreveria "eu".
      De quebra, resolve correções sobrepostas: a primeira aplicada muda o
      texto, a âncora da segunda deixa de bater e ela cai sozinha em vez de
      sobrescrever o que já foi corrigido.
    """
    tokens = [p.texto for p in palavras]
    aplicadas: list[dict] = []
    ignoradas: list[dict] = []
    for c in sorted(correcoes, key=lambda c: int(c["indice"]), reverse=True):
        i, n = int(c["indice"]), int(c.get("n", 1))
        if i < 0 or n < 1 or i + n > len(tokens):
            ignoradas.append({**c, "motivo": "índice fora do intervalo"})
            continue
        trecho = " ".join(tokens[i:i + n])
        if c.get("de") and alinhar.tokenizar(c["de"]) != alinhar.tokenizar(trecho):
            ignoradas.append({**c, "motivo": f"âncora não bate: {trecho!r}"})
            continue
        tokens[i:i + n] = alinhar.tokenizar(c["para"])
        aplicadas.append(c)
    return tokens, aplicadas, ignoradas


# ------------------------------------------------------------------ cenários

def scribe(video: Path, trabalho: Path) -> Saida:
    """A — ElevenLabs Scribe, o baseline de nuvem."""
    if not os.environ.get("ELEVENLABS_API_KEY"):
        raise MotorIndisponivel("ELEVENLABS_API_KEY ausente")
    bruto, dt = _rodar_transcribe(video, trabalho, "elevenlabs")
    palavras = _palavras_do_schema(bruto)
    return Saida(motor="scribe", palavras=palavras,
                 texto=bruto.get("text") or " ".join(p.texto for p in palavras),
                 tempos={"total": round(dt, 3)},
                 meta={"modelo": "scribe_v1", "nuvem": True, "offline": False})


def whisper_local(video: Path, trabalho: Path, modelo: str = "medium") -> Saida:
    """B — faster-whisper local, exatamente como o produto usa hoje.

    Inclui, porque vem de graça ao chamar o código real: timestamps por
    palavra, guarda contra alucinação, catálogo de modelo por VRAM, queda para
    CPU e o schema atual.
    """
    bruto, dt = _rodar_transcribe(video, trabalho, "local", modelo)
    palavras = _palavras_do_schema(bruto)
    return Saida(motor="whisper_local", palavras=palavras,
                 texto=bruto.get("text") or " ".join(p.texto for p in palavras),
                 tempos={"total": round(dt, 3)},
                 meta={"modelo": bruto.get("_modelo", modelo),
                       "backend": bruto.get("_backend", ""),
                       "nuvem": False, "offline": True})


def gemini_audio(video: Path, trabalho: Path) -> Saida:
    """C — áudio original direto para o Gemini, sem transcrição prévia."""
    from tools.bench_transcricao import gemini_api

    audio = gemini_api.extrair_audio(video, trabalho / "audio")
    t0 = time.perf_counter()
    r = gemini_api.transcrever(audio)
    dt = time.perf_counter() - t0
    return Saida(motor="gemini_audio", palavras=r.palavras, texto=r.texto,
                 granularidade=r.granularidade,
                 tempos={"total": round(dt, 3), **r.tempos},
                 meta={**r.meta, "nuvem": True, "offline": False})


def whisper_mais_gemini(base: Saida, video: Path, trabalho: Path, *,
                        ouvindo: bool = True) -> Saida:
    """D (ouvindo) e E (só texto) — o Gemini revisa, o Whisper manda no tempo.

    O que sai daqui tem os timestamps do cenário B, sempre. `alinhar.aplicar`
    levanta se algum tempo escapar, então um erro aqui derruba a rodada em vez
    de virar legenda dessincronizada.
    """
    from tools.bench_transcricao import gemini_api

    nome = "whisper_gemini" if ouvindo else "whisper_gemini_texto"
    if not base.palavras:
        raise MotorIndisponivel(f"{nome} depende do cenário B, que não rodou")

    # E vai pelo gateway que o projeto JA TEM (sessao web, so texto): ele
    # mede o que da para ter hoje sem integracao nova. So D precisa da API.
    t0 = time.perf_counter()
    if ouvindo:
        audio = gemini_api.extrair_audio(video, trabalho / "audio")
        correcoes = gemini_api.revisar(base.palavras, base.texto, audio=audio)
        via = "gemini-api"
    else:
        correcoes = gemini_api.revisar_pelo_gateway(base.palavras, base.texto)
        via = "llm_gateway (sessao web)"
    dt = time.perf_counter() - t0

    tokens, aplicadas, ignoradas = aplicar_correcoes(base.palavras, correcoes)
    r = alinhar.aplicar(base.palavras, tokens)
    return Saida(
        motor=nome, palavras=r.palavras,
        texto=" ".join(p.texto for p in r.palavras),
        tempos={"whisper": base.tempos.get("total", 0.0),
                "revisao": round(dt, 3),
                "total": round(base.tempos.get("total", 0.0) + dt, 3)},
        meta={"nuvem": True, "offline": False, "ouviu_o_audio": ouvindo,
              "via": via,
              "correcoes_propostas": len(correcoes),
              "correcoes_aplicadas": len(aplicadas),
              "correcoes_ignoradas": ignoradas,
              "insercoes_recusadas": len(r.recusadas),
              "revisao_descartada": r.revisao_descartada,
              "motivo": r.motivo,
              "alteracoes": [vars(a) for a in r.alteracoes],
              "linha_do_tempo_preservada":
                  alinhar.linha_do_tempo_preservada(base.palavras, r.palavras),
              "retencao_de_fronteiras":
                  alinhar.retencao_de_fronteiras(base.palavras, r.palavras)})
