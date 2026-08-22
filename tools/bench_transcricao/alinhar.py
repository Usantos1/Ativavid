# -*- coding: utf-8 -*-
"""Re-exporta `app.transcricao.alinhar`. O alinhador virou produção.

Este arquivo era a implementação. Quando o cenário E foi para produção, o
módulo inteiro subiu para `app/transcricao/alinhar.py` sem uma linha
reescrita, e aqui ficou só o apontamento.

Não é indireção por gosto: o benchmark tem de medir o MESMO código que roda
em produção. Se o alinhador tivesse duas cópias, uma correção numa delas
faria o número do benchmark descrever software que não existe. Os testes do
harness continuam valendo sem edição, e agora exercitam produção.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao.alinhar import *          # noqa: F401,F403,E402
from app.transcricao.alinhar import (          # noqa: E402
    AMOSTRA_MINIMA_PARA_FREIO,
    DURACAO_MINIMA,
    EPS,
    FRACAO_MAXIMA_ALTERADA,
    Alteracao,
    Resultado,
    aplicar,
    chave,
    conferir,
    linha_do_tempo_preservada,
    repartir,
    retencao_de_fronteiras,
    tokenizar,
)
