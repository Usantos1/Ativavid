# -*- coding: utf-8 -*-
"""Qual motor transcreve. Um lugar só, para virar a chave num arquivo só.

Três modos internos. O usuário final não escolhe nada disto — para ele a tela
diz "Transcrevendo áudio…" e pronto.

    LOCAL   faster-whisper nesta máquina: sem conta, sem chave, sem internet
    SCRIBE  ElevenLabs Scribe, o que o app usa hoje
    AUTO    hoje resolve para SCRIBE

`AUTO` NÃO é "o melhor disponível" ainda, de propósito: enquanto a decisão
entre local e nuvem não estiver tomada, mudar o padrão por conta própria
mudaria o resultado dos vídeos do usuário sem ninguém pedir.

Ordem de precedência: variável de ambiente (para teste e para o benchmark),
depois a configuração gravada, depois o padrão.
"""
from __future__ import annotations

import os

LOCAL = "local"
SCRIBE = "elevenlabs"
AUTO = "auto"

# Enquanto a decisão não está tomada. Trocar para LOCAL vira a chave do
# produto inteiro -- e é a única linha que precisa mudar.
AUTO_RESOLVE_PARA = SCRIBE


def modo_configurado() -> str:
    """O modo pedido, ainda sem resolver `AUTO`."""
    env = (os.environ.get("ATIVAVID_TRANSCRICAO") or "").strip().lower()
    if env in (LOCAL, SCRIBE, AUTO):
        return env
    try:
        from app.settings_store import load_settings

        valor = str(load_settings().get("transcricao") or "").strip().lower()
        if valor in (LOCAL, SCRIBE, AUTO):
            return valor
    except Exception:  # noqa: BLE001
        pass
    return AUTO


def backend_para_o_pipeline() -> str:
    """O que passar em `--backend` do `transcribe.py`.

    Se o modo é LOCAL mas o motor não está instalado, cai para o Scribe em vez
    de derrubar o job: o usuário quer o vídeo, não uma aula sobre backends.
    """
    modo = modo_configurado()
    if modo == AUTO:
        modo = AUTO_RESOLVE_PARA
    if modo == LOCAL:
        try:
            from app.transcricao.whisper_local import MotorWhisperLocal

            ok, motivo = MotorWhisperLocal().disponivel()
            if not ok:
                print(f"TRANSCRICAO_LOCAL_INDISPONIVEL {motivo} — usando Scribe",
                      flush=True)
                return SCRIBE
        except Exception as e:  # noqa: BLE001
            print(f"TRANSCRICAO_LOCAL_INDISPONIVEL {type(e).__name__}: "
                  f"{str(e)[:120]} — usando Scribe", flush=True)
            return SCRIBE
    return modo
