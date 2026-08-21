# -*- coding: utf-8 -*-
"""O /api/save tem de DIZER se a correção de legenda pegou.

Ele descartava o veredito de `apply_caption_fixes` e respondia `{"ok": true}`
sempre. A tela, que só olha `data.ok`, limpava `S.captionFixes`, apagava o chip
e cantava "✓ Legenda corrigida" — com a palavra errada ainda no vídeo.

A ARMADILHA no meio do caminho: `changed == 0` NÃO é falha. No app o mesmo fix
passa duas vezes (uma no clique, por /api/corrections, e outra ao salvar), e na
segunda o texto já está no lugar. Tratar isso como erro faria TODO salvamento
normal reclamar. O que separa os dois casos é se o texto de DESTINO está lá.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _projeto(tmp_path: Path, palavras: list[tuple[str, int, int]]) -> Path:
    edit = tmp_path / "edit"
    pub = edit / "remotion" / "public"
    pub.mkdir(parents=True)
    caps = [{"text": t, "startMs": a, "endMs": b} for t, a, b in palavras]
    (pub / "captions.json").write_text(json.dumps(caps), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps({"durationSec": 10}), encoding="utf-8")
    return edit


@pytest.fixture()
def edit(tmp_path):
    return _projeto(tmp_path, [
        ("moço", 0, 500), ("nossa", 500, 1000), ("capinha", 1000, 1600),
        ("do", 1600, 1900), ("celular", 1900, 2500),
    ])


def test_correcao_que_pega_diz_quantas_trocou(edit):
    from app.caption_fixes import apply_caption_fixes

    out = apply_caption_fixes(edit, [{"from": "capinha", "to": "capinhas",
                                      "startMs": 1000, "endMs": 1600}])
    assert out["ok"] is True
    assert out["changed"] >= 1
    caps = json.loads((edit / "remotion/public/captions.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in caps][2] == "capinhas"


def test_aplicar_a_mesma_correcao_de_novo_nao_e_falha(edit):
    """O caso NORMAL do app: o clique já aplicou, o salvar reaplica.

    Sem esta distinção, todo salvamento de legenda passaria a reclamar.
    """
    from app.caption_fixes import apply_caption_fixes

    fix = {"from": "capinha", "to": "capinhas", "startMs": 1000, "endMs": 1600}
    apply_caption_fixes(edit, [fix])
    out = apply_caption_fixes(edit, [fix])
    assert out["ok"] is True, "reaplicar o mesmo fix virou erro"
    assert out["changed"] == 0
    assert out.get("alreadyApplied") is True


def test_texto_que_nao_existe_e_reprovado_e_nao_some_calado(edit):
    """O caso que se perdia: editar a MESMA legenda duas vezes antes de salvar
    manda um `from` que nunca esteve em captions.json."""
    from app.caption_fixes import apply_caption_fixes

    out = apply_caption_fixes(edit, [{"from": "guarda-chuva", "to": "sombrinha",
                                      "startMs": 1000, "endMs": 1600}])
    assert out["ok"] is False, "correção que não pegou foi reportada como ok"
    assert out.get("notFound") is True
    assert out.get("error")


def test_o_save_devolve_o_veredito_no_corpo():
    """A metade do servidor: sem isto a tela não tem o que ler."""
    src = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    i = src.index('name = "preview_style.json"')
    trecho = src[i:i + 3000]
    assert "cap_res = apply_caption_fixes" in trecho, "o retorno segue descartado"
    assert 'resp["captionFix"] = cap_res' in trecho, "o veredito não vai na resposta"
    assert "except Exception:\n                pass" not in trecho, (
        "a exceção do apply de legenda ainda é engolida"
    )


def test_a_tela_nao_joga_fora_a_correcao_que_falhou():
    """A metade do cliente. Sem ela o servidor fala sozinho: `app.js` só olhava
    `data.ok` e limpava `S.captionFixes` de qualquer jeito."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "data.captionFix && data.captionFix.ok === false" in js, (
        "o cliente não lê o veredito"
    )
    assert "if (!capFalhou) { S.captionFixes = {}; S.capApagadas = []; }" in js, (
        "o cliente ainda apaga a correção que não pegou"
    )
    i = js.index("if (captionOnly) {")
    assert "capFalhou" in js[i:i + 400], (
        "o ramo de legenda ainda canta sucesso sem olhar o veredito"
    )


