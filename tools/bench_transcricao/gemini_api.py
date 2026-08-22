# -*- coding: utf-8 -*-
"""Gemini API — a ÚNICA integração nova, e só dentro do benchmark.

POR QUE ELA EXISTE. O Gemini que o ATIVAVID já tem (`app/llm_gateway.py` →
`app/llm_session.py`) fala com o gemini.google.com por cookies capturados pela
extensão, e achata `messages` numa string de texto. Não há upload de arquivo
nem `inline_data`: **não existe caminho de áudio ali**. Os cenários C e D
exigem que o Gemini OUÇA o áudio, então não há como medi-los com o gateway
atual.

O QUE ESTE ARQUIVO NÃO FAZ. Não toca em `llm_gateway.py`, `llm_session.py` nem
em nada de produção. Nenhum módulo do app importa daqui. Se C e D perderem o
benchmark, apagar este arquivo não deixa rastro; se ganharem, a decisão de
levar a Gemini API para produção passa a ser deliberada, com número na mão.

O cenário E (revisão sem áudio) NÃO usa este arquivo: ele roda pelo
`llm_gateway.chat_completions` que já existe, porque texto o gateway atual
entrega. É de propósito — E mede o que dá para ter hoje, sem integração nova.

    GEMINI_API_KEY=...   é o que liga C e D
    uv pip install google-genai
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra                       # noqa: E402

MODELO_PADRAO = os.environ.get("BENCH_GEMINI_MODELO", "gemini-2.5-pro")


class GeminiIndisponivel(RuntimeError):
    pass


# --------------------------------------------------------------------- áudio

def extrair_audio(video: Path, destino_dir: Path) -> Path:
    """Reaproveita `extract_audio` do projeto: mp3 mono 16 kHz 64 kbps.

    O mesmo formato que o caminho de nuvem já usa para o Scribe — assim C e A
    recebem exatamente o mesmo áudio, e uma diferença de resultado não pode
    ser atribuída à codificação.
    """
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{video.stem}.mp3"
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    sys.path.insert(0, str(RAIZ / "helpers"))
    from transcribe import extract_audio

    extract_audio(video, destino)
    return destino


# ------------------------------------------------------------------- prompts

TRANSCREVER = """\
Você vai transcrever um áudio em português brasileiro.

Regras obrigatórias:
1. Transcreva LITERALMENTE o que foi realmente falado.
2. Português brasileiro.
3. Preserve gírias e linguagem coloquial exatamente como foram ditas.
4. NÃO corrija a maneira como a pessoa falou. Se ela disse "cê", escreva
   "cê", não "você". Se disse "tá", escreva "tá", não "está".
5. NÃO resuma.
6. NÃO reescreva frases.
7. Identifique nomes próprios, marcas, produtos, empresas, cidades e termos
   técnicos com a máxima precisão possível.
8. Retorne timestamps.

Sobre os timestamps — isto é importante:
Devolva a MAIOR granularidade que você conseguir sustentar com precisão real.
Se consegue timestamp confiável por palavra, use "palavra". Se só por frase,
use "frase". Se só por segmento, use "segmento".

NÃO invente timestamps por palavra interpolando um intervalo maior. É melhor
declarar "frase" honestamente do que entregar "palavra" impreciso. O campo
"granularidade" deve dizer o que você REALMENTE entregou.

Responda SOMENTE com JSON válido:
{
  "granularidade": "palavra" | "frase" | "segmento",
  "texto": "transcrição completa",
  "segmentos": [
    {"inicio": 0.0, "fim": 3.21, "texto": "...",
     "palavras": [{"texto": "...", "inicio": 0.0, "fim": 0.4}]}
  ]
}
Se granularidade != "palavra", devolva "palavras" como lista vazia.
"""

REVISAR_OUVINDO = """\
Você é um REVISOR de transcrição, não um transcritor.

Você recebe:
1. O áudio original.
2. A transcrição de um modelo local (Whisper), palavra por palavra, indexada.

Sua função é APENAS apontar palavras provavelmente transcritas de forma
incorreta, ouvindo o áudio para confirmar.

Foque em: nomes próprios, empresas, marcas, produtos, palavras incomuns ou
técnicas, gírias, contrações, números, valores, datas, lugares, e palavras
que não fazem sentido no contexto.

Proibições absolutas:
- NÃO retranscreva o áudio do zero.
- NÃO reescreva frases que já estão corretas.
- NÃO formalize a fala. "cê", "tá", "tô", "né", "pra" e gírias ficam como
  estão. Trocar "cê" por "você" é ERRO, não correção.
- NÃO resuma, NÃO corte, NÃO acrescente palavras que não foram faladas.
- NÃO mexa em pontuação por estilo.

Responda SOMENTE com JSON válido:
{
  "correcoes": [
    {"indice": 42, "n": 1, "de": "praimcamp", "para": "PrimeCamp",
     "motivo": "marca", "confianca": 0.93}
  ]
}
- "indice": índice da PRIMEIRA palavra do trecho no array do Whisper.
- "n": quantas palavras do Whisper o trecho cobre (n>1 para juntar palavras).
- "para": pode conter mais de uma palavra (para separar uma em duas).
- "confianca": 0 a 1. Só envie correção em que você confia depois de ouvir.
  Na dúvida, não corrija.
Se nada precisar mudar, devolva {"correcoes": []}.
"""

REVISAR_SO_TEXTO = REVISAR_OUVINDO.replace(
    """Você recebe:
1. O áudio original.
2. A transcrição de um modelo local (Whisper), palavra por palavra, indexada.

