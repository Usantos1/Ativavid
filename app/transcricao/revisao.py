# -*- coding: utf-8 -*-
"""Revisão textual do Whisper pelo Gemini. Os tempos continuam sendo do Whisper.

Cenário E do benchmark, promovido a produção em 22/08/2026. O motor local
transcreve, o Gemini lê **só o texto** — nunca o áudio — e aponta palavras
provavelmente erradas. As correções entram pelo `alinhar`, que reconcilia o
texto novo com a linha do tempo antiga sem mover um milissegundo.

    Whisper (áudio → palavras + tempos)
        ↓ texto
    Gemini (sessão web do projeto, sem chave e sem custo de API)
        ↓ [{indice, n, de, para}]
    aplicar_correcoes  → guarda de âncora
        ↓ tokens
    alinhar.aplicar    → sete políticas de bloco
    alinhar.conferir   → gate rígido: um tempo fora e a revisão inteira cai
        ↓
    palavras revisadas, tempos idênticos aos do Whisper

## Por que isto existe

Medido em 4 vídeos validados de ouvido (568 palavras por consenso, 177
conferidas palavra a palavra), contra o Whisper local puro:

    WER              22,7% → 21,3%
    CER              15,4% → 15,0%
    números          82,7% → 85,1%
    intervenções/100  8,7  →  7,9
    timestamps       idênticos em 100% dos 12 vídeos, 0 ms de desvio

O caso que resume o ganho: `perícula` nove vezes num vídeo, corrigido para
`película` nas nove, confirmado por ouvido humano. É o erro que o motor local
repete sistematicamente e que um revisor de contexto pega sem ouvir nada.

## Três coisas que este módulo NUNCA faz

**Não mexe em tempo.** `alinhar.conferir()` levanta se qualquer palavra sair
do intervalo original. Quem chama descarta a revisão e fica com o Whisper
puro. Legenda dessincronizada não é um resultado aceitável, nem no pior dia.

**Não cai para serviço pago.** Sessão expirada, Gemini fora do ar, JSON
quebrado: tudo termina em Whisper puro. Cair no Scribe sozinho gastaria a
cota do usuário sem ele pedir — a mesma decisão que `modo.py` já tomou.

**Não formaliza a fala.** "cê", "tá", "pra" e gíria ficam como estão. Trocar
"cê" por "você" é erro, não correção, e o prompt diz isso com todas as letras.

## O que ficou de fora

Gemini OUVINDO o áudio (cenários C e D) não foi testado e não está aqui. A
integração do projeto (`app/llm_session.py:245`) monta o pedido como uma
string de prompt e não tem caminho de upload; áudio exigiria API paga. Fica
registrado como experimento futuro, não como opção descartada.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from . import Palavra
from . import alinhar

# Versão do processo de revisão. Entra na chave de cache e na assinatura do
# transcript. Mudou o prompt, o modelo ou uma política do alinhador? Vire
# para `rev2`: os transcripts antigos ficam onde estão em vez de serem
# servidos como se tivessem passado pelo processo novo.
VERSAO = "rev1"

# Sufixo que marca um transcript revisado, no cache entre projetos e no
# `.srcsig` do projeto. É por ele que o rollback funciona sem apagar arquivo.
SUFIXO = f"+{VERSAO}"

# O modelo, no vocabulário do `llm_gateway`. Pseudo-modelo da sessão web —
# não existe chave de API neste caminho.
MODELO = "gemini-web/pro"

# Acima disto a revisão é pulada. O prompt manda TODAS as palavras indexadas,
# e uma fonte longa viraria um pedido que ninguém mediu: pode estourar
# contexto, degradar em silêncio ou demorar demais. O benchmark rodou em
# vídeos curtos — a fonte mais longa das 149 medidas na máquina do usuário
# tem 2,8 min, cerca de 700 palavras. 3.000 é ~4x o maior caso medido, e
# ainda assim conservador.
#
# Fatiar o pedido é a solução certa e exigiria uma rodada de validação nova.
# Enquanto ela não acontece, fonte longa sai com Whisper puro e diz que saiu.
MAXIMO_DE_PALAVRAS = 3000

LIGADA, DESLIGADA = "gemini", "off"
PADRAO = LIGADA


def modo() -> str:
    """Revisão ligada ou não. Env, depois configuração, depois o padrão.

    Mesma precedência de `modo.py`: a variável de ambiente ganha, para que
    teste, canário e rollback de emergência não dependam de editar arquivo.
    """
    env = (os.environ.get("ATIVAVID_REVISAO") or "").strip().lower()
    if env in (LIGADA, DESLIGADA):
        return env
    try:
        from app.settings_store import load_settings

        valor = str(load_settings().get("revisao") or "").strip().lower()
        if valor in (LIGADA, DESLIGADA):
            return valor
    except Exception:  # noqa: BLE001
        pass
    return PADRAO


def ligada() -> bool:
    return modo() == LIGADA


def sufixo_desejado() -> str:
    """`"+rev1"` quando a revisão está ligada, `""` quando não.

    É o que a assinatura do transcript tem de conter para ele poder ser
    reaproveitado. Se não bater, o transcript gravado passou por um processo
    diferente do que está pedido agora e não serve.
    """
    return SUFIXO if ligada() else ""


def palavras_do_schema(payload: dict) -> list[Palavra]:
    """Lê o schema do Scribe de volta para `Palavra`.

    A revisão trabalha sobre o payload já convertido, e não sobre o
    `ResultadoDeTranscricao`, por dois motivos. O prático: quando o transcript
    do Whisper vem do cache entre projetos, o objeto não existe mais — só o
    JSON. O de fidelidade: foi assim que o benchmark mediu o cenário E, lendo
    o schema, e `para_schema_scribe` não emite `confidence`. Ler daqui
    reproduz exatamente aquele caminho em vez de um parecido.
    """
    return [Palavra(texto=(w.get("text") or "").strip(),
                    inicio=float(w["start"]), fim=float(w["end"]),
                    confianca=w.get("confidence"))
            for w in (payload.get("words") or [])
            if w.get("type", "word") == "word" and w.get("start") is not None
            and (w.get("text") or "").strip()]


# --------------------------------------------------------------- o prompt

PROMPT = """\
Você é um REVISOR de transcrição, não um transcritor.

