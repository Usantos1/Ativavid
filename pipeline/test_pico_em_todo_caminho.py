# -*- coding: utf-8 -*-
"""Todo caminho que entrega um vídeo respeita o mesmo limite de pico.

São TRÊS os caminhos que produzem o `final.mp4` que o usuário publica, e cada
um podia divergir por conta própria:

1. **render de um job novo** (`run_fast`) — nos dois motores: o próprio
   (`render_proprio`) e o Remotion. O motor próprio não define alvo de pico:
   ele IMPORTA `LOUDNORM_TP` do `overlay_compose`. Se alguém fixar um número
   lá, os motores divergem e ninguém vê — o vídeo simplesmente sai diferente
   conforme o caminho que o job pegou.
2. **apply** (corrigir legenda, mudar o corte) — refaz o final pelo mesmo
   `try_overlay_final`, mas não passava por conferência nenhuma.
3. **emenda** (`emenda_legenda`) — troca só um pedaço do vídeo. Usa `-an` em
   todos os passos e herda a faixa de áudio intacta; se um dia passar a
   reencodar áudio, precisa do mesmo alvo.

O limite de entrega é −1,0 dBTP. Medido nos projetos do usuário: 30 dos 31
com apply bem-sucedido estão dentro, e o único fora é um arquivo em que
nenhum caminho consegue baixar o pico (teve 3 applies, um por motor).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LIMITE_DE_ENTREGA = -1.0

from pipeline.leitura_de_codigo import apenas_codigo


def _codigo(rel: str) -> str:
    """Atalho para `apenas_codigo`, que mora em `pipeline/leitura_de_codigo`.

    Ele foi extraído para lá quando um TERCEIRO teste casou com o comentário
    em vez do código — o motivo completo está documentado no módulo.
    """
    return apenas_codigo(REPO / rel)


def test_o_motor_proprio_nao_tem_alvo_proprio():
    """Ele importa a constante; fixar um número lá separa os dois motores."""
    s = _codigo("app/render_proprio.py")
    assert "LOUDNORM_TP" in s, "o motor próprio deixou de normalizar"
    assert not re.search(r"^\s*LOUDNORM_TP\s*=\s*-?[\d.]+", s, re.M), (
        "o motor próprio passou a definir o próprio alvo de pico"
    )
    # o fallback de quando a 1a passada falha também não pode divergir
    from app.overlay_compose import LOUDNORM_TP

    for alvo in re.findall(r"tp_target = LOUDNORM_TP if measured else (-?[\d.]+)", s):
        assert float(alvo) <= LOUDNORM_TP, (
            f"o fallback do motor ({alvo}) é mais frouxo que o alvo "
            f"({LOUDNORM_TP})"
        )


def test_o_apply_confere_o_pico_antes_de_promover():
    s = _codigo("app/apply_execute.py")
    assert "def _conferir_pico(" in s
    i = s.index("_conferir_pico(final_tmp")
    j = s.index("hooks.promote_file(final_tmp", i)
    assert i < j, "a conferência tem de acontecer ANTES de promover"
    # e não pode derrubar o apply: o texto do usuário vale mais que 0,2 dB
    corpo = s[s.index("def _conferir_pico("):s.index("def _reembutir_capa(")]
    assert "except Exception" in corpo, (
        "o pico é acabamento — recusar a correção do usuário por causa dele "
        "seria pior que entregar 0,2 dB acima"
    )
    assert "raise" not in corpo


def test_a_emenda_nao_reencoda_audio():
    """Ela herda a faixa do final anterior. Se isso mudar, o áudio passa a
    precisar do mesmo loudnorm — e este teste avisa."""
    s = _codigo("app/emenda_legenda.py")
    assert '"-an"' in s, "a emenda parou de descartar áudio"
    assert '"-c:a"' not in s and "loudnorm" not in s, (
        "a emenda passou a mexer no áudio: precisa do alvo de pico do compose"
    )


def test_nenhum_caminho_mira_no_proprio_limite():
    """Varre os alvos de loudnorm de TODOS os arquivos que entregam vídeo."""
    from app.overlay_compose import LOUDNORM_TP

    alvos: dict[str, list[float]] = {}
    for rel in ("pipeline/run_fast.py", "app/overlay_compose.py",
                "app/render_proprio.py"):
        s = _codigo(rel)
        achados = [float(x) for x in re.findall(r"TP=(-[\d.]+)", s)]
        achados += [float(x) for x in re.findall(r"loudnorm=I=-14:TP=(-[\d.]+)", s)]
        if achados:
            alvos[rel] = achados
    assert alvos, "não achei nenhum alvo de loudnorm — a varredura quebrou"
    for rel, achados in alvos.items():
        for tp in achados:
            assert tp <= LOUDNORM_TP, (
                f"{rel} mira {tp}, mais frouxo que o alvo comum {LOUDNORM_TP} "
                f"— o limite de entrega é {LIMITE_DE_ENTREGA}"
            )
