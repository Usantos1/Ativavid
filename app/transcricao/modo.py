# -*- coding: utf-8 -*-
"""Qual motor transcreve. Um lugar só, para virar a chave num arquivo só.

O padrão é **LOCAL**: o ATIVAVID transcreve na própria máquina, sem conta, sem
chave e sem internet depois que os componentes estiverem no disco. O usuário
final não escolhe nada disto — para ele a tela diz "Transcrevendo áudio…".

    LOCAL   faster-whisper nesta máquina  ← padrão
    SCRIBE  ElevenLabs Scribe, mantido como alternativa para comparação
    AUTO    resolve para LOCAL

**Não há queda automática para o Scribe.** Ela existiu enquanto o local era
experimental e foi retirada de propósito: o Scribe é um serviço pago, e cair
nele sozinho gastaria a cota do usuário sem ele pedir — justamente o que a
migração veio evitar. Auditados os motivos pelos quais o local pode faltar,
nenhum se resolve com o Scribe:

| por que o local falhou | o Scribe resolveria? |
|---|---|
| componentes ainda não baixados | não — ele também precisa de rede, e a resposta certa é baixar |
| download falhou (sem rede) | não — o Scribe precisa da mesma rede |
| GPU indisponível | não — o motor local já cai para CPU sozinho |
| modelo corrompido | não — a resposta é rebaixar o modelo |

Quem quiser o Scribe pede por ele — por configuração ou por
`ATIVAVID_TRANSCRICAO=elevenlabs`. Aí é escolha, não surpresa na fatura.

Ordem de precedência: variável de ambiente (teste e benchmark), depois a
configuração gravada, depois o padrão.
"""
from __future__ import annotations

import os

LOCAL = "local"
SCRIBE = "elevenlabs"
AUTO = "auto"

# O padrão do produto. Mudou de SCRIBE para LOCAL em 21/08/2026, depois dos
# benchmarks: 96,6% das palavras no lugar certo contra 99,7% do Scribe, tempo
# total do job indistinguível (mediana -1,8s em 3 rodadas) e a guarda contra
# alucinação sem perder nenhuma das 1.055 palavras reais medidas.
AUTO_RESOLVE_PARA = LOCAL


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

    Devolve o que foi pedido, sem trocar por baixo do pano. Se o local não
    puder rodar, quem descobre é o próprio `transcribe.py` — que tenta
    preparar os componentes antes de desistir, e falha com mensagem em vez de
    gastar cota de um serviço pago sem ninguém pedir.
    """
    modo = modo_configurado()
    return AUTO_RESOLVE_PARA if modo == AUTO else modo
