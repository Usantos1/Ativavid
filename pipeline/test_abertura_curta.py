# -*- coding: utf-8 -*-
"""O app cobrava abertura curta e nunca pedia uma.

Medido nos 189 projetos do usuario (`edl.json`, duracao do primeiro
range):

    TODOS               mediana 5,6s   108 acima de 5s  (57%)
    modo dynamic (144)  mediana 5,4s    80 acima de 5s   23 na faixa ideal
    tipo viral   (118)  mediana 5,1s    61 acima de 5s

A ficha reprovava a abertura em mais da metade dos videos ("corte antes:
as primeiras falas prendem melhor entre 1,5 e 3,5s") — e a regra que o
planejador recebia para `viral`, o tipo de 118 dos 189, falava do que a
frase precisa SER e nada sobre quanto ela deve DURAR. So o `ad` pedia, e
sao 5 videos.

Dois lados do mesmo desencontro:
  - viral e humor passam a PEDIR a abertura de 1,5-3,5s no prompt;
  - a nota para de COBRAR dos tipos que preservam por contrato
    (`informational` tinha mediana de 15,3s, e a regra dele manda
    "ritmo equilibrado sem sacrificar clareza").
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app.content_type import prompt_rules  # noqa: E402
from video_score import (  # noqa: E402
    MODOS_PRESERVADORES, TIPOS_PRESERVADORES, score_structural,
)


def _ranges(dur_primeiro: float) -> list[dict]:
    return [
        {"start": 0.0, "end": dur_primeiro, "beat": "HOOK", "quote": "uma frase de gancho"},
        {"start": dur_primeiro, "end": dur_primeiro + 6, "quote": "o miolo do video"},
        {"start": dur_primeiro + 6, "end": dur_primeiro + 9, "beat": "CTA", "quote": "me chama no direct"},
    ]


def _nota(dur: float, *, mode="dynamic", tipo=None) -> dict:
    return score_structural(
        duration=dur + 9, ranges=_ranges(dur), mode=mode, tipo=tipo,
        transcript_ok=True, spoken="x" * 200)


def test_os_tipos_de_retencao_pedem_a_abertura_curta():
    for tipo in ("viral", "humor", "ad"):
        regra = prompt_rules(tipo)
        assert "1,5 e 3,5" in regra or "primeiros 2s" in regra, tipo


def test_o_pedido_e_a_frase_que_cabe_nao_a_frase_cortada():
    """Truncar a frase mais forte no meio troca um defeito por outro — a
    propria regra do viral avisa que promessa sem entrega esvazia."""
    regra = prompt_rules("viral")
    assert "Nao corte uma frase longa no meio" in regra
    assert "caiba inteira" in regra


def test_abertura_longa_ainda_pesa_num_viral():
    curta = _nota(2.5, tipo="viral")
    longa = _nota(11.9, tipo="viral")
    assert longa["hook"] < curta["hook"], (longa["hook"], curta["hook"])
    assert any("abertura" in str(t).lower() for t in longa.get("tips") or [])


def test_abertura_longa_NAO_pesa_num_informativo():
    """13 videos dele, mediana de 15,3s — a nota cobrava o contrario do
    que a regra do tipo manda."""
    curta = _nota(2.5, tipo="informational")
    longa = _nota(15.3, tipo="informational")
    assert longa["hook"] == curta["hook"], (longa["hook"], curta["hook"])
    assert not any("abertura" in str(t).lower() for t in longa.get("tips") or [])


def test_a_isencao_por_modo_continua_valendo():
    for modo in MODOS_PRESERVADORES:
        longa = _nota(20.0, mode=modo, tipo="viral")
        assert not any("abertura" in str(t).lower() for t in longa.get("tips") or []), modo


def test_os_dois_caminhos_que_gravam_a_nota_passam_o_tipo():
    """`score.json` sai do render E do apply — se so um passar o tipo, a
    nota do mesmo video muda ao aplicar uma correcao."""
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    ap = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")
    for fonte, nome in ((rf, "run_fast"), (ap, "apply_execute")):
        i = fonte.index("score_structural(")
        assert "tipo=" in fonte[i:i + 400], nome


def test_a_lista_de_tipos_isentos_bate_com_a_regra_deles():
    """Isento tem de ser quem a propria regra manda preservar — senao a
    isencao vira gosto."""
    for tipo in TIPOS_PRESERVADORES:
        regra = prompt_rules(tipo).lower()
        assert any(p in regra for p in (
            "preserve", "conservadora", "clareza", "não pule", "nao pule")), tipo