Sua função é APENAS apontar palavras provavelmente transcritas de forma
incorreta, ouvindo o áudio para confirmar.""",
    """Você recebe APENAS a transcrição de um modelo local (Whisper), palavra
por palavra, indexada. Você NÃO tem acesso ao áudio.

Sua função é APENAS apontar palavras provavelmente transcritas de forma
incorreta, usando só coerência de contexto, gramática e conhecimento de
marcas e nomes próprios.

Como não pode ouvir, seja MAIS conservador: só corrija quando o contexto
tornar o erro evidente.""")


# -------------------------------------------------------------------- chamada

def _cliente():
    chave = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not chave:
        raise GeminiIndisponivel(
            "GEMINI_API_KEY ausente — cenários C e D não podem rodar. "
            "O gateway de sessão web do projeto não envia áudio.")
    try:
        from google import genai
    except ImportError as e:
        raise GeminiIndisponivel(
            "pacote google-genai não instalado (uv pip install google-genai)"
        ) from e
    return genai.Client(api_key=chave)


def _json_da_resposta(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError(f"resposta do Gemini sem JSON: {(texto or '')[:400]}")
    return json.loads(m.group(0))


@dataclass
class Transcricao:
    palavras: list[Palavra] = field(default_factory=list)
    texto: str = ""
    granularidade: str = "segmento"
    tempos: dict[str, float] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def transcrever(audio: Path, modelo: str = MODELO_PADRAO) -> Transcricao:
    """Cenário C. Registra a granularidade que o Gemini declarou, sem promover."""
    cli = _cliente()
    t0 = time.perf_counter()
    arq = cli.files.upload(file=str(audio))
    t_upload = time.perf_counter() - t0

    t1 = time.perf_counter()
    resp = cli.models.generate_content(model=modelo, contents=[arq, TRANSCREVER])
    t_proc = time.perf_counter() - t1

    d = _json_da_resposta(resp.text)
    gran = d.get("granularidade", "segmento")
    if gran not in ("palavra", "frase", "segmento"):
        gran = "segmento"

    palavras: list[Palavra] = []
    if gran == "palavra":
        for s in d.get("segmentos", []):
            for p in (s.get("palavras") or []):
                palavras.append(Palavra(texto=str(p["texto"]).strip(),
                                        inicio=float(p["inicio"]),
                                        fim=float(p["fim"])))

    texto = d.get("texto") or " ".join(
        (s.get("texto") or "") for s in d.get("segmentos", []))

    meta = {"modelo": modelo, "granularidade_declarada": d.get("granularidade")}
    if gran != "palavra":
        meta["nota_timestamp"] = (
            f"O Gemini declarou granularidade '{gran}'. As métricas de "
            "timestamp por palavra NÃO se aplicam a este motor. Nenhum "
            "timestamp por palavra foi interpolado.")
    return Transcricao(palavras=palavras, texto=texto.strip(),
                       granularidade=gran,
                       tempos={"upload": round(t_upload, 3),
                               "processar": round(t_proc, 3)},
                       meta=meta)


def revisar(palavras: list[Palavra], texto: str, audio: Path | None,
            modelo: str = MODELO_PADRAO) -> list[dict]:
    """Cenários D (audio != None) e E (audio None).

    E não passa por aqui na rodada normal — `revisar_pelo_gateway` usa o
    gateway que o projeto já tem. Esta função aceita `audio=None` para o caso
    de alguém querer comparar D e E no MESMO modelo, isolando a variável
    "ouvir" da variável "modelo".
    """
    cli = _cliente()
    indexado = "\n".join(f"{i}\t{p.texto}\t{p.inicio:.2f}-{p.fim:.2f}"
                         for i, p in enumerate(palavras))
    corpo = (f"{REVISAR_OUVINDO if audio else REVISAR_SO_TEXTO}\n\n"
             f"TEXTO COMPLETO DO WHISPER:\n{texto}\n\n"
             f"PALAVRAS DO WHISPER (índice, palavra, tempo):\n{indexado}\n")
    conteudo: list = [corpo]
    if audio is not None:
        conteudo.insert(0, cli.files.upload(file=str(audio)))
    resp = cli.models.generate_content(model=modelo, contents=conteudo)
    return _json_da_resposta(resp.text).get("correcoes", [])


def revisar_pelo_gateway(palavras: list[Palavra], texto: str) -> list[dict]:
    """Cenário E pelo caminho que o ATIVAVID JÁ TEM — sem integração nova.

    Usa `app.llm_gateway.chat_completions`, o mesmo que o planejador de cortes
    usa. Mede o que é possível hoje, com a sessão web do usuário.
    """
    from app.llm_gateway import chat_completions

    indexado = "\n".join(f"{i}\t{p.texto}\t{p.inicio:.2f}-{p.fim:.2f}"
                         for i, p in enumerate(palavras))
    codigo, resp = chat_completions({
        "model": "gemini-web/pro",
        "messages": [{"role": "user", "content":
                      f"{REVISAR_SO_TEXTO}\n\nTEXTO COMPLETO DO WHISPER:\n"
                      f"{texto}\n\nPALAVRAS DO WHISPER (índice, palavra, "
                      f"tempo):\n{indexado}\n"}],
    })
    if codigo != 200:
        raise GeminiIndisponivel(
            f"gateway do projeto: {(resp.get('error') or {}).get('message', resp)}")
    conteudo = resp["choices"][0]["message"]["content"]
    return _json_da_resposta(conteudo).get("correcoes", [])
