# -*- coding: utf-8 -*-
"""Qual motor transcreve. Um lugar só, para virar a chave num arquivo só.

O ATIVAVID transcreve **LOCAL**: na própria máquina, sem conta, sem chave e
sem internet depois que os componentes estiverem no disco. O usuário final
não escolhe nada disto — para ele a tela diz "Transcrevendo áudio…".

    LOCAL   faster-whisper nesta máquina  ← único motor do produto
    AUTO    resolve para LOCAL

O modo SCRIBE (ElevenLabs) foi **removido do produto em 02/09/2026** a
pedido do dono ("vamos remover todo o elevenlabs da jogada"). Ele já não
era padrão desde 21/08 (benchmarks: 96,6% das palavras no lugar certo
contra 99,7% do Scribe, tempo de job indistinguível) e a queda automática
para ele já tinha sido retirada antes — serviço pago não entra sozinho na
fatura de ninguém. `ATIVAVID_TRANSCRICAO=elevenlabs` e o valor gravado em
configuração passam a resolver para LOCAL, sem erro: instalação antiga com
o valor velho continua funcionando, só que no motor local.

O `helpers/transcribe.py` mantém o backend elevenlabs por fora do produto
(uso de ferramenta/benchmark) — o PIPELINE é que nunca mais pede por ele.

## A revisão textual é outra chave

`ATIVAVID_REVISAO` (ver `app/transcricao/revisao.py`) liga a revisão do
Gemini sobre o resultado do motor LOCAL. Ela é ortogonal a este arquivo:
é um pós-processo do motor local, não um motor. Revisão que falha entrega
Whisper puro.
"""
from __future__ import annotations

import os

LOCAL = "local"
AUTO = "auto"

AUTO_RESOLVE_PARA = LOCAL


def modo_configurado() -> str:
    """O modo pedido, ainda sem resolver `AUTO`.

    Valor desconhecido (inclusive o antigo "elevenlabs") cai em AUTO — que
    resolve para LOCAL. Ninguém trava por ter uma configuração velha.
    """
    env = (os.environ.get("ATIVAVID_TRANSCRICAO") or "").strip().lower()
    if env in (LOCAL, AUTO):
        return env
    try:
        from app.settings_store import load_settings

        valor = str(load_settings().get("transcricao") or "").strip().lower()
        if valor in (LOCAL, AUTO):
            return valor
    except Exception:  # noqa: BLE001
        pass
    return AUTO


def backend_para_o_pipeline() -> str:
    """O que passar em `--backend` do `transcribe.py`: sempre o local."""
    modo = modo_configurado()
    return AUTO_RESOLVE_PARA if modo == AUTO else modo
