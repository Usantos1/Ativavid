# -*- coding: utf-8 -*-
"""Quando o motor rápido cai, o relatório diz por quê.

`overlayEngineSkip` existe para responder "por que o motor próprio não
desenhou este vídeo". Respondia certo quando a recusa vinha do
`motivo_nao_suportado` — e ficava em `None` quando o motor aceitava o
vídeo e depois estourava.

Caso real (29/08): `20260829-171222` levou **479s** de overlay, onde o
próprio faria ~130s, com `overlayEngine=remotion` e
`overlayEngineSkip=None`. O motivo saiu só no log, que não chega à tela
nem ao relatório. Campo que responde "nada" quando a resposta existe é
pior que campo nenhum: quem lê conclui que o motor rodou.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FONTE = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")
RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _bloco(texto: str, marca: str, n: int = 900) -> str:
    return texto[texto.index(marca):][:n]


def test_a_queda_do_motor_proprio_vira_motivo():
    b = _bloco(FONTE, 'print(f"RENDER_PROPRIO_FALLBACK')
    assert "motivo_proprio = " in b, "a queda continua calada"
    assert 'snapshot["_engine"] = "remotion"' in b


def test_o_motivo_chega_ao_relatorio():
    assert '"engineSkip": motivo_proprio,' in FONTE


def test_a_passada_unica_que_falha_tambem_e_registrada():
    """Ainda é o motor próprio, mas pela cadeia lenta de duas etapas."""
    i = FONTE.index('print(f"UMA_PASSADA_FALLBACK')
    assert "uma_passada_falhou = " in FONTE[i - 300:i]
    assert '"onePassFail": uma_passada_falhou,' in FONTE


def test_a_variavel_nasce_definida():
    """Sem isto o caminho feliz explode com NameError no dicionário."""
    i = FONTE.index("motivo_proprio = None")
    assert "uma_passada_falhou = None" in FONTE[i:i + 200]


def test_o_caminho_feliz_declara_os_dois_campos():
    b = _bloco(FONTE, '"engine": "proprio",')
    assert '"engineSkip": None,' in b and '"onePassFail": None,' in b


def test_os_campos_atravessam_ate_o_timing():
    assert '_RENDER_META["overlayUmaPassadaFalhou"]' in RUN
    b = _bloco(RUN, 'for campo in ("overlayEngine"')
    assert "overlayUmaPassadaFalhou" in b


def test_o_motivo_e_curto():
    """Traceback inteiro num campo de relatório vira lixo na tela."""
    assert re.search(r"motivo_proprio = f\"o motor proprio falhou:.*?\"\[:200\]",
                     FONTE), "sem corte de tamanho"
