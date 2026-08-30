# -*- coding: utf-8 -*-
"""O editor não bate no disco quando não há nada acontecendo.

Medido na máquina do usuário, editor aberto e ninguém mexendo:
`/api/state` a cada 2s **para sempre** — 6,5 ms e 10 KB por chamada, cada
uma lendo `state.json`, `edl.json` e os mtimes. São 1800 chamadas/h,
11,7s de CPU/h e 18 MB de JSON/h disputando a máquina com o render, que é
o trabalho de verdade (notebook com uma 3050).

Medido depois, na mesma tela: **20 chamadas em 40s → 6** com a janela à
vista e ociosa, **→ 1** com ela escondida.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def _poll() -> str:
    i = APP.index("async function poll() {")
    return APP[i:APP.index("\nasync function applyState(", i)]


def test_os_tres_ritmos_existem():
    for nome in ("POLL_VIVO", "POLL_OCIOSO", "POLL_ESCONDIDO"):
        assert re.search(rf"const {nome} = \d+;", APP), nome


def test_o_intervalo_cresce_quando_nada_muda():
    corpo = _poll()
    assert "Math.min(POLL_OCIOSO" in corpo
    assert "* 1.5" in corpo


def test_o_apply_continua_no_ritmo_rapido():
    """A barra de progresso do apply depende deste poll."""
    corpo = _poll()
    i = corpo.index("if (S.applying)")
    assert "setTimeout(poll, 700)" in corpo[i:i + 260]


def test_escondido_diminui_mas_nao_para():
    """Há embutidos que dizem "escondido" com a janela à vista; um editor
    que congela nesse caso seria pior que o gasto."""
    corpo = _poll()
    i = corpo.index("document.hidden")
    trecho = corpo[i:i + 400]
    assert "S.pollPulos" in trecho, "sem contador, ele nunca busca escondido"
    assert "< 4" in trecho


def test_qualquer_sinal_de_vida_acorda():
    for ev in ("visibilitychange", "focus", "pointerdown", "keydown"):
        assert f"'{ev}'" in APP, ev
    assert "function acordarPoll()" in APP
    assert "S.pollEspera = POLL_VIVO;" in APP


def test_mudanca_de_estado_zera_a_espera():
    corpo = _poll()
    i = corpo.index("if (sig !== S.lastSig)")
    assert "acordarPoll();" in corpo[i:i + 400]


def test_o_teto_e_menor_que_um_apply():
    """Um apply começado noutra janela leva no máximo o teto para aparecer
    aqui — e ele dura ~107s (mediana medida nos 99 applies do usuário)."""
    teto = int(re.search(r"const POLL_OCIOSO = (\d+);", APP).group(1))
    assert teto <= 10000, teto