def test_apagar_tira_a_palavra_de_captions_e_das_cues(tmp_path):
    """O usuário pediu: "quero poder selecionar e deletar algumas legendas".

    Antes só dava para TROCAR o texto. Salvar vazio não apagava — e também não
    dizia nada, então parecia que o editor tinha ignorado o clique.
    """
    from app.caption_fixes import apply_caption_fixes

    edit = _projeto(tmp_path, [
        ("moço", 0, 500), ("nossa", 500, 1000), ("capinha", 1000, 1600),
    ])
    pub = edit / "remotion" / "public"
    (pub / "caption-cues.json").write_text(json.dumps([
        {"i": 0, "startMs": 0, "endMs": 1600,
         # `fromMs`/`toMs` sao os nomes REAIS das palavras de cue (conferido em
         # caption-cues.json dos projetos): so `fromMs` faria o filtro de tempo
         # medir fim 0 e o teste passaria por motivo errado.
         "lines": [[{"text": "moço", "fromMs": 0, "toMs": 500},
                    {"text": "nossa", "fromMs": 500, "toMs": 1000},
                    {"text": "capinha", "fromMs": 1000, "toMs": 1600}]]},
    ]), encoding="utf-8")

    out = apply_caption_fixes(edit, [{"from": "nossa", "to": "", "delete": True,
                                      "startMs": 500, "endMs": 1000}])
    assert out["ok"] is True and out["changed"] >= 1

    caps = json.loads((pub / "captions.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in caps] == ["moço", "capinha"]
    cues = json.loads((pub / "caption-cues.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in cues[0]["lines"][0]] == ["moço", "capinha"]


def test_texto_vazio_sem_a_marca_de_apagar_nao_apaga_nada(tmp_path):
    """A guarda que separa "apague isto" de "o campo veio vazio por engano"."""
    from app.caption_fixes import apply_caption_fixes

    edit = _projeto(tmp_path, [("moço", 0, 500), ("nossa", 500, 1000)])
    apply_caption_fixes(edit, [{"from": "nossa", "to": "", "startMs": 500, "endMs": 1000}])
    caps = json.loads((edit / "remotion/public/captions.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in caps] == ["moço", "nossa"], "campo vazio apagou sozinho"


def test_a_tela_oferece_apagar_e_nao_engole_o_campo_vazio():
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "del.textContent = 'apagar';" in js, "o editor de legenda não tem apagar"
    assert "delete: true" in js, "o pedido de apagar não chega ao servidor"
    assert 'use o botão "apagar"' in js, "campo vazio ainda some calado"


def test_o_cursor_da_headline_vai_para_onde_se_clica():
    """Editar a headline selecionava TUDO: clicar no meio para apagar uma
    palavra não funcionava e só restava andar com as setas."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function beginHeadlineEdit(")
    trecho = js[i:i + 2600]
    assert "caretRangeFromPoint" in trecho, "o clique ainda não posiciona o cursor"
    assert "beginHeadlineEdit(e)" in js, "o clique na headline não passa o evento"


def _cue(i: int, ini: int, fim: int, palavras: list[tuple[str, int, int]]) -> dict:
    return {"i": i, "startMs": ini, "endMs": fim, "preset": "STACK_MIXED",
            "lines": [[{"text": t, "fromMs": a, "toMs": b} for t, a, b in palavras]]}


def test_apagar_a_cue_inteira_tira_a_cue_e_nao_derruba_o_render(tmp_path):
    """Cue sem NENHUMA linha quebrava o motor.

    `_tempos_cue` faz `max()` sobre as palavras da cue; com a sequência vazia
    ele levantava `max() iterable argument is empty` e o render inteiro caía.
    Foi o que aconteceu ao apagar as 4 legendas de uma vez no editor: duas cues
    ficaram sem linha e o projeto parou de renderizar.
    """
    import numpy as np

    from app.caption_fixes import apply_caption_fixes
    from app.render_proprio import Renderizador

    edit = _projeto(tmp_path, [
        ("moço", 0, 500), ("nossa", 500, 1000), ("capinha", 1000, 1600),
        ("do", 2000, 2400), ("celular", 2400, 3000),
    ])
    pub = edit / "remotion" / "public"
    (pub / "caption-cues.json").write_text(json.dumps([
        _cue(0, 0, 1600, [("moço", 0, 500), ("nossa", 500, 1000), ("capinha", 1000, 1600)]),
        _cue(1, 2000, 3000, [("do", 2000, 2400), ("celular", 2400, 3000)]),
    ]), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps({
        "durationSec": 4, "fps": 30, "width": 1080, "height": 1920,
        "captions": {"enabled": True, "style": "stacked"},
    }), encoding="utf-8")

    # apaga TODAS as palavras da cue 1
    apply_caption_fixes(edit, [{"from": "do", "to": "", "delete": True,
                                "startMs": 2000, "endMs": 2400}])
    apply_caption_fixes(edit, [{"from": "celular", "to": "", "delete": True,
                                "startMs": 2400, "endMs": 3000}])

    cues = json.loads((pub / "caption-cues.json").read_text(encoding="utf-8"))
    assert len(cues) == 1, "a cue que ficou sem linha continuou no arquivo"
    assert cues[0]["i"] == 0

    # e o motor desenha o vídeo inteiro sem levantar
    ed = json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))
    r = Renderizador(pub, ed, frames=120, fps=30.0)
    for f in (0, 15, 30, 60, 90, 119):
        buf = np.zeros((r.h, r.w, 4), dtype=np.uint8)
        sujo = [0, 0, 0, 0]
        for leg in r.camadas:
            if leg.inicio_f <= f <= leg.fim_f:
                r.desenhar(leg, f - leg.inicio_f, buf, sujo, False)


def test_o_motor_aguenta_uma_cue_vazia_vinda_de_fora(tmp_path):
    """Cinto de seguranca: um caption-cues.json produzido por outra versao (ou
    editado a mao) nao pode derrubar o render."""
    from app.render_proprio import Renderizador

    edit = _projeto(tmp_path, [("moço", 0, 500)])
    pub = edit / "remotion" / "public"
    (pub / "caption-cues.json").write_text(json.dumps([
        {"i": 0, "startMs": 0, "endMs": 500, "preset": "STACK_MIXED", "lines": []},
    ]), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps({
        "durationSec": 2, "fps": 30, "width": 1080, "height": 1920,
        "captions": {"enabled": True, "style": "stacked"},
    }), encoding="utf-8")
    Renderizador(pub, json.loads((pub / "edit-data.json").read_text(encoding="utf-8")),
                 frames=60, fps=30.0)


def test_apagar_desloca_as_correcoes_de_texto_de_baixo():
    """`captionFixes` é indexado por posição em `S.captions`. Apagar a legenda i
    faz tudo abaixo dela descer uma casa — sem o deslocamento, a correção de uma
    legenda passava a aparecer noutra."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function apagarLegendas(")
    trecho = js[i:i + 1800]
    assert "sort((a, b) => b - a)" in trecho, "apaga de frente para trás e desloca errado"
    assert "desloc[n > i ? n - 1 : n]" in trecho, "as correções de baixo não descem"
    assert "S.capApagadas.push" in trecho, "o apagar não fica pendente para o salvar"
