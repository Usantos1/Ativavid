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
from app.transcricao import revisao                       # noqa: E402

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


# O prompt e o parser de JSON moraram aqui enquanto o cenário E era
# experimento. Viraram produção em `app/transcricao/revisao.py`; o harness
# passou a importar de lá para medir o mesmo texto que roda no pipeline.
REVISAR_SO_TEXTO = revisao.PROMPT
_json_da_resposta = revisao._json_da_resposta


def revisar_pelo_gateway(palavras: list[Palavra], texto: str) -> list[dict]:
    """Cenário E, pelo caminho que o ATIVAVID já tem. Sem chave, sem custo.

    Invocador fino de `app.transcricao.revisao.pedir_correcoes`. A troca do
    tipo de exceção mantém o contrato antigo do harness: quem chama aqui
    espera `GeminiIndisponivel`.
    """
    try:
        return revisao.pedir_correcoes(palavras, texto)
    except revisao.RevisaoIndisponivel as e:
        raise GeminiIndisponivel(str(e)) from e
