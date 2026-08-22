# -*- coding: utf-8 -*-
"""Gemini pela sessão web que o ATIVAVID já tem. Sem chave, sem custo de API.

O projeto fala com o Gemini por cookies capturados pela extensão
(`app/llm_session.py` → `app/llm_gateway.py`). O benchmark usa exatamente essa
integração — não existe caminho pago aqui, e nenhum módulo de produção é tocado.

## Por que os cenários C e D estão indisponíveis

Ambos exigem que o Gemini OUÇA o áudio. A integração atual não envia arquivo.
Verificado no código, não presumido — `app/llm_session.py:245` monta o pedido
como:

    inner[0] = [prompt, 0, None, None, None, None, 0]

Uma string de prompt. O arquivo inteiro não tem endpoint de upload,
`inline_data`, multipart nem `file_data`; anexar arquivo no Gemini web exige um
upload separado para `push.clients6.google.com/upload/` e referenciar o
identificador retornado no payload, e nada disso existe.

Fazer isso funcionar significaria uma de duas coisas, ambas recusadas aqui:
introduzir a API paga só para o teste, ou mexer no `llm_session.py`, que é
produção. Então C e D são registrados como **indisponíveis com a integração
atual** e o benchmark segue com os cenários viáveis. A matriz mostra a lacuna
em vez de escondê-la.

## O que roda

Cenário E — `transcript do Whisper → Gemini`, sem áudio — passa por
`app.llm_gateway.chat_completions`, o mesmo caminho do planejador de cortes.
É revisão por contexto linguístico apenas, e mede exatamente quanto dá para
ganhar sem o modelo ouvir nada.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra                       # noqa: E402

# Motivo único, para a matriz e o log dizerem a mesma coisa.
SEM_AUDIO = (
    "a integração Gemini do projeto é por sessão web e envia apenas texto "
    "(app/llm_session.py:245 monta o pedido como uma string de prompt; não há "
    "upload de arquivo). Enviar áudio exigiria API paga ou mexer em produção "
    "— nenhuma das duas foi autorizada para este benchmark."
)


class GeminiIndisponivel(RuntimeError):
    pass


def extrair_audio(video: Path, destino_dir: Path) -> Path:
    """Reaproveita `extract_audio` do projeto: mp3 mono 16 kHz 64 kbps.

    Continua aqui porque a página de validação humana usa o áudio extraído
    para tocar os trechos divergentes.
    """
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{video.stem}.mp3"
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    sys.path.insert(0, str(RAIZ / "helpers"))
    from transcribe import extract_audio

    extract_audio(video, destino)
    return destino


REVISAR_SO_TEXTO = """\
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


def _json_da_resposta(texto: str) -> dict:
    """Extrai JSON mesmo com cerca de código ou prosa em volta."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError(f"resposta do Gemini sem JSON: {(texto or '')[:400]}")
    return json.loads(m.group(0))


def revisar_pelo_gateway(palavras: list[Palavra], texto: str) -> list[dict]:
    """Cenário E, pelo caminho que o ATIVAVID já tem. Sem chave, sem custo."""
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
    return _json_da_resposta(
        resp["choices"][0]["message"]["content"]).get("correcoes", [])