Você recebe APENAS a transcrição de um modelo local (Whisper), palavra por
palavra, indexada. Você NÃO tem acesso ao áudio.

Sua função é APENAS apontar palavras provavelmente transcritas de forma
incorreta, usando só coerência de contexto, gramática e conhecimento de marcas
e nomes próprios.

Como não pode ouvir, seja MAIS conservador: só corrija quando o contexto
tornar o erro evidente.

Foque em: nomes próprios, empresas, marcas, produtos, palavras incomuns ou
técnicas, gírias, contrações, números, valores, datas, lugares, e palavras
que não fazem sentido no contexto.

Proibições absolutas:
- NÃO retranscreva do zero.
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
- "confianca": 0 a 1. Na dúvida, não corrija.
Se nada precisar mudar, devolva {"correcoes": []}.
"""


class RevisaoIndisponivel(RuntimeError):
    """O Gemini não respondeu, ou respondeu o que não dá para usar.

    Nunca é fatal: quem chama fica com o Whisper puro. Existe como tipo
    próprio para o log dizer POR QUE a revisão não aconteceu.
    """


def _json_da_resposta(texto: str) -> dict:
    """Extrai JSON mesmo com cerca de código ou prosa em volta."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError(f"resposta do Gemini sem JSON: {(texto or '')[:400]}")
    return json.loads(m.group(0))


