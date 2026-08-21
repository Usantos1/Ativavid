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

import io
import re
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LIMITE_DE_ENTREGA = -1.0

_ASPAS_TRIPLAS = ('"""', "'''")


def _codigo(rel: str) -> str:
    """O arquivo sem comentários e sem docstrings.

    Necessário, não preciosismo: a primeira versão destes testes casava com o
    COMENTÁRIO que explica a decisão em vez do código, e acusou defeito onde
    não havia — `TP=-1.0` aparece no texto que explica por que o alvo deixou
    de ser −1,0. Um teste assim também passaria com o código errado, desde que
    o comentário continuasse certo.

    Aspas triplas caem junto: neste código elas são sempre docstring ou texto
    longo, nunca argumento de ffmpeg.

    O resto do arquivo sai IDÊNTICO: os trechos a ignorar são apagados no
    lugar, em vez de o código ser remontado a partir dos tokens. Remontar
    normaliza o espaçamento (`def f(` vira `def f (`) e quebraria toda busca
    escrita do jeito natural.
    """
    linhas = (REPO / rel).read_text(encoding="utf-8").splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO("".join(linhas)).readline):
        se_apaga = tok.type == tokenize.COMMENT or (
            tok.type == tokenize.STRING
            and tok.string.lstrip("rbfuRBFU")[:3] in _ASPAS_TRIPLAS)
        if not se_apaga:
            continue
        (l0, c0), (l1, c1) = tok.start, tok.end
        for n in range(l0 - 1, l1):
            linha = linhas[n]
            ini = c0 if n == l0 - 1 else 0
            fim = c1 if n == l1 - 1 else len(linha.rstrip("\n"))
            linhas[n] = linha[:ini] + " " * (fim - ini) + linha[fim:]
    return "".join(linhas)


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
