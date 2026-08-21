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
    assert "if (!capFalhou) S.captionFixes = {};" in js, (
        "o cliente ainda apaga a correção que não pegou"
    )
    i = js.index("if (captionOnly) {")
    assert "capFalhou" in js[i:i + 400], (
        "o ramo de legenda ainda canta sucesso sem olhar o veredito"
    )