def pedir_correcoes(palavras: list[Palavra], texto: str) -> list[dict]:
    """Pergunta ao Gemini pela sessão web do projeto. Sem chave, sem custo."""
    from app.llm_gateway import chat_completions

    indexado = "\n".join(f"{i}\t{p.texto}\t{p.inicio:.2f}-{p.fim:.2f}"
                         for i, p in enumerate(palavras))
    codigo, resp = chat_completions({
        "model": MODELO,
        "messages": [{"role": "user", "content":
                      f"{PROMPT}\n\nTEXTO COMPLETO DO WHISPER:\n"
                      f"{texto}\n\nPALAVRAS DO WHISPER (índice, palavra, "
                      f"tempo):\n{indexado}\n"}],
    })
    if codigo != 200:
        raise RevisaoIndisponivel(
            f"gateway: {(resp.get('error') or {}).get('message', resp)}")
    try:
        conteudo = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RevisaoIndisponivel(f"resposta fora de forma: {e}") from e
    try:
        dados = _json_da_resposta(conteudo)
    except ValueError as e:
        raise RevisaoIndisponivel(str(e)[:300]) from e
    correcoes = dados.get("correcoes")
    if not isinstance(correcoes, list):
        raise RevisaoIndisponivel("JSON sem a lista `correcoes`")
    return correcoes


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


def revisar(palavras: list[Palavra], texto: str) -> tuple[list[Palavra], dict]:
    """Revisa e devolve `(palavras, meta)`. Nunca levanta.

    `meta["revisado"]` é a única coisa que o chamador precisa olhar:

        True   as palavras devolvidas passaram pelo Gemini E pelo
               `conferir()`. Podem ser gravadas com o sufixo `+rev1`.
        False  as palavras devolvidas são as do Whisper, intactas. NÃO
               podem ser gravadas como revisadas — senão uma queda de rede
               de dez segundos envenenaria o cache e a próxima chance de
               revisar aquele vídeo só voltaria com a versão `rev2`.

    `meta["motivo"]` diz por que não revisou, e é isso que aparece no log.
    """
    meta: dict[str, Any] = {
        "revisado": False, "motivo": "", "seg": 0.0,
        "propostas": 0, "aplicadas": 0, "ignoradas": 0,
        "palavras": len(palavras),
    }
    if not palavras:
        meta["motivo"] = "transcrição vazia"
        return palavras, meta
    if len(palavras) > MAXIMO_DE_PALAVRAS:
        meta["motivo"] = (f"fonte longa: {len(palavras)} palavras, teto de "
                          f"{MAXIMO_DE_PALAVRAS}")
        meta["pulada"] = True
        return palavras, meta

    t0 = time.perf_counter()
    try:
        correcoes = pedir_correcoes(palavras, texto)
        tokens, aplicadas, ignoradas = aplicar_correcoes(palavras, correcoes)
        r = alinhar.aplicar(palavras, tokens)
        # O gate. `aplicar` já recusa inserção e já descarta a revisão inteira
        # quando o modelo retranscreveu em vez de revisar; `conferir` é a
        # última linha, e ela olha os tempos um por um.
        alinhar.conferir(palavras, r.palavras)
    except Exception as e:  # noqa: BLE001
        # Largo de propósito. Qualquer coisa que aconteça aqui tem a mesma
        # resposta certa: entregar o Whisper puro e seguir o job.
        meta["seg"] = round(time.perf_counter() - t0, 3)
        meta["motivo"] = f"{type(e).__name__}: {str(e)[:200]}"
        return palavras, meta

    meta.update({
        "revisado": True,
        "seg": round(time.perf_counter() - t0, 3),
        "propostas": len(correcoes),
        "aplicadas": len(aplicadas),
        "ignoradas": len(ignoradas),
        "insercoes_recusadas": len(r.recusadas),
        "revisao_descartada": r.revisao_descartada,
        "ts_preservados": alinhar.linha_do_tempo_preservada(palavras, r.palavras),
        "fronteiras": alinhar.retencao_de_fronteiras(palavras, r.palavras),
    })
    if r.revisao_descartada:
        # `aplicar` já devolveu as palavras originais neste caso — o freio
        # anti-retranscrição disparou. Não é revisão: não pode virar `+rev1`.
        meta["revisado"] = False
        meta["motivo"] = f"revisão descartada pelo freio: {r.motivo}"
    return (r.palavras if meta["revisado"] else palavras), meta
