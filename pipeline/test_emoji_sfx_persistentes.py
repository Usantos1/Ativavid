# -*- coding: utf-8 -*-
"""Emoji e som postos na mão sobrevivem ao render (item de 02/09).

Mesma família da 4.61: depois do "Aplicar", o emoji e o efeito sonoro
sumiam da timeline do editor — e como o pipeline SOMAVA as listas, mover
um duplicava e apagar ressuscitava. Agora a tela recarrega os dois como
camada viva e manda o estado COMPLETO com a marca `emojiSfxCompleto`; o
pipeline SUBSTITUI. Preview velho em cache não manda a marca e cai no
caminho antigo (somar+deduplicar).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pipeline.run_fast import midia_do_editor  # noqa: E402


def _pedido(tmp_path: Path, ed_tela: dict) -> tuple[Path, Path]:
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    (public / "sfx").mkdir(parents=True)
    (edit / "preview_edits.json").write_text(
        json.dumps({"editData": ed_tela}), encoding="utf-8")
    return edit, public


def test_com_a_marca_a_lista_da_tela_substitui(tmp_path):
    """Emoji movido de 2s para 5s: o antigo tem de SAIR do edit-data."""
    edit, public = _pedido(tmp_path, {
        "emojiSfxCompleto": True,
        "emojis": [{"char": "🔥", "atSec": 5.0, "durSec": 1.6}],
    })
    ed = {"emojis": [{"char": "🔥", "atSec": 2.0, "durSec": 1.6,
                      "x": 0.5, "y": 0.34, "size": 0.22}]}
    midia_do_editor(edit, public, ed)
    assert len(ed["emojis"]) == 1, "mover o emoji duplicou"
    assert ed["emojis"][0]["atSec"] == 5.0


def test_com_a_marca_apagar_apaga(tmp_path):
    """Lista vazia + marca = o usuário apagou tudo; sem a marca, lista
    vazia é um preview velho que não sabe do estado completo."""
    edit, public = _pedido(tmp_path, {"emojiSfxCompleto": True,
                                      "emojis": [], "sfxManual": []})
    ed = {"emojis": [{"char": "🔥", "atSec": 2.0}],
          "sfxManual": [{"src": "pop.mp3", "atSec": 1.0, "volume": 0.5}]}
    midia_do_editor(edit, public, ed)
    assert ed["emojis"] == [] and ed["sfxManual"] == []


def test_sem_a_marca_continua_somando(tmp_path):
    """Preview velho em cache: comportamento de sempre — soma e deduplica,
    nunca apaga o que já estava aplicado."""
    edit, public = _pedido(tmp_path, {
        "emojis": [{"char": "😱", "atSec": 7.0}],
    })
    ed = {"emojis": [{"char": "🔥", "atSec": 2.0, "durSec": 1.6,
                      "x": 0.5, "y": 0.34, "size": 0.22}]}
    midia_do_editor(edit, public, ed)
    chars = sorted(x["char"] for x in ed["emojis"])
    assert chars == ["🔥", "😱"], ed["emojis"]


def test_som_tambem_substitui_e_saneia(tmp_path):
    edit, public = _pedido(tmp_path, {
        "emojiSfxCompleto": True,
        "sfxManual": [{"src": "whoosh.mp3", "atSec": 3.0, "volume": 0.8}],
    })
    (public / "sfx" / "whoosh.mp3").write_bytes(b"x")
    ed = {"sfxManual": [{"src": "whoosh.mp3", "atSec": 1.0, "volume": 0.5}]}
    midia_do_editor(edit, public, ed)
    assert ed["sfxManual"] == [{"src": "whoosh.mp3", "atSec": 3.0,
                                "volume": 0.8}]


def test_a_tela_recarrega_emoji_e_som_como_camada_viva():
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function buildInsertsDraft")
    bloco = js[i:js.index("async function loadWave", i)]
    assert "(d.emojis || []).forEach" in bloco
    assert "(d.sfxManual || []).forEach" in bloco
    # os recarregados nascem `manual` (ajustaveis e apagaveis), nunca isNew
    assert bloco.count("manual: true") >= 2
    # e a tela manda a marca do protocolo no salvar
    assert "emojiSfxCompleto: true" in js


def test_a_edicao_mostra_o_emoji_e_o_som_recarregados():
    """O filtro da Edição só deixava passar `insert` manual: o emoji e o
    som recarregados existiam no rascunho mas não apareciam na faixa."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("const visiveis = soManuais")
    assert "c.isNew || c.kind === 'hook' || c.manual" in js[i:i + 260]
    i2 = js.index("const temManual = S.insertsDraft.some")
    assert "|| c.manual" in js[i2:i2 + 200]


def test_mexida_no_emoji_aplicado_arma_o_aplicar():
    """manualMudou olhava so kind==='insert': mover um emoji aplicado nao
    acendia o botao e a mudanca morria na tela."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function manualMudou")
    bloco = js[i:i + 400]
    assert "'emoji'" in bloco and "'sfx'" in bloco
    # o volume do som entra no retrato (roda do mouse muda so ele)
    i2 = js.index("function geoDoInsert")
    assert "c.volume ?? null" in js[i2:i2 + 400]


def test_emoji_aplicado_nao_duplica_na_aba_visual():
    """No Visual o final ja tem o emoji QUEIMADO no video: o cartao vivo
    so entra quando o video da aba e o cut (mesma regra dos inserts)."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "c.kind === 'emoji' && (c.isNew || (c.manual && !naFinal))" in js
